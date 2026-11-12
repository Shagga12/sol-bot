import json
import unittest
from pathlib import Path
from strategy_signals import evaluate


class StrategyTest(unittest.TestCase):
    def setUp(self):
        self.policy=json.loads(Path(__file__).with_name('strategy_proposal.json').read_text())
        self.candles=[{'close_ms':(i+1)*900000,'close':'100'} for i in range(51)]
        self.candles[-1]['close']='110'
        self.now=51*900000+1000
    def run_signal(self,**kwargs):
        args=dict(now_ms=self.now,bid='110',ask='110.01',quote_ms=self.now,paused=False)
        args.update(kwargs)
        return evaluate(self.policy,self.candles,**args)
    def test_cross_signal_is_explicitly_not_authorization(self):
        r=self.run_signal()
        self.assertEqual(r['signal'],'PAPER_ENTRY_SIGNAL')
        self.assertFalse(r['permits_live_order'])
    def test_no_crossover_no_trade(self):
        self.candles[-1]['close']='100'
        self.assertEqual(self.run_signal()['signal'],'WAIT')
    def test_pause_blocks_entries(self):
        self.assertEqual(self.run_signal(paused=True)['signal'],'PAUSED')
    def test_same_candle_cannot_trigger_second_entry(self):
        self.assertEqual(self.run_signal(last_entry_signal_ms=self.candles[-1]['close_ms'])['signal'],'WAIT')
    def test_daily_entry_limit(self):
        self.assertEqual(self.run_signal(entries_today=2)['signal'],'PAUSED')
    def test_daily_loss_threshold(self):
        self.assertEqual(self.run_signal(realized_loss_today='.11')['signal'],'PAUSED')
    def test_missing_and_future_quotes_stop(self):
        for stamp in [self.now-6000,self.now+1]:
            self.assertEqual(self.run_signal(quote_ms=stamp)['signal'],'HALT')
    def test_unknown_order_halts_even_if_price_trigger(self):
        r=self.run_signal(unresolved_order=True,position={'qty':'1','cost_usdt':'100'})
        self.assertEqual(r['signal'],'HALT')
    def test_exit_signal_uses_net_proceeds_and_is_available_while_paused(self):
        r=self.run_signal(bid='102.1',ask='102.11',position={'qty':'1','cost_usdt':'100'},paused=True)
        self.assertEqual(r['signal'],'HOLD')
        r=self.run_signal(bid='102.2',ask='102.21',position={'qty':'1','cost_usdt':'100'},paused=True)
        self.assertEqual(r['signal'],'PAPER_EXIT_SIGNAL')
    def test_stop_signal_uses_net_after_fee(self):
        self.assertEqual(self.run_signal(bid='99',ask='99.01',position={'qty':'1','cost_usdt':'100'})['signal'],'PAPER_EXIT_SIGNAL')
    def test_unclosed_or_gapped_bars_rejected(self):
        self.candles[-1]['close_ms']+=900000
        self.assertEqual(self.run_signal()['signal'],'HALT')
    def test_spread_prevents_entry(self):
        self.assertEqual(self.run_signal(ask='112')['signal'],'WAIT')
    def test_cannot_turn_evaluator_into_live_mode(self):
        self.policy['live_activation']=True
        with self.assertRaises(ValueError): self.run_signal()
    def test_nan_not_accepted(self):
        with self.assertRaises(ValueError): self.run_signal(bid='NaN')

if __name__ == '__main__': unittest.main()
