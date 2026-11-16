# Protected Quant readiness — 2026-11-16 UTC

**Status: STRATEGY_REWORK_REQUIRED.** Risk-model code is prepared and tested; this candidate is not ready for live activation. All tested annual cost scenarios and all independently restarted quarters lost money. No parameters were optimized against these periods. No live strategy, exchange order, deployment or owner configuration was changed.

## What was implemented

`capital_connect_v1/quant_risk_backtest.py` combines the existing research Quant signal with an offline model of the owner's saved limits:

| Setting | Value |
| --- | --- |
| Allocated quote capital | 56 |
| Maximum order cost including quote entry fee | 15 |
| Daily realized-loss entry cutoff | 10 |
| Stop fraction | 1% |
| Take-profit fraction | 4% |
| Entry slippage ceiling | 0.10% |
| Reentry cooldown | Four complete 15-minute buckets after any exit |

Uses the existing production `attach_protection` calculation for fee-adjusted, tick-rounded trigger prices. Uses only the preceding 31 completed closes for each next-open entry. One protected position at a time; Quant sell candidates do not race an attached bracket. Quantity is rounded down and minimum order notional checked. Stops that gap through the trigger receive the worse opening price plus assumed exit slippage. A known opening gap is evaluated before later bar extremes; otherwise if both triggers are touched, the stop is chosen. Daily cutoff stops further entries and does not cancel protections. Open holdings are marked to hypothetical liquidation value including exit costs.

All 114 local unit tests pass, including 12 new tests for past-only signals, bounded sizing, protection triggers, double-trigger bars, gap losses, gap ordering, cooldown, UTC daily resets, invalid OHLC/gaps/duplicates, minimum order blocking, open-position liquidation costs and invalid execution assumptions. These are offline/mocked checks, not fresh Bybit exchange orders.

## Historical results

Official Bitstamp BTC/USD OHLC, 900-second cadence, all expected aligned candles present with no missing intervals: 35,136 in 2024 and 35,040 in 2025. Overlapping equal records deduplicated; conflicting duplicates rejected. Raw dataset hashes and all summary results are in `results.json`. The downloader rejects missing intervals at evaluation time and the simulator validates OHLC. The earlier third-party file with gaps is not used.

Baseline: 0.10% fee per side, 0.10% entry ceiling, 0.10% adverse exit slippage, assumed price tick 0.1, quantity step 0.000001 and minimum order 5 quote units. These are explicit simulation assumptions, not current Bybit instrument/fee verification.

| Period | Ending liquidation value from 56 | Net return | Maximum modeled drawdown | Closed trades | Winning trades |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2024 | 37.0969 | -33.76% | 35.17% | 462 | 67 |
| 2025 | 33.2948 | -40.55% | 41.89% | 367 | 43 |

Baseline win rates: 14.50% in 2024 and 11.72% in 2025. Average winning trade approximately 0.60 quote units; average losing trade approximately -0.15. Profit factor: 0.679 and 0.531 respectively. Full baseline simulated fills are saved in `trades_2024_baseline.csv` and `trades_2025_baseline.csv`.

With exit slippage increased to 0.20%, returns were -46.11% and -50.31%. With fees also increased to 0.20% per side, returns were -91.08% and -88.10%; minimum order rules eventually blocked entries in the 2024 stress run. Increasing the fee assumption changes fee-adjusted trigger levels, so this stress case changes trigger incidence as well as costs. All eight baseline quarterly reset runs also lost money. Independently reset quarters should not be compounded to reproduce uninterrupted annual results.

## Readiness and limitations

The saved result never approves live activation or claims authenticated exchange validation. It records the historical positivity check separately; all annual scenarios must be positive for that narrow check to pass. Even a passing positivity check would not establish future profitability or authorize execution.

These BTC/USD proxy simulations are not Bybit BTC/USDT fills or losses in Ron's wallet. The model assumes entry fills at the bounded worst-case price; it does not reproduce available liquidity, IOC partial fills, rejected/unfilled orders, spread paths, fee tier/currency changes, base-fee dust, latency, outages or exchange-held child-order discovery. Fees are modeled in quote currency. OHLC cannot determine the actual sequence within a bar, so ambiguous bars use the adverse outcome. Exit slippage is an assumption, not a guaranteed bound. Open-position drawdown uses the intrabar low net of exit costs, but real drawdowns may differ. The existing live strategy still uses `strategy.evaluate`; this research candidate is not wired to it and is not a trained machine-learning model.

Before considering activation, the strategy needs revision and evaluation on additional untouched periods, followed by integration and authenticated exchange validation of the exact candidate, current fees/instrument constraints and protective-order reconciliation. No such validation is claimed here. Existing unit tests protect against software regressions; they do not create an economic trading edge.

## Reproduce

From the repository root with Python 3.10+:

```bash
python -m unittest discover -s tests -q
python verification/quant_protected_2026_11_16/fetch_official.py --year 2024
python verification/quant_protected_2026_11_16/fetch_official.py --year 2025
python verification/quant_protected_2026_11_16/run.py
```

Requires public Bitstamp data access only; no API keys. Downloads are written to `/tmp/quant-official-btcusd-YEAR.json`. The runner writes summary results and baseline fill CSVs beside this document, and complete scenario fill JSONs under `/tmp`. Source data can be corrected later; compare saved hashes and candle counts.
