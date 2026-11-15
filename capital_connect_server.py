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
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPORT = None
LIVE_REPORT = None
CHECK_LOCK = threading.Lock()
LAST_CHECK = 0
LOCK = threading.Lock()
from pathlib import Path

DASHBOARD = Path(__file__).resolve().parent / 'dashboard'
SYMBOLS = ('BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT')
VERSION = 'owner-setup-v2'


def live_readiness():
    with LOCK:
        report = LIVE_REPORT
    fresh = bool(report and time.time()-report['received_at'] < 180)
    state = report['state'] if fresh else 'NOT_CONNECTED'
    messages = {
        'SETUP_REQUIRED': 'Connection worker is online. Its secure credentials and trading configuration are not configured.',
        'CHECK_PASSED': 'Read-only worker checks passed. Exchange order and exit validation is still incomplete.',
        'CHECK_FAILED': 'The worker connection check failed. Review its Render logs.',
        'NOT_CONNECTED': 'No recent connection-worker heartbeat has arrived.'}
    return {'state': state, 'real_trading_active': False, 'can_activate': False,
            'execution_connected': False, 'connection_monitor_connected': fresh,
            'blockers': [messages[state], 'This worker cannot activate orders from the dashboard.']}



def validate_live_setup(data):
    fields = {'environment', 'symbol', 'capital_usdt', 'order_usdt',
              'daily_loss_usdt', 'stop_loss_percent', 'take_profit_percent', 'slippage_percent'}
    if not isinstance(data, dict) or set(data) != fields:
        raise ValueError('Complete the setup fields. Do not include API credentials.')
    if data['environment'] not in ('testnet', 'mainnet') or data['symbol'] not in SYMBOLS:
        raise ValueError('Choose testnet or mainnet and one supported spot pair.')
    values = {}
    for key in fields - {'environment', 'symbol'}:
        raw = data[key]
        if not isinstance(raw, str) or len(raw) > 24 or not re.fullmatch(r'(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)', raw):
            raise ValueError('Enter positive decimal numbers for every limit.')
        value = Decimal(raw)
        if not value.is_finite() or value <= 0:
            raise ValueError('Every trading limit must be greater than zero.')
        values[key] = value
    if values['order_usdt'] > values['capital_usdt']:
        raise ValueError('Order ceiling cannot exceed total allocation.')
    if values['daily_loss_usdt'] > values['capital_usdt']:
        raise ValueError('Daily loss limit cannot exceed total allocation.')
    if any(values[key] >= 100 for key in ('stop_loss_percent', 'take_profit_percent')):
        raise ValueError('Stop-loss and profit target must be below 100%.')
    slip = values['slippage_percent']
    if not Decimal('.01') <= slip <= 10 or slip % Decimal('.01'):
        raise ValueError('Slippage must be 0.01–10%, with at most two decimal places.')
    config = {'environment': data['environment'], 'symbol': data['symbol']}
    for key in ('capital_usdt', 'order_usdt', 'daily_loss_usdt', 'slippage_percent'):
        config[key] = format(values[key], 'f')
    config['stop_loss_fraction'] = format(values['stop_loss_percent'] / 100, 'f')
    config['take_profit_fraction'] = format(values['take_profit_percent'] / 100, 'f')
    return {'valid': True, 'config': config, 'readiness': live_readiness(),
            'settings_applied_to_bot': False, 'orders_submitted': 0}


class ConnectionCheckError(Exception):
    pass

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

def bybit_read(path, key, secret, params=None):
    if path not in ('/v5/user/query-api', '/v5/account/wallet-balance',
                    '/v5/order/spot-borrow-check', '/v5/market/instruments-info'):
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
    symbol=input.get('symbol','BTCUSDT')
    if symbol not in SYMBOLS:
        raise ValueError('Select a supported USDT spot pair.')
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
    funding = {'available_spot_usdt': None, 'minimum_order_usdt': None,
               'funding_note': 'Available spot funds and current pair minimum were not verified.'}
    try:
        available=bybit_read('/v5/order/spot-borrow-check',key,secret,
                             {'category':'spot','symbol':symbol,'side':'Buy'})
        if available.get('symbol')!=symbol or available.get('side')!='Buy':
            raise ConnectionCheckError('Unexpected spot availability response.')
        actual=Decimal(str(available.get('spotMaxTradeAmount')))
        if not actual.is_finite() or actual<0:
            raise ValueError()
        funding['available_spot_usdt']=str(actual)
        rules=bybit_read('/v5/market/instruments-info',key,secret,{'category':'spot','symbol':symbol})
        instrument=next((x for x in rules.get('list',[]) if x.get('symbol')==symbol and x.get('status')=='Trading'),None)
        minimum=Decimal(str((instrument or {}).get('lotSizeFilter',{}).get('minOrderAmt')))
        if not minimum.is_finite() or minimum<=0:
            raise ValueError()
        funding.update(minimum_order_usdt=str(minimum),
                       funding_note='Non-borrowed spot availability and the pair minimum were returned. Order sizing and fees still require validation.')
    except (ConnectionCheckError, InvalidOperation, ValueError, TypeError, KeyError, OSError):
        pass
    return {'verified':True,'checked_at':time.time(),'account':'UNIFIED','symbol':symbol,
        'key_access':{0:'Read/write',1:'Read-only'}.get(info.get('readOnly'),'Unknown'),
        'wallet_usdt':coin.get('walletBalance'), 'locked_usdt':coin.get('locked'),
        'note':'Wallet balance is not a verified spendable amount. Check Available in Bybit before placing your trade.',
        'spot_trade_permission': info.get('readOnly') == 0 and 'SpotTrade' in info.get('permissions', {}).get('Spot', []),
        'dedicated_spot_key': info.get('readOnly') == 0 and info.get('permissions', {}).get('Spot') == ['SpotTrade'] and not any(v for k,v in info.get('permissions', {}).items() if k != 'Spot'),
        'automatic_real_orders':False,'credentials_saved':False,**funding}

