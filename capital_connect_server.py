"""Private Capital Connect demo monitor. No exchange order endpoints."""
import base64
import hmac
import hashlib
import re
from urllib.parse import urlencode
from urllib.request import Request, HTTPRedirectHandler, build_opener
from urllib.error import HTTPError
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPORT = None
CHECK_LOCK = threading.Lock()
LAST_CHECK = 0
LOCK = threading.Lock()
PAGE = '''<!doctype html><html lang="en"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Capital Connect</title><style>body{background:#101923;color:#edf4fa;font:18px system-ui;max-width:1050px;margin:auto;padding:28px}h1{color:#61dfbd}section{background:#1b2a39;border-radius:16px;padding:22px;margin:18px 0}table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:12px;border-bottom:1px solid #425060}button{padding:12px;font:inherit}small{color:#acbdce}.scroll{overflow:auto}</style><h1>Capital Connect</h1><p>Demo bot monitor · Singapore · Real orders disabled</p><button onclick="load()">Refresh activity</button><p id="message">Loading…</p><section id="totals"></section><section><h2>Open demo positions</h2><div id="positions" class="scroll"></div></section><section><h2>Recent demo trades</h2><div id="trades" class="scroll"></div></section><section><h2>Check your real Bybit account</h2><p>Use a separate read-only HMAC API key for account monitoring. Enter it here only. Keys are used for this check and are not saved.</p><form id="bybit-form" autocomplete="off"><p><label>API key<br><input name="apiKey" type="password" required autocomplete="off" autocapitalize="none" spellcheck="false" style="width:100%;box-sizing:border-box;padding:12px;font:inherit"></label></p><p><label>API secret<br><input name="apiSecret" type="password" required autocomplete="new-password" autocapitalize="none" spellcheck="false" style="width:100%;box-sizing:border-box;padding:12px;font:inherit"></label></p><button id="bybit-check" type="submit">Check Bybit connection</button></form><p id="bybit-result" role="status" aria-live="polite">Not checked. Real trading is disabled.</p></section><section><h2>Manual trading readiness</h2><p>Bybit connection and spendable funds still require verification. This dashboard cannot activate or submit real orders.</p></section><script>
const el=id=>document.getElementById(id);
el('bybit-form').addEventListener('submit',async e=>{e.preventDefault();const f=e.target,b=el('bybit-check');b.disabled=true;el('bybit-result').textContent='Checking account access…';const body=JSON.stringify({apiKey:f.elements.apiKey.value.trim(),apiSecret:f.elements.apiSecret.value.trim()});try{const r=await fetch('/api/bybit/check',{method:'POST',headers:{'Content-Type':'application/json'},body,cache:'no-store',signal:AbortSignal.timeout(35000)});const d=await r.json();if(!r.ok||!d.verified)throw Error(d.error||'Connection not verified');el('bybit-result').textContent='Connection verified at '+new Date(d.checked_at*1000).toLocaleString()+'. Unified USDT wallet: '+(d.wallet_usdt??'not returned')+'; locked: '+(d.locked_usdt??'not returned')+'. Key access: '+d.key_access+'. '+d.note+' Keys were not saved. Automatic real orders remain disabled.';}catch(e){el('bybit-result').textContent=e.message;}finally{f.reset();b.disabled=false;}});
function table(id,rows,fields){const t=document.createElement('table'),head=t.insertRow();for(const f of fields){const th=document.createElement('th');th.textContent=f;head.append(th)}for(const row of rows){const r=t.insertRow();for(const f of fields)r.insertCell().textContent=row[f]??'—'}el(id).replaceChildren(t)}
async function load(){try{const r=await fetch('/api/status',{cache:'no-store'});if(!r.ok)throw Error('Unable to read worker report');const d=await r.json();if(!d.report){el('message').textContent='Waiting for the worker’s first report. No results shown yet.';return}const s=d.report,age=Math.round((Date.now()/1000-d.received_at)/60);el('message').textContent=(age>20?'STALE REPORT — ':'Latest worker report — ')+age+' minutes ago. Scans every 15 minutes.';el('totals').textContent='Mode: DEMO | Demo cash: '+s.cash_usdt+' USDT | Realized demo P&L: '+s.realized_pnl_usdt+' USDT | Estimated commission: '+s.commission_estimate_usdt+' USDT';table('positions',s.positions,['symbol','entry','qty','cost']);table('trades',s.recent_trades.map(x=>({...x,time:new Date(x.ts*1000).toLocaleString()})),['time','symbol','action','reason','price','pnl'])}catch(e){el('message').textContent=e.message+' — previous data may be stale.'}}load();setInterval(load,60000);
</script></html>'''

