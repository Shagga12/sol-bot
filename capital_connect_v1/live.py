"""User-operated, single-account spot worker. Not imported by the demo worker.

No orders are sent by `check`. `run` requires explicit command-line activation.
This module must only be tested against injected fake transports by an agent.
"""
import argparse
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from decimal import Decimal as D, ROUND_DOWN
import fcntl
import hashlib
import hmac
import json
import os
import signal
import sqlite3
import threading
import time
from urllib.parse import urlencode
from urllib.request import Request, HTTPRedirectHandler, build_opener
from urllib.error import HTTPError

from .engine import SYMBOLS
from .strategy import evaluate


class Halt(RuntimeError):
    """No further orders may be attempted until the issue is resolved."""


def number(value, positive=False):
    try:
        result = D(str(value))
    except Exception:
        raise Halt('Missing or invalid numeric data') from None
    if not result.is_finite() or (positive and result <= 0):
        raise Halt('Missing or invalid numeric data')
    return result


def floor(value, step):
    return (number(value) / number(step, True)).to_integral_value(rounding=ROUND_DOWN) * number(step)


@dataclass(frozen=True)
class Config:
    environment: str
    symbol: str
    capital_usdt: str
    order_usdt: str
    daily_loss_usdt: str
    stop_loss_fraction: str
    take_profit_fraction: str
    slippage_percent: str

    def __post_init__(self):
        if self.environment not in ('testnet', 'mainnet') or self.symbol not in SYMBOLS:
            raise Halt('Choose testnet/mainnet and a supported USDT spot pair')
        for key in ('capital_usdt', 'order_usdt', 'daily_loss_usdt', 'stop_loss_fraction',
                    'take_profit_fraction', 'slippage_percent'):
            number(getattr(self, key), True)
        if not number(self.order_usdt) <= number(self.capital_usdt):
            raise Halt('Order budget exceeds allocated capital')
        if number(self.daily_loss_usdt) > number(self.capital_usdt):
            raise Halt('Daily loss limit exceeds allocated capital')
        if not 0 < number(self.stop_loss_fraction) < 1 or not 0 < number(self.take_profit_fraction) < 1:
            raise Halt('Stop and profit fractions must be between zero and one')
        slip = number(self.slippage_percent)
        if not D('.01') <= slip <= 10 or floor(slip, '.01') != slip:
            raise Halt('Slippage percent must be 0.01–10 with at most two decimals')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Bybit:
    READS = {'/v5/user/query-api', '/v5/order/spot-borrow-check', '/v5/account/fee-rate',
             '/v5/order/realtime', '/v5/order/history', '/v5/execution/list'}
    PUBLIC = {'/v5/market/tickers', '/v5/market/kline', '/v5/market/instruments-info'}

    def __init__(self, config, key, secret, allow_orders=False, opener=None, inspection_only=False):
        self.config = config
        self.key = key.strip() if isinstance(key, str) else key
        self.secret = secret.strip() if isinstance(secret, str) else secret
        self.allow_orders = allow_orders
        if inspection_only and allow_orders:
            raise Halt('Inspection transport cannot enable orders')
        self.inspection_only = inspection_only
        self.non_spot_permissions = {}
        self.base = {'testnet': 'https://api-testnet.bybit.com', 'mainnet': 'https://api.bybit.com'}[config.environment]
        self.opener = opener or build_opener(NoRedirect)

    def request(self, path, params=None, write=False):
        params = params or {}
        if write:
            if not self.allow_orders or path not in ('/v5/order/create','/v5/order/cancel'):
                raise Halt('Order submission is disabled')
            if path == '/v5/order/cancel':
                if (set(params) != {'category','symbol','orderId','orderFilter'} or
                        params.get('category') != 'spot' or params.get('symbol') != self.config.symbol or
                        not isinstance(params.get('orderId'),str) or not params['orderId'] or
                        params.get('orderFilter') not in ('Order','tpslOrder','StopOrder')):
                    raise Halt('Unexpected cancellation parameters')
            # No transfers, withdrawals, leverage or arbitrary order payloads.
            elif (params.get('category') != 'spot' or params.get('symbol') != self.config.symbol
                    or params.get('isLeverage') != 0 or params.get('orderFilter') != 'Order'
                    or params.get('orderType') != 'Limit' or params.get('timeInForce') != 'IOC'
                    or params.get('side') not in ('Buy', 'Sell')):
                raise Halt('Unexpected order parameters')
            payload = json.dumps(params, separators=(',', ':'))
        elif path in self.READS | self.PUBLIC:
            payload = urlencode(params)
        else:
            raise Halt('Unsupported endpoint')
        headers = {'Content-Type': 'application/json'}
        if write or path in self.READS:
            if not self.key or not self.secret:
                raise Halt('Credentials are not configured')
            if self.key == self.secret:
                raise Halt('API key and secret are identical; check the saved credential fields')
            if self.secret.startswith('-----BEGIN'):
                raise Halt('RSA private key detected; this worker currently supports system-generated HMAC keys only')
            if any(c.isspace() for c in self.key + self.secret):
                raise Halt('Internal whitespace detected in credentials; check saved formatting')
            timestamp = str(int(time.time() * 1000))
            signature = hmac.new(self.secret.encode(),
                (timestamp + self.key + '5000' + payload).encode(), hashlib.sha256).hexdigest()
            headers.update({'X-BAPI-API-KEY': self.key, 'X-BAPI-SIGN': signature,
                            'X-BAPI-TIMESTAMP': timestamp, 'X-BAPI-RECV-WINDOW': '5000'})
        request = Request(self.base + path + (('?' + payload) if payload and not write else ''),
                          data=payload.encode() if write else None, headers=headers,
                          method='POST' if write else 'GET')
        try:
            with self.opener.open(request, timeout=10) as response:
                data = json.load(response)
        except HTTPError as error:
            raise Halt('Exchange HTTP rejection; status=' + str(error.code)) from None
        except Exception:
            # Do not print signed requests, secrets or raw exchange response bodies.
            raise Halt('Exchange request failed; reconcile any pending order before continuing') from None
        if data.get('retCode') != 0:
            raise Halt('Exchange rejected request; code=' + str(data.get('retCode')))
        server_ms = number(data.get('time'), True)
        if abs(server_ms - D(str(time.time())) * 1000) > 5000:
            raise Halt('Exchange response is stale or system clock is incorrect')
        if not isinstance(data.get('result'), dict):
            raise Halt('Malformed exchange response')
        return data['result']

    def identity(self):
        info = self.request('/v5/user/query-api')
        permissions = info.get('permissions', {})
        if info.get('readOnly') != 0 or 'SpotTrade' not in permissions.get('Spot', []):
            raise Halt('A spot-trading API key is required')
        self.non_spot_permissions = {k:v for k,v in permissions.items() if k != 'Spot' and v}
        # Bybit labels this exact flag as Unified-account permission. Actual
        # ContractTrade/Options permissions remain forbidden, as do transfers.
        unexpected = {k:v for k,v in self.non_spot_permissions.items()
                      if not (k == 'Derivatives' and v == ['DerivativesTrade'])}
        self.permissions_compatible = not unexpected
        if unexpected and not self.inspection_only:
            raise Halt('Non-spot permissions enabled: ' + json.dumps(unexpected, sort_keys=True))
        if not info.get('userID'):
            raise Halt('Account identity not returned')
        return str(info['userID'])

    def one(self, path, **params):
        rows = self.request(path, {'category': 'spot', 'symbol': self.config.symbol, **params}).get('list')
        if not isinstance(rows, list) or len(rows) != 1 or rows[0].get('symbol') != self.config.symbol:
            raise Halt('Expected one matching spot instrument')
        return rows[0]

    def available(self, side):
        data = self.request('/v5/order/spot-borrow-check',
                            {'category': 'spot', 'symbol': self.config.symbol, 'side': side})
        if data.get('symbol') != self.config.symbol or data.get('side') != side:
            raise Halt('Unexpected availability response')
        # Never use maxTradeAmount/maxTradeQty: those can include borrowing.
        value = number(data.get('spotMaxTradeAmount' if side == 'Buy' else 'spotMaxTradeQty'))
        if value < 0:
            raise Halt('Invalid available amount')
        return value


