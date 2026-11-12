# Capital Connect bot repair

This branch is an undeployed repair draft. It does not enable live trading.

## Completed

- Removed substitute prices, hardcoded balance, and order placement from the diagnostic dashboard.
- Added read-only credential and Unified balance checks plus a desktop popup checker.
- Added paper_engine.py: SQLite-backed paper account starting with 20 simulated USDT, four supported pairs, unique order IDs, a single pending order, cumulative fill reconciliation, fee-inclusive cash and position cost tracking, and realized net P&L.
- Unknown order outcomes remain unresolved and block new orders. Failed sells preserve holdings. Duplicate requests and snapshots do not debit twice. Terminal contradictions stop processing.
- All ledger mutations use SQLite immediate transactions. Decimal text storage avoids binary float money arithmetic.

## Validation

Run `python -m unittest discover -v`: 111 tests pass, including restart recovery, duplicate fills, rejected sells, partial/cancelled fills, rollback, competing connections, and the 20 USDT initial budget. Run `python paper_engine.py` for a temporary simulated buy/sell scenario; its prices and profit are fixtures, not market results.

## Order checks and read-only execution receipts

spot_preflight.py builds an offline limit-IOC buy plan with a 20 USDT total allocation ceiling, explicit fee reserve, price/balance freshness checks, quantity precision, exchange minimum notional, and maximum quantity checks. It does not submit the plan. Instrument filters and balances in tests are fixtures, not current exchange values. A fee reserve is not a guarantee about real fee rates or denomination.

order_reconciliation.py queries matching spot orders and every execution page using GET requests. It falls back to order history when realtime evidence is absent, retains UNKNOWN for missing evidence, checks the full order lifetime is covered, validates identities, deduplicates fills, and requires executed totals to agree before identifying a terminal result as final. Fees remain separated by their actual asset currency (including base assets and rebates). ReceiptJournal saves audit receipts idempotently; these are not spendable-balance records or trading authorizations.

The private diagnostic dashboard now includes client-order-ID lookup behind its existing password and read-only key check. Set BOT_RECEIPT_DB to a persistent mounted database path to retain audit receipts. With no path, it explicitly reports display-only mode. No automatic order submission, retries, or cancellation is exposed. The lookup window is at most seven days, must cover the entire order lifetime, and does not claim to support historical orders beyond that window.

Documentation used:
- https://bybit-exchange.github.io/docs/v5/market/instrument
- https://bybit-exchange.github.io/docs/v5/order/create-order
- https://bybit-exchange.github.io/docs/v5/order/open-order
- https://bybit-exchange.github.io/docs/v5/order/execution

## Submission component (unwired and disabled)

bybit_submission.py now contains a signed Bybit spot limit-IOC BUY/SELL transport and a durable submission coordinator. The transport is disabled by default. The coordinator also requires explicit activation; neither is called by app.py or any deployed worker. Tests use fake credentials and injected fake transports only.

The coordinator persists UNKNOWN before invoking the writer, never resends a previously claimed client ID, blocks a second unresolved intent, and distinguishes ACKNOWLEDGED from a verified final execution receipt. It keeps filled/partial capital reserved, releases only proven zero-fill intents, and checks the aggregate reserved ceiling of 20 USDT. This is a ceiling, not a claim that the owner still has 20 USDT available. The integration fixture uses 5.5241 USDT available and a 5.50 USDT plan, not actual funds.

The writer signs the exact JSON bytes sent, uses only the documented mainnet endpoint, disables redirects, never retries writes, and sanitizes uncertain outcomes. It now supports sells against bot-owned positions and receipt-based position/cost accounting. Credential/region eligibility checks, refreshed runtime inputs, and a strategy remain unfinished. No existing UI or worker can activate it. Do not wire it into a live application until those missing pieces are integrated and verified. Its separate SQLite journal must be hosted durably before production use.

An end-to-end fixture test covers planning, acknowledgement, partial-fill cancellation, base-currency fees, receipt verification, and restart without resubmission. There was no authenticated live exchange test and no production deployment.

## Remaining before live operation

The paper ledger has no exchange order adapter, automation strategy, or live execution switch. Do not feed raw Bybit messages into its simulation snapshot API. The submission journal now integrates verified receipts with fee-adjusted positions and stable client IDs. A production runtime still must refresh account eligibility and spendable balances, detect external account changes, and apply an owner-approved trading strategy. Durable hosting needs a persistent database, a single execution worker, private authentication, and operational pause/recovery controls. No SQLite file on ephemeral Render storage should be treated as durable production state.

