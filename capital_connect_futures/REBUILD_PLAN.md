# Capital Connect — Bybit SOLUSDT Futures rebuild

Status: DESIGN / DEMO ONLY. This branch is not approved for live execution.

## Scope
- Bybit USDT-settled SOLUSDT perpetual futures (linear category), not spot.
- Default environment: Bybit demo/test environment. No production orders by default.
- Margin: isolated. Leverage ceiling: 2x. Never silently switch to cross.
- Position sizing: configurable, bounded by account and per-order limits.
- Initial planned stop loss: 1% below actual filled entry for longs (above for shorts).
- Initial planned take profit: 4% above actual filled entry for longs (below for shorts).
- Exchange tick-size and quantity-step rounding must be read from instrument metadata.
- Use actual average fill price, not an unfilled limit price, to calculate final protections.
- Stop-loss and take-profit must be exchange-held, closing-only, for the entire position.
- Trigger basis must be explicit (Last/Mark), validated against exchange rules.
- All order operations require unique idempotency keys and read-back verification.
- If protection cannot be verified, fail closed: do not submit another entry; alert operator; apply a tested emergency risk procedure.
- Reconcile positions and protective orders from exchange on restart and periodically.
- Never claim an order or protection is live based on a request acknowledgement alone.
- Daily loss cap, max notional, max open positions, and kill switch must be enforced before any order.
- API keys must not be committed or logged; use Render secret environment variables.
- Only one live trading worker per account/symbol; prevent duplicate concurrent engines.
- No deployment or automatic live activation from this document.

## Reference demo observation (user screenshot, Nov 19 2026)
- SOLUSDT perpetual, long, isolated 2x, quantity 0.1 SOL.
- Actual entry 72.890; mark 72.900 at screenshot.
- Bybit demo interface showed full-position TP 75.92 and SL 72.27, market exits.
- Those prices were based on intended 73.00 limit entry; actual entry differs.
- Protective order display is observed; trigger execution is not yet verified.

## Verification gates before live trading
1. Static checks and tests for correct linear-futures API category, rounding, side, reduce-only, trigger direction, and error handling.
2. Demo entry and exchange read-back of position, full-position TP and SL.
3. Demo stop-loss trigger and take-profit trigger, independently verified in trade history.
4. Simulated partial fills, rejected TP/SL, disconnects, duplicate signals, restart and stale-order reconciliation.
5. Explicit human review of funding, jurisdiction, account permissions, order sizing, and max loss.
6. Separate manual live-enable action after all gates pass. No implied approval.

## Next implementation
Implement a dedicated futures engine in this branch; do not reuse spot execution or alter deployed services until demo tests pass.
