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


    def test_reject_invalid_numeric_values(self):
        for field in ("margin_usdt", "stop_loss_fraction", "take_profit_fraction"):
            for value in ("NaN", "Infinity", "-Infinity", "invalid", ""):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(FuturesConfigurationError):
                        replace(SOLFuturesPlan(), **{field: value}).validate()

    def test_reject_nonapproved_order_activation(self):
        for value in (True, 1, "true"):
            with self.subTest(value=value):
                with self.assertRaises(FuturesConfigurationError):
                    replace(SOLFuturesPlan(), orders_enabled=value).validate()

    def test_default_budget_and_protection_settings(self):
        p = SOLFuturesPlan().validate()
        self.assertEqual(p.symbol, "SOLUSDT")
        self.assertEqual(p.category, "linear")
        self.assertEqual(p.environment, "testnet")
        self.assertEqual(p.margin_mode, "ISOLATED")
        self.assertEqual(p.leverage, 3)
        self.assertEqual(p.stop_loss_fraction, "0.01")
        self.assertEqual(p.take_profit_fraction, "0.04")

if __name__ == "__main__":
    unittest.main()
