import unittest
from decimal import Decimal
from capital_connect_v1.strategy import evaluate

class StrategyTests(unittest.TestCase):
    def setUp(self):
        self.rising = list(range(100, 130))
    def test_buy_is_demo_only(self):
        result = evaluate(self.rising, 100, 0, 100, "0.001")
        self.assertEqual(result.action, "DEMO_BUY")
        self.assertEqual(result.budget_usdt, Decimal("10"))
    def test_warmup_differs_from_bad_prices(self):
        self.assertEqual(evaluate([1, 2], 100, 0, 100, ".001").reason, "warming_up_price_history")
        self.assertEqual(evaluate([0]*30, 100, 0, 100, ".001").reason, "invalid_market_price")

    def test_daily_loss_blocks(self):
        self.assertEqual(evaluate(self.rising, 100, -2, 100, "0.001").action, "WAIT")
    def test_spread_blocks(self):
        self.assertEqual(evaluate(self.rising, 100, 0, 100, "0.01").action, "WAIT")
    def test_open_position_blocks(self):
        self.assertEqual(evaluate(self.rising, 100, 0, 100, "0.001", True).action, "WAIT")
    def test_missing_candles_blocks(self):
        self.assertEqual(evaluate([1,2], 100, 0, 100, "0.001").action, "WAIT")
    def test_bad_price_blocks(self):
        self.assertEqual(evaluate([0]*30, 100, 0, 100, "0.001").action, "WAIT")

if __name__ == "__main__":
    unittest.main()
