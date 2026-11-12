"""Durable PAPER ledger. No exchange client, credentials, or network requests.

Snapshots are cumulative simulated fills; fees must be quote-denominated USDT.
This is not an adapter for raw Bybit responses or a live trading engine.
"""
import json
import sqlite3
from decimal import Decimal, InvalidOperation

PAIRS = ('BTCUSDT', 'SOLUSDT', 'ETHUSDT', 'BNBUSDT')
TERMINAL = {'FILLED', 'CANCELLED', 'REJECTED'}


def amount(value):
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise ValueError('Invalid amount') from None
    if not result.is_finite() or result < 0:
        raise ValueError('Amounts must be finite and nonnegative')
    return result


class PaperLedger:
    def __init__(self, path):
        self.db = sqlite3.connect(path, isolation_level=None, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS account (id INTEGER PRIMARY KEY CHECK(id=1), cash TEXT NOT NULL);
        INSERT OR IGNORE INTO account VALUES (1, '20');
        CREATE TABLE IF NOT EXISTS positions (symbol TEXT PRIMARY KEY, qty TEXT NOT NULL, cost TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS orders (
          id TEXT PRIMARY KEY, symbol TEXT NOT NULL, side TEXT NOT NULL,
          requested TEXT NOT NULL, status TEXT NOT NULL,
          qty TEXT NOT NULL DEFAULT '0', quote TEXT NOT NULL DEFAULT '0',
          fee TEXT NOT NULL DEFAULT '0', pnl TEXT NOT NULL DEFAULT '0');
        ''')

    def close(self):
        self.db.close()

    def state(self):
        return {
            'mode': 'PAPER',
            'cash': self.db.execute('SELECT cash FROM account').fetchone()[0],
            'positions': [dict(r) for r in self.db.execute('SELECT * FROM positions ORDER BY symbol')],
            'orders': [dict(r) for r in self.db.execute('SELECT * FROM orders ORDER BY rowid')],
        }

    def create(self, order_id, symbol, side, requested):
        """Buy request = total USDT budget including fee. Sell request = base qty."""
        size = amount(requested)
        if not isinstance(order_id, str) or not order_id.strip() or len(order_id) > 64:
            raise ValueError('A unique order ID is required')
        if symbol not in PAIRS or side not in ('BUY', 'SELL') or size <= 0:
            raise ValueError('Invalid paper order')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            old = self.db.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone()
            if old:
                if (old['symbol'], old['side'], amount(old['requested'])) != (symbol, side, size):
                    raise ValueError('Order ID reused with different parameters')
            else:
                if self.db.execute("SELECT 1 FROM orders WHERE status NOT IN ('FILLED','CANCELLED','REJECTED')").fetchone():
                    raise ValueError('Reconcile the pending order first')
                if side == 'BUY':
                    available = amount(self.db.execute('SELECT cash FROM account').fetchone()[0])
                else:
                    p = self.db.execute('SELECT qty FROM positions WHERE symbol=?', (symbol,)).fetchone()
                    available = amount(p[0]) if p else Decimal(0)
                if size > available:
                    raise ValueError('Insufficient paper funds or position')
                self.db.execute('INSERT INTO orders(id,symbol,side,requested,status) VALUES(?,?,?,?,?)',
                                (order_id, symbol, side, str(size), 'PENDING'))
            self.db.execute('COMMIT')
        except Exception:
            self.db.execute('ROLLBACK')
            raise

    def reconcile(self, order_id, status, qty='0', quote='0', fee='0'):
        """Apply a cumulative PAPER snapshot once. Unknown outcomes remain pending.

        A missing response must never be converted to REJECTED or retried with a
        different order ID. Reconcile the same ID with its known fills instead.
        """
        if status not in TERMINAL | {'PENDING', 'PARTIAL', 'UNKNOWN'}:
            raise ValueError('Invalid order status')
        q, v, f = map(amount, (qty, quote, fee))
        if (q == 0) != (v == 0) or (q == 0 and f != 0):
            raise ValueError('Inconsistent fill amounts')
        if status == 'FILLED' and q == 0:
            raise ValueError('Filled order requires execution evidence')
        if status == 'REJECTED' and q != 0:
            raise ValueError('Rejected order cannot contain fills')
        if status == 'PARTIAL' and q == 0:
            raise ValueError('Partial order requires fills')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            o = self.db.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone()
            if o is None:
                raise ValueError('Unknown order ID')
            previous = tuple(amount(o[k]) for k in ('qty', 'quote', 'fee'))
            if o['status'] in TERMINAL and (status != o['status'] or (q, v, f) != previous):
                raise ValueError('Conflicting terminal snapshot')
            if any(a < b for a, b in zip((q, v, f), previous)):
                raise ValueError('Cumulative fills cannot decrease')
            dq, dv, df = (a-b for a, b in zip((q, v, f), previous))
            p = self.db.execute('SELECT * FROM positions WHERE symbol=?', (o['symbol'],)).fetchone()
            pq, cost = (amount(p['qty']), amount(p['cost'])) if p else (Decimal(0), Decimal(0))
            cash = amount(self.db.execute('SELECT cash FROM account').fetchone()[0])
            pnl = Decimal(o['pnl'])
            if o['side'] == 'BUY':
                if v+f > amount(o['requested']) or dv+df > cash:
                    raise ValueError('Fill exceeds paper budget including fees')
                cash -= dv+df
                pq += dq
                cost += dv+df
            else:
                if q > amount(o['requested']) or dq > pq or f > v:
                    raise ValueError('Fill exceeds position or fee exceeds proceeds')
                removed_cost = cost if dq == pq else (cost*dq/pq if pq else Decimal(0))
                cash += dv-df
                pnl += dv-df-removed_cost
                pq -= dq
                cost -= removed_cost
            self.db.execute('UPDATE account SET cash=? WHERE id=1', (str(cash),))
            self.db.execute('INSERT OR REPLACE INTO positions VALUES(?,?,?)', (o['symbol'], str(pq), str(cost)))
            self.db.execute('UPDATE orders SET status=?,qty=?,quote=?,fee=?,pnl=? WHERE id=?',
                            (status, str(q), str(v), str(f), str(pnl), order_id))
            self.db.execute('COMMIT')
        except Exception:
            self.db.execute('ROLLBACK')
            raise


if __name__ == '__main__':
    # Explicit paper-only smoke scenario, no keys and no exchange connection.
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as folder:
        ledger = PaperLedger(str(Path(folder) / 'paper.sqlite'))
        ledger.create('demo-buy', 'BTCUSDT', 'BUY', '10')
        ledger.reconcile('demo-buy', 'FILLED', '.0001', '9.99', '.01')
        ledger.create('demo-sell', 'BTCUSDT', 'SELL', '.0001')
        ledger.reconcile('demo-sell', 'FILLED', '.0001', '10.5', '.01')
        print(json.dumps(ledger.state(), indent=2))
        ledger.close()
