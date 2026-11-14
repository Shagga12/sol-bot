"""Persistent single-account paper ledger. Never sends exchange orders."""
import json
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal as D
from capital_connect_v1.engine import SYMBOLS
from capital_connect_v1.strategy import evaluate

INTERVAL = 900
FEE = D('0.001')  # Simulation assumption; not an exchange fee quote.
TAKE_PROFIT = D('0.01')
STOP_LOSS = D('0.01')
STOP_COOLDOWN_BUCKETS = 4
STRATEGY_VERSION = 'demo-trend-cooldown-v2'

class PaperLedger:
    def __init__(self, path, initial_cash='1000'):
        self.db = sqlite3.connect(path, timeout=30, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS account (id INTEGER PRIMARY KEY CHECK(id=1), cash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS samples (symbol TEXT, bucket INTEGER, price TEXT NOT NULL,
            PRIMARY KEY(symbol,bucket));
        CREATE TABLE IF NOT EXISTS positions (symbol TEXT PRIMARY KEY, entry TEXT, qty TEXT, cost TEXT);
        CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, ts INTEGER, symbol TEXT,
            action TEXT, reason TEXT, price TEXT, pnl TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS days (day TEXT PRIMARY KEY, equity TEXT NOT NULL);
        ''')
        cash = D(initial_cash)
        if not cash.is_finite() or cash <= 0:
            raise ValueError('Initial demo balance must be positive')
        self.db.execute('INSERT OR IGNORE INTO account VALUES (1,?)', (str(cash),))

    def close(self):
        self.db.close()

    def scan(self, prices, timestamp):
        """All symbols must have fresh prices from this scan. Atomic bucket deduplication."""
        if set(prices) != set(SYMBOLS):
            raise ValueError('A complete market snapshot is required')
        prices = {s: D(str(p)) for s, p in prices.items()}
        if any(not p.is_finite() or p <= 0 for p in prices.values()):
            raise ValueError('Invalid market price')
        bucket = int(timestamp) // INTERVAL
        day = datetime.fromtimestamp(timestamp, timezone.utc).date().isoformat()
        self.db.execute('BEGIN IMMEDIATE')
        try:
            latest = self.db.execute('SELECT MAX(bucket) FROM samples').fetchone()[0]
            if latest is not None and bucket <= latest:
                self.db.execute('ROLLBACK')
                return [{'action': 'WAIT', 'reason': 'duplicate_or_old_scan'}]
            cash = D(self.db.execute('SELECT cash FROM account WHERE id=1').fetchone()[0])
            equity = cash + sum((D(r['qty']) * prices[r['symbol']] for r in
                                 self.db.execute('SELECT * FROM positions')), D(0))
            self.db.execute('INSERT OR IGNORE INTO days VALUES (?,?)', (day, str(equity)))
            start_equity = D(self.db.execute('SELECT equity FROM days WHERE day=?', (day,)).fetchone()[0])
            midnight = int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp())
            pnl = sum((D(r[0]) for r in self.db.execute(
                'SELECT pnl FROM events WHERE ts>=? AND action=?', (midnight, 'DEMO_SELL'))), D(0))
            results = []
            for symbol in SYMBOLS:
                price = prices[symbol]
                self.db.execute('INSERT INTO samples VALUES (?,?,?)', (symbol, bucket, str(price)))
                rows = self.db.execute('SELECT bucket,price FROM samples WHERE symbol=? ORDER BY bucket DESC LIMIT 30',
                                       (symbol,)).fetchall()
                consecutive = 0
                for row in rows:
                    if row['bucket'] != bucket - consecutive:
                        break
                    consecutive += 1
                closes = [r['price'] for r in reversed(rows[:consecutive])]
                position = self.db.execute('SELECT * FROM positions WHERE symbol=?', (symbol,)).fetchone()
                action, reason, realized = 'WAIT', 'position_already_open', D(0)
                if position:
                    change = price / D(position['entry']) - 1
                    if change >= TAKE_PROFIT or change <= -STOP_LOSS:
                        proceeds = D(position['qty']) * price * (1 - FEE)
                        realized = proceeds - D(position['cost'])
                        cash += proceeds
                        pnl += realized
                        self.db.execute('DELETE FROM positions WHERE symbol=?', (symbol,))
                        action = 'DEMO_SELL'
                        reason = 'take_profit' if change >= TAKE_PROFIT else 'stop_loss'
                else:
                    # Spread is modeled as zero in this paper simulator, not measured.
                    decision = evaluate(closes, cash, pnl, start_equity, 0)
                    action, reason = decision.action, decision.reason
                    last_stop = self.db.execute(
                        "SELECT MAX(ts) FROM events WHERE symbol=? AND action='DEMO_SELL' AND reason='stop_loss'",
                        (symbol,)).fetchone()[0]
                    if (last_stop is not None and
                            bucket - int(last_stop) // INTERVAL <= STOP_COOLDOWN_BUCKETS):
                        action, reason = 'WAIT', 'stop_loss_cooldown'
                    if action == 'DEMO_BUY':
                        cost = decision.budget_usdt
                        qty = cost * (1 - FEE) / price
                        cash -= cost
                        self.db.execute('INSERT INTO positions VALUES (?,?,?,?)',
                                        (symbol, str(price), str(qty), str(cost)))
                self.db.execute('INSERT INTO events(ts,symbol,action,reason,price,pnl) VALUES (?,?,?,?,?,?)',
                                (int(timestamp), symbol, action, reason, str(price), str(realized)))
                results.append({'symbol': symbol, 'action': action, 'reason': reason, 'price': str(price),
                                'history_samples': consecutive, 'history_required': 30,
                                'warmup_remaining_minutes': max(0, 30-consecutive)*15})
            self.db.execute('UPDATE account SET cash=? WHERE id=1', (str(cash),))
            self.db.execute('DELETE FROM samples WHERE bucket<?', (bucket - 120,))
            self.db.execute('COMMIT')
            return results
        except Exception:
            self.db.execute('ROLLBACK')
            raise

    def status(self):
        cash = self.db.execute('SELECT cash FROM account WHERE id=1').fetchone()[0]
        positions = [dict(r) for r in self.db.execute('SELECT * FROM positions')]
        latest = self.db.execute('SELECT MAX(bucket) FROM samples').fetchone()[0]
        marks = {r['symbol']: D(r['price']) for r in self.db.execute(
            'SELECT symbol,price FROM samples WHERE bucket=?', (latest,))}
        marked_value = sum((D(r['qty'])*marks[r['symbol']]*(1-FEE) for r in positions), D(0))
        unrealized = marked_value - sum((D(r['cost']) for r in positions), D(0))
        trades = [dict(r) for r in self.db.execute(
            "SELECT * FROM events WHERE action != 'WAIT' ORDER BY id DESC LIMIT 100")]
        pnl = sum((D(r[0]) for r in self.db.execute("SELECT pnl FROM events WHERE action='DEMO_SELL'")), D(0))
        return {'name': 'Capital Connect', 'mode': 'DEMO', 'live_order_execution': False,
                'strategy_version': STRATEGY_VERSION,
                'strategy_validation': 'experimental; profitability not established',
                'cash_usdt': cash, 'realized_pnl_usdt': str(pnl),
                'estimated_liquidation_equity_usdt': str(D(cash)+marked_value),
                'unrealized_pnl_after_exit_fee_usdt': str(unrealized),
                'total_pnl_after_exit_fee_usdt': str(pnl+unrealized),
                'valuation_timestamp': latest*INTERVAL if latest is not None else None,
                'commission_estimate_usdt': str(max(D(0), pnl) * D('0.10')),
                'positions': positions,
                'recent_trades': trades, 'interval_seconds': INTERVAL,
                'fee_assumption_per_side': str(FEE), 'spread_model': 'zero; not measured',
                'last_decisions': [dict(r) for r in self.db.execute('SELECT * FROM events ORDER BY id DESC LIMIT 4')]}
