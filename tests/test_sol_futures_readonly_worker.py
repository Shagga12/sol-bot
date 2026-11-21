"""Safety regression tests for the read-only Futures worker."""
import unittest
from unittest.mock import patch
from capital_connect_v1.sol_futures_readonly_worker import snapshot

class TestReadOnlyWorker(unittest.TestCase):
    @patch("capital_connect_v1.sol_futures_readonly_worker.verify_testnet_credentials")
    def test_verified_testnet_is_still_execution_disabled(self, probe):
        probe.return_value = {"environment": "TESTNET", "authentication": "VERIFIED",
            "read_only": {"wallet": "VERIFIED", "positions": "VERIFIED", "orders": "VERIFIED"}}
        status = snapshot()
        self.assertTrue(status["read_only_ready"])
        self.assertFalse(status["execution_enabled"])
        self.assertFalse(status["mainnet_verified"])
        self.assertFalse(status["exchange_side_protection_verified"])
        self.assertEqual(status["orders_submitted"], 0)

    @patch("capital_connect_v1.sol_futures_readonly_worker.verify_testnet_credentials")
    def test_missing_orders_check_fails_closed(self, probe):
        probe.return_value = {"environment": "TESTNET", "authentication": "VERIFIED",
            "read_only": {"wallet": "VERIFIED", "positions": "VERIFIED", "orders": "FAILED"}}
        self.assertFalse(snapshot()["read_only_ready"])

    @patch("capital_connect_v1.sol_futures_readonly_worker.verify_testnet_credentials")
    def test_mainnet_never_qualifies_as_testnet_ready(self, probe):
        probe.return_value = {"environment": "MAINNET", "authentication": "VERIFIED",
            "read_only": {"wallet": "VERIFIED", "positions": "VERIFIED", "orders": "VERIFIED"}}
        self.assertFalse(snapshot()["read_only_ready"])

if __name__ == "__main__":
    unittest.main()
