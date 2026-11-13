import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from capital_connect_v1.engine import SYMBOLS
from capital_connect_v1.paper import PaperLedger

class PaperTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / 'paper.sqlite3')
        self.ledger = PaperLedger(self.path)
        self.start = 1800000000 // 900 * 900
    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()
    def prices(self, price):
        return {s: price for s in SYMBOLS}
    def warmup(self):
        for i in range(30):
            self.ledger.scan(self.prices(100+i), self.start+i*900)
    def test_warmup_progress(self):
        result = self.ledger.scan(self.prices(100), self.start)
        self.assertTrue(all(r["reason"] == "warming_up_price_history" for r in result))
        self.assertEqual(result[0]["history_samples"], 1)
        self.assertEqual(result[0]["warmup_remaining_minutes"], 435)
        result = self.ledger.scan(self.prices(102), self.start+1800)
        self.assertEqual(result[0]["history_samples"], 1)

    def test_restart_and_duplicate_scan(self):
        self.warmup()
        before = self.ledger.status()
        self.assertEqual(len(before['positions']), 4)
        self.ledger.close()
        self.ledger = PaperLedger(self.path)
        self.assertEqual(before, self.ledger.status())
        self.ledger.scan(self.prices(129), self.start+29*900)
        self.assertEqual(before, self.ledger.status())
    def test_exit_and_fees(self):
        self.warmup()
        self.ledger.scan(self.prices(132), self.start+30*900)
        status = self.ledger.status()
        self.assertEqual(status['positions'], [])
        expected = 4*(D(10)*(1-D('.001'))/D(129)*D(132)*(1-D('.001'))-D(10))
        self.assertAlmostEqual(D(status['realized_pnl_usdt']), expected)
        self.assertAlmostEqual(D(status['cash_usdt']), D(1000)+expected)
        self.assertAlmostEqual(D(status['commission_estimate_usdt']), expected*D('.1'))
    def test_bad_data_does_not_mutate(self):
        before = self.ledger.status()
        for price in ['NaN', 'Infinity', '-1', '0']:
            with self.assertRaises(ValueError):
                self.ledger.scan(self.prices(price), self.start)
        with self.assertRaises(ValueError):
            self.ledger.scan({'BTCUSDT': 100}, self.start)
        self.assertEqual(before, self.ledger.status())
    def test_gap_requires_new_warmup(self):
        for i in range(29):
            self.ledger.scan(self.prices(100+i), self.start+i*900)
        results = self.ledger.scan(self.prices(140), self.start+30*900)
        self.assertTrue(all(x['action']=='WAIT' for x in results))
        self.assertEqual(self.ledger.status()['positions'], [])
    def test_stop_loss_closes_position(self):
        self.warmup()
        results = self.ledger.scan(self.prices(120), self.start+30*900)
        self.assertTrue(all(x['reason']=='stop_loss' for x in results))
        self.assertLess(D(self.ledger.status()['realized_pnl_usdt']), 0)
    def test_second_connection_cannot_duplicate(self):
        self.warmup()
        other = PaperLedger(self.path)
        try:
            self.assertEqual(other.scan(self.prices(129), self.start+29*900)[0]['reason'], 'duplicate_or_old_scan')
            self.assertEqual(len(other.status()['recent_trades']), 4)
        finally:
            other.close()

if __name__ == '__main__':
    unittest.main()
