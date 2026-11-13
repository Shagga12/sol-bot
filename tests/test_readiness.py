import unittest
from capital_connect_v1.readiness import read, summarize

class ReadinessTests(unittest.TestCase):
    def test_write_endpoints_are_rejected_before_network(self):
        for path in ['/v5/order/create', '/v5/asset/withdraw/create']:
            with self.assertRaises(ValueError):
                read(path, 'unused', 'unused')
    def test_does_not_confuse_wallet_balance_with_ready(self):
        result = summarize({'readOnly': 1, 'permissions': {}}, {'list': [{'accountType': 'UNIFIED', 'coin': [{'coin': 'USDT', 'walletBalance': '59', 'locked': '20'}]}]})
        self.assertFalse(result['activation_ready'])
        self.assertFalse(result['automatic_real_orders'])
        self.assertEqual(result['reported_usdt_wallet_balance'], '59')
        self.assertFalse(result['spot_permission_present'])
    def test_unknown_fields_stay_unknown(self):
        result = summarize({}, {})
        self.assertEqual(result['key_access'], 'unknown')
        self.assertIsNone(result['reported_usdt_wallet_balance'])
        self.assertFalse(result['unified_wallet_returned'])