class Journal:
    def __init__(self, path, config, uid):
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS live_meta (id INTEGER PRIMARY KEY CHECK(id=1), binding TEXT);
          CREATE TABLE IF NOT EXISTS live_position (id INTEGER PRIMARY KEY CHECK(id=1), qty TEXT, cost TEXT);
          CREATE TABLE IF NOT EXISTS live_orders (link TEXT PRIMARY KEY, created INTEGER, side TEXT,
            payload TEXT, terminal INTEGER NOT NULL DEFAULT 0, result TEXT, pnl TEXT NOT NULL DEFAULT '0', settled INTEGER);
          CREATE TABLE IF NOT EXISTS live_scans (bucket INTEGER PRIMARY KEY);
          CREATE TABLE IF NOT EXISTS live_days (day INTEGER PRIMARY KEY, equity TEXT);
        ''')
        binding = json.dumps({'uid': uid, 'config': asdict(config)}, sort_keys=True)
        self.db.execute('INSERT OR IGNORE INTO live_meta VALUES(1,?)', (binding,))
        if self.db.execute('SELECT binding FROM live_meta').fetchone()[0] != binding:
            self.db.close()
            raise Halt('Database belongs to a different account or configuration')
        self.db.execute("INSERT OR IGNORE INTO live_position VALUES(1,'0','0')")

    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def position(self):
        row = self.db.execute('SELECT qty,cost FROM live_position WHERE id=1').fetchone()
        return number(row['qty']), number(row['cost'])

    def pending(self):
        return self.db.execute('SELECT * FROM live_orders WHERE terminal=0 ORDER BY created').fetchall()

    def pnl(self, since=0):
        return sum((number(r[0]) for r in self.db.execute(
            'SELECT pnl FROM live_orders WHERE terminal=1 AND settled>=?', (since,))), D(0))

    def reserve(self, payload, now, bucket=None):
        with self.transaction():
            if self.pending():
                raise Halt('An unresolved order blocks new submissions')
            if bucket is not None:
                self.db.execute('INSERT INTO live_scans VALUES(?)', (bucket,))
            self.db.execute('INSERT INTO live_orders(link,created,side,payload) VALUES(?,?,?,?)',
                (payload['orderLinkId'], now, payload['side'], json.dumps(payload)))

    def settle(self, row, order, fills, symbol, now):
        expected_qty = number(order.get('cumExecQty'))
        expected_value = number(order.get('cumExecValue'))
        requested_qty = number(json.loads(row['payload'])['qty'], True)
        if expected_qty < 0 or expected_qty > requested_qty or expected_value < 0:
            raise Halt('Order execution exceeds recorded intent')
        qty = value = base_fee = quote_fee = D(0)
        seen = set()
        for fill in fills:
            if (fill.get('orderId') != order['orderId'] or fill.get('symbol') != symbol
                    or fill.get('side') != row['side'] or not fill.get('execId')
                    or fill['execId'] in seen or fill.get('execType') != 'Trade'):
                raise Halt('Unexpected or duplicate execution')
            seen.add(fill['execId'])
            qty += number(fill.get('execQty'), True)
            value += number(fill.get('execValue'), True)
            fee = number(fill.get('execFee'))
            currency = fill.get('feeCurrency')
            if fee and currency not in (symbol[:-4], 'USDT'):
                raise Halt('Fee currency requires manual reconciliation')
            if fill.get('extraFees'):
                raise Halt('Additional fees require manual reconciliation')
            if currency == symbol[:-4]:
                base_fee += fee
            elif currency == 'USDT':
                quote_fee += fee
        if qty != expected_qty or value != expected_value or qty < 0 or value < 0:
            raise Halt('Execution totals not yet reconciled')
        with self.transaction():
            if self.db.execute('SELECT terminal FROM live_orders WHERE link=?', (row['link'],)).fetchone()[0]:
                return
            owned, cost = self.position()
            pnl = D(0)
            if row['side'] == 'Buy':
                owned += qty - base_fee
                cost += value + quote_fee
            elif qty:
                removed = qty + base_fee
                if removed > owned or removed <= 0:
                    raise Halt('Sell exceeds bot-owned quantity')
                allocated_cost = cost * removed / owned
                pnl = value - quote_fee - allocated_cost
                owned -= removed
                cost -= allocated_cost
            if owned < 0 or cost < 0:
                raise Halt('Invalid reconciled holdings')
            self.db.execute('UPDATE live_position SET qty=?,cost=? WHERE id=1', (str(owned), str(cost)))
            self.db.execute('UPDATE live_orders SET terminal=1,result=?,pnl=?,settled=? WHERE link=?',
                (json.dumps({'orderId': order['orderId'], 'status': order['orderStatus'],
                             'executed_qty': str(qty), 'executed_value': str(value)}), str(pnl), now, row['link']))


class Worker:
    def __init__(self, config, exchange, journal):
        self.c, self.api, self.journal = config, exchange, journal

    def reconcile(self, now):
        for row in self.journal.pending():
            params = {'category': 'spot', 'symbol': self.c.symbol, 'orderLinkId': row['link']}
            rows = self.api.request('/v5/order/realtime', params).get('list', [])
            if not rows:
                rows = self.api.request('/v5/order/history', params).get('list', [])
            if len(rows) != 1:
                # An absent order after a timed-out POST is uncertain, never a reason to retry.
                raise Halt('Pending order not found; inspect Bybit before any further submission')
            order = rows[0]
            if (order.get('orderLinkId') != row['link'] or order.get('symbol') != self.c.symbol
                    or order.get('side') != row['side'] or not order.get('orderId')):
                raise Halt('Order identity mismatch')
            if order.get('orderStatus') not in ('Filled', 'Cancelled', 'Rejected', 'PartiallyFilledCanceled'):
                return False
            if now - row['created'] >= 6 * 86400:
                raise Halt('Pending order is too old for automatic reconciliation')
            fills, cursor, seen_cursors = [], '', set()
            while True:
                page = self.api.request('/v5/execution/list', {'category': 'spot',
                    'symbol': self.c.symbol, 'orderId': order['orderId'], 'limit': 100,
                    'startTime': (row['created'] - 60) * 1000, 'endTime': now * 1000,
                    **({'cursor': cursor} if cursor else {})})
                fills.extend(page.get('list', []))
                cursor = page.get('nextPageCursor')
                if not cursor:
                    break
                if cursor in seen_cursors or len(fills) > 10000:
                    raise Halt('Execution pagination could not complete')
                seen_cursors.add(cursor)
            self.journal.settle(row, order, fills, self.c.symbol, now)
        return not self.journal.pending()

    def snapshot(self):
        rules = self.api.one('/v5/market/instruments-info')
        if rules.get('status') != 'Trading' or rules.get('quoteCoin') != 'USDT':
            raise Halt('Spot pair is not trading')
        ticker = self.api.one('/v5/market/tickers')
        bid, ask = number(ticker.get('bid1Price'), True), number(ticker.get('ask1Price'), True)
        if bid > ask:
            raise Halt('Invalid quote spread')
        fee = number(self.api.one('/v5/account/fee-rate').get('takerFeeRate'))
        if not 0 <= fee < D('.1'):
            raise Halt('Unexpected fee rate')
        return rules, bid, ask, fee

    def payload(self, side, amount, rules, bid, ask, fee, now):
        lot = rules['lotSizeFilter']
        # A fixed-price IOC bounds the quote amount even if the market moves
        # between the quote read and submission. It may fill partly or not at all.
        slip = number(self.c.slippage_percent) / 100
        price = floor(ask * (1 + slip) if side == 'Buy' else bid * (1 - slip), rules['priceFilter']['tickSize'])
        if price <= 0:
            raise Halt('Rounded order price is invalid')
        qty = floor(amount / (price * (1 + fee)) if side == 'Buy' else amount,
                    lot['basePrecision'])
        if qty <= 0 or qty * price < number(lot['minOrderAmt'], True):
            raise Halt('Amount is below current spot minimum after rounding')
        if qty > number(lot['maxLimitOrderQty'], True):
            raise Halt('Amount exceeds exchange limit-order maximum')
        binding = self.journal.db.execute('SELECT binding FROM live_meta').fetchone()[0]
        seed = f'{binding}-{now}-{side}-{self.journal.db.execute("SELECT COUNT(*) FROM live_orders").fetchone()[0]}'
        link = 'cc-' + hashlib.sha256(seed.encode()).hexdigest()[:32]
        return {'category': 'spot', 'symbol': self.c.symbol, 'side': side,
                'orderType': 'Limit', 'timeInForce': 'IOC', 'price': format(price, 'f'), 'qty': format(qty, 'f'),
                'isLeverage': 0, 'orderFilter': 'Order', 'orderLinkId': link,
                }

    def submit(self, payload, now, bucket=None):
        # Commit intent to durable storage BEFORE the single network write.
        self.journal.reserve(payload, now, bucket)
        self.api.request('/v5/order/create', payload, write=True)
        # Acceptance is not a fill. Position changes only during reconciliation.
        return {'state': 'ORDER_PENDING', 'side': payload['side'], 'order_link_id': payload['orderLinkId']}

    def tick(self, now):
        if not self.reconcile(now):
            return {'state': 'WAIT', 'reason': 'order_pending'}
        rules, bid, ask, fee = self.snapshot()
        qty, cost = self.journal.position()
        # Retain both quantity and cost of untradeable dust; it is never written
        # off as profit. It can be combined with the next filled bot buy.
        tradable_position = qty and floor(qty, rules['lotSizeFilter']['basePrecision']) * bid >= number(rules['lotSizeFilter']['minOrderAmt'], True)
        if tradable_position:
            proceeds = qty * bid * (1 - number(self.c.slippage_percent) / 100) * (1 - fee)
            change = proceeds / cost - 1
            if change >= number(self.c.take_profit_fraction) or change <= -number(self.c.stop_loss_fraction):
                available = self.api.available('Sell')
                if available <= 0:
                    raise Halt('Bot-owned assets are locked or unavailable; inspect account')
                return self.submit(self.payload('Sell', min(qty, available), rules, bid, ask, fee, now), now)
            return {'state': 'WAIT', 'reason': 'position_open', 'net_return_estimate': str(change)}
        bucket = now // 900
        if self.journal.db.execute('SELECT 1 FROM live_scans WHERE bucket=?', (bucket,)).fetchone():
            return {'state': 'WAIT', 'reason': 'entry_already_checked'}
        # Loss limits apply to this bot's allocation, not unrelated wallet activity.
        capital = number(self.c.capital_usdt)
        free = min(self.api.available('Buy'), capital + self.journal.pnl() - cost)
        if free <= 0:
            raise Halt('Allocated capital exhausted')
        day = now // 86400
        self.journal.db.execute('INSERT OR IGNORE INTO live_days VALUES(?,?)', (day, str(capital + self.journal.pnl())))
        start = number(self.journal.db.execute('SELECT equity FROM live_days WHERE day=?', (day,)).fetchone()[0], True)
        daily_pnl = self.journal.pnl(day * 86400)
        if daily_pnl <= -number(self.c.daily_loss_usdt):
            return {'state': 'WAIT', 'reason': 'configured_daily_loss_limit'}
        # Stop-loss cooldown survives restarts; all exits use four-bucket cooldown.
        last_exit = self.journal.db.execute("SELECT MAX(settled) FROM live_orders WHERE side='Sell' AND terminal=1").fetchone()[0]
        if last_exit is not None and bucket - last_exit // 900 <= 4:
            return {'state': 'WAIT', 'reason': 'exit_cooldown'}
        candles = self.api.request('/v5/market/kline', {'category': 'spot', 'symbol': self.c.symbol,
                                                     'interval': '15', 'limit': 31}).get('list', [])
        closed = sorted((int(r[0]) // 1000, r[4]) for r in candles if int(r[0]) // 1000 + 900 <= now)
        closed = closed[-30:]
        expected = [(bucket - 30 + i) * 900 for i in range(30)]
        if [r[0] for r in closed] != expected:
            raise Halt('Thirty consecutive completed candles are required')
        decision = evaluate([r[1] for r in closed], free, daily_pnl, start, (ask-bid)/ask)
        if decision.action != 'DEMO_BUY':
            self.journal.db.execute('INSERT INTO live_scans VALUES(?)', (bucket,))
            return {'state': 'WAIT', 'reason': decision.reason}
        # Signal/risk checks remain shared with demo; sizing uses the owner's
        # explicit live ceiling, not the demo's fixed 10-USDT/10% sizing rule.
        budget = min(number(self.c.order_usdt), free)
        payload = self.payload('Buy', budget, rules, bid, ask, fee, now)
        return self.submit(payload, now, bucket)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('check', 'run', 'status'))
    parser.add_argument('--config', required=True)
    parser.add_argument('--db', required=True)
    parser.add_argument('--enable-orders', action='store_true')
    parser.add_argument('--acknowledge-real-money', action='store_true')
    args = parser.parse_args(argv)
    journal = None
    try:
        with open(args.config) as handle:
            config = Config(**json.load(handle))
        if args.command != 'run' and (args.enable_orders or args.acknowledge_real_money):
            raise Halt('Activation flags are only valid for run')
        if args.command == 'run' and (not args.enable_orders or
                (config.environment == 'mainnet' and not args.acknowledge_real_money)):
            raise Halt('Explicit activation flags are required; no orders submitted')
        api = Bybit(config, os.getenv('BYBIT_API_KEY'), os.getenv('BYBIT_API_SECRET'),
                    allow_orders=args.command == 'run', inspection_only=args.command == 'check')
        # One owner on one Linux host/filesystem only. Do not run replicas.
        with open(args.db + '.lock', 'a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise Halt('Another process owns this live database') from None
            uid = api.identity()
            journal = Journal(args.db, config, uid)
            worker = Worker(config, api, journal)
            if args.command == 'status':
                qty, cost = journal.position()
                print(json.dumps({'environment': config.environment, 'symbol': config.symbol,
                    'bot_owned_qty': str(qty), 'cost_usdt': str(cost), 'realized_pnl_usdt': str(journal.pnl()),
                    'pending_orders': len(journal.pending()), 'orders_submitted_by_this_command': 0}))
                return 0
            reconciled = worker.reconcile(int(time.time()))
            if args.command == 'check':
                if not reconciled or journal.pending():
                    raise Halt('Unresolved order; connection check cannot approve readiness')
                rules, bid, ask, fee = worker.snapshot()
                free = api.available('Buy')
                _, position_cost = journal.position()
                budget = min(number(config.order_usdt), free,
                    number(config.capital_usdt) + journal.pnl() - position_cost)
                if budget <= 0:
                    raise Halt('Allocated capital exhausted')
                planned = worker.payload('Buy', budget, rules, bid, ask, fee, int(time.time()))
                print(json.dumps({'environment': config.environment, 'symbol': config.symbol,
                    'connection_verified': True, 'available_spot_usdt': str(free),
                    'non_spot_permissions': getattr(api, 'non_spot_permissions', {}),
                    'spot_permission_check_passed': getattr(api, 'permissions_compatible', False),
                    'execution_approved': False,
                    'order_budget_ceiling_usdt': str(budget),
                    'buy_preview_qty': planned['qty'], 'pending_orders': len(journal.pending()),
                    'orders_submitted_by_this_command': 0, 'profitability_verified': False}))
                return 0
            stop = threading.Event()
            signal.signal(signal.SIGTERM, lambda *_: stop.set())
            signal.signal(signal.SIGINT, lambda *_: stop.set())
            while not stop.is_set():
                print(json.dumps(worker.tick(int(time.time()))), flush=True)
                stop.wait(5)
            return 0
    except (Halt, ValueError, TypeError, KeyError, OSError, sqlite3.Error) as error:
        message = str(error) if isinstance(error, Halt) else type(error).__name__
        print(json.dumps({'state': 'HALTED', 'reason': message,
            'action': 'Inspect Bybit orders and holdings; do not delete the journal or blindly retry.'}), flush=True)
        return 1
    finally:
        if journal is not None:
            journal.db.close()


if __name__ == '__main__':
    raise SystemExit(main())
