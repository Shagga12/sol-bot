"""Owner-private review server. Separate process; never imports personal bot code."""
import base64,hmac,json,os,re,secrets,threading,time
from dataclasses import fields
from pathlib import Path
from http.cookies import SimpleCookie,CookieError
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from uuid import UUID
from .domain import Release,Locked,Invalid,order_review
from .supabase_client import Supabase,Unauthorized,Unavailable

WEB=Path(__file__).with_name('web')
PROFILE='/rest/v1/cc_trader_profiles?select=user_id,display_name,status,order_limit_usdt,created_at'
WALLET='/rest/v1/cc_trader_wallet_entries?select=asset,amount,kind,created_at&order=created_at.desc&limit=100'
ORDERS='/rest/v1/cc_trader_orders?select=side,symbol,quantity,average_price,net_realized_pnl,status,created_at&order=created_at.desc&limit=100'
FEES='/rest/v1/cc_trader_commissions?select=settlement_id,net_realized_pnl,commission_amount,created_at&order=created_at.desc&limit=100'
AUDIT='/rest/v1/cc_trader_audit?select=actor,action,target,created_at&order=created_at.desc&limit=100'

class ReviewServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,address,client,review_password,origin):
        if not review_password or len(review_password)<12:raise ValueError('Set a private review password of at least 12 characters')
        if not re.fullmatch(r'https://[a-zA-Z0-9.-]+(?::[0-9]+)?|http://(?:127\.0\.0\.1|localhost):[0-9]+',origin):raise ValueError('HTTPS origin required except loopback tests')
        self.client=client;self.review_password=review_password;self.origin=origin
        self.sessions={};self.attempts={};self.lock=threading.Lock()
        super().__init__(address,Handler)
    def session(self,cookie):
        with self.lock:
            now=time.time()
            self.sessions={key:value for key,value in self.sessions.items() if value['expires']>now}
            return self.sessions.get(cookie)

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*_):pass
    def send(self,data,status=200,kind='application/json',cookie=None):
        body=(json.dumps(data) if kind=='application/json' else data).encode()
        self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Cache-Control','private, no-store')
        self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY');self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'; object-src 'none'")
        if cookie:self.send_header('Set-Cookie',cookie)
        self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def private(self):
        expected='Basic '+base64.b64encode(('ron:'+self.server.review_password).encode()).decode()
        if not hmac.compare_digest(self.headers.get('Authorization',''),expected):
            self.send_response(401);self.send_header('WWW-Authenticate','Basic realm="Capital Connect private preparation"');self.send_header('Cache-Control','no-store');self.end_headers();return False
        return True
    def token(self):
        try:
            cookie=SimpleCookie(self.headers.get('Cookie',''));sid=cookie.get('cc_review')
        except CookieError:raise Unauthorized('Sign in first') from None
        session=self.server.session(sid.value if sid else '')
        if not session:raise Unauthorized('Sign in first')
        user=self.server.client.user(session['token']) # Authoritative Auth check on every API request.
        if user['id']!=session['user_id']:raise Unauthorized('Session identity changed')
        return session['token'],user
    def identity(self,token,user):
        identity=self.server.client.identity(token)
        if identity.get('user_id')!=user['id']:raise Unauthorized('Account identity mismatch')
        return identity
    def release(self,token):
        rows=self.server.client.request('/rest/v1/cc_trader_release?select=*',token)
        if not isinstance(rows,list) or len(rows)!=1:raise Unavailable('Review schema is not installed')
        return Release(**{f.name:rows[0][f.name] for f in fields(Release)})
    def body(self):
        if self.headers.get('Origin')!=self.server.origin:raise Unauthorized('Request origin rejected')
        if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise Invalid('JSON is required')
        try:size=int(self.headers.get('Content-Length','0'))
        except ValueError:raise Invalid('Invalid request size') from None
        if not 0<size<=8000:raise Invalid('Invalid request size')
        try:data=json.loads(self.rfile.read(size))
        except ValueError:raise Invalid('Invalid JSON') from None
        if not isinstance(data,dict):raise Invalid('An object is required')
        return data
    def cookie(self,value,age):
        return f'cc_review={value}; Path=/; HttpOnly; SameSite=Strict; Max-Age={age}'+('; Secure' if self.server.origin.startswith('https:') else '')
    def do_GET(self):
        if not self.private():return
        try:
            assets={'/':'index.html','/portal.js':'portal.js','/portal.css':'portal.css'}
            if self.path in assets:
                name=assets[self.path];kind='text/html' if name.endswith('html') else 'text/javascript' if name.endswith('js') else 'text/css'
                return self.send((WEB/name).read_text(),kind=kind+'; charset=utf-8')
            token,user=self.token();identity=self.identity(token,user)
            if self.path=='/api/me':
                profiles=self.server.client.request(PROFILE,token)
                own=next((p for p in profiles if p['user_id']==user['id']),None)
                return self.send({'user_id':user['id'],'is_owner':identity['is_owner'],'profile':own,
                                  'release':self.release(token).public(),'commission_policy':'10% of positive net realized profit above the prior high-water mark; collection is disabled.'})
            if self.path=='/api/account':
                return self.send({'wallet_entries':self.server.client.request(WALLET,token),'orders':self.server.client.request(ORDERS,token),
                                  'commissions':self.server.client.request(FEES,token),'deposit_address':None,'withdrawals_enabled':False})
            if self.path=='/api/admin':
                if not identity['is_owner']:return self.send({'error':'Owner access only'},403)
                return self.send({'profiles':self.server.client.request(PROFILE,token),'audit':self.server.client.request(AUDIT,token),
                                  'release':self.release(token).public(),'can_activate_funding':False})
            return self.send({'error':'Not found'},404)
        except Unauthorized as e:self.send({'error':str(e)},401)
        except Unavailable as e:self.send({'error':str(e)},503)
        except Exception:self.send({'error':'Review service unavailable'},503)
    def do_POST(self):
        if not self.private():return
        try:
            body=self.body()
            if self.path=='/api/login':
                with self.server.lock:
                    now=time.time();ip=self.client_address[0]
                    attempts=[t for t in self.server.attempts.get(ip,[]) if now-t<60]
                    if len(attempts)>=5:return self.send({'error':'Wait a minute before another sign-in attempt'},429)
                    self.server.attempts[ip]=attempts+[now]
                if set(body)!={'email','password'} or not isinstance(body['email'],str) or not re.fullmatch(r'[^\s@]{1,128}@[^\s@]{1,120}',body['email']) or not isinstance(body['password'],str) or not 8<=len(body['password'])<=1024:raise Invalid('Provide email and password')
                token,user=self.server.client.sign_in(body['email'],body['password'])
                # Client receives a random session cookie, never the provider access token.
                sid=secrets.token_hex(32)
                with self.server.lock:self.server.sessions[sid]={'token':token,'user_id':user['id'],'expires':time.time()+3600}
                return self.send({'signed_in':True},cookie=self.cookie(sid,3600))
            if self.path=='/api/register':
                # Closed even if someone edits the HTML or misconfigures a release flag.
                raise Locked('New trader registration remains closed in this preparation build')
            token,user=self.token();identity=self.identity(token,user)
            if self.path=='/api/logout':
                cookie=SimpleCookie(self.headers.get('Cookie',''));sid=cookie.get('cc_review')
                with self.server.lock:
                    if sid:self.server.sessions.pop(sid.value,None)
                try:self.server.client.request('/auth/v1/logout',token,body={},method='POST')
                except (Unauthorized,Unavailable):pass
                return self.send({'signed_out':True},cookie=self.cookie('',0))
            if self.path in ('/api/deposit-address','/api/withdraw','/api/order-submit','/api/commission-collect'):
                raise Locked('Funding, withdrawals, real orders and commission collection are locked in preparation')
            profiles=self.server.client.request(PROFILE,token)
            if self.path=='/api/order-review':
                profile=next((p for p in profiles if p['user_id']==user['id']),None)
                if not profile:raise Locked('No real-money trader account has been onboarded')
                return self.send(order_review(profile,body))
            if self.path=='/api/admin/profile':
                if not identity['is_owner']:return self.send({'error':'Owner access only'},403)
                if set(body)!={'user_id','status','order_limit_usdt'} or body['status'] not in ('pending','approved','suspended'):raise Invalid('Invalid profile update')
                from .domain import decimal
                limit=decimal(body['order_limit_usdt'])
                if limit<0 or limit>=10**20 or (body['status']=='approved' and limit<=0):raise Invalid('A positive saved order limit is required for approved profiles')
                uid=str(UUID(body['user_id']))
                # Review-only account vetting. This cannot activate deposits or exchange writes.
                rows=self.server.client.request('/rest/v1/cc_trader_profiles?user_id=eq.'+uid,token,
                    body={'status':body['status'],'order_limit_usdt':str(limit)},method='PATCH')
                if not rows:return self.send({'error':'Trader profile not found'},404)
                return self.send({'updated':rows,'funding_enabled':False,'trading_enabled':False})
            return self.send({'error':'Not found'},404)
        except Locked as e:self.send({'error':str(e),'orders_submitted':0},423)
        except Invalid as e:self.send({'error':str(e)},400)
        except Unauthorized as e:self.send({'error':str(e)},401)
        except Unavailable as e:self.send({'error':str(e)},503)
        except (ValueError,TypeError,KeyError):self.send({'error':'Invalid request'},400)
        except Exception:self.send({'error':'Review service unavailable'},503)

def main():
    client=Supabase(os.environ['TRADER_SUPABASE_URL'],os.environ['TRADER_SUPABASE_PUBLISHABLE_KEY'])
    origin=os.getenv('TRADER_REVIEW_ORIGIN','http://127.0.0.1:8766')
    server=ReviewServer(('127.0.0.1',8766),client,os.environ['TRADER_REVIEW_PASSWORD'],origin)
    print('Private trader preparation server listening on loopback; funding and real orders locked',flush=True)
    server.serve_forever()
if __name__=='__main__':main()
