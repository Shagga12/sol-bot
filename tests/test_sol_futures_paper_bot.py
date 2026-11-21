import unittest
from decimal import Decimal
from capital_connect_v1.sol_futures_paper_bot import SOLFuturesPaperBot
from capital_connect_v1.bybit_futures_testnet_probe import verify_contract, check


class PaperBotTests(unittest.TestCase):
    def test_stopped_by_default(self):
        bot = SOLFuturesPaperBot()
        self.assertFalse(bot.running)
        with self.assertRaises(ValueError):
            bot.enter("Long", "100")

    def test_long_stop_and_target(self):
        for price, reason, pnl in (("99", "STOP_LOSS", "-0.30"), ("104", "TAKE_PROFIT", "1.20")):
            bot = SOLFuturesPaperBot()
            bot.start()
            p = bot.enter("Long", "100")
            self.assertEqual(p.quantity, Decimal("0.3"))
            result = bot.tick(price)
            self.assertEqual(result["reason"], reason)
            self.assertEqual(result["pnl_before_fees"], Decimal(pnl))

    def test_short_stop_and_target(self):
        for price, reason in (("101", "STOP_LOSS"), ("96", "TAKE_PROFIT")):
            bot = SOLFuturesPaperBot()
            bot.start()
            bot.enter("Short", "100")
            self.assertEqual(bot.tick(price)["reason"], reason)

    def test_stop_blocks_entries_but_keeps_exits(self):
        bot = SOLFuturesPaperBot()
        bot.start()
        bot.enter("Long", "100")
        bot.stop()
        self.assertEqual(bot.tick("99")["reason"], "STOP_LOSS")
        with self.assertRaises(ValueError):
            bot.enter("Long", "100")

    def test_one_position_only(self):
        bot = SOLFuturesPaperBot()
        bot.start()
        bot.enter("Long", "100")
        with self.assertRaises(ValueError):
            bot.enter("Short", "100")


class TestnetContractValidationTests(unittest.TestCase):
    def test_live_public_bybit_testnet_contract(self):
        result = check()
        self.assertEqual(result['testnet_contract'], 'VERIFIED')
        self.assertEqual(result['orders_submitted'], 0)

    def test_valid_contract(self):
        data = {"retCode": 0, "result": {"list": [{"symbol": "SOLUSDT", "status": "Trading", "lotSizeFilter": {"qtyStep": "0.1", "minOrderQty": "0.1"}}]}}
        self.assertEqual(verify_contract(data)["orders_submitted"], 0)

    def test_reject_wrong_symbol(self):
        data = {"retCode": 0, "result": {"list": [{"symbol": "BTCUSDT", "status": "Trading", "lotSizeFilter": {"qtyStep": "0.1", "minOrderQty": "0.1"}}]}}
        with self.assertRaises(ValueError):
            verify_contract(data)


if __name__ == "__main__":
    unittest.main()
