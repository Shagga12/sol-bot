"""Private Capital Connect demo monitor. No exchange order endpoints."""
import base64
import hmac
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPORT = None
LOCK = threading.Lock()
PAGE = '''<!doctype html><html lang="en"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Capital Connect</title><style>body{background:#101923;color:#edf4fa;font:18px system-ui;max-width:1050px;margin:auto;padding:28px}h1{color:#61dfbd}section{background:#1b2a39;border-radius:16px;padding:22px;margin:18px 0}table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:12px;border-bottom:1px solid #425060}button{padding:12px;font:inherit}small{color:#acbdce}.scroll{overflow:auto}</style><h1>Capital Connect</h1><p>Demo bot monitor · Singapore · Real orders disabled</p><button onclick="load()">Refresh activity</button><p id="message">Loading…</p><section id="totals"></section><section><h2>Open demo positions</h2><div id="positions" class="scroll"></div></section><section><h2>Recent demo trades</h2><div id="trades" class="scroll"></div></section><section><h2>Manual trading readiness</h2><p>Bybit connection and spendable funds still require verification. This dashboard cannot activate or submit real orders.</p></section><script>
const el=id=>document.getElementById(id);function table(id,rows,fields){const t=document.createElement('table'),head=t.insertRow();for(const f of fields){const th=document.createElement('th');th.textContent=f;head.append(th)}for(const row of rows){const r=t.insertRow();for(const f of fields)r.insertCell().textContent=row[f]??'—'}el(id).replaceChildren(t)}
async function load(){try{const r=await fetch('/api/status',{cache:'no-store'});if(!r.ok)throw Error('Unable to read worker report');const d=await r.json();if(!d.report){el('message').textContent='Waiting for the worker’s first report. No results shown yet.';return}const s=d.report,age=Math.round((Date.now()/1000-d.received_at)/60);el('message').textContent=(age>20?'STALE REPORT — ':'Latest worker report — ')+age+' minutes ago. Scans every 15 minutes.';el('totals').textContent='Mode: DEMO | Demo cash: '+s.cash_usdt+' USDT | Realized demo P&L: '+s.realized_pnl_usdt+' USDT | Estimated commission: '+s.commission_estimate_usdt+' USDT';table('positions',s.positions,['symbol','entry','qty','cost']);table('trades',s.recent_trades.map(x=>({...x,time:new Date(x.ts*1000).toLocaleString()})),['time','symbol','action','reason','price','pnl'])}catch(e){el('message').textContent=e.message+' — previous data may be stale.'}}load();setInterval(load,60000);
</script></html>'''

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def send(self, body, status=200, content_type='application/json'):
        data=body.encode();self.send_response(status)
        self.send_header('Content-Type',content_type);self.send_header('Cache-Control','private, no-store')
        self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY')
        self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def viewer(self):
        password=os.getenv('CAPITAL_VIEW_PASSWORD','')
        expected='Basic '+base64.b64encode(('ron:'+password).encode()).decode()
        return bool(password) and hmac.compare_digest(self.headers.get('Authorization',''),expected)
    def do_GET(self):
        if self.path=='/health':return self.send('{"status":"ok","live_orders":false}')
        if not self.viewer():
            self.send_response(401);self.send_header('WWW-Authenticate','Basic realm="Capital Connect", charset="UTF-8"');self.send_header('Cache-Control','no-store');self.end_headers();return
        if self.path=='/':return self.send(PAGE,content_type='text/html; charset=utf-8')
        if self.path=='/api/status':
            with LOCK:data=json.dumps(REPORT or {'report':None})
            return self.send(data)
        self.send('{}',404)
    def do_POST(self):
        global REPORT
        token=os.getenv('CAPITAL_REPORT_TOKEN','')
        if self.path!='/api/report' or not token or not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+token):return self.send('{}',403)
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=200000:return self.send('{}',413)
            report=json.loads(self.rfile.read(size))
            if report.get('mode')!='DEMO' or report.get('live_order_execution') is not False:raise ValueError()
            for key in ['positions','recent_trades']:
                if not isinstance(report.get(key),list):raise ValueError()
            with LOCK:REPORT={'received_at':time.time(),'report':report}
            return self.send('{"accepted":true}')
        except (ValueError,TypeError):return self.send('{}',400)
if __name__=='__main__':ThreadingHTTPServer(('0.0.0.0',int(os.getenv('PORT','10000'))),Handler).serve_forever()