The owner confirmed moving 20 USDT into Unified Trading. Authentication succeeded locally with a read-only key; authenticated Render connectivity remains unverified. This branch has not changed either existing Render deployment or the private Capital Connect site. Main remains unchanged.

Do not enable trading permissions or restart the legacy trading dashboard on the strength of these simulation tests. No real order was placed during this repair.

Latest owner screenshots showed 5.5241 USDT in Unified and 1.2000 USDT in Funding after a withdrawal. Do not assume the original 20 USDT is still available or treat the paper initial balance as real capital. No fresh authenticated cloud balance check has been performed.

Dashboard authentication/lookup control flow is covered with a Streamlit stub. app.py and connection modules compile. Streamlit is not installed in the test runtime, so browser rendering and a real hosted lookup have not been verified in this session.

## Verified position accounting and sell cycle

spot_accounting.py tracks only bot-owned assets derived from verified final execution receipts. Base-asset buy fees reduce held quantity. Quote fees affect cost/proceeds; base-asset sell fees consume additional holdings. Partial sells release proportional cost and reserved capital. Duplicate receipts/executions cannot alter balances twice. Unknown third-currency fees remain explicitly unpriced; net-profit commission estimates are suppressed until those fees can be valued. The 10% figure is only an estimate and never a debit or payout.

The submission journal updates intent status, positions, execution IDs, and realized P&L in one immediate SQLite transaction. Sells cannot exceed bot-owned holdings. Failed sells leave positions intact. A fully verified close releases the matching capital reservation, allowing reuse within the original software ceiling. An older database with finalized receipts but no accounting history is rejected and requires a reviewed migration; it must not silently start with empty positions.

plan_sell validates current spendable and bot-owned quantities separately, base-fee reserve, lot precision, minimum notional, maximum size, and source freshness. Dust remains unsold rather than increasing the order to satisfy a minimum. Tests cover the complete simulated buy, fee deduction, sell, realized P&L, restart, no resubmission, and allocation reuse. These tests do not validate live pricing, real balances, or cloud operation.

Remaining operational blockers: no owner-approved automatic strategy is integrated; no durable production worker is wired to this code; no current authenticated Render balance/permission/eligibility check has passed. The old sol-bot screenshot showed no environment variables. Do not add keys to the old service or treat its Deploy status as evidence that the repaired bot is running.

## Strategy proposal checkpoint

STRATEGY_REVIEW.md and strategy_proposal.json contain an unapproved, unbacktested BTCUSDT-only simulation proposal: closed 15-minute 20/50 SMA crossover entry, estimated net +2% / -1% exits, bearish-crossover exit, one position, at most two entries daily, and a daily new-entry pause after 2% realized losses. strategy_signals.py implements a pure evaluator with stale-data, unresolved-order, pause and duplicate-candle guards. It has no network or execution imports and always reports permits_live_order=false. Live allocation is unset and live activation is false. Thresholds are test examples rather than profitability claims or guaranteed risk caps.

100 tests now pass. The proposal does not implement a persistent scheduler, actual market backtesting, live order activation or independently verified continuous/protective exit handling. Full operational blockers still apply. The owner has authorized preparation and review, not autonomous discretionary live trading.

## Historical test attempt

strategy_backtest.py is a standalone standard-library public-data downloader and historical simulation tool. It uses documented Bybit BTCUSDT 15-minute spot candles, excludes forming bars, checks complete coverage, fills signals at the next bar open, deducts fees and adverse execution costs, preserves dust and open positions, and reports data hashes and limitations. It uses current exchange size filters as a proxy, not historical filter versions, and cannot reconstruct historical spreads, orderbook liquidity or intrabar protective fills.

The actual 90-day historical test attempt from this workspace FAILED because the public API returned an HTML Site Unavailable page instead of market data. historical_test_result.json records the failure and live_trading_ready=false. No historical return, win rate or profitability result is claimed. A local run from the owner's computer is required to obtain data if that computer remains eligible and can reach Bybit. No keys or orders are involved. Eleven additional fixture tests cover next-bar fills, fee deductions, missing data, minimum-notional failures, no private endpoints and Tortola day boundaries; the full suite passes 111 tests.
