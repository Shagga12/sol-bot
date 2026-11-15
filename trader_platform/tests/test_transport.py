import unittest,json
from unittest.mock import MagicMock
from trader_platform.supabase_client import Supabase,Unauthorized
URL='https://mlybldtawwltavngqmul.supabase.co'
class Transport(unittest.TestCase):
    def test_service_role_and_non_project_hosts_rejected(self):
        with self.assertRaises(ValueError):Supabase(URL,'sb_secret_never-use')
        with self.assertRaises(ValueError):Supabase('https://supabase.co.evil.invalid','key')
        with self.assertRaises(ValueError):Supabase('http://mlybldtawwltavngqmul.supabase.co','key')
    def test_get_user_is_authoritative_not_local_jwt_decode(self):
        opener=MagicMock();response=opener.open.return_value.__enter__.return_value
        response.read.return_value=json.dumps({'id':'verified','email_confirmed_at':'now','is_anonymous':False}).encode()
        c=Supabase(URL,'sb_publishable_test-only',opener);self.assertEqual(c.user('jwt')['id'],'verified')
        req=opener.open.call_args.args[0];self.assertEqual(req.full_url,URL+'/auth/v1/user');self.assertEqual(req.get_header('Authorization'),'Bearer jwt')
    def test_anonymous_accounts_rejected_and_arbitrary_routes_forbidden(self):
        opener=MagicMock();opener.open.return_value.__enter__.return_value.read.return_value=b'{"id":"x","is_anonymous":true}'
        c=Supabase(URL,'sb_publishable_test-only',opener)
        with self.assertRaises(Unauthorized):c.user('jwt')
        with self.assertRaises(ValueError):c.request('/v5/order/create',body={'side':'Buy'},method='POST')
