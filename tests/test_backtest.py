import unittest
from decimal import Decimal as D
from capital_connect_v1.backtest import replay
from capital_connect_v1.engine import SYMBOLS

class BacktestTests(unittest.TestCase):
    def snapshots(self):
        return [(1800000000//900*900+i*900, {s: D(100+i) for s in SYMBOLS}) for i in range(40)]

    def test_execution_cost_reduces_returns(self):
        rows = self.snapshots()
        low = replay(rows, execution_cost='0.001')
        high = replay(rows, execution_cost='0.002')
        self.assertLess(D(high['net_liquidation_pnl_usdt']), D(low['net_liquidation_pnl_usdt']))
        self.assertGreater(low['closed_trades'], 0)

    def test_future_data_cannot_change_prefix_results(self):
        rows = self.snapshots()
        before = replay(rows[:31])
        rows.append((rows[-1][0]+900, {s:D('0.01') for s in SYMBOLS}))
        self.assertEqual(before, replay(rows[:31]))

    def test_invalid_cost_rejected(self):
        with self.assertRaises(ValueError):
            replay(self.snapshots(), execution_cost='NaN')
