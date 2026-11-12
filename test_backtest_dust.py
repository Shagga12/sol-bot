import json
from pathlib import Path
import tempfile
import unittest
from decimal import Decimal
from strategy_backtest import replay,make_bundle,load_bundle,DataUnavailable,INTERVAL_MS


def fixture():
    data=[{'start_ms':i*INTERVAL_MS,'open':'90','high':'90','low':'90','close':'90'} for i in range(220)]
    for row in data[:50]: row.update(open='100',high='100',low='100',close='100')
    data[50].update(open='100',high='110',low='100',close='110')
    data[51].update(open='120',high='120',low='120',close='120')
    data[52].update(open='120',high='120',low='90',close='90')
    data[150].update(open='90',high='110',low='90',close='110')
    for row in data[151:]: row.update(open='110',high='110',low='110',close='110')
    return data


class DustTest(unittest.TestCase):
    def setUp(self): self.filters={'base_step':'.001','minimum_notional':'1'}

    def test_strict_policy_halts_once_not_thousands_of_skip_attempts(self):
        r=replay(fixture(),self.filters)
        self.assertEqual(r['entries'],1)
        self.assertEqual(r['exit_fills'],1)
        self.assertEqual(r['dust_event_count'],1)
        self.assertEqual(r['halt_reason'],'UNSELLABLE_DUST_BLOCKS_NEW_ENTRIES')
        self.assertEqual(r['minimum_notional_skips'],0)
        self.assertIsNone(r['pending_final_signal_not_executed'])
        self.assertGreater(Decimal(r['remaining_base_qty']),0)

    def test_quarantine_is_explicit_and_can_take_another_signal(self):
        baseline=replay(fixture(),self.filters)
        alternate=replay(fixture(),self.filters,dust_policy='quarantine')
        self.assertEqual(baseline['dust_policy'],'halt')
        self.assertGreater(alternate['entries'],baseline['entries'])
        self.assertGreater(Decimal(alternate['quarantined_dust_qty']),0)
        self.assertFalse(alternate['live_trading_ready'])

    def test_dust_keeps_cost_and_never_becomes_cash(self):
        r=replay(fixture(),self.filters,dust_policy='quarantine')
        sold=sum((Decimal(t['qty']) for t in r['trades'] if t['side']=='SELL'),Decimal(0))
        acquired=sum((Decimal(t['net_qty']) for t in r['trades'] if t['side']=='BUY'),Decimal(0))
        self.assertEqual(acquired-sold,Decimal(r['remaining_base_qty']))
        outflow=sum((Decimal(t['cost_usdt']) for t in r['trades'] if t['side']=='BUY'),Decimal(0))
        inflow=sum((Decimal(t['net_proceeds_usdt']) for t in r['trades'] if t['side']=='SELL'),Decimal(0))
        self.assertEqual(Decimal('5.5')-outflow+inflow,Decimal(r['ending_cash_usdt']))
        self.assertGreater(Decimal(r['quarantined_dust_cost_usdt']),0)

    def test_data_bundle_round_trip_preserves_candles_and_filter_proxy(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'market.json'
            p.write_text(json.dumps(make_bundle(fixture(),self.filters)))
            data,filters=load_bundle(p)
            self.assertEqual(data,fixture())
            self.assertEqual(filters,self.filters)

    def test_tampered_bundle_fails_checksum(self):
        bundle=make_bundle(fixture(),self.filters)
        bundle['bars'][0]['close']='1'
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'market.json';p.write_text(json.dumps(bundle))
            with self.assertRaises(DataUnavailable): load_bundle(p)

    def test_policy_name_cannot_silently_change(self):
        with self.assertRaises(ValueError): replay(fixture(),self.filters,dust_policy='ignore')

if __name__=='__main__': unittest.main()
