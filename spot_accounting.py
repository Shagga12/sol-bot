"""Bot-owned positions from verified final receipts; not an exchange wallet.

No network access, initial balance, order execution, or commission collection.
Third-currency fees remain unpriced; realized profit/commission are provisional.
"""
import json
import sqlite3
from decimal import Decimal, InvalidOperation


class AccountingError(ValueError): pass


def num(value, signed=False):
    try: d = Decimal(str(value))
    except InvalidOperation: raise AccountingError('Invalid receipt amount') from None
    if not d.is_finite() or (d < 0 and not signed):
        raise AccountingError('Nonfinite or negative receipt amount')
    return d


class SpotAccounting:
    def __init__(self, connection):
        self.db = connection
        self.db.execute('''CREATE TABLE IF NOT EXISTS bot_positions (
            symbol TEXT PRIMARY KEY, qty TEXT NOT NULL, cost TEXT NOT NULL, reserved TEXT NOT NULL)''')
        self.db.execute('''CREATE TABLE IF NOT EXISTS accounted_receipts (
            client_id TEXT PRIMARY KEY, receipt TEXT NOT NULL, pnl TEXT NOT NULL)''')
        self.db.execute('''CREATE TABLE IF NOT EXISTS accounted_executions (
            execution_id TEXT PRIMARY KEY, client_id TEXT NOT NULL)''')
        self.db.execute('''CREATE TABLE IF NOT EXISTS unpriced_fees (
            client_id TEXT NOT NULL, currency TEXT NOT NULL, amount TEXT NOT NULL,
            PRIMARY KEY(client_id,currency))''')

    def position(self, symbol):
        row = self.db.execute('SELECT qty,cost,reserved FROM bot_positions WHERE symbol=?', (symbol,)).fetchone()
        return tuple(map(Decimal, row)) if row else (Decimal(0), Decimal(0), Decimal(0))

    def committed(self):
        return sum((Decimal(r[0]) for r in self.db.execute('SELECT reserved FROM bot_positions')), Decimal(0))

    def apply(self, receipt, *, buy_reserve='0'):
        # Must be part of the caller's immediate transaction so intent status,
        # execution deduplication, position and cost all commit or roll back together.
        if not self.db.in_transaction:
            raise AccountingError('Accounting requires a surrounding database transaction')
        if receipt.get('final') is not True or receipt.get('consistent') is not True:
            raise AccountingError('A verified final receipt is required')
        symbol, client_id, side = receipt.get('symbol'), receipt.get('client_id'), receipt.get('side')
        if symbol not in {'BTCUSDT','SOLUSDT','ETHUSDT','BNBUSDT'} or not client_id or side not in {'Buy','Sell'}:
            raise AccountingError('Unsupported receipt identity')
        encoded = json.dumps(receipt, sort_keys=True, separators=(',', ':'), allow_nan=False)
        old = self.db.execute('SELECT receipt FROM accounted_receipts WHERE client_id=?',(client_id,)).fetchone()
        if old:
            if old[0] != encoded: raise AccountingError('Conflicting previously accounted receipt')
            return
        q, value, reservation = num(receipt.get('filled_qty')), num(receipt.get('filled_value_usdt')), num(buy_reserve)
        if (q == 0) != (value == 0): raise AccountingError('Inconsistent receipt totals')
        execution_ids = receipt.get('execution_ids')
        fees = receipt.get('fees_by_currency')
        if (not isinstance(execution_ids, list) or any(not isinstance(x,str) or not x for x in execution_ids)
                or len(execution_ids) != len(set(execution_ids)) or (q > 0 and not execution_ids)
                or (q == 0 and execution_ids) or not isinstance(fees,dict)):
            raise AccountingError('Complete unique executions and fee currencies are required')
        fees = {k:num(v, signed=True) for k,v in fees.items()}
        if any(not isinstance(k,str) or not k.isalnum() for k in fees):
            raise AccountingError('Invalid fee currency')
        if q == 0 and any(fees.values()): raise AccountingError('Zero-fill receipt has fees')
        for execution_id in execution_ids:
            try: self.db.execute('INSERT INTO accounted_executions VALUES(?,?)',(execution_id,client_id))
            except sqlite3.IntegrityError:
                raise AccountingError('Execution is already assigned to another receipt') from None
        base_fee = fees.get(symbol[:-4],Decimal(0))
        quote_fee = fees.get('USDT',Decimal(0))
        pq, cost, reserved = self.position(symbol)
        pnl = Decimal(0)
        if q:
            if side == 'Buy':
                net_qty, added_cost = q-base_fee, value+quote_fee
                if net_qty <= 0 or added_cost <= 0 or added_cost > reservation:
                    raise AccountingError('Invalid fee-adjusted buy')
                pq += net_qty
                cost += added_cost
                reserved += reservation
            else:
                consumed, proceeds = q+base_fee, value-quote_fee
                if consumed <= 0 or consumed > pq or proceeds < 0:
                    raise AccountingError('Sell exceeds the bot-owned fee-adjusted position')
                removed_cost = cost if consumed == pq else cost*consumed/pq
                removed_reserve = reserved if consumed == pq else reserved*consumed/pq
                pq -= consumed
                cost -= removed_cost
                reserved -= removed_reserve
                pnl = proceeds-removed_cost
            self.db.execute('INSERT OR REPLACE INTO bot_positions VALUES(?,?,?,?)',
                            (symbol,str(pq),str(cost),str(reserved)))
        for currency, fee in fees.items():
            if currency not in {symbol[:-4],'USDT'} and fee:
                self.db.execute('INSERT INTO unpriced_fees VALUES(?,?,?)',(client_id,currency,str(fee)))
        self.db.execute('INSERT INTO accounted_receipts VALUES(?,?,?)',(client_id,encoded,str(pnl)))

    def report(self):
        pnl = sum((Decimal(r[0]) for r in self.db.execute('SELECT pnl FROM accounted_receipts')), Decimal(0))
        missing = [{'client_id':r[0],'currency':r[1],'amount':r[2]}
                   for r in self.db.execute('SELECT client_id,currency,amount FROM unpriced_fees ORDER BY rowid')]
        return {'source':'BOT_VERIFIED_RECEIPTS_ONLY', 'is_wallet_balance':False,
                'positions':[{'symbol':r[0],'qty':r[1],'cost_usdt':r[2],'reserved_usdt':r[3]}
                             for r in self.db.execute('SELECT * FROM bot_positions ORDER BY symbol')],
                'realized_pnl_usdt_before_unpriced_fees':str(pnl), 'unpriced_fees':missing,
                'commission_estimate_usdt':None if missing else str(max(pnl,Decimal(0))*Decimal('.10')),
                'commission_charged':False}
