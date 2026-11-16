import unittest
from capital_connect_v1.quant_backtest import backtest


class QuantBacktestTests(unittest.TestCase):
    def test_flat_prices_stay_in_cash(self):
        result = backtest([100.0] * 40)
        self.assertEqual(result.trades, 0)
        self.assertEqual(result.ending_usdt, 1000.0)

    def test_uptrend_has_buy_and_fees(self):
        result = backtest([100.0 + i for i in range(50)])
        self.assertEqual(result.trades, 1)
        self.assertGreater(result.fees_usdt, 0)
        self.assertGreater(result.ending_usdt, 1000.0)

    def test_invalid_data_rejected(self):
        with self.assertRaises(ValueError):
            backtest([100.0] * 39 + [float("nan")])

    def test_no_lookahead(self):
        prices = [100.0 + i for i in range(45)]
        first = backtest(prices)
        second = backtest(prices + [10000.0])
        self.assertEqual(first.trades, 1)
        self.assertEqual(second.trades, 1)
        self.assertGreater(second.ending_usdt, first.ending_usdt)


if __name__ == "__main__":
    unittest.main()
