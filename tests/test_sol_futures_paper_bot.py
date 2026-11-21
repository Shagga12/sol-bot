import unittest
from decimal import Decimal
from capital_connect_v1.sol_futures_paper_bot import SOLFuturesPaperBot


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


if __name__ == "__main__":
    unittest.main()
