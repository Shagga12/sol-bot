import io
import json
import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import patch

from capital_connect_v1.live import Bybit, Config, Halt, Journal, Worker, floor, main


def config(**changes):
    # Fixture values are test inputs, not recommended trading settings.
    return Config(**{'environment': 'testnet', 'symbol': 'BTCUSDT', 'capital_usdt': '50',
        'order_usdt': '10', 'daily_loss_usdt': '1', 'stop_loss_fraction': '.01',
        'take_profit_fraction': '.04', 'slippage_percent': '.10', **changes})


RULES = {'symbol': 'BTCUSDT', 'status': 'Trading', 'quoteCoin': 'USDT',
         'priceFilter': {'tickSize': '.1'},
         'lotSizeFilter': {'basePrecision': '.000001', 'minOrderAmt': '1', 'maxLimitOrderQty': '1'}}
NOW = 1800000000


class Fake:
    def __init__(self):
        self.writes = []
        self.calls = []
        self.fail_write = False
        self.order = None
        self.fills = []
        self.availability = {'Buy': D('50'), 'Sell': D('1')}
        self.bid, self.ask = D('60000'), D('60001')
        self.closes = [str(100 + i) for i in range(30)]

    def one(self, endpoint, **kwargs):
        if endpoint.endswith('instruments-info'):
            return RULES
        if endpoint.endswith('tickers'):
            return {'bid1Price': str(self.bid), 'ask1Price': str(self.ask)}
        return {'takerFeeRate': '.001'}

    def available(self, side):
        return self.availability[side]

    def request(self, endpoint, params=None, write=False):
        self.calls.append((endpoint, params))
        if write:
            self.writes.append(params)
            if self.fail_write:
                raise Halt('Timed out after possible exchange acceptance')
            return {'orderId': 'exchange-order'}
        if endpoint.endswith('/realtime') or endpoint.endswith('/history'):
            return {'list': [self.order] if self.order else []}
        if endpoint.endswith('/list'):
            return {'list': self.fills}
        if endpoint.endswith('/kline'):
            bucket = NOW // 900
            return {'list': [[str((bucket-30+i)*900*1000), '0', '0', '0', close]
                             for i, close in reversed(list(enumerate(self.closes)))]}
        raise AssertionError(endpoint)


def fill(side='Buy', qty='.00005', value='3', fee='.00000005', currency='BTC', identity='fill-1'):
    return {'orderId': 'exchange-order', 'symbol': 'BTCUSDT', 'side': side, 'execId': identity,
            'execType': 'Trade', 'execQty': qty, 'execValue': value, 'execFee': fee,
            'feeCurrency': currency, 'extraFees': ''}


class LiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / 'live.sqlite3')
        self.c = config()
        self.j = Journal(self.path, self.c, 'account-1')
        self.fake = Fake()
        self.worker = Worker(self.c, self.fake, self.j)

    def tearDown(self):
        self.j.db.close()
        self.tmp.cleanup()

    def order(self, side='Buy', qty='.00005', value='3', status='Filled'):
        payload = self.worker.payload(side, D('5') if side == 'Buy' else D('.00005'),
                                      RULES, D('60000'), D('60001'), D('.001'), NOW)
        self.j.reserve(payload, NOW)
        self.fake.order = {'orderId': 'exchange-order', 'orderLinkId': payload['orderLinkId'],
            'symbol': 'BTCUSDT', 'side': side, 'orderStatus': status,
            'cumExecQty': qty, 'cumExecValue': value}
        return payload

    def test_config_rejects_missing_and_nonfinite_numbers(self):
        for val in (None, 'NaN', 'Infinity', '0', '-1'):
            with self.subTest(val=val), self.assertRaises(Halt):
                config(capital_usdt=val)

    def test_config_rejects_unsupported_pair_and_overspending(self):
        for values in ({'symbol': 'BTCUSD'}, {'environment': 'demo'}, {'order_usdt': '51'},
                       {'slippage_percent': '.001'}, {'stop_loss_fraction': '1'}):
            with self.subTest(values=values), self.assertRaises(Halt):
                config(**values)

    def test_database_binding_rejects_different_account_or_configuration(self):
        for uid, c in [('account-2', self.c), ('account-1', config(environment='mainnet'))]:
            with self.assertRaises(Halt):
                Journal(self.path, c, uid)

    def test_floor_handles_non_power_of_ten_steps(self):
        self.assertEqual(floor('1.249', '.05'), D('1.20'))

    def test_rounding_and_worst_price_respect_budget(self):
        p = self.worker.payload('Buy', D('5'), RULES, D('60000'), D('60001'), D('.001'), NOW)
        self.assertLessEqual(D(p['qty']) * D('60001') * D('1.001') * D('1.001'), 5)
        self.assertEqual(p['isLeverage'], 0)
        self.assertEqual(p['orderType'], 'Limit')
        self.assertEqual(p['timeInForce'], 'IOC')
        self.assertLessEqual(D(p['qty']) * D(p['price']) * D('1.001'), 5)
        self.assertLessEqual(len(p['orderLinkId']), 36)
        self.assertEqual(D(p['qty']) % D('.000001'), 0)

    def test_under_minimum_is_rejected(self):
        with self.assertRaises(Halt):
            self.worker.payload('Buy', D('.5'), RULES, D('60000'), D('60001'), D('.001'), NOW)

    def test_order_limit_uses_current_instrument_maximum(self):
        rules = {**RULES, 'lotSizeFilter': {**RULES['lotSizeFilter'], 'maxLimitOrderQty': '.00001'}}
        with self.assertRaises(Halt):
            self.worker.payload('Buy', D('5'), rules, D('60000'), D('60001'), D('.001'), NOW)

    def test_custom_daily_loss_limit_blocks_entries(self):
        self.j.db.execute("INSERT INTO live_orders(link,created,side,payload,terminal,pnl,settled) VALUES('old',?,'Sell','{}',1,'-1',?)",
                          (NOW - 7200, NOW - 7200))
        self.assertEqual(self.worker.tick(NOW)['reason'], 'configured_daily_loss_limit')
        self.assertEqual(self.fake.writes, [])

    def test_dust_cost_remains_owned_when_new_buy_is_prepared(self):
        self.j.db.execute("UPDATE live_position SET qty='.000001',cost='.06'")
        self.worker.tick(NOW)
        self.assertEqual(self.fake.writes[0]['side'], 'Buy')
        self.assertEqual(self.j.position(), (D('.000001'), D('.06')))

    def test_wide_spread_blocks_entry(self):
        self.fake.ask = D('61000')
        self.assertEqual(self.worker.tick(NOW)['reason'], 'spread_too_wide')
        self.assertEqual(self.fake.writes, [])

    def test_acceptance_does_not_create_position(self):
        result = self.worker.tick(NOW)
        self.assertEqual(result['state'], 'ORDER_PENDING')
        self.assertEqual(self.j.position(), (D(0), D(0)))
        self.assertEqual(len(self.j.pending()), 1)
        # Existing strategy keeps its 10% allocation cap: 50 available -> <=5.
        self.assertLess(D(self.fake.writes[0]['qty']) * self.fake.ask, 5)

    def test_unknown_submission_is_durable_and_never_retried(self):
        self.fake.fail_write = True
        with self.assertRaises(Halt):
            self.worker.tick(NOW)
        self.j.db.close()
        self.j = Journal(self.path, self.c, 'account-1')
        self.worker = Worker(self.c, self.fake, self.j)
        with self.assertRaises(Halt):
            self.worker.tick(NOW + 5)
        self.assertEqual(len(self.fake.writes), 1)
        self.assertEqual(len(self.j.pending()), 1)

    def test_partial_active_order_blocks_new_orders(self):
        self.order(status='PartiallyFilled')
        self.assertEqual(self.worker.tick(NOW + 5)['reason'], 'order_pending')
        self.assertEqual(self.fake.writes, [])

    def test_partial_cancelled_buy_uses_fills_and_base_fee(self):
        self.order(status='PartiallyFilledCanceled')
        self.fake.fills = [fill()]
        self.assertTrue(self.worker.reconcile(NOW + 5))
        self.assertEqual(self.j.position(), (D('.00004995'), D('3')))
        self.assertTrue(self.worker.reconcile(NOW + 10))
        self.assertEqual(self.j.position(), (D('.00004995'), D('3')))

    def test_quote_fee_is_added_to_buy_cost(self):
        self.order()
        self.fake.fills = [fill(fee='.003', currency='USDT')]
        self.worker.reconcile(NOW + 5)
        self.assertEqual(self.j.position(), (D('.00005'), D('3.003')))

    def test_no_fill_cancel_does_not_change_position(self):
        self.order(qty='0', value='0', status='Cancelled')
        self.worker.reconcile(NOW + 5)
        self.assertEqual(self.j.position(), (D(0), D(0)))

    def test_missing_or_duplicate_fills_halt_without_ledger_mutation(self):
        self.order()
        for fills in ([], [fill(), fill()], [fill(currency='BNB')], [fill(qty='.00004')]):
            self.fake.fills = fills
            with self.subTest(fills=fills), self.assertRaises(Halt):
                self.worker.reconcile(NOW + 5)
            self.assertEqual(self.j.position(), (D(0), D(0)))
            self.assertEqual(len(self.j.pending()), 1)

    def test_partial_sell_keeps_remaining_cost_and_realizes_actual_profit(self):
        self.j.db.execute("UPDATE live_position SET qty='.0001',cost='6'")
        self.order(side='Sell', qty='.00005', value='3.3')
        self.fake.fills = [fill(side='Sell', value='3.3', fee='.0033', currency='USDT')]
        self.worker.reconcile(NOW + 5)
        self.assertEqual(self.j.position(), (D('.00005'), D('3')))
        self.assertEqual(self.j.pnl(), D('.2967'))

    def test_sell_cannot_consume_unowned_assets(self):
        self.order(side='Sell')
        self.fake.fills = [fill(side='Sell', fee='.003', currency='USDT')]
        with self.assertRaises(Halt):
            self.worker.reconcile(NOW + 5)

    def test_profit_exit_sells_only_owned_available_qty(self):
        self.j.db.execute("UPDATE live_position SET qty='.0001',cost='5'")
        self.worker.tick(NOW)
        self.assertEqual(self.fake.writes[0]['side'], 'Sell')
        self.assertEqual(self.fake.writes[0]['qty'], '0.0001')

    def test_loss_exit_is_allowed_despite_daily_entry_limit(self):
        self.j.db.execute("UPDATE live_position SET qty='.0001',cost='7'")
        self.worker.tick(NOW)
        self.assertEqual(self.fake.writes[0]['side'], 'Sell')

    def test_no_signal_does_not_submit_or_repeat_scan(self):
        self.fake.closes.reverse()
        self.assertEqual(self.worker.tick(NOW)['state'], 'WAIT')
        self.assertEqual(self.worker.tick(NOW + 5)['reason'], 'entry_already_checked')
        self.assertEqual(self.fake.writes, [])

    def test_missing_candle_or_bad_spread_prevents_order(self):
        self.fake.closes = self.fake.closes[:-1]
        with self.assertRaises(Halt):
            self.worker.tick(NOW)
        self.assertEqual(self.fake.writes, [])

    def test_stale_pending_order_cannot_be_resubmitted(self):
        self.order()
        with self.assertRaises(Halt):
            self.worker.reconcile(NOW + 7 * 86400)
        self.assertEqual(self.fake.writes, [])

    def test_mainnet_run_without_explicit_ack_never_calls_network(self):
        path = Path(self.tmp.name) / 'config.json'
        from dataclasses import asdict
        path.write_text(json.dumps(asdict(config(environment='mainnet'))))
        with patch('capital_connect_v1.live.Bybit.request', side_effect=AssertionError('network')), patch('sys.stdout', new_callable=io.StringIO):
            self.assertEqual(main(['run', '--config', str(path), '--db', self.path, '--enable-orders']), 1)


