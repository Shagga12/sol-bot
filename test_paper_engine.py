import tempfile
import unittest
from pathlib import Path
from decimal import Decimal
from paper_engine import PaperLedger


class PaperLedgerTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = str(Path(self.folder.name) / 'ledger.sqlite')
        self.ledger = PaperLedger(self.path)

    def tearDown(self):
        self.ledger.close()
        self.folder.cleanup()

    def buy(self):
        self.ledger.create('b', 'SOLUSDT', 'BUY', '10')
        self.ledger.reconcile('b', 'FILLED', '1', '9.99', '.01')

    def test_restart_preserves_position_and_balance(self):
        self.buy()
        before = self.ledger.state()
        self.ledger.close()
        self.ledger = PaperLedger(self.path)
        self.assertEqual(self.ledger.state(), before)

    def test_duplicate_fill_and_request_are_idempotent(self):
        self.buy()
        before = self.ledger.state()
        self.ledger.create('b', 'SOLUSDT', 'BUY', '10')
        self.ledger.reconcile('b', 'FILLED', '1', '9.99', '.01')
        self.assertEqual(before, self.ledger.state())

    def test_rejected_sell_keeps_position(self):
        self.buy()
        self.ledger.create('s', 'SOLUSDT', 'SELL', '1')
        self.ledger.reconcile('s', 'REJECTED')
        self.assertEqual(self.ledger.state()['positions'][0]['qty'], '1')

    def test_unknown_blocks_next_order_after_restart(self):
        self.ledger.create('b', 'BTCUSDT', 'BUY', '10')
        self.ledger.reconcile('b', 'UNKNOWN')
        self.ledger.close()
        self.ledger = PaperLedger(self.path)
        with self.assertRaises(ValueError):
            self.ledger.create('b2', 'BTCUSDT', 'BUY', '10')

    def test_partial_cancel_then_sell_preserves_cost_and_net_pnl(self):
        self.buy()
        self.ledger.create('s', 'SOLUSDT', 'SELL', '1')
        self.ledger.reconcile('s', 'PARTIAL', '.4', '4.4', '.01')
        self.ledger.reconcile('s', 'CANCELLED', '.4', '4.4', '.01')
        state = self.ledger.state()
        self.assertEqual(Decimal(state['positions'][0]['qty']), Decimal('.6'))
        self.assertEqual(Decimal(state['positions'][0]['cost']), Decimal('6'))
        self.assertEqual(Decimal(state['orders'][-1]['pnl']), Decimal('.39'))
        self.assertEqual(Decimal(state['cash']), Decimal('14.39'))

    def test_partial_buy_cumulative_snapshot_not_double_counted(self):
        self.ledger.create('b', 'SOLUSDT', 'BUY', '10')
        self.ledger.reconcile('b', 'PARTIAL', '.4', '3.99', '.01')
        self.ledger.reconcile('b', 'FILLED', '1', '9.98', '.02')
        state = self.ledger.state()
        self.assertEqual(Decimal(state['cash']), Decimal('10'))
        self.assertEqual(Decimal(state['positions'][0]['qty']), Decimal('1'))

    def test_invalid_snapshot_rolls_back(self):
        self.ledger.create('b', 'SOLUSDT', 'BUY', '10')
        before = self.ledger.state()
        with self.assertRaises(ValueError):
            self.ledger.reconcile('b', 'FILLED', '1', '10', '.01')
        self.assertEqual(before, self.ledger.state())

    def test_cumulative_regression_and_terminal_conflict_rejected(self):
        self.buy()
        with self.assertRaises(ValueError):
            self.ledger.reconcile('b', 'CANCELLED', '1', '9.99', '.01')
        with self.assertRaises(ValueError):
            self.ledger.reconcile('b', 'FILLED', '.5', '5', '0')

    def test_budget_and_no_short_sales(self):
        for symbol, side, size in [('BTCUSDT', 'BUY', '20.01'), ('ETHUSDT', 'SELL', '1')]:
            with self.assertRaises(ValueError): self.ledger.create('x', symbol, side, size)

    def test_order_identity_cannot_change(self):
        self.buy()
        with self.assertRaises(ValueError): self.ledger.create('b', 'ETHUSDT', 'BUY', '10')

    def test_nonfinite_and_negative_values_rejected(self):
        for size in ['NaN', 'Infinity', '-1', '0']:
            with self.assertRaises(ValueError): self.ledger.create('x', 'BTCUSDT', 'BUY', size)

    def test_concurrent_second_connection_cannot_create_second_pending(self):
        other = PaperLedger(self.path)
        try:
            self.ledger.create('a', 'BTCUSDT', 'BUY', '10')
            with self.assertRaises(ValueError): other.create('b', 'ETHUSDT', 'BUY', '10')
        finally:
            other.close()

    def test_no_fill_evidence_is_not_success(self):
        self.ledger.create('a', 'BTCUSDT', 'BUY', '10')
        with self.assertRaises(ValueError): self.ledger.reconcile('a', 'FILLED')


if __name__ == '__main__':
    unittest.main()
