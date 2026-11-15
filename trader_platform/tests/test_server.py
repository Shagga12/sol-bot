import unittest,threading,json,http.client,base64,time
from copy import deepcopy
from trader_platform.server import ReviewServer
from trader_platform.supabase_client import Unauthorized

OWNER='11111111-1111-4111-8111-111111111111';TRADER='22222222-2222-4222-8222-222222222222';OTHER='33333333-3333-4333-8333-333333333333'
class FakeProvider:
    def __init__(self):self.owner=False;self.calls=[]
    def sign_in(self,email,password):
        if password!='test-signin-password':raise Unauthorized('Sign-in or access could not be verified')
        self.owner=email=='owner@example.invalid';return 'verified-test-access',self.user('verified-test-access')
    def user(self,token):
        if token!='verified-test-access':raise Unauthorized('Invalid session')
        return {'id':OWNER if self.owner else TRADER,'email_confirmed_at':'now','user_metadata':{'role':'super_admin'}}
    def identity(self,token):return {'user_id':OWNER if self.owner else TRADER,'is_owner':self.owner}
    def request(self,path,token=None,body=None,method='GET'):
        self.calls.append((path,deepcopy(body),method))
        if 'cc_trader_release?' in path:return [{'approval_reference':'','onboarding_enabled':False,'funding_enabled':False,'trading_enabled':False,'custody_provider':'','execution_release':''}]
        if 'cc_trader_profiles?' in path:
            if method=='PATCH':return [{'user_id':OTHER,**body}]
            return [{'user_id':OWNER if self.owner else TRADER,'display_name':'Review profile','status':'pending','order_limit_usdt':'15','created_at':'now'}]
        return []

class PortalHTTP(unittest.TestCase):
    def setUp(self):
        self.provider=FakeProvider();self.server=ReviewServer(('127.0.0.1',0),self.provider,'private-review-test-password','http://127.0.0.1:8766')
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.cookie=None
    def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join()
    def req(self,path,body=None,private=True,origin='http://127.0.0.1:8766'):
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        headers={}
        if private:headers['Authorization']='Basic '+base64.b64encode(b'ron:private-review-test-password').decode()
        if self.cookie:headers['Cookie']=self.cookie
        if body is not None:headers.update({'Content-Type':'application/json','Origin':origin})
        c.request('GET' if body is None else 'POST',path,None if body is None else json.dumps(body),headers)
        r=c.getresponse();data=r.read();cookie=r.getheader('Set-Cookie')
        if cookie:self.cookie=cookie.split(';')[0]
        result=r.status,data,cookie;c.close();return result
    def login(self,owner=False):
        code,_,cookie=self.req('/api/login',{'email':'owner@example.invalid' if owner else 'trader@example.invalid','password':'test-signin-password'})
        self.assertEqual(code,200);self.assertIn('HttpOnly',cookie);self.assertIn('SameSite=Strict',cookie);self.assertNotIn('verified-test-access',cookie)
    def test_private_assets_and_api_require_owner_preview_access(self):
        for p in ('/','/portal.js','/api/me'):self.assertEqual(self.req(p,private=False)[0],401)
    def test_login_me_account_and_server_verified_role(self):
        self.login();code,data,_=self.req('/api/me');self.assertEqual(code,200)
        data=json.loads(data);self.assertFalse(data['is_owner']);self.assertFalse(data['release']['funding_enabled'])
        self.assertEqual(self.req('/api/account')[0],200)
    def test_trader_cannot_admin_even_with_spoofed_user_metadata(self):
        self.login();self.assertEqual(self.req('/api/admin')[0],403)
        self.assertEqual(self.req('/api/admin/profile',{'user_id':OTHER,'status':'approved','order_limit_usdt':'15'})[0],403)
        self.assertFalse(any(method=='PATCH' for _,_,method in self.provider.calls))
    def test_owner_can_vet_without_activating_money(self):
        self.login(True);self.assertEqual(self.req('/api/admin')[0],200)
        code,data,_=self.req('/api/admin/profile',{'user_id':OTHER,'status':'approved','order_limit_usdt':'15'})
        self.assertEqual(code,200);self.assertFalse(json.loads(data)['funding_enabled'])
    def test_every_money_route_and_registration_remain_locked(self):
        self.login(True)
        for path in ('/api/deposit-address','/api/withdraw','/api/order-submit','/api/commission-collect','/api/register'):
            code,data,_=self.req(path,{});self.assertEqual(code,423);self.assertEqual(json.loads(data)['orders_submitted'],0)
        self.assertFalse(any(method=='PATCH' for _,_,method in self.provider.calls))
    def test_buy_sell_review_is_not_order_submission(self):
        self.login()
        for side in ('Buy','Sell'):
            code,data,_=self.req('/api/order-review',{'side':side,'symbol':'BTCUSDT','amount_usdt':'15'})
            self.assertEqual(code,200);self.assertFalse(json.loads(data)['can_submit'])
        self.assertEqual(self.req('/api/order-review',{'side':'Buy','symbol':'BTCUSDT','amount_usdt':'16'})[0],400)
    def test_cross_origin_write_rejected_and_session_expires(self):
        self.login();self.assertEqual(self.req('/api/order-review',{},origin='https://other.invalid')[0],401)
        for session in self.server.sessions.values():session['expires']=0
        self.assertEqual(self.req('/api/me')[0],401)
    def test_logout_removes_session(self):
        self.login();self.assertEqual(self.req('/api/logout',{})[0],200);self.assertEqual(self.req('/api/me')[0],401)
    def test_login_rate_limit(self):
        for _ in range(5):self.assertEqual(self.req('/api/login',{'email':'trader@example.invalid','password':'incorrect-password'})[0],401)
        self.assertEqual(self.req('/api/login',{'email':'trader@example.invalid','password':'incorrect-password'})[0],429)
