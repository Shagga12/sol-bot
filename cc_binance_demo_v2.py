import os, json, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from collections import deque
from hmac import compare_digest
from urllib.parse import urlsplit
import base64

LOCK=threading.RLock()
S=dict(running=False,symbol='SOLUSDT',leverage=3,price=None,position=None,balance=1000.,trades=[],error='',history=[],pnl=0.)
ENTRY_INTERVAL_SECONDS=900
def tick(price):
    s=S
    s['price']=price
    h=s['history']; h.append(price); del h[:-120]
    p=s['position']
    if p:
        d=p['direction']; move=d*(price/p['entry']-1)
        p['peak']=max(p['peak'],move)
        s['pnl']=move*p['notional']
        if move<=-.01 or move>=.04 or (p['peak']>=.01 and move<=p['peak']-.005):
            s['balance']+=s['pnl']; s['trades'].append(dict(exit=price,pnl=round(s['pnl'],4),**p)); s['position']=None;s['pnl']=0.
    elif s['running'] and len(h)>=20 and s['balance']>=10 and time.monotonic()>=s.get('next_entry_at',0):
        fast=sum(h[-5:])/5; slow=sum(h[-20:])/20
        if abs(fast/slow-1)>.001:
            s['position']=dict(entry=price,direction=1 if fast>slow else -1,notional=10*s['leverage'],peak=0.)
            s['next_entry_at']=time.monotonic()+ENTRY_INTERVAL_SECONDS
def worker():
    while True:
        with LOCK: symbol=S['symbol']
        try:
            with urllib.request.urlopen('https://demo-fapi.binance.com/fapi/v1/ticker/price?symbol='+symbol,timeout=10) as r: price=float(json.load(r)['price'])
            if not 0<price<float('inf'): raise ValueError('invalid price')
            with LOCK:
                if S['symbol']==symbol: tick(price); S['error']=''
        except Exception as e:
            with LOCK: S['error']='Demo market feed unavailable: '+type(e).__name__
        time.sleep(15)
PAGE='''<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{background:#10151d;color:#e9edf4;font:16px system-ui;margin:24px}section{background:#1b2430;padding:20px;border-radius:12px;margin:12px 0}button,select,input{padding:12px;margin:5px;background:#263443;color:white;border:1px solid #526174;border-radius:6px}button{background:#087d55}button.stop{background:#a52e40}pre{white-space:pre-wrap}canvas{width:100%;height:180px}</style><h1>Capital Connect</h1><p>BINANCE FUTURES • PAPER DEMO • NO REAL ORDERS</p><section><select id="pair"><option>SOLUSDT</option><option>BSBUSDT</option></select><label>Leverage <input id="lev" type="number" min="1" max="20" value="3"></label><button onclick="cmd('start')">Start</button><button class="stop" onclick="cmd('stop')">Stop</button><p>1% stop loss · 4% take profit · 0.5% trailing after 1% gain</p></section><section><h2 id="status"></h2><h2 id="price"></h2><canvas id="chart" width="600" height="180"></canvas><p id="bal"></p><p id="pnl"></p><p id="err"></p></section><section><h3>Position and trade history</h3><pre id="trades"></pre></section><script>async function cmd(action){let r=await fetch('/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,symbol:pair.value,leverage:Number(lev.value)})});if(!r.ok)alert(await r.text());refresh()}async function refresh(){try{let s=await(await fetch('/state')).json();status.textContent=s.running?'RUNNING':'STOPPED';price.textContent=s.symbol+' '+(s.price??'Waiting for price');bal.textContent='Demo balance: '+s.balance.toFixed(2)+' USDT';pnl.textContent='Open P&L: '+s.pnl.toFixed(4);pnl.style.color=s.pnl<0?'#ff6474':'#43d99b';err.textContent=s.error;trades.textContent=JSON.stringify({position:s.position,trades:s.trades.slice(-10)},null,2);let h=s.history,c=chart.getContext('2d');c.clearRect(0,0,600,180);if(h.length>1){let lo=Math.min(...h),hi=Math.max(...h);c.strokeStyle='#43d99b';c.beginPath();h.forEach((v,i)=>{let x=i*600/(h.length-1),y=170-160*(v-lo)/(hi-lo||1);i?c.lineTo(x,y):c.moveTo(x,y)});c.stroke()}}catch(e){err.textContent='Connection unavailable'}}refresh();setInterval(refresh,3000)</script>'''
class Handler(BaseHTTPRequestHandler):
    def auth(self):
        secret=os.environ.get('CC_DEMO_PASSWORD','')
        expected='Basic '+base64.b64encode(('admin:'+secret).encode()).decode()
        if secret and compare_digest(self.headers.get('Authorization',''),expected): return True
        self.send_response(401);self.send_header('WWW-Authenticate','Basic realm="Capital Connect"');self.end_headers();return False
    def reply(self,data,typ='application/json',status=200):
        self.send_response(status);self.send_header('Content-Type',typ);self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data.encode()) if self.command != 'HEAD' else None
    def do_HEAD(self):
        self.do_GET()
    def do_GET(self):
        path=urlsplit(self.path).path
        if path=='/health': return self.reply('{"demo":true}')
        if not self.auth(): return
        if path=='/state':
            with LOCK: return self.reply(json.dumps(S))
        if path=='/': return self.reply(PAGE,'text/html')
        self.reply('Not found','text/plain',404)
    def do_POST(self):
        if not self.auth(): return
        if self.path!='/control': return self.reply('Not found','text/plain',404)
        try:
            n=int(self.headers.get('Content-Length','0'))
            if not 0<n<4096: raise ValueError()
            a=json.loads(self.rfile.read(n))
            with LOCK:
                if a['action']=='stop': S['running']=False
                elif a['action']=='start':
                    symbol=a['symbol']; lev=int(a['leverage'])
                    if symbol not in ('SOLUSDT','BSBUSDT') or not 1<=lev<=20: raise ValueError()
                    if S['position'] and (symbol!=S['symbol'] or lev!=S['leverage']): return self.reply('Wait for open position to close','text/plain',409)
                    if symbol!=S['symbol']: S['history']=[];S['price']=None
                    S.update(symbol=symbol,leverage=lev,running=True)
                else: raise ValueError()
            self.reply('{"ok":true}')
        except Exception: self.reply('Invalid request','text/plain',400)
def verify_feeds():
    for symbol in ('BSBUSDT','SOLUSDT'):
        try:
            with urllib.request.urlopen('https://demo-fapi.binance.com/fapi/v1/ticker/price?symbol='+symbol,timeout=10) as r:
                data=json.load(r)
            price=float(data['price'])
            if data.get('symbol')!=symbol or not 0<price<float('inf'): raise ValueError('invalid response')
            print('DEMO FEED VERIFIED',symbol,price,flush=True)
        except Exception as e:
            print('DEMO FEED FAILED',symbol,str(e),flush=True)
if __name__=='__main__':
    threading.Thread(target=verify_feeds,daemon=True).start()
    threading.Thread(target=worker,daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0',int(os.environ.get('PORT','10000'))),Handler).serve_forever()
