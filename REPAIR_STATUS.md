# Capital Connect bot repair

This branch is an undeployed repair draft. It does not enable live trading.

## Completed

- Removed substitute prices, hardcoded balance, and order placement from the diagnostic dashboard.
- Added read-only credential and Unified balance checks plus a desktop popup checker.
- Added paper_engine.py: SQLite-backed paper account starting with 20 simulated USDT, four supported pairs, unique order IDs, a single pending order, cumulative fill reconciliation, fee-inclusive cash and position cost tracking, and realized net P&L.
- Unknown order outcomes remain unresolved and block new orders. Failed sells preserve holdings. Duplicate requests and snapshots do not debit twice. Terminal contradictions stop processing.
- All ledger mutations use SQLite immediate transactions. Decimal text storage avoids binary float money arithmetic.

## Validation

Run `python -m unittest discover -v`: 19 tests pass, including restart recovery, duplicate fills, rejected sells, partial/cancelled fills, rollback, competing connections, and the 20 USDT initial budget. Run `python paper_engine.py` for a temporary simulated buy/sell scenario; its prices and profit are fixtures, not market results.

## Remaining before live operation

The paper ledger has no exchange order adapter, automation strategy, or live execution switch. Do not feed raw Bybit messages into its simulation snapshot API. A real adapter must account for base-asset fees, actual executions, exchange precision/minimums, stale prices, account restrictions, externally changed balances, and reconciliation of uncertain submissions by stable client order ID. Durable hosting needs a persistent database, a single execution worker, private authentication, and operational pause/recovery controls. No SQLite file on ephemeral Render storage should be treated as durable production state.

The owner confirmed moving 20 USDT into Unified Trading. Authentication succeeded locally with a read-only key; authenticated Render connectivity remains unverified. This branch has not changed either existing Render deployment or the private Capital Connect site. Main remains unchanged.

Do not enable trading permissions or restart the legacy trading dashboard on the strength of these simulation tests. No real order was placed during this repair.