class ConnectionCheckError(Exception):
    pass

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

def bybit_read(path, key, secret, params=None):
    if path not in ('/v5/user/query-api', '/v5/account/wallet-balance'):
        raise ValueError('Unsupported read')
    query = urlencode(params or {})
    ts = str(int(time.time()*1000))
    signature = hmac.new(secret.encode(), (ts+key+'5000'+query).encode(), hashlib.sha256).hexdigest()
    request = Request('https://api.bybit.com'+path+('?' + query if query else ''),
        headers={'X-BAPI-API-KEY':key,'X-BAPI-SIGN':signature,'X-BAPI-TIMESTAMP':ts,'X-BAPI-RECV-WINDOW':'5000'},method='GET')
    try:
        with build_opener(NoRedirect).open(request, timeout=12) as response:
            data = json.load(response)
    except HTTPError as error:
        if error.code == 403:
            raise ConnectionCheckError('Bybit declined this server connection (403). Account access was not verified.') from None
        if error.code == 429:
            raise ConnectionCheckError('Bybit rate limit reached. Wait before retrying.') from None
        raise ConnectionCheckError('Bybit connection failed. No orders were submitted.') from None
    if data.get('retCode') != 0:
        code = data.get('retCode')
        raise ConnectionCheckError('Bybit rejected the connection check (code '+str(code)+'). Check key, secret, expiry and IP restrictions.')
    if not isinstance(data.get('result'),dict):
        raise ConnectionCheckError('Unexpected Bybit response. Connection not verified.')
    return data['result']

def check_bybit(input):
    key,secret=input.get('apiKey',''),input.get('apiSecret','')
    if not isinstance(key,str) or not isinstance(secret,str) or not re.fullmatch(r'[A-Za-z0-9_-]{10,128}',key.strip()) or not re.fullmatch(r'[A-Za-z0-9_-]{10,256}',secret.strip()):
        raise ValueError('Enter a system-generated HMAC API key and secret, not your Bybit password.')
    key,secret=key.strip(),secret.strip()
    info=bybit_read('/v5/user/query-api',key,secret)
    wallet=bybit_read('/v5/account/wallet-balance',key,secret,{'accountType':'UNIFIED','coin':'USDT'})
    account=next((x for x in wallet.get('list',[]) if x.get('accountType')=='UNIFIED'),None)
    if account is None:
        raise ConnectionCheckError('API access verified, but no Unified wallet was returned.')
    coin=next((x for x in account.get('coin',[]) if x.get('coin')=='USDT'),{})
    return {'verified':True,'checked_at':time.time(),'account':'UNIFIED',
        'key_access':{0:'Read/write',1:'Read-only'}.get(info.get('readOnly'),'Unknown'),
        'wallet_usdt':coin.get('walletBalance'), 'locked_usdt':coin.get('locked'),
        'note':'Wallet balance is not a verified spendable amount. Check Available in Bybit before placing your trade.',
        'automatic_real_orders':False,'credentials_saved':False}

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
        global REPORT, LAST_CHECK
        if self.path=='/api/bybit/check':
            if not self.viewer():return self.send('{"error":"Sign in again before checking Bybit."}',401)
            if self.headers.get('Origin')!='https://capital-connect-preflight.onrender.com':return self.send('{"error":"Request origin not allowed."}',403)
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':return self.send('{}',415)
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=4000:return self.send('{}',413)
                data=json.loads(self.rfile.read(size))
                if not isinstance(data,dict):raise ValueError('Invalid request')
                with CHECK_LOCK:
                    if time.time()-LAST_CHECK<15:return self.send('{"error":"Wait 15 seconds before checking again."}',429)
                    LAST_CHECK=time.time()
                result=check_bybit(data)
                return self.send(json.dumps(result))
            except (ValueError,ConnectionCheckError) as error:return self.send(json.dumps({'verified':False,'error':str(error)}),400)
            except Exception:return self.send('{"verified":false,"error":"Bybit is unavailable. Connection not verified; no orders submitted."}',503)
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
