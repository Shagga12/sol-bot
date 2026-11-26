import io
import unittest
from contextlib import redirect_stdout
from decimal import Decimal
from unittest.mock import patch

from check_binance_demo_orders import ALGO, OPEN_ALGOS, ORDER, DemoClient, verify_orders


class FakeExchange:
    def __init__(self):
        self.amount = '0'
        self.active = []
        self.calls = []
        self.reject_profit = False

    def signed(self, method, path, **params):
        self.calls.append((method, path, params))
        if path.endswith('/dual'):
            return {'dualSidePosition': False}
        if path.endswith('/positionRisk'):
            return [{'symbol': 'SOLUSDT', 'positionAmt': self.amount}]
        if path == OPEN_ALGOS:
            return self.active[:]
        if path.endswith('/openOrders'):
            return []
        if path == ORDER and params['side'] == 'BUY':
            self.amount = params['quantity']
            return {'status': 'FILLED', 'executedQty': self.amount, 'avgPrice': '100'}
        if path == ORDER and params.get('reduceOnly') == 'true':
            self.amount = '0'
            return {'status': 'FILLED'}
        if method == 'POST' and path == ALGO:
            if self.reject_profit and params['type'] == 'TAKE_PROFIT_MARKET':
                raise RuntimeError('rejected take-profit')
            self.active.append(dict(clientAlgoId=params['clientAlgoId'], orderType=params['type'],
                                    triggerPrice=params['triggerPrice'], algoStatus='NEW', reduceOnly=True))
            return {}
        if method == 'DELETE' and path == ALGO:
            self.active = [row for row in self.active if row['clientAlgoId'] != params['clientAlgoId']]
            return {}
        raise AssertionError((method, path))


class DemoOrdersTest(unittest.TestCase):
    def verify(self, exchange):
        with patch('check_binance_demo_orders.order_size', return_value=(Decimal('0.25'), Decimal('0.01'))):
            with redirect_stdout(io.StringIO()):
                verify_orders(exchange, 'SOLUSDT', Decimal('25'))

    def test_entry_protection_and_cleanup(self):
        exchange = FakeExchange()
        self.verify(exchange)
        exits = [params for method, path, params in exchange.calls if method == 'POST' and path == ALGO]
        self.assertEqual([(p['type'], p['triggerPrice']) for p in exits],
                         [('STOP_MARKET', '99.00'), ('TAKE_PROFIT_MARKET', '104.00')])
        self.assertTrue(all(p['reduceOnly'] == 'true' for p in exits))
        self.assertEqual(exchange.amount, '0')
        self.assertEqual(exchange.active, [])

    def test_rejected_protection_flattens_and_cancels_remaining_order(self):
        exchange = FakeExchange()
        exchange.reject_profit = True
        with self.assertRaisesRegex(RuntimeError, 'rejected take-profit'):
            self.verify(exchange)
        self.assertEqual(exchange.amount, '0')
        self.assertEqual(exchange.active, [])

    def test_existing_position_blocks_all_writes(self):
        exchange = FakeExchange()
        exchange.amount = '1'
        with self.assertRaisesRegex(RuntimeError, 'existing position'):
            self.verify(exchange)
        self.assertTrue(all(method == 'GET' for method, _, _ in exchange.calls))

    def test_signed_requests_use_demo_origin(self):
        with patch.object(DemoClient, 'public', return_value={'serverTime': 1}):
            client = DemoClient('mock-key', 'mock-secret')
        with patch.object(client.opener, 'open', return_value=io.StringIO('{}')) as send:
            client.signed('POST', ALGO, symbol='SOLUSDT')
        request = send.call_args.args[0]
        self.assertEqual(request.host, 'demo-fapi.binance.com')
        self.assertIn(b'signature=', request.data)


if __name__ == '__main__':
    unittest.main()
