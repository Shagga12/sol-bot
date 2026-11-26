"""Verify one Binance Futures demo entry and its protective orders, then clean up."""

import argparse
import hmac
import json
import os
import time
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4


DEMO = 'https://demo-fapi.binance.com'
ORDER = '/fapi/v1/order'
ALGO = '/fapi/v1/algoOrder'
OPEN_ALGOS = '/fapi/v1/openAlgoOrders'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class DemoClient:
    def __init__(self, key, secret):
        self.key = key
        self.secret = secret.encode()
        self.opener = build_opener(NoRedirect())
        self.clock_offset = self.public('/fapi/v1/time')['serverTime'] - self.now()

    @staticmethod
    def now():
        return time.time_ns() // 1_000_000

    def request(self, method, path, params, headers):
        query = urlencode(params)
        data = query.encode() if method == 'POST' else None
        url = DEMO + path + ('?' + query if query and data is None else '')
        try:
            with self.opener.open(Request(url, data, headers, method=method), timeout=10) as response:
                return json.load(response)
        except HTTPError as error:
            try:
                code = int(json.load(error)['code'])
            except (KeyError, ValueError, TypeError):
                code = error.code
            raise RuntimeError(f'Binance Demo rejected {method} {path} (code {code})') from None

    def public(self, path, **params):
        return self.request('GET', path, params, {})

    def signed(self, method, path, **params):
        params['timestamp'] = self.now() + self.clock_offset
        params['recvWindow'] = 5000
        params['signature'] = hmac.digest(self.secret, urlencode(params).encode(), 'sha256').hex()
        return self.request(method, path, params, {'X-MBX-APIKEY': self.key})


def rounded(value, step, rounding):
    return (value / step).to_integral_value(rounding=rounding) * step


def position(client, symbol):
    positions = client.signed('GET', '/fapi/v3/positionRisk', symbol=symbol)
    amounts = [Decimal(row['positionAmt']) for row in positions if row['symbol'] == symbol]
    if len(amounts) > 1:
        raise RuntimeError('The demo test requires one-way position mode')
    return amounts[0] if amounts else Decimal(0)


def order_size(client, symbol, budget):
    info = client.public('/fapi/v1/exchangeInfo')
    market = next((row for row in info['symbols'] if row['symbol'] == symbol and row['status'] == 'TRADING'), None)
    if market is None:
        raise RuntimeError(f'{symbol} is unavailable on Binance Demo')
    rules = {rule['filterType']: rule for rule in market['filters']}
    lot = rules['MARKET_LOT_SIZE']
    step = Decimal(lot['stepSize'])
    minimum = Decimal(lot['minQty'])
    maximum = Decimal(lot['maxQty'])
    price = Decimal(client.public('/fapi/v1/ticker/price', symbol=symbol)['price'])
    notional = Decimal(rules['MIN_NOTIONAL']['notional'])
    quantity = rounded(budget / price, step, ROUND_FLOOR)
    if not minimum <= quantity <= maximum or quantity * price < notional:
        raise RuntimeError('Test order size does not meet the exchange limits')
    return quantity, Decimal(rules['PRICE_FILTER']['tickSize'])


def market_order(client, symbol, side, quantity, order_id, *, closing=False):
    params = {'reduceOnly': 'true'} if closing else {}
    return client.signed('POST', ORDER, symbol=symbol, side=side, type='MARKET',
                         quantity=format(quantity, 'f'), newClientOrderId=order_id,
                         newOrderRespType='RESULT', **params)


def cleanup(client, symbol, run_id, order_ids):
    amount = position(client, symbol)
    if amount < 0:
        raise RuntimeError('Unexpected short demo position; inspect the account before retrying')
    if amount:
        market_order(client, symbol, 'SELL', amount, run_id + '-close', closing=True)
    if position(client, symbol):
        raise RuntimeError('Demo position still open; existing protection has been left in place')
    active = client.signed('GET', OPEN_ALGOS, symbol=symbol)
    for order in active:
        if order['clientAlgoId'] in order_ids:
            client.signed('DELETE', ALGO, clientAlgoId=order['clientAlgoId'])
    remaining = client.signed('GET', OPEN_ALGOS, symbol=symbol)
    if any(order['clientAlgoId'] in order_ids for order in remaining):
        raise RuntimeError('Demo protective orders remain open; inspect the account before retrying')