def validate_report(report):
    if not isinstance(report,dict) or report.get('mode')!='DEMO' or report.get('live_order_execution') is not False:
        raise ValueError('Only demo worker reports are accepted')
    for field in ('positions','recent_trades'):
        if not isinstance(report.get(field),list) or len(report[field])>500 or any(not isinstance(row,dict) for row in report[field]):
            raise ValueError('Invalid report rows')
    for field in ('last_decisions',):
        if field in report and (not isinstance(report[field],list) or any(not isinstance(row,dict) for row in report[field])):
            raise ValueError('Invalid decisions')
    # Strict JSON disallows NaN and Infinity in authenticated worker reports.
    json.dumps(report,allow_nan=False)
    return report

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def send(self, body, status=200, content_type='application/json'):
        data=body.encode();self.send_response(status)
        self.send_header('Content-Type',content_type);self.send_header('Cache-Control','private, no-store')
        self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def viewer(self):
        password=os.getenv('CAPITAL_VIEW_PASSWORD','')
        expected='Basic '+base64.b64encode(('ron:'+password).encode()).decode()
        return bool(password) and hmac.compare_digest(self.headers.get('Authorization',''),expected)
    def do_GET(self):
        if self.path=='/health':return self.send(json.dumps({'status':'ok','live_orders':False,'dashboard_version':VERSION}))
        if not self.viewer():
            self.send_response(401);self.send_header('WWW-Authenticate','Basic realm="Capital Connect", charset="UTF-8"');self.send_header('Cache-Control','no-store');self.end_headers();return
        if self.path=='/':return self.send((DASHBOARD/'index.html').read_text(),content_type='text/html; charset=utf-8')
        if self.path in ('/dashboard.css','/dashboard.js'):
            name=self.path[1:]
            kind='text/css' if name.endswith('.css') else 'text/javascript'
            return self.send((DASHBOARD/name).read_text(),content_type=kind+'; charset=utf-8')
        if self.path=='/api/status':
            with LOCK:data=json.dumps(REPORT or {'report':None})
            return self.send(data)
        if self.path=='/api/live/status':return self.send(json.dumps(live_readiness()))
        self.send('{}',404)
    def do_POST(self):
        global REPORT, LAST_CHECK, LIVE_REPORT
        if self.path == '/api/live/report':
            token = os.getenv('CAPITAL_LIVE_REPORT_TOKEN', '')
            if not token or not hmac.compare_digest(self.headers.get('Authorization',''), 'Bearer '+token):
                return self.send('{}',403)
            try:
                size = int(self.headers.get('Content-Length','0'))
                if not 0 < size <= 1000: return self.send('{}',413)
                report = json.loads(self.rfile.read(size))
                if not isinstance(report,dict) or set(report) != {'state','orders_enabled'} or report['orders_enabled'] is not False or report['state'] not in ('SETUP_REQUIRED','CHECK_PASSED','CHECK_FAILED'):
                    raise ValueError()
                with LOCK: LIVE_REPORT = {'received_at':time.time(), 'state':report['state']}
                return self.send('{"accepted":true}')
            except (ValueError,TypeError): return self.send('{}',400)
        if self.path in ('/api/live/validate', '/api/live/activate'):
            if not self.viewer():return self.send('{"error":"Sign in before changing setup."}',401)
            if self.headers.get('Origin')!=os.getenv('CAPITAL_PUBLIC_ORIGIN','https://capital-connect-preflight.onrender.com'):return self.send('{"error":"Request origin not allowed."}',403)
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':return self.send('{}',415)
            if self.path=='/api/live/activate':
                return self.send(json.dumps({'error':'Live activation is unavailable until an execution worker is connected and validated.', **live_readiness()}),409)
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=4000:return self.send('{}',413)
                result=validate_live_setup(json.loads(self.rfile.read(size)))
                return self.send(json.dumps(result))
            except (ValueError, TypeError, InvalidOperation):
                return self.send('{"error":"Invalid setup. Use positive decimal limits; order and daily loss limits cannot exceed allocation. Targets must be below 100%; slippage must be 0.01–10% with at most two decimals."}',400)
        if self.path=='/api/bybit/check':
            if not self.viewer():return self.send('{"error":"Sign in again before checking Bybit."}',401)
            if self.headers.get('Origin')!=os.getenv('CAPITAL_PUBLIC_ORIGIN','https://capital-connect-preflight.onrender.com'):return self.send('{"error":"Request origin not allowed."}',403)
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
            report=validate_report(json.loads(self.rfile.read(size)))
            with LOCK:REPORT={'received_at':time.time(),'report':report}
            return self.send('{"accepted":true}')
        except (ValueError,TypeError):return self.send('{}',400)
if __name__=='__main__':ThreadingHTTPServer(('0.0.0.0',int(os.getenv('PORT','10000'))),Handler).serve_forever()

