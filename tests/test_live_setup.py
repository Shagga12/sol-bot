import json
import unittest
from unittest.mock import patch

import capital_connect_server as app
import test_dashboard


def draft(**changes):
    # Test inputs only; never suggested account limits.
    return {'environment': 'testnet', 'symbol': 'BTCUSDT', 'capital_usdt': '50',
            'order_usdt': '5', 'daily_loss_usdt': '1', 'stop_loss_percent': '1',
            'take_profit_percent': '4', 'slippage_percent': '0.10', **changes}


class SetupTests(unittest.TestCase):
    def test_configuration_matches_execution_schema_and_never_activates(self):
        result = app.validate_live_setup(draft())
        self.assertEqual(result['config']['stop_loss_fraction'], '0.01')
        self.assertEqual(result['config']['take_profit_fraction'], '0.04')
        self.assertNotIn('stop_loss_percent', result['config'])
        self.assertFalse(result['settings_applied_to_bot'])
        self.assertFalse(result['readiness']['can_activate'])
        self.assertEqual(result['orders_submitted'], 0)

    def test_limits_and_payloads_are_rejected(self):
        for changes in ({'order_usdt':'51'}, {'daily_loss_usdt':'51'},
                        {'capital_usdt': 'NaN'}, {'capital_usdt': True},
                        {'stop_loss_percent':'100'}, {'take_profit_percent':'0'},
                        {'slippage_percent':'.001'}, {'slippage_percent':'10.01'},
                        {'symbol':'BTCUSD'}, {'environment':'DEMO'},
                        {'apiSecret':'must-not-be-accepted'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                app.validate_live_setup(draft(**changes))


class SetupHTTPTests(unittest.TestCase):
    setUpClass = classmethod(test_dashboard.DashboardHTTPTests.setUpClass.__func__)
    tearDownClass = classmethod(test_dashboard.DashboardHTTPTests.tearDownClass.__func__)
    setUp = test_dashboard.DashboardHTTPTests.setUp
    request = test_dashboard.DashboardHTTPTests.request

    def test_live_state_requires_owner_auth(self):
        self.assertEqual(self.request('/api/live/status', auth=False)[0], 401)
        state = json.loads(self.request('/api/live/status')[2])
        self.assertFalse(state['can_activate'])
        self.assertFalse(state['real_trading_active'])

    def test_validation_and_activation_respect_auth_and_origin(self):
        for path in ('/api/live/validate','/api/live/activate'):
            self.assertEqual(self.request(path, 'POST', '{}', auth=False)[0],401)
            self.assertEqual(self.request(path, 'POST', '{}', headers={
                'Origin':'https://untrusted.example','Content-Type':'application/json'})[0],403)

    def test_valid_mainnet_configuration_cannot_unlock_activation(self):
        headers={'Origin':'https://capital-connect-preflight.onrender.com','Content-Type':'application/json'}
        with patch.object(app,'bybit_read',side_effect=AssertionError('no exchange calls')):
            status,_,body=self.request('/api/live/validate','POST',json.dumps(draft(environment='mainnet')),headers=headers)
            self.assertEqual(status,200)
            self.assertFalse(json.loads(body)['readiness']['can_activate'])
            status,_,body=self.request('/api/live/activate','POST','{}',headers=headers)
            self.assertEqual(status,409)
            self.assertFalse(json.loads(body)['real_trading_active'])
        self.assertIsNone(app.REPORT)

    def test_secret_fields_are_never_echoed_or_saved(self):
        headers={'Origin':'https://capital-connect-preflight.onrender.com','Content-Type':'application/json'}
        status,_,body=self.request('/api/live/validate','POST',json.dumps(draft(apiSecret='sensitive-test-value')),headers=headers)
        self.assertEqual(status,400)
        self.assertNotIn(b'sensitive-test-value',body)


if __name__=='__main__':
    unittest.main()
