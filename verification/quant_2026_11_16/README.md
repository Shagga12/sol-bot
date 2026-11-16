# Quant verification — 2026-11-16 UTC

Verdict: software checks pass; profitability validation fails for this research strategy and sample. Do not describe it as a proven profitable AI system.

Tested source: `1841934c9bddc1d1ad0fc73fc931abc77c50697a`.

## Checks performed

- Ran the deployed revision locally: all 102 unit tests passed. Exchange objects in these local tests are mocks; they are not new authenticated Bybit exchange tests.
- Independent streaming backtest matched the existing implementation on 100 deterministic randomized paths (25,000 intervals) and 3,000 actual historical candles.
- Future-price shock tests preserved all earlier signals; NaN, infinity, zero and negative price checks passed.
- Confirmed Quant research/backtest modules exist in deployed source, but live order decisions still call `strategy.evaluate`. These Quant modules have no execution call sites. There is no trained machine-learning model; the confidence number is an uncalibrated moving-average spread score.
- Latest worker deploy `dep-dbt6h40ae00c739qiad0` was live, and runtime logs reported STOPPED during verification. No deploy, Start, cancel, or exchange write was performed for this verification.

## Data integrity and method

Downloaded official Bitstamp BTC/USD OHLC via https://www.bitstamp.net/api/v2/ohlc/btcusd/ at 900-second intervals. Period: 2025-01-01 00:00 through 2025-12-31 23:45 UTC. All 35,040 expected candles present; no missing intervals. Overlapping API pages returned 3,860 identical duplicates, deduplicated with conflicts rejected. OHLC prices were checked positive, finite and internally consistent.

Canonical downloaded JSON SHA-256: `0a02b1749f9f3969c4aacde507e9984ababbd4e4ed48d2a61f4a284fccc84ab6`.

The initial third-party minute file had missing timestamps and was rejected for this test. Direct Bybit data access returned an unavailable HTML page, so these are BTC/USD proxy results, not Bybit BTC/USDT execution validation.

Used existing defaults unchanged: fast 10, slow 30, volatility ceiling 0.04, trend spread threshold 0.002. No parameter tuning. Signals use only completed past candles. Compared the original same-close model with next-candle-open fills. Positions alternate between all cash and all BTC; this is not the personal bot's 15-USDT order sizing. Research-only, long-only simulation with terminal liquidation cost included. WAIT preserves the prior position. Costs are an assumed proportional fee plus execution-cost allowance, charged per side; actual exchange fee rates were not retrieved.

## Full-year results

| Per-side modeled cost | Same-close net return | Next-open net return | Next-open maximum drawdown |
| --- | ---: | ---: | ---: |
| 0.10% | -26.91% | -27.42% | 35.64% |
| 0.20% | -61.42% | -61.69% | 64.66% |
| 0.30% | -79.65% | -79.79% | 80.62% |

At 0.10% per side, the next-open simulation completed 319 round trips and buy-and-hold returned -6.64% net over the corresponding window. Turnover costs substantially eroded results. At 0.20% per side, all four independently restarted quarterly simulations lost money: Q1 -24.85%, Q2 -17.29%, Q3 -14.94%, Q4 -29.46%. Do not compound these reset-quarter numbers to reproduce the uninterrupted annual run.

## Limitations and outstanding work

The current backtest omits the live worker's exchange-held 1% stop / 4% take-profit, daily entry loss limit, 15-USDT order ceiling, exchange minimums, bid/ask spread path, partial fills, latency and protective-order reconciliation. Close-to-close drawdown can miss worse intrabar drawdowns. Terminal liquidation cost is added by the audit, not the existing backtest module. A future evaluation of a combined Quant/protection strategy must explicitly model these and use untouched data periods. This test does not establish the safety or profitability of the separate existing live bot, and does not confirm any currently held Bybit position or protective order.

## Reproduce

From this repository checkout, with Python 3.10+:

```bash
python -m unittest discover -s tests -q
python verification/quant_2026_11_16/check_invariants.py
python verification/quant_2026_11_16/fetch_official.py
python verification/quant_2026_11_16/run_audit.py
```

The downloader and audit use temporary `/tmp/quant-official-btcusd-2025.json` and `/tmp/quant-audit-results.json`. No credentials required. Source API data may be corrected later; compare integrity counts and the recorded hash when reproducing.
