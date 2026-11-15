"""User-token-only Supabase transport; no service-role key or exchange credentials."""
import json,re
from urllib.request import Request,build_opener,HTTPRedirectHandler
from urllib.error import HTTPError
from urllib.parse import urlencode

class Unauthorized(Exception):pass
class Unavailable(Exception):pass
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

class Supabase:
    def __init__(self,url,key,opener=None):
        if not re.fullmatch(r'https://[a-z0-9]{20}\.supabase\.co',url):raise ValueError('Use the fixed project HTTPS URL')
        if not key or key.startswith('sb_secret_'):raise ValueError('A publishable key is required; secret keys are forbidden')
        # Reject legacy service-role JWT keys too; only an anon JWT can be used.
        if key.count('.')==2:
            import base64
            try:role=json.loads(base64.urlsafe_b64decode(key.split('.')[1]+'==='))['role']
            except Exception:raise ValueError('Invalid publishable key') from None
            if role!='anon':raise ValueError('Service-role keys are forbidden')
        self.url=url;self.key=key;self.opener=opener or build_opener(NoRedirect)
    def request(self,path,token=None,body=None,method='GET'):
        allowed=('/auth/v1/token?grant_type=password','/auth/v1/user','/auth/v1/logout','/auth/v1/signup',
                 '/rest/v1/rpc/cc_trader_public_gate','/rest/v1/rpc/cc_trader_identity','/rest/v1/rpc/cc_request_trader_account',
                 '/rest/v1/cc_trader_release?select=*',
                 '/rest/v1/cc_trader_profiles?select=user_id,display_name,status,order_limit_usdt,created_at',
                 '/rest/v1/cc_trader_wallet_entries?select=asset,amount,kind,created_at&order=created_at.desc&limit=100',
                 '/rest/v1/cc_trader_orders?select=side,symbol,quantity,average_price,net_realized_pnl,status,created_at&order=created_at.desc&limit=100',
                 '/rest/v1/cc_trader_commissions?select=settlement_id,net_realized_pnl,commission_amount,created_at&order=created_at.desc&limit=100',
                 '/rest/v1/cc_trader_audit?select=actor,action,target,created_at&order=created_at.desc&limit=100')
        patch=method=='PATCH' and re.fullmatch(r'/rest/v1/cc_trader_profiles\?user_id=eq\.[0-9a-f-]{36}',path)
        if path not in allowed and not patch:raise ValueError('Unsupported data route')
        headers={'apikey':self.key,'Content-Type':'application/json'}
        if token:headers['Authorization']='Bearer '+token
        if patch:headers['Prefer']='return=representation'
        req=Request(self.url+path,headers=headers,data=None if body is None else json.dumps(body).encode(),method=method)
        try:
            with self.opener.open(req,timeout=10) as response:
                data=response.read(250000)
                return json.loads(data) if data else None
        except HTTPError as error:
            if error.code in (400,401,403):raise Unauthorized('Sign-in or access could not be verified') from None
            raise Unavailable('Account service unavailable') from None
        except (OSError,ValueError):raise Unavailable('Account service unavailable') from None
    def sign_in(self,email,password):
        data=self.request('/auth/v1/token?grant_type=password',body={'email':email,'password':password},method='POST')
        token=data.get('access_token','')
        user=self.user(token)
        return token,user
    def user(self,token):
        if not token:raise Unauthorized('Sign in first')
        user=self.request('/auth/v1/user',token)
        if not isinstance(user,dict) or not user.get('id') or not user.get('email_confirmed_at') or user.get('is_anonymous'):raise Unauthorized('A verified account is required')
        return user
    def identity(self,token):
        result=self.request('/rest/v1/rpc/cc_trader_identity',token,body={},method='POST')
        if not isinstance(result,dict) or type(result.get('is_owner')) is not bool:raise Unauthorized('Account role could not be verified')
        return result
