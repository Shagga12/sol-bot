import unittest
from unittest.mock import patch
import diagnostics as d

class DiagnosticsTest(unittest.TestCase):
    def test_no_unsupported_write_endpoint(self):
        with self.assertRaises(d.ConnectionError):
            d.get('/v5/order/create')
    def test_missing_credentials(self):
        with self.assertRaises(d.ConnectionError):
            d.account_check(None, None)
    def test_no_fake_price(self):
        with patch.object(d, 'get', return_value={}):
            with self.assertRaises(d.ConnectionError): d.price()
    def test_accepts_real_price_below_100(self):
        with patch.object(d, 'get', return_value={'list': [{'lastPrice': '42.5'}]}):
            self.assertEqual(d.price(), 42.5)
    def test_writable_key_stops_before_balance(self):
        with patch.object(d, 'get', return_value={'readOnly': 0}) as get:
            with self.assertRaises(d.ConnectionError): d.account_check('fixture', 'fixture')
            self.assertEqual(get.call_count, 1)
    def test_balance_is_provider_response(self):
        result = {'list': [{'coin': [{'coin': 'USDT', 'walletBalance': '12.34'}]}]}
        with patch.object(d, 'get', side_effect=[{'readOnly': 1}, result]):
            self.assertEqual(d.account_check('fixture', 'fixture'), result)
if __name__ == '__main__': unittest.main()
