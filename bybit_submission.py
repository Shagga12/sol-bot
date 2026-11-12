"""Unwired spot BUY/SELL submission component. Disabled by default; not an auto bot.

No CLI or dashboard calls this module. Tests inject a fake transport. Production
activation, strategy and worker integration are separate work.
"""
import hashlib
import hmac
import json
import re
import sqlite3
import time
import urllib.request
from decimal import Decimal, InvalidOperation
from spot_accounting import SpotAccounting

PAIRS = {'BTCUSDT', 'SOLUSDT', 'ETHUSDT', 'BNBUSDT'}
CAP = Decimal('20')


class SubmissionError(Exception):
    pass


def positive(value):
    try:
        n = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise SubmissionError('Invalid numeric order field') from None
    if not n.is_finite() or n <= 0:
        raise SubmissionError('Numeric order fields must be finite and positive')
    return n


def validate(plan):
    if not isinstance(plan, dict) or plan.get('mode') != 'PLAN_ONLY':
        raise SubmissionError('An offline validated plan is required')
    p = plan.get('payload', {})
    expected = {'category','symbol','side','orderType','timeInForce','isLeverage','qty','price','orderLinkId'}
    if set(p) != expected:
        raise SubmissionError('Unexpected order fields')
    if (p['category'] != 'spot' or p['symbol'] not in PAIRS or p['side'] not in {'Buy','Sell'}
            or p['orderType'] != 'Limit' or p['timeInForce'] != 'IOC'
            or type(p['isLeverage']) is not int or p['isLeverage'] != 0):
        raise SubmissionError('Only unleveraged spot limit-IOC orders are supported')
    if not isinstance(p['orderLinkId'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,36}', p['orderLinkId']):
        raise SubmissionError('Invalid stable client order ID')
    qty, price = positive(p['qty']), positive(p['price'])
    if p['side'] == 'Sell':
        try: base_reserve = Decimal(str(plan.get('base_fee_reserve')))
        except InvalidOperation: raise SubmissionError('Invalid base fee reserve') from None
        if not base_reserve.is_finite() or base_reserve < 0:
            raise SubmissionError('Invalid base fee reserve')
        return dict(p), Decimal(0)
    reserve = positive(plan.get('maximum_quote_with_fee_reserve'))
    try:
        fee = Decimal(str(plan.get('fee_reserve_usdt')))
    except InvalidOperation:
        raise SubmissionError('Invalid fee reserve') from None
    if not fee.is_finite() or fee < 0 or reserve != qty*price+fee or reserve > CAP:
        raise SubmissionError('Inconsistent or excessive reserved allocation')
    return dict(p), reserve


class BybitSpotWriter:
    """Explicitly enabled writer, never constructed automatically by the app."""
    def __init__(self, key, secret, *, enabled=False, opener=None, clock=time.time):
        self.key, self.secret, self.enabled = key, secret, enabled
        self.clock = clock
        # An HTTP redirect must not forward signed headers or replay the POST.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        self.opener = opener if opener is not None else urllib.request.build_opener(NoRedirect)

    def submit(self, payload):
        if self.enabled is not True:
            raise SubmissionError('Live submission is disabled')
        if not self.key or not self.secret:
            raise SubmissionError('Both server-side credentials are required')
        notional = positive(payload.get('qty')) * positive(payload.get('price'))
        validate({'mode': 'PLAN_ONLY', 'payload': payload,
                  'maximum_quote_with_fee_reserve': str(notional), 'fee_reserve_usdt': '0', 'base_fee_reserve':'0'})
        body = json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False)
        stamp = str(int(self.clock()*1000))
        sig = hmac.new(self.secret.encode(), (stamp+self.key+'5000'+body).encode(), hashlib.sha256).hexdigest()
        request = urllib.request.Request('https://api.bybit.com/v5/order/create', data=body.encode(),
                    method='POST', headers={'Content-Type':'application/json', 'Accept':'application/json',
                    'X-BAPI-API-KEY':self.key, 'X-BAPI-TIMESTAMP':stamp,
                    'X-BAPI-RECV-WINDOW':'5000', 'X-BAPI-SIGN':sig})
        # No network retries, domain fallback, redirects or exception text with secrets.
        try:
            with self.opener.open(request, timeout=10) as response:
                if not 200 <= response.status < 300:
                    raise ValueError('Unexpected HTTP status')
                result = json.load(response)
        except Exception:
            raise SubmissionError('Submission outcome is unknown; reconcile the same client ID') from None
        if not isinstance(result, dict):
            raise SubmissionError('Invalid acknowledgement; reconcile the same client ID')
        if type(result.get('retCode')) is not int or result['retCode'] != 0:
            raise SubmissionError('Exchange did not acknowledge acceptance; reconcile the same client ID')
        return result.get('result', {})


