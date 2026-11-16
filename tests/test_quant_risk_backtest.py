import unittest
from unittest.mock import patch
from types import SimpleNamespace
from decimal import Decimal as D
from capital_connect_v1.live import Config
from capital_connect_v1.quant_risk_backtest import Assumptions, simulate


def config(**changes):
    return Config(**{'environment': 'mainnet', 'symbol': 'BTCUSDT',
        'capital_usdt': '56', 'order_usdt': '15', 'daily_loss_usdt': '10',
        'stop_loss_fraction': '.01', 'take_profit_fraction': '.04',
        'slippage_percent': '.10', **changes})


A = Assumptions('.001', '.001', '.0001', '.000001', '5')
BASE = 1735689600


def candles(n=40):
    return [{'timestamp': str(BASE+i*900), 'open': '100', 'high': '100.2',
             'low': '99.8', 'close': '100'} for i in range(n)]


class QuantRiskBacktestTests(unittest.TestCase):
    def run_buy(self, data, **changes):
        with patch('capital_connect_v1.quant_risk_backtest.analyze_prices',
                   return_value=SimpleNamespace(action='BUY_CANDIDATE')):
            return simulate(data, config(**changes), A)

    def test_uses_only_completed_candles_and_never_approves_activation(self):
        data = candles(); seen = []
        def observe(prices):
            seen.append(prices)
            return SimpleNamespace(action='WAIT')
        data[-1].update(open='10000', high='10000', low='10000', close='10000')
        with patch('capital_connect_v1.quant_risk_backtest.analyze_prices', side_effect=observe):
            result = simulate(data, config(), A)
        self.assertTrue(all(len(p) == 31 and 10000. not in p for p in seen))
        self.assertEqual(result['entries'], 0)
        self.assertEqual(D(result['ending_liquidation_quote']), 56)
        self.assertFalse(result['live_activation_approved'])
        self.assertFalse(result['exchange_validation'])

    def test_stop_and_profit_are_attached_and_order_cost_is_bounded(self):
        for reason, extremes in [('STOP_LOSS', {'low': '98'}),
                                  ('TAKE_PROFIT', {'high': '106'})]:
            data = candles(); data[31].update(extremes)
            result = self.run_buy(data); trade = result['trades'][0]
            self.assertEqual(trade['reason'], reason)
            self.assertLessEqual(D(trade['cost']), 15)
            self.assertLess(D(trade['stop']), D(trade['take']))
            self.assertGreater(D(result['fees_paid_quote']), 0)
            self.assertEqual(D(trade['pnl']) > 0, reason == 'TAKE_PROFIT')

    def test_same_bar_double_trigger_uses_stop(self):
        data = candles(); data[31].update(low='98', high='106')
        self.assertEqual(self.run_buy(data)['trades'][0]['reason'], 'STOP_LOSS')

    def test_gap_through_stop_fills_below_trigger(self):
        data = candles(); data[32].update(open='90', high='91', low='89', close='90')
        trade = self.run_buy(data)['trades'][0]
        self.assertEqual(trade['reason'], 'STOP_LOSS')
        self.assertEqual(D(trade['exit_price']), D('90') * D('.999'))
        self.assertLess(D(trade['exit_price']), D(trade['stop']))

    def test_known_open_above_target_precedes_later_bar_low(self):
        data = candles(); data[32].update(open='106', high='107', low='98', close='100')
        self.assertEqual(self.run_buy(data)['trades'][0]['reason'], 'TAKE_PROFIT')

    def test_cooldown_blocks_four_following_buckets(self):
        data = candles(); data[31].update(low='98')
        result = self.run_buy(data)
        self.assertEqual(result['cooldown_blocks'], 4)
        self.assertEqual(result['entries'], 2)

    def test_daily_loss_blocks_entries_until_next_utc_day(self):
        data = candles(100); data[31].update(low='98')
        result = self.run_buy(data, daily_loss_usdt='.01')
        self.assertEqual(result['entries'], 2)
        self.assertGreater(result['daily_loss_blocks'], 0)
        self.assertEqual(result['closed_trades'], 1)

    def test_open_bracket_prevents_additional_signal_entries(self):
        data = candles()
        def signal(prices):
            return SimpleNamespace(action='BUY_CANDIDATE')
        with patch('capital_connect_v1.quant_risk_backtest.analyze_prices', side_effect=signal) as mock:
            result = simulate(data, config(), A)
        self.assertEqual(mock.call_count, 1)
        self.assertEqual(result['open_positions'], 1)

    def test_invalid_ohlc_gaps_and_duplicates_are_rejected(self):
        for mutate in [lambda r: r.update(low='101'),
                       lambda r: r.update(close='NaN'),
                       lambda r: r.update(timestamp=str(BASE+1)),
                       lambda r: r.update(timestamp=str(BASE+30*900))]:
            data = candles(); mutate(data[31])
            with self.assertRaises((ValueError, RuntimeError)):
                self.run_buy(data)

    def test_minimum_and_rounding_can_block_an_entry(self):
        result = self.run_buy(candles(), order_usdt='1')
        self.assertEqual(result['entries'], 0)
        self.assertGreater(result['minimum_order_blocks'], 0)

    def test_liquidation_mark_includes_exit_cost_for_open_holdings(self):
        result = self.run_buy(candles())
        self.assertEqual(result['open_positions'], 1)
        self.assertEqual(result['closed_trades'], 0)
        self.assertLess(D(result['ending_liquidation_quote']), 56)

    def test_invalid_assumptions_rejected(self):
        for changes in [dict(fee='NaN'), dict(exit_slippage='1'), dict(tick='0')]:
            with self.assertRaises((ValueError, RuntimeError)):
                Assumptions(**{**A.__dict__, **changes})
