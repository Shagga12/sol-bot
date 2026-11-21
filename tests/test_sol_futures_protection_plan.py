import unittest
from capital_connect_v1.sol_futures_protection_plan import protection_plan

class ProtectionPlanTests(unittest.TestCase):
    def test_long_matches_bybit_reference(self):
        p = protection_plan("70.110", "Buy", tick="0.01")
        self.assertEqual(p["stop_loss"], "69.40")
        self.assertEqual(p["take_profit"], "72.92")
        self.assertEqual(p["trailing_activation_price"], "71.52")
        self.assertEqual(p["trailing_distance_usdt"], "0.71")
        self.assertFalse(p["live_orders_enabled"])

    def test_short_inverts_protection(self):
        p = protection_plan("70", "Sell", tick="0.01")
        self.assertEqual(p["stop_loss"], "70.70")
        self.assertEqual(p["take_profit"], "67.20")
        self.assertEqual(p["trailing_activation_price"], "68.60")

    def test_invalid_inputs(self):
        for price, side in [(0, "Buy"), (70, "Long")]:
            with self.assertRaises(ValueError):
                protection_plan(price, side)

if __name__ == "__main__":
    unittest.main()
