# Quantitative system ideas for Capital Connect

Research date: November 12, 2026. Ideas for design and testing, not instructions to trade or evidence that a strategy is profitable.

| Source | Useful idea | Capital Connect status / application |
| --- | --- | --- |
| QuantConnect Algorithm Framework | Separate signal generation, position sizing, risk adjustment and execution | Existing draft separates signals, offline size checks, accounting and disabled submission. A persistent runtime to connect them is unfinished. Keep a clear explanation of which layer blocked each proposed trade. |
| Freqtrade backtesting | Compare strategies on the same historical data with entry and exit fees included; retain detailed results and assumptions | Standalone Bybit historical downloader/replay now exists; the actual 90-day attempt FAILED because data was inaccessible from this workspace. No performance is claimed. |
| Freqtrade lookahead analysis | Detect accidental use of future prices in historical signals | Current replay executes a previous completed-bar signal on the next bar open. Additional out-of-sample and bias checks are still required. |
| Freqtrade protections | Entry cooldowns, stop-loss guards and drawdown-based pauses | Existing pure signal evaluator has daily entry/loss limits and a duplicate-candle guard. A persistent after-loss cooldown and portfolio drawdown guard are ideas to test, not implemented cloud features. |
| Hummingbot Strategy V2 / Grid Strike | Manage each order workflow as a bounded executor with explicit lifecycle and risk parameters | Reuse the lifecycle concept rather than adopting a multi-order grid immediately. The current journal distinguishes UNKNOWN, ACKNOWLEDGED and verified FINAL, while partial/failed orders remain reconciled. Multi-order allocation is not implemented. |

## Concrete research direction

Keep the BTC/USDT crossover proposal as a baseline for simulation. Compare any additional rule or protection against that unchanged baseline, using the same dates, fees and execution assumptions. Record trade count, net return, maximum drawdown, blocked orders, exit failures and open dust positions. Reserve a later time period for evaluation instead of tuning parameters against every available candle. Do not select a strategy merely because it has the highest historical return.

A range/grid system would require splitting capital across multiple orders and handling inventory and minimum trade sizes. That is a separate design from the current one-position proposal; no grid or martingale has been enabled. The historical 5.5241 USDT balance is not a verified current balance, and neither a larger deposit nor a subscription to these frameworks is required by this research.

## Exact status

- 111 code/fixture tests pass.
- The real historical-data download FAILED; historical_test_result.json explicitly reports live_trading_ready=false.
- None of these external frameworks has been installed, connected to credentials, or used to activate live trading.
- Current cloud integration, eligibility/balance verification and protective-exit work remain unfinished.

## Primary sources

- https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/overview
- https://www.freqtrade.io/en/stable/backtesting/
- https://www.freqtrade.io/en/stable/lookahead-analysis/
- https://www.freqtrade.io/en/stable/plugins/#protections
- https://hummingbot.org/blog/strategy-guide-grid-strike/
