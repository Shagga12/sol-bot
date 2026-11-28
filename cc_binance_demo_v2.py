import os, json, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from collections import deque
from hmac import compare_digest
from urllib.parse import urlsplit
from uuid import uuid4
import base64

from cc_demo_ledger import PaperLedger

LOCK=threading.RLock()
STARTING_BALANCE = 1000.
S=dict(running=False,symbol='SOLUSDT',leverage=3,price=None,position=None,balance=STARTING_BALANCE,trades=[],error='',history=[],pnl=0.)
ENTRY_INTERVAL_SECONDS=900
ledger = None
pending_close = None


class PaperStorageError(Exception):
    pass


def restore_ledger(store):
    trades, realized_pnl = store.restore()
    S.update(balance=STARTING_BALANCE + realized_pnl, trades=trades)
    print(f'Paper trade ledger ready; restored {len(trades)} closed trades', flush=True)


def close_position(price):
    global pending_close
    if pending_close is None:
        realized_pnl = S['pnl']
        trade = dict(S['position'], exit=price, pnl=round(realized_pnl, 4), symbol=S['symbol'])
        pending_close = (uuid4(), trade, realized_pnl)

    trade_id, trade, realized_pnl = pending_close
    if ledger is not None:
        try:
            ledger.record(trade_id, trade, realized_pnl)
        except Exception:
            raise PaperStorageError('Could not save closed paper trade') from None

    S['balance'] += realized_pnl
    S['trades'].append(trade)
    S.update(position=None, pnl=0.)
    pending_close = None


def tick(price):
    s=S
    s['price']=price
    h=s['history']; h.append(price); del h[:-120]
    p=s['position']
    if p:
        d=p['direction']; move=d*(price/p['entry']-1)
        p['peak']=max(p['peak'],move)
        s['pnl']=move*p['notional']
        if pending_close is not None or move<=-.01 or move>=.04 or (p['peak']>=.01 and move<=p['peak']-.005):
            close_position(price)
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
        except PaperStorageError as e:
            with LOCK: S['error']=str(e)+'; retrying'
        except Exception as e:
            with LOCK: S['error']='Demo market feed unavailable: '+type(e).__name__
        time.sleep(15)
PAGE='''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{background:#10151d;color:#e9edf4;font:16px system-ui;margin:24px}section{background:#1b2430;padding:20px;border-radius:12px;margin:12px 0}button,select,input{padding:12px;margin:5px;background:#263443;color:white;border:1px solid #526174;border-radius:6px}button{background:#087d55}button.stop{background:#a52e40}pre{white-space:pre-wrap}canvas{width:100%;height:180px}</style><h1>Capital Connect</h1><p>BINANCE FUTURES • PAPER DEMO • NO REAL ORDERS</p><section><select id="pair"><option>SOLUSDT</option><option>BSBUSDT</option></select><label>Leverage <input id="lev" type="number" min="1" max="20" value="3"></label><button onclick="cmd('start')">Start</button><button class="stop" onclick="cmd('stop')">Stop</button><p>Pair and leverage apply when you press Start.</p><p>1% stop loss · 4% take profit · 0.5% trailing after 1% gain</p></section><section><h2 id="bot-status" role="status">Checking bot status…</h2><h2 id="price"></h2><canvas id="chart" width="600" height="180"></canvas><p id="bal"></p><p id="pnl"></p><p id="err"></p></section><section><h3>Position and trade history</h3><pre id="trades"></pre></section><script>
const pair = document.getElementById('pair');
const leverage = document.getElementById('lev');
const botStatus = document.getElementById('bot-status');
const quote = document.getElementById('price');
const balance = document.getElementById('bal');
const openPnl = document.getElementById('pnl');
const feedError = document.getElementById('err');
const tradeHistory = document.getElementById('trades');
const chart = document.getElementById('chart');
const controlButtons = [...document.querySelectorAll('button')];
let refreshVersion = 0;
let pendingCommand = false;
let controlError = '';

async function cmd(action) {
    if (pendingCommand) return;
    pendingCommand = true;
    refreshVersion++;
    controlError = '';
    controlButtons.forEach(button => button.disabled = true);
    botStatus.textContent = action === 'start' ? 'Starting…' : 'Stopping…';
    try {
        const response = await fetch('/control', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({action, symbol: pair.value, leverage: Number(leverage.value)})
        });
        if (!response.ok) {
            controlError = response.status === 401
                ? 'Sign in to control the paper bot.'
                : await response.text() || 'The bot command failed.';
        }
    } catch {
        controlError = 'The bot command could not be confirmed.';
    } finally {
        pendingCommand = false;
        controlButtons.forEach(button => button.disabled = false);
        await refresh();
    }
}

async function refresh() {
    if (pendingCommand) return;
    const version = ++refreshVersion;
    try {
        const response = await fetch('/state');
        if (!response.ok) throw new Error('State unavailable');
        const state = await response.json();
        if (version !== refreshVersion) return;
        botStatus.textContent = state.running ? 'RUNNING' : 'STOPPED';
        quote.textContent = state.symbol + ' ' + (state.price ?? 'Waiting for price');
        balance.textContent = 'Demo balance: ' + state.balance.toFixed(2) + ' USDT';
        openPnl.textContent = 'Open P&L: ' + state.pnl.toFixed(4);
        openPnl.style.color = state.pnl < 0 ? '#ff6474' : '#43d99b';
        feedError.textContent = [controlError, state.error].filter(Boolean).join(' ');
        tradeHistory.textContent = JSON.stringify({position: state.position, trades: state.trades.slice(-10)}, null, 2);
        drawChart(state.history);
    } catch {
        if (version !== refreshVersion) return;
        botStatus.textContent = 'Bot status unavailable';
        feedError.textContent = [controlError, 'Dashboard connection unavailable.'].filter(Boolean).join(' ');
    }
}

function drawChart(history) {
    const context = chart.getContext('2d');
    context.clearRect(0, 0, chart.width, chart.height);
    if (history.length < 2) return;
    const low = Math.min(...history);
    const range = Math.max(...history) - low || 1;
    context.strokeStyle = '#43d99b';
    context.beginPath();
    history.forEach((price, index) => {
        const x = index * chart.width / (history.length - 1);
        const y = 170 - 160 * (price - low) / range;
        if (index === 0) context.moveTo(x, y);
        else context.lineTo(x, y);
    });
    context.stroke();
}

refresh();
setInterval(refresh, 3000);
</script>'''
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
        if path=='/': return self.reply(PAGE,'text/html; charset=utf-8')
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
    database_url = os.environ.get('CC_DEMO_DATABASE_URL')
    if database_url:
        try:
            ledger = PaperLedger(database_url)
            restore_ledger(ledger)
        except Exception as error:
            raise SystemExit(f'Paper trade ledger startup failed ({type(error).__name__})') from None
    threading.Thread(target=verify_feeds,daemon=True).start()
    threading.Thread(target=worker,daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0',int(os.environ.get('PORT','10000'))),Handler).serve_forever()
