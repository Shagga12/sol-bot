import base64
import http.client
import json
import os
import threading
import unittest
from unittest.mock import patch

import capital_connect_server as app


class DashboardHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment=patch.dict(os.environ,{'CAPITAL_VIEW_PASSWORD':'local-test-password','CAPITAL_REPORT_TOKEN':'local-report-token'})
        cls.environment.start()
        cls.server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()
        cls.environment.stop()

    def setUp(self):
        app.REPORT=None;app.LAST_CHECK=0

    def request(self,path,method='GET',body=None,auth=True,headers=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        request_headers={}
        if auth:
            request_headers['Authorization']='Basic '+base64.b64encode(b'ron:local-test-password').decode()
        request_headers.update(headers or {})
        connection.request(method,path,body=body,headers=request_headers)
        response=connection.getresponse()
        result=response.status,dict(response.getheaders()),response.read()
        connection.close()
        return result

    def test_dashboard_assets_and_account_state_require_authentication(self):
        for path in ['/', '/dashboard.css','/dashboard.js','/api/status']:
            with self.subTest(path=path):
                self.assertEqual(self.request(path,auth=False)[0],401)

    def test_health_exposes_release_and_disabled_orders_only(self):
        status,headers,body=self.request('/health',auth=False)
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body),{'status':'ok','live_orders':False,'dashboard_version':'mobile-desk-v1'})
        self.assertNotIn(b'local-test-password',body)

    def test_page_and_assets_serve_with_security_headers(self):
        for path,expected in [('/',b'Your trading desk.'),('/dashboard.js',b'function reportAge'),('/dashboard.css',b'@media(max-width:700px)')]:
            status,headers,body=self.request(path)
            self.assertEqual(status,200)
            self.assertIn(expected,body)
            self.assertIn('no-store',headers['Cache-Control'])
            self.assertIn("script-src 'self'",headers['Content-Security-Policy'])

    def test_unknown_asset_paths_are_not_read_from_filesystem(self):
        self.assertEqual(self.request('/../capital_connect_server.py')[0],404)

    def test_missing_report_is_explicit_instead_of_fake_balances(self):
        _,_,body=self.request('/api/status')
        self.assertEqual(json.loads(body),{'report':None})

    def test_authenticated_worker_report_reaches_dashboard(self):
        report={'mode':'DEMO','live_order_execution':False,'positions':[], 'recent_trades':[],'cash_usdt':'998.39'}
        status,_,_=self.request('/api/report','POST',json.dumps(report),headers={'Authorization':'Bearer local-report-token'})
        self.assertEqual(status,200)
        _,_,body=self.request('/api/status')
        self.assertEqual(json.loads(body)['report'],report)

    def test_real_mode_and_malformed_reports_are_rejected(self):
        for report in [[],{}, {'mode':'LIVE','live_order_execution':True,'positions':[],'recent_trades':[]},
                       {'mode':'DEMO','live_order_execution':False,'positions':[1],'recent_trades':[]}]:
            status,_,_=self.request('/api/report','POST',json.dumps(report),headers={'Authorization':'Bearer local-report-token'})
            self.assertEqual(status,400)
            self.assertIsNone(app.REPORT)

    def test_report_cannot_be_written_with_viewer_credentials(self):
        self.assertEqual(self.request('/api/report','POST','{}')[0],403)

    def test_connection_check_rejects_cross_origin_before_using_credentials(self):
        with patch.object(app,'check_bybit') as check:
            status,_,_=self.request('/api/bybit/check','POST','{}',headers={'Content-Type':'application/json','Origin':'https://untrusted.example'})
            self.assertEqual(status,403)
            check.assert_not_called()

    def test_connection_check_is_rate_limited_and_does_not_save_credentials(self):
        headers={'Content-Type':'application/json','Origin':'https://capital-connect-preflight.onrender.com'}
        with patch.object(app,'check_bybit',return_value={'verified':True}) as check:
            self.assertEqual(self.request('/api/bybit/check','POST',json.dumps({'apiKey':'test-only','apiSecret':'test-only'}),headers=headers)[0],200)
            self.assertEqual(self.request('/api/bybit/check','POST','{}',headers=headers)[0],429)
            check.assert_called_once()
        self.assertIsNone(app.REPORT)


class BybitCheckTests(unittest.TestCase):
    def test_unknown_pair_is_rejected_before_network(self):
        with patch.object(app,'bybit_read') as read, self.assertRaises(ValueError):
            app.check_bybit({'symbol':'NOTUSDT'})
        read.assert_not_called()

    def test_available_amount_excludes_borrowable_amount(self):
        responses=[{'readOnly':1}, {'list':[{'accountType':'UNIFIED','coin':[{'coin':'USDT','walletBalance':'59','locked':'10'}]}]},
                   {'symbol':'BTCUSDT','side':'Buy','spotMaxTradeAmount':'49','maxTradeAmount':'99999'},
                   {'list':[{'symbol':'BTCUSDT','status':'Trading','lotSizeFilter':{'minOrderAmt':'5'}}]}]
        with patch.object(app,'bybit_read',side_effect=responses) as read:
            result=app.check_bybit({'apiKey':'test-key-1234','apiSecret':'test-secret-1234','symbol':'BTCUSDT'})
        self.assertEqual(result['available_spot_usdt'],'49')
        self.assertEqual(result['minimum_order_usdt'],'5')
        self.assertFalse(result['automatic_real_orders'])
        self.assertFalse(result['credentials_saved'])
        self.assertNotIn('apiKey',result)
        self.assertTrue(all(call.args[0] != '/v5/order/create' for call in read.call_args_list))

    def test_wallet_check_does_not_claim_spendable_funds_on_partial_failure(self):
        responses=[{'readOnly':1}, {'list':[{'accountType':'UNIFIED','coin':[]}]},app.ConnectionCheckError('not available')]
        with patch.object(app,'bybit_read',side_effect=responses):
            result=app.check_bybit({'apiKey':'test-key-1234','apiSecret':'test-secret-1234'})
        self.assertTrue(result['verified'])
        self.assertIsNone(result['available_spot_usdt'])
        self.assertIsNone(result['minimum_order_usdt'])

    def test_order_and_withdrawal_endpoints_remain_rejected(self):
        for path in ['/v5/order/create','/v5/asset/withdraw/create']:
            with self.assertRaises(ValueError):
                app.bybit_read(path,'test','test')


if __name__=='__main__':
    unittest.main()
