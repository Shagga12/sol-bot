import copy
import unittest
from decimal import Decimal
from spot_preflight import plan_buy


class PreflightTest(unittest.TestCase):
    def setUp(self):
        self.args = dict(instrument={'symbol': 'BTCUSDT', 'baseCoin': 'BTC', 'quoteCoin': 'USDT',
                         'status': 'Trading', 'lotSizeFilter': {'basePrecision': '.000001',
                         'minOrderAmt': '5', 'maxLimitOrderQty': '10'},
                         'priceFilter': {'tickSize': '.1'}}, instrument_at=100,
                         bid='60000', ask='60001', quote_at=100, now=101,
                         available_usdt='20', balance_at=100, committed_usdt='0',
                         budget='20', fee_reserve_rate='.001', order_link_id='cc-test-1')

    def test_budget_includes_fees_and_spot_no_borrow(self):
        p = plan_buy(**self.args)
        self.assertLessEqual(Decimal(p['maximum_quote_with_fee_reserve']), Decimal('20'))
        self.assertEqual(p['payload']['isLeverage'], 0)
        self.assertEqual(p['payload']['timeInForce'], 'IOC')
        self.assertEqual(p['mode'], 'PLAN_ONLY')

    def test_stale_or_future_sources_stop(self):
        for field, value in [('quote_at', 90), ('quote_at', 102), ('balance_at', 90), ('instrument_at', 0)]:
            a = dict(self.args, **{field: value})
            if field == 'instrument_at': a['now'] = 400
            with self.assertRaises(ValueError): plan_buy(**a)

    def test_allocation_cannot_grow_beyond_20(self):
        with self.assertRaises(ValueError): plan_buy(**dict(self.args, committed_usdt='1'))

    def test_insufficient_spendable_balance(self):
        with self.assertRaises(ValueError): plan_buy(**dict(self.args, available_usdt='19'))

    def test_below_minimum_after_rounding(self):
        with self.assertRaises(ValueError): plan_buy(**dict(self.args, budget='4'))

    def test_invalid_numeric_inputs(self):
        for v in ['NaN', 'Infinity', '-1']:
            with self.assertRaises(ValueError): plan_buy(**dict(self.args, ask=v))

    def test_maximum_quantity(self):
        a = copy.deepcopy(self.args)
        a['instrument']['lotSizeFilter']['maxLimitOrderQty'] = '.000001'
        with self.assertRaises(ValueError): plan_buy(**a)

    def test_wrong_asset_or_inactive_instrument(self):
        for key, value in [('symbol', 'XRPUSDT'), ('quoteCoin', 'USDC'), ('status', 'Suspended'), ('isPreListing', True)]:
            a = copy.deepcopy(self.args)
            a['instrument'][key] = value
            with self.assertRaises(ValueError): plan_buy(**a)

    def test_no_missing_filters(self):
        a = copy.deepcopy(self.args)
        del a['instrument']['lotSizeFilter']['minOrderAmt']
        with self.assertRaises(ValueError): plan_buy(**a)

    def test_bad_client_id(self):
        for v in ['', 'a'*37, 'with space']:
            with self.assertRaises(ValueError): plan_buy(**dict(self.args, order_link_id=v))

    def test_bad_spread(self):
        for v in ['61000', '50000']:
            with self.assertRaises(ValueError): plan_buy(**dict(self.args, bid=v))

    def test_supported_pairs(self):
        for base in ['BTC', 'SOL', 'ETH', 'BNB']:
            a = copy.deepcopy(self.args)
            a['instrument'].update(symbol=base+'USDT', baseCoin=base)
            self.assertEqual(plan_buy(**a)['payload']['symbol'], base+'USDT')

if __name__ == '__main__': unittest.main()
