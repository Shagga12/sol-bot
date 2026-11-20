import unittest
from capital_connect_v1.futures_direction import propose_direction, proposed_protection, SignalError

class FuturesDirectionTests(unittest.TestCase):
    def test_uptrend(self):
        self.assertEqual(propose_direction([100] * 15 + [102, 103, 104, 105, 106]), "LONG")

    def test_downtrend(self):
        self.assertEqual(propose_direction([100] * 15 + [98, 97, 96, 95, 94]), "SHORT")

    def test_flat_market_wait(self):
        self.assertEqual(propose_direction([100] * 20), "WAIT")

    def test_missing_candles_rejected(self):
        with self.assertRaises(SignalError):
            propose_direction([100] * 19)

    def test_invalid_prices_rejected(self):
        with self.assertRaises(SignalError):
            propose_direction([100] * 19 + [0])

    def test_long_protection(self):
        self.assertEqual(proposed_protection("150", "LONG"),
                         {"stop_loss": "148.50", "take_profit": "156.00"})

    def test_short_protection(self):
        self.assertEqual(proposed_protection("150", "SHORT"),
                         {"stop_loss": "151.50", "take_profit": "144.00"})

    def test_wait_has_no_order_targets(self):
        with self.assertRaises(SignalError):
            proposed_protection("150", "WAIT")

if __name__ == "__main__":
    unittest.main()
