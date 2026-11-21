import unittest
from capital_connect_v1.futures_protection import verify_linear_position, ProtectionNotVerified

class FuturesProtectionTests(unittest.TestCase):
    def setUp(self):
        self.position = {
            "symbol": "SOLUSDT", "side": "Buy", "size": "0.5",
            "avgPrice": "150", "stopLoss": "148.5", "takeProfit": "156",
            "tradeMode": 1, "leverage": "3", "tpslMode": "Full"
        }

    def test_exchange_snapshot_is_not_activation(self):
        result = verify_linear_position(self.position)
        self.assertTrue(result["exchange_snapshot_verified"])
        self.assertFalse(result["live_activation_authorized"])

    def test_missing_stop_rejected(self):
        self.position["stopLoss"] = ""
        with self.assertRaises(ProtectionNotVerified):
            verify_linear_position(self.position)

    def test_missing_take_profit_rejected(self):
        self.position["takeProfit"] = "0"
        with self.assertRaises(ProtectionNotVerified):
            verify_linear_position(self.position)

    def test_wrong_contract_rejected(self):
        self.position["symbol"] = "BTCUSDT"
        with self.assertRaises(ProtectionNotVerified):
            verify_linear_position(self.position)

    def test_wrong_direction_rejected(self):
        self.position["stopLoss"] = "160"
        with self.assertRaises(ProtectionNotVerified):
            verify_linear_position(self.position)

    def test_cross_margin_rejected(self):
        self.position["tradeMode"] = 0
        with self.assertRaises(ProtectionNotVerified):
            verify_linear_position(self.position)

    def test_wrong_leverage_rejected(self):
        self.position["leverage"] = "5"
        with self.assertRaises(ProtectionNotVerified):
            verify_linear_position(self.position)

    def test_partial_protection_rejected(self):
        self.position["tpslMode"] = "Partial"
        with self.assertRaises(ProtectionNotVerified):
            verify_linear_position(self.position)

if __name__ == "__main__":
    unittest.main()
