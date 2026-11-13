"""Offline safety tests for isolated live-order gateway."""
import os
import unittest
from unittest.mock import patch
from capital_connect_v1 import live_orders as orders

class SafetyTests(unittest.TestCase):
    def test_disarmed_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "disarmed"):
                orders.submit_market_buy("BTCUSDT", "6", approved_available_usdt="6", approval_token="yes")
    def test_reject_bad_amount(self):
        for amount in ("nan", "-1", "0", "Infinity"):
            with self.assertRaises(ValueError):
                orders.positive(amount)
    def test_preflight_rejects_unsupported_pair(self):
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            orders.prepare_buy("DOGEUSDT", "5", "key", "secret")
    def test_preflight_caps_order(self):
        with self.assertRaisesRegex(ValueError, "risk cap"):
            orders.prepare_buy("BTCUSDT", "11", "key", "secret")
    def test_minimum_order(self):
        def fake_api(method, path, params=None, key=None, secret=None):
            if path.endswith("instruments-info"):
                return {"list": [{"symbol": "BTCUSDT", "status": "Trading",
                         "lotSizeFilter": {"minOrderAmt": "5", "maxMarketOrderQty": "1"}}]}
            raise AssertionError("Wallet must not be requested when below minimum")
        with patch.object(orders, "api", side_effect=fake_api):
            with self.assertRaisesRegex(ValueError, "minimum"):
                orders.prepare_buy("BTCUSDT", "4", "key", "secret")

if __name__ == "__main__":
    unittest.main()
