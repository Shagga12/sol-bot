# Capital Connect: proposed strategy for Ron's review

Status: simulation proposal only. Not activated, deployed, backtested, or approved for live trading. Prepared November 12, 2026. The developer-selected numbers below are illustrative test settings, not evidence of suitability, profitability, or a promise to limit losses.

## Proposed rules

| Item | Proposed test setting |
| --- | --- |
| Market | Bybit BTC/USDT spot only; no margin, leverage, futures, borrowing or withdrawals |
| Entry signal | On completed 15-minute candles, the average of the latest 20 closes crosses from at/below to above the average of the latest 50 closes |
| History | At least 51 consecutive completed candles; no future or incomplete candle data |
| Position limit | One bot-owned position; no averaging down and no second entry on the same signal candle |
| Profit signal | Estimated proceeds after exit fees are at least 2% above the fee-adjusted position cost |
| Loss signal | Estimated proceeds after exit fees fall to 1% below the fee-adjusted position cost |
| Additional exit | Bearish crossover of the same moving averages |
| Entry frequency | At most two new entries per local day; no trade is required if there is no signal |
| Daily pause | Pause new entries after realized losses total 2% of the test allocation; maintain exit monitoring for an existing position |
| Entry spread | Wait when the bid/ask spread exceeds 0.2% |
| Failures | Pause new orders for stale prices, unresolved submissions, inconsistent fills or missing account information |
| Simulation allocation | 5.50 simulated USDT. This does not reserve or spend actual funds |
| Live allocation | Unset. Must be confirmed against a fresh spendable account balance and current exchange minimums before any possible activation |
| Fees | 0.1% exit fee is a simulation assumption only; actual account fee tier and fee currency must be checked |
| Commission | Display an estimate of 10% of positive realized net profit only; do not collect or transfer any fee |

The latest screenshots showed 5.5241 USDT in Unified and 1.2000 USDT in Funding after withdrawals. These are historical observations, not a verified current balance. No further deposit or transfer is requested. The earlier 20 USDT software ceiling must not be mistaken for available capital.

The daily reset timezone is intended to be America/Tortola. A worker must persist daily counts, loss totals and consumed signal timestamps before this rule can operate reliably across restarts. The present pure evaluator receives those values; it does not maintain the clock or persistence itself.

## How the exit calculation works

The strategy compares fee-adjusted cost with current bid proceeds less the assumed exit fee. It does not simply compare the chart price with the buy price. Buy fees charged in BTC reduce the quantity held; sell fees charged in USDT reduce proceeds. Fees in another currency stay unpriced and prevent a final net-profit commission estimate.

For scale only: 2% of a 5.50 USDT cost is 0.11 USDT before the separate 10% commission estimate. A 1% loss threshold is 0.055 USDT. Neither amount is guaranteed. The required chart-price move differs because of fees and execution costs.

## What losses remain possible

A stop threshold is a trigger to seek an exit, not a guaranteed execution price or guaranteed maximum loss. A gap, outage, missing liquidity, exchange limit, partial fill, or rejected exit can leave an asset unsold. An IOC limit order can cancel without completing its intended exit. A 15-minute entry schedule is not adequate continuous protection for an open position by itself.

Bybit-hosted protective orders, or an independently verified continuously running exit monitor, still need design and integration before live use. A free service that sleeps cannot be relied upon as the only stop monitor. The software must verify whether protective orders exist and reconcile any partial/manual fills, not merely display a stop percentage.

A small balance can also produce a sell below the exchange's minimum notional after fees, rounding, or a price decline. The system must skip an unsafe entry or stop for manual review; it must not borrow or increase the order amount to force a trade. An allocated spot position can lose most or all of its value. There is no promised return.

## Completed and tested

- Durable client IDs and submission records; no automatic resend after an uncertain outcome.
- Read-only final-fill reconciliation and actual fee currency handling.
- Fee-adjusted bot-owned positions, buy/sell cost accounting and realized P&L.
- Offline buy and sell size checks, no-short-sale checks, and reservation limits.
- The proposed simulation-only crossover/exit evaluator and decision tests.
- 111 unit, control-flow and integration fixture tests pass. No exchange order was sent in testing. No real-market historical backtest or profitability evaluation has been completed.

## Remaining before a possible live setup

- Backtest the strategy without look-ahead and forward-test against real market data, including realistic fees, spread, slippage and partial fills.
- Build one durable cloud worker, authenticated owner controls, daily state, pause/recovery handling and independent exit protection.
- Verify current Bybit account eligibility, key permissions, spendable funds, actual fee tier and instrument filters from the intended host.
- Reconcile external account changes and any existing/manual/protective orders.
- Review the exact live parameters and the remaining risks with Ron. A generic approval of this development task does not activate an order, trade, or bot.

The private Capital Connect website and current Render services have not been changed by this proposal. Existing keys remain unchanged. No automatic real trading has been enabled.

## Official references checked

- https://www.bybit.com/en/help-center/article/Bybit-Spot-Fees-Explained
- https://www.bybit.com/en/help-center/article/Introduction-to-Take-Profit-and-Stop-Loss-Spot-Trading
- https://bybit-exchange.github.io/docs/v5/market/instrument
- https://bybit-exchange.github.io/docs/v5/order/create-order
- https://bybit-exchange.github.io/docs/v5/order/execution

## Historical-data test status

A 90-day public-data test was attempted and FAILED from the current workspace: Bybit public data could not be downloaded (HTML Site Unavailable response). No real historical performance is available. The standalone strategy_backtest.py can run on an eligible computer without API keys, saving a JSON report. It does not place orders or activate the bot. Next-bar execution, fees, adverse execution assumptions, exchange minimums, open positions and dust are represented; historical spread, liquidity and continuous stop performance remain unverified. The test must not be reported as successful merely because the fixture suite passes.
