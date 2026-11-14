# Recorded-price comparison — 14 November 2026

Source: 152 consecutive 15-minute worker snapshots from Render logs, approximately 38 hours. Both strategies replayed from 1,000 USDT with 10 USDT maximum per position, starting without positions and warming up on the same prices.

| Per-side modeled cost | Original net P&L | Updated net P&L | Original maximum drawdown | Updated maximum drawdown |
|---|---:|---:|---:|---:|
| 0.1% | -1.6140 USDT | -0.9506 USDT | 0.2135% | 0.1487% |
| 0.2% | -1.9710 USDT | -1.2089 USDT | 0.2391% | 0.1644% |

At 0.1% costs, original: 18 closed trades, 5 winners; updated: 13 closed trades, 4 winners. Both ended flat.

Conclusion: lower losses in this short replay, neither profitable. This is not independent out-of-sample validation: some recorded observations predate the changes and were already inspected. Close-only execution misses intrabar stops, liquidity and actual fills. Drawdowns are measured against the entire 1,000 USDT account, most of which stays in cash. Results are replay results, not the existing deployed ledger's cumulative P&L. No evidence yet to support automatic real-money activation.

Reproduce: `python -m capital_connect_v1.backtest recorded-prices.csv`
