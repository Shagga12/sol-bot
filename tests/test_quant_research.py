import unittest
from capital_connect_v1.quant_research import analyze_prices


class QuantResearchTests(unittest.TestCase):
    def test_short_history_waits(self):
        self.assertEqual(analyze_prices([100.0] * 10).reason, "insufficient_history")

    def test_uptrend_candidate(self):
        result = analyze_prices([100.0 + i for i in range(31)])
        self.assertEqual(result.action, "BUY_CANDIDATE")

    def test_downtrend_candidate(self):
        result = analyze_prices([100.0 - i for i in range(31)])
        self.assertEqual(result.action, "SELL_CANDIDATE")

    def test_flat_prices_wait(self):
        self.assertEqual(analyze_prices([100.0] * 31).action, "WAIT")

    def test_bad_price_wait(self):
        self.assertEqual(analyze_prices([100.0] * 30 + [0.0]).reason, "invalid_prices")

    def test_invalid_parameters(self):
        with self.assertRaises(ValueError):
            analyze_prices([100.0] * 31, fast=30, slow=10)


if __name__ == "__main__":
    unittest.main()