class SubmissionJournal:
    def __init__(self, path):
        self.db = sqlite3.connect(path, isolation_level=None, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute('''CREATE TABLE IF NOT EXISTS submissions (
          client_id TEXT PRIMARY KEY, payload TEXT NOT NULL, initial_reserve TEXT NOT NULL, reserve TEXT NOT NULL,
          state TEXT NOT NULL, order_id TEXT, receipt TEXT)''')
        self.accounting = SpotAccounting(self.db)
        if self.db.execute("SELECT 1 FROM submissions s LEFT JOIN accounted_receipts a ON s.client_id=a.client_id WHERE s.state='FINAL' AND a.client_id IS NULL").fetchone():
            self.db.close()
            raise SubmissionError('Older final receipts require accounting migration before submission')

    def close(self):
        self.db.close()

    def entries(self):
        return [dict(r) for r in self.db.execute('SELECT * FROM submissions ORDER BY rowid')]

    def claim(self, plan):
        payload, reserve = validate(plan)
        encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        client_id = payload['orderLinkId']
        self.db.execute('BEGIN IMMEDIATE')
        try:
            old = self.db.execute('SELECT * FROM submissions WHERE client_id=?', (client_id,)).fetchone()
            if old:
                if old['payload'] != encoded or Decimal(old['initial_reserve']) != reserve:
                    raise SubmissionError('Client ID cannot be reused with a different plan')
                self.db.execute('COMMIT')
                return False, dict(old)
            if self.db.execute("SELECT 1 FROM submissions WHERE state != 'FINAL'").fetchone():
                raise SubmissionError('Resolve the outstanding submission before any new order')
            if payload['side'] == 'Sell':
                available = self.accounting.position(payload['symbol'])[0]
                if Decimal(payload['qty'])+Decimal(str(plan['base_fee_reserve'])) > available:
                    raise SubmissionError('Sell exceeds bot-owned position including fee reserve')
            committed = self.accounting.committed()
            if committed+reserve > CAP:
                raise SubmissionError('Journal allocation ceiling reached; reconcile positions before proceeding')
            # Persist first, then send exactly once. Even a crash before the send
            # leaves an UNKNOWN intent that needs explicit reconciliation.
            self.db.execute('INSERT INTO submissions VALUES(?,?,?,?,?,?,?)',
                            (client_id, encoded, str(reserve), str(reserve), 'UNKNOWN', None, None))
            self.db.execute('COMMIT')
            return True, {'client_id': client_id, 'payload': encoded, 'state': 'UNKNOWN'}
        except Exception:
            if self.db.in_transaction:
                self.db.execute('ROLLBACK')
            raise

    def acknowledge(self, client_id, result):
        if (not isinstance(result, dict) or not isinstance(result.get('orderId'), str)
                or not result['orderId'] or result.get('orderLinkId') != client_id):
            raise SubmissionError('Acknowledgement identity mismatch; submission remains UNKNOWN')
        with self.db:
            self.db.execute("UPDATE submissions SET state='ACKNOWLEDGED',order_id=? WHERE client_id=? AND state='UNKNOWN'",
                            (result['orderId'], client_id))

    def finish(self, receipt):
        """Apply a verified read-only reconciliation receipt, never an HTTP ack."""
        if receipt.get('final') is not True or receipt.get('consistent') is not True:
            raise SubmissionError('A complete verified final receipt is required')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row = self.db.execute('SELECT * FROM submissions WHERE client_id=?', (receipt.get('client_id'),)).fetchone()
            if row is None:
                raise SubmissionError('No matching local intent')
            payload = json.loads(row['payload'])
            if (receipt.get('symbol') != payload['symbol'] or receipt.get('side') != payload['side']
                    or (row['order_id'] and receipt.get('order_id') != row['order_id'])
                    or not isinstance(receipt.get('order_id'), str) or not receipt['order_id']):
                raise SubmissionError('Receipt identity does not match intent')
            try:
                qty = Decimal(receipt['filled_qty'])
                value = Decimal(receipt['filled_value_usdt'])
            except (KeyError, InvalidOperation, TypeError):
                raise SubmissionError('Receipt amount missing') from None
            if (not qty.is_finite() or not value.is_finite() or qty < 0 or value < 0
                    or qty > Decimal(payload['qty'])
                    or (payload['side'] == 'Buy' and value > qty*Decimal(payload['price']))
                    or (payload['side'] == 'Sell' and value < qty*Decimal(payload['price']))
                    or (qty == 0) != (value == 0)):
                raise SubmissionError('Receipt exceeds the submitted limit or quantity')
            status = receipt.get('outcome')
            if status not in {'Filled','Cancelled','PartiallyFilledCanceled','Rejected','Deactivated'}:
                raise SubmissionError('Nonterminal receipt')
            if status == 'Filled' and qty != Decimal(payload['qty']):
                raise SubmissionError('Filled receipt does not cover requested quantity')
            if status in {'Rejected','Deactivated'} and qty != 0:
                raise SubmissionError('Rejected intent cannot contain executions')
            encoded = json.dumps(receipt, sort_keys=True, separators=(',', ':'), allow_nan=False)
            if row['state'] == 'FINAL' and row['receipt'] != encoded:
                raise SubmissionError('Conflicting final receipt')
            self.accounting.apply(receipt, buy_reserve=row['initial_reserve'])
            # Open buys retain their reservation in the position ledger. Sells
            # release the matching proportional cost/reserve atomically.
            reserve = '0' if qty == 0 or payload['side'] == 'Sell' else row['reserve']
            self.db.execute("UPDATE submissions SET state='FINAL',reserve=?,order_id=?,receipt=? WHERE client_id=?",
                            (reserve, receipt['order_id'], encoded, receipt['client_id']))
            self.db.execute('COMMIT')
        except Exception:
            if self.db.in_transaction:
                self.db.execute('ROLLBACK')
            raise


def submit_once(plan, journal, writer, *, activated=False):
    """Not wired to app/worker. Caller must separately refresh account/preflight.

    Disabling prevents both network access and creation of a submission intent.
    Duplicate IDs are never resent, including after timeouts or process restarts.
    """
    if activated is not True:
        raise SubmissionError('Submission coordinator is not activated')
    claimed, entry = journal.claim(plan)
    if not claimed:
        return {'client_id': entry['client_id'], 'state': entry['state'], 'resent': False}
    payload = json.loads(entry['payload'])
    try:
        result = writer.submit(payload)
        journal.acknowledge(payload['orderLinkId'], result)
    except Exception:
        # Never propagate transport exceptions that may include signed headers.
        return {'client_id': payload['orderLinkId'], 'state': 'UNKNOWN', 'resent': False}
    return {'client_id': payload['orderLinkId'], 'state': 'ACKNOWLEDGED', 'resent': False}
