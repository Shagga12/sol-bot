import unittest
from dataclasses import replace
from capital_connect_v1.futures_plan import SOLFuturesPlan, FuturesConfigurationError

class FuturesPlanTests(unittest.TestCase):
    def test_safe_proposal(self):
        p = SOLFuturesPlan().validate()
        self.assertEqual(str(p.maximum_notional_usdt), "30")
        self.assertFalse(p.orders_enabled)

    def test_reject_live_orders(self):
        for changes in (
            {"orders_enabled": True}, {"environment": "mainnet"},
            {"leverage": 10}, {"margin_mode": "CROSS"},
            {"margin_usdt": "100"}, {"symbol": "BTCUSDT"},
            {"stop_loss_fraction": "0.05"}, {"take_profit_fraction": "0.10"},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(FuturesConfigurationError):
                    replace(SOLFuturesPlan(), **changes).validate()

if __name__ == "__main__":
    unittest.main()
