"""Read-only Bybit spot order reconciliation; never submits or cancels orders.

A submission acknowledgement is not a fill. Match the stable client order ID,
fetch all executions, and require totals to agree before calling a result final.
No private response is sent to the paper ledger (its quote-only fee model differs).
"""
from decimal import Decimal, InvalidOperation
import json
import re
import sqlite3
from diagnostics import ConnectionError, get

PAIRS = {'BTCUSDT', 'SOLUSDT', 'ETHUSDT', 'BNBUSDT'}
TERMINAL = {'Filled', 'Cancelled', 'PartiallyFilledCanceled', 'Rejected', 'Deactivated'}
KNOWN = TERMINAL | {'New', 'PartiallyFilled', 'Untriggered', 'Triggered'}


def dec(value, signed=False):
    try:
        n = Decimal(str(value))
    except InvalidOperation:
        raise ConnectionError('Invalid execution amount') from None
    if not n.is_finite() or (not signed and n < 0):
        raise ConnectionError('Invalid execution amount')
    return n


def rows(endpoint, params, key, secret, fetch):
    result, seen = [], set()
    query = dict(params, limit=100 if endpoint == '/v5/execution/list' else 50)
    for _ in range(100):
        page = fetch(endpoint, query, key, secret)
        if not isinstance(page, dict) or not isinstance(page.get('list'), list):
            raise ConnectionError('Incomplete order history response')
        result.extend(page['list'])
        cursor = page.get('nextPageCursor', '')
        if not cursor:
            return result
        if not isinstance(cursor, str) or cursor in seen:
            raise ConnectionError('Order history cursor did not advance')
        seen.add(cursor)
        query = dict(query, cursor=cursor)
    raise ConnectionError('Order history pagination limit reached; outcome unresolved')


def reconcile(symbol, client_id, key, secret, *, start_ms, end_ms, fetch=get):
    if symbol not in PAIRS or not isinstance(client_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,36}', client_id):
        raise ValueError('Invalid pair or client order ID')
    if not key or not secret:
        raise ConnectionError('Both private credential settings are required')
    if (type(start_ms) is not int or type(end_ms) is not int
            or not 0 <= start_ms < end_ms or end_ms-start_ms > 7*24*60*60*1000):
        raise ValueError('Supply an explicit execution window of at most seven days')
    identity = dict(category='spot', symbol=symbol, orderLinkId=client_id)
    orders = rows('/v5/order/realtime', identity, key, secret, fetch)
    if not orders:
        orders = rows('/v5/order/history', dict(identity, startTime=start_ms, endTime=end_ms), key, secret, fetch)
    if not orders:
        return {'symbol': symbol, 'client_id': client_id, 'outcome': 'UNKNOWN',
                'final': False, 'reason': 'No matching order evidence; do not resubmit blindly'}
    if len(orders) != 1:
        raise ConnectionError('Ambiguous order identity; outcome unresolved')
    order = orders[0]
    if (order.get('symbol') != symbol or order.get('orderLinkId') != client_id
            or not order.get('orderId') or order.get('side') not in ('Buy', 'Sell')):
        raise ConnectionError('Order identity does not match the requested spot order')
    status = order.get('orderStatus')
    if status not in KNOWN:
        raise ConnectionError('Unrecognised order status; outcome unresolved')
    # A bounded query must include this order's entire lifetime, otherwise older
    # fills could be silently excluded from the receipt.
    try:
        created, updated = int(order['createdTime']), int(order['updatedTime'])
    except (KeyError, TypeError, ValueError):
        raise ConnectionError('Order timestamps missing') from None
    if not start_ms <= created <= updated <= end_ms:
        raise ConnectionError('Execution window does not cover the complete order lifetime')
    executions = rows('/v5/execution/list', dict(category='spot', symbol=symbol,
                      orderId=order['orderId'], startTime=start_ms, endTime=end_ms), key, secret, fetch)
    unique, fees = {}, {}
    qty, value = Decimal(0), Decimal(0)
    for fill in executions:
        if (fill.get('symbol') != symbol or fill.get('orderId') != order['orderId']
                or fill.get('side') != order['side'] or fill.get('execType') != 'Trade'):
            raise ConnectionError('Execution identity or type mismatch')
        execution_id = fill.get('execId')
        if not isinstance(execution_id, str) or not execution_id:
            raise ConnectionError('Execution ID missing')
        canonical = {k: fill.get(k) for k in ('orderId','symbol','side','execType','execQty','execValue','execFee','feeCurrency','execTime')}
        if execution_id in unique:
            if unique[execution_id] != canonical:
                raise ConnectionError('Conflicting duplicate execution')
            continue
        unique[execution_id] = canonical
        try:
            fill_time = int(fill['execTime'])
        except (KeyError, TypeError, ValueError):
            raise ConnectionError('Execution time missing') from None
        if not created <= fill_time <= updated:
            raise ConnectionError('Execution outside order lifetime')
        q, v, fee = dec(fill.get('execQty')), dec(fill.get('execValue')), dec(fill.get('execFee'), signed=True)
        if q <= 0 or v <= 0:
            raise ConnectionError('Execution must contain positive filled quantity and value')
        currency = fill.get('feeCurrency')
        if not isinstance(currency, str) or not re.fullmatch(r'[A-Za-z0-9]{1,32}', currency):
            raise ConnectionError('Fee currency missing; cannot infer it from trade side')
        fees[currency] = fees.get(currency, Decimal(0)) + fee
        qty += q
        value += v
    expected_qty, expected_value = dec(order.get('cumExecQty')), dec(order.get('cumExecValue'))
    consistent = qty == expected_qty and value == expected_value
    if status == 'Filled' and qty == 0:
        consistent = False
    if status in ('Rejected', 'Deactivated') and qty != 0:
        consistent = False
    return {'symbol': symbol, 'client_id': client_id, 'order_id': order['orderId'],
            'outcome': status, 'final': status in TERMINAL and consistent,
            'consistent': consistent, 'side': order['side'], 'updated_ms': updated,
            'filled_qty': str(qty), 'filled_value_usdt': str(value),
            'fees_by_currency': {k: str(v) for k, v in sorted(fees.items())},
            'execution_ids': sorted(unique),
            'reason': 'Verified execution totals' if consistent else 'Order and execution totals disagree; refresh before taking any action'}


class ReceiptJournal:
    """Durable audit receipts only; not a spendable balance or a trading ledger."""
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS receipts (receipt TEXT PRIMARY KEY)')
        self.db.commit()

    def save(self, receipt):
        encoded = json.dumps(receipt, sort_keys=True, separators=(',', ':'), allow_nan=False)
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO receipts VALUES (?)', (encoded,))

    def all(self):
        return [json.loads(row[0]) for row in self.db.execute('SELECT receipt FROM receipts ORDER BY rowid')]

    def close(self):
        self.db.close()