def verify_orders(client, symbol, budget):
    if client.signed('GET', '/fapi/v1/positionSide/dual')['dualSidePosition'] is not False:
        raise RuntimeError('Use one-way mode on a dedicated Binance Demo account')
    if (position(client, symbol)
            or client.signed('GET', '/fapi/v1/openOrders', symbol=symbol)
            or client.signed('GET', OPEN_ALGOS, symbol=symbol)):
        raise RuntimeError('Use a demo symbol with no existing position or orders')

    quantity, tick = order_size(client, symbol, budget)
    run_id = 'cc-test-' + uuid4().hex[:16]
    stop_id, profit_id = run_id + '-sl', run_id + '-tp'
    print(f'Binance Demo test {run_id} ({symbol})', flush=True)
    try:
        entry = market_order(client, symbol, 'BUY', quantity, run_id + '-entry')
        if entry['status'] != 'FILLED' or Decimal(entry['executedQty']) != quantity:
            raise RuntimeError('Demo entry did not fill in full')
        price = Decimal(entry['avgPrice'])
        if not price.is_finite() or price <= 0:
            raise RuntimeError('Invalid demo entry price')
        exits = (
            (stop_id, 'STOP_MARKET', rounded(price * Decimal('0.99'), tick, ROUND_CEILING)),
            (profit_id, 'TAKE_PROFIT_MARKET', rounded(price * Decimal('1.04'), tick, ROUND_CEILING)),
        )
        if not 0 < exits[0][2] < price < exits[1][2]:
            raise RuntimeError('Rounded protective prices do not bracket the entry')
        for client_id, kind, trigger in exits:
            client.signed('POST', ALGO, algoType='CONDITIONAL', symbol=symbol, side='SELL',
                          type=kind, triggerPrice=format(trigger, 'f'), quantity=format(quantity, 'f'),
                          reduceOnly='true', workingType='MARK_PRICE', clientAlgoId=client_id)
        active = client.signed('GET', OPEN_ALGOS, symbol=symbol)
        expected = {(order_id, kind, trigger) for order_id, kind, trigger in exits}
        confirmed = {(row['clientAlgoId'], row['orderType'], Decimal(row['triggerPrice']))
                     for row in active if row['algoStatus'] == 'NEW' and row['reduceOnly'] is True}
        if not expected <= confirmed:
            raise RuntimeError('Binance Demo did not report both protective orders as active')
    finally:
        cleanup(client, symbol, run_id, {stop_id, profit_id})
    print('Demo entry filled, stop-loss and take-profit confirmed active, and test position and orders cleared.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--symbol', choices=('SOLUSDT', 'BSBUSDT'), required=True)
    parser.add_argument('--notional', type=Decimal, required=True, help='Target demo order size in USDT')
    args = parser.parse_args()
    if not args.notional.is_finite() or not Decimal(0) < args.notional <= Decimal(50):
        parser.error('--notional must be greater than 0 and no more than 50 demo USDT')
    key, secret = os.getenv('CC_BINANCE_DEMO_API_KEY'), os.getenv('CC_BINANCE_DEMO_API_SECRET')
    if not key or not secret:
        parser.error('Set CC_BINANCE_DEMO_API_KEY and CC_BINANCE_DEMO_API_SECRET in the test environment')
    try:
        verify_orders(DemoClient(key, secret), args.symbol, args.notional)
    except Exception as error:
        message = str(error) if type(error) is RuntimeError else type(error).__name__
        parser.exit(1, f'Demo test failed: {message}\n')


if __name__ == '__main__':
    main()
