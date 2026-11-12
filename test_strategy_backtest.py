import io
import json
import unittest
from decimal import Decimal
from unittest.mock import Mock
from strategy_backtest import download,replay,public_json,DataUnavailable,INTERVAL_MS,day_key


def bars(count=55):
    data=[{'start_ms':i*INTERVAL_MS,'open':'100','high':'100','low':'100','close':'100'} for i in range(count)]
    data[50].update(high='110',close='110')
    for row in data[51:]: row.update(open='120',high='120',low='120',close='120')
    return data


class BacktestTest(unittest.TestCase):
    def test_signal_fills_next_open_not_known_close(self):
        r=replay(bars(),{'base_step':'.001','minimum_notional':'1'})
        trade=r['trades'][0]
        self.assertEqual(trade['time_ms'],51*INTERVAL_MS)
        self.assertEqual(Decimal(trade['price']),Decimal('120.120'))
        self.assertFalse(r['live_trading_ready'])

    def test_buy_fee_reduces_base_and_cash_is_not_negative(self):
        r=replay(bars(),{'base_step':'.001','minimum_notional':'1'})
        t=r['trades'][0]
        self.assertEqual(Decimal(t['net_qty']),Decimal(t['gross_qty'])*Decimal('.999'))
        self.assertGreaterEqual(Decimal(r['ending_cash_usdt']),0)

    def test_too_small_entry_is_skipped_not_borrowed(self):
        r=replay(bars(),{'base_step':'.001','minimum_notional':'6'})
        self.assertEqual(r['entries'],0)
        self.assertGreater(r['minimum_notional_skips'],0)

    def test_decline_can_make_exit_unsellable_due_to_minimum(self):
        data=bars(55)
        data[52].update(low='100',close='100')
        for row in data[53:]: row.update(open='90',high='90',low='90',close='90')
        r=replay(data,{'base_step':'.001','minimum_notional':'5'})
        self.assertEqual(r['exit_fills'],0)
        self.assertGreater(Decimal(r['remaining_base_qty']),0)
        self.assertGreater(r['minimum_notional_skips'],0)

    def test_final_signal_not_filled_at_end_of_dataset(self):
        data=bars(52)
        data[51].update(low='90',close='90')
        r=replay(data,{'base_step':'.001','minimum_notional':'1'})
        self.assertEqual(r['pending_final_signal_not_executed'],'SELL')
        self.assertEqual(r['exit_fills'],0)

    def test_data_gap_or_reversal_rejected(self):
        data=bars()
        data[-1]['start_ms']+=INTERVAL_MS
        with self.assertRaises(DataUnavailable): replay(data,{'base_step':'.001','minimum_notional':'1'})

    def test_complete_public_download_closed_bars_only(self):
        now=200*INTERVAL_MS+123
        start=8*INTERVAL_MS
        records=[[str(start+i*INTERVAL_MS),'100','100','100','100','0','0'] for i in range(192)]
        fetch=Mock(return_value={'symbol':'BTCUSDT','category':'spot','list':list(reversed(records))})
        data=download(2,now_ms=now,fetch=fetch)
        self.assertEqual(len(data),192)
        self.assertEqual(data[-1]['start_ms'],199*INTERVAL_MS)
        self.assertEqual(fetch.call_count,1)

    def test_incomplete_history_cannot_be_reported_as_complete(self):
        fetch=Mock(return_value={'symbol':'BTCUSDT','category':'spot','list':[]})
        with self.assertRaises(DataUnavailable): download(2,now_ms=200*INTERVAL_MS,fetch=fetch)

    def test_html_unavailable_page_not_treated_as_market_data(self):
        response=io.BytesIO(b'<html>Site Unavailable</html>')
        response.status=200
        opener=Mock(); opener.open.return_value=response
        with self.assertRaises(DataUnavailable): public_json('/v5/market/kline',{},opener)
        self.assertEqual(opener.open.call_count,1)

    def test_no_private_or_order_endpoint(self):
        with self.assertRaises(ValueError): public_json('/v5/order/create',{})

    def test_day_rollover_uses_tortola_not_host_timezone(self):
        self.assertEqual(day_key(0),'1969-12-31')
        self.assertEqual(day_key(4*3600000),'1970-01-01')

if __name__=='__main__': unittest.main()
