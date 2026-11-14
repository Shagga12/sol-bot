"""Offline comparison using chronological, complete 15-minute CSV snapshots.
Usage: python -m capital_connect_v1.backtest prices.csv
Columns: timestamp (Unix seconds), BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT.
Close-only replay cannot model intrabar stops, liquidity or actual fills.
"""
import argparse
import csv
import json
from decimal import Decimal as D
from unittest.mock import patch
from capital_connect_v1 import paper
from capital_connect_v1.engine import SYMBOLS
from capital_connect_v1.strategy import evaluate, Decision


def baseline(closes, cash, pnl, equity, spread):
    # Original entry rule; same validation, sizing and daily loss checks.
    result = evaluate(closes, cash, pnl, equity, spread)
    if result.reason == 'trend_not_confirmed':
        return Decision('DEMO_BUY', 'moving_average_signal', min(D('10'), D(str(cash))*D('.10')))
    return result


def load_snapshots(path):
    snapshots = []
    previous = None
    with open(path, newline='') as source:
        for row in csv.DictReader(source):
            ts = int(row['timestamp'])
            if ts % 900 or (previous is not None and ts != previous + 900):
                raise ValueError('Require consecutive, aligned 15-minute snapshots')
            prices = {symbol: D(row[symbol]) for symbol in SYMBOLS}
            if any(not price.is_finite() or price <= 0 for price in prices.values()):
                raise ValueError('Require positive finite prices')
            snapshots.append((ts, prices))
            previous = ts
    if len(snapshots) < 31:
        raise ValueError('Insufficient data: need at least 31 snapshots; longer history is required for evaluation')
    return snapshots


def replay(snapshots, original=False, execution_cost='0.001'):
    cost = D(execution_cost)
    if not cost.is_finite() or not 0 <= cost < 1:
        raise ValueError('Invalid per-side execution cost')
    ledger = paper.PaperLedger(':memory:')
    peak = D('1000')
    drawdown = D(0)
    try:
        with patch.object(paper, 'evaluate', baseline if original else evaluate), patch.object(paper, 'STOP_COOLDOWN_BUCKETS', -1 if original else 4), patch.object(paper, 'FEE', cost):
            for ts, prices in snapshots:
                ledger.scan(prices, ts)
                cash = D(ledger.db.execute('SELECT cash FROM account').fetchone()[0])
                # Estimate liquidation value, including a final sell-side cost.
                equity = cash + sum((D(r['qty'])*prices[r['symbol']]*(1-cost) for r in ledger.db.execute('SELECT * FROM positions')), D(0))
                peak = max(peak, equity)
                drawdown = max(drawdown, (peak-equity)/peak)
        sells = [D(r[0]) for r in ledger.db.execute("SELECT pnl FROM events WHERE action='DEMO_SELL'")]
        return {'net_liquidation_pnl_usdt': str(equity-D('1000')), 'maximum_drawdown_pct': str(drawdown*100), 'closed_trades': len(sells), 'winning_trades': sum(p>0 for p in sells), 'open_positions': ledger.db.execute('SELECT COUNT(*) FROM positions').fetchone()[0]}
    finally:
        ledger.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv')
    args = parser.parse_args()
    snapshots = load_snapshots(args.csv)
    results = {'limitations': 'Close-only replay; no intrabar fills; no proof of live profitability. Evaluate on untouched periods.', 'snapshots': len(snapshots), 'comparisons': {}}
    for cost in ('0.001', '0.002'):
        results['comparisons'][cost] = {name: replay(snapshots, original, cost) for name, original in (('original', True), ('trend_cooldown_v2', False))}
    print(json.dumps(results, indent=2))

if __name__ == '__main__':
    main()