class TransportTests(unittest.TestCase):
    def test_inspection_can_report_unified_permission_but_cannot_write(self):
        result = {'readOnly':0,'userID':1,'permissions':{'Spot':['SpotTrade'],'Derivatives':['DerivativesTrade']}}
        api, _ = self.api(result, inspection_only=True)
        with patch('time.time', return_value=NOW):
            self.assertEqual(api.identity(), '1')
        self.assertEqual(api.non_spot_permissions, {'Derivatives':['DerivativesTrade']})
        with self.assertRaises(Halt):
            api.request('/v5/order/create', {}, write=True)
        with self.assertRaises(Halt):
            self.api(result, inspection_only=True, allow_orders=True)

    def test_empty_query_signing_has_no_get_body_and_trims_outer_whitespace(self):
        import hmac
        import hashlib
        api, opener = self.api()
        api = Bybit(config(), ' fake-key\n', ' fake-secret\n', opener=opener)
        with patch('time.time', return_value=NOW):
            api.request('/v5/user/query-api')
        req = opener.requests[0]
        expected = hmac.new(b'fake-secret', (str(NOW*1000)+'fake-key5000').encode(), hashlib.sha256).hexdigest()
        self.assertEqual(req.get_header('X-bapi-sign'), expected)
        self.assertEqual(req.get_header('X-bapi-api-key'), 'fake-key')
        self.assertIsNone(req.data)
        self.assertNotIn('?', req.full_url)

    def test_invalid_credential_formats_fail_without_network_or_secret_output(self):
        for key, secret, expected in [('same','same','identical'), ('fake-key','-----BEGIN PRIVATE KEY-----','RSA'), ('fake-key','fake secret','whitespace')]:
            api, opener = self.api()
            api = Bybit(config(), key, secret, opener=opener)
            with self.assertRaisesRegex(Halt, expected):
                api.request('/v5/user/query-api')
            self.assertEqual(opener.requests, [])

    def api(self, result=None, **kwargs):
        class Opener:
            def __init__(self):
                self.requests = []
            def open(self, req, timeout):
                self.requests.append(req)
                return io.StringIO(json.dumps({'retCode': 0, 'time': NOW * 1000, 'result': result or {}}))
        opener = Opener()
        return Bybit(config(), 'fake-key', 'fake-secret', opener=opener, **kwargs), opener

    def test_default_transport_rejects_writes_and_withdrawals(self):
        api, opener = self.api()
        for path, write in [('/v5/order/create', True), ('/v5/asset/withdraw/create', False)]:
            with self.assertRaises(Halt):
                api.request(path, {}, write=write)
        self.assertEqual(opener.requests, [])

    def test_borrowing_fields_are_never_used_as_available_balance(self):
        api, _ = self.api({'symbol': 'BTCUSDT', 'side': 'Buy', 'maxTradeAmount': '10000', 'spotMaxTradeAmount': '5'})
        with patch('time.time', return_value=NOW):
            self.assertEqual(api.available('Buy'), 5)

    def test_missing_actual_available_balance_halts(self):
        api, _ = self.api({'symbol': 'BTCUSDT', 'side': 'Buy', 'maxTradeAmount': '10000'})
        with patch('time.time', return_value=NOW), self.assertRaises(Halt):
            api.available('Buy')

    def test_broad_api_permissions_are_rejected(self):
        api, _ = self.api({'readOnly': 0, 'userID': 1,
            'permissions': {'Spot': ['SpotTrade'], 'Wallet': ['Withdraw']}})
        with patch('time.time', return_value=NOW), self.assertRaises(Halt):
            api.identity()

    def test_read_only_key_is_not_reported_ready(self):
        api, _ = self.api({'readOnly': 1, 'userID': 1, 'permissions': {'Spot': ['SpotTrade']}})
        with patch('time.time', return_value=NOW), self.assertRaises(Halt):
            api.identity()

    def test_stale_exchange_response_is_rejected(self):
        api, _ = self.api()
        with patch('time.time', return_value=NOW + 10), self.assertRaises(Halt):
            api.request('/v5/market/tickers')

    def test_signing_uses_exact_query_and_testnet_host(self):
        import hashlib
        import hmac
        api, opener = self.api()
        with patch('time.time', return_value=NOW):
            api.request('/v5/order/spot-borrow-check', {'category': 'spot', 'symbol': 'BTCUSDT', 'side': 'Buy'})
        req = opener.requests[0]
        self.assertTrue(req.full_url.startswith('https://api-testnet.bybit.com/'))
        query = req.full_url.split('?')[1]
        expected = hmac.new(b'fake-secret', (str(NOW*1000)+'fake-key5000'+query).encode(), hashlib.sha256).hexdigest()
        self.assertEqual(req.get_header('X-bapi-sign'), expected)
        self.assertEqual(req.get_method(), 'GET')

    def test_post_signing_uses_exact_serialized_body(self):
        import hashlib
        import hmac
        api, opener = self.api(allow_orders=True)
        payload = {'category': 'spot', 'symbol': 'BTCUSDT', 'isLeverage': 0,
            'orderFilter': 'Order', 'orderType': 'Limit', 'timeInForce': 'IOC',
            'side': 'Buy', 'price': '60000', 'qty': '.0001'}
        with patch('time.time', return_value=NOW):
            api.request('/v5/order/create', payload, write=True)
        req = opener.requests[0]
        expected = hmac.new(b'fake-secret', (str(NOW*1000)+'fake-key5000').encode() + req.data, hashlib.sha256).hexdigest()
        self.assertEqual(req.get_header('X-bapi-sign'), expected)
        self.assertEqual(req.get_method(), 'POST')

    def test_check_command_never_enables_order_transport(self):
        from dataclasses import asdict
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            path.write_text(json.dumps(asdict(config())))
            fake = Fake()
            fake.identity = lambda: 'account-1'
            with patch('capital_connect_v1.live.Bybit', return_value=fake) as factory, patch('sys.stdout', new_callable=io.StringIO):
                self.assertEqual(main(['check', '--config', str(path), '--db', str(Path(directory)/'db')]), 0)
            self.assertFalse(factory.call_args.kwargs['allow_orders'])
            self.assertEqual(fake.writes, [])


if __name__ == '__main__':
    unittest.main()
