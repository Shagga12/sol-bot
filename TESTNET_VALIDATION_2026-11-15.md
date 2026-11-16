# Capital Connect exchange validation — 15 November 2026

Scope: one personal Bybit spot account, BTCUSDT. Mainnet remains stopped; no mainnet order was submitted during this validation. Testnet uses separate credentials, a hard-bound Testnet host, separate persistent journals, virtual funds and idempotent completion markers.

## Actual Testnet runtime evidence (UTC)

| Completed | Check | Observed result |
| --- | --- | --- |
| 08:59:42 | Buy, process exit before reconciliation, separate-process recovery, sell | Actual Testnet fills reconciled; zero pending orders; dust retained |
| 09:02:45–47 | Profit and loss decision branches | Controlled decision prices exercised both branches; exits submitted at fresh actual Testnet prices and filled |
| 09:02:51 | Process supervisor Start and Stop | Exchange worker started, waited without a signal, terminated on Stop |
| 09:12:08 | Entry with attached market TP/SL, process exit, separate-process inspection | Bybit retained one protective bracket; exact test bracket cancelled for cleanup, test holdings sold |
| 09:17:47 | Integrated protected worker and restart | Exact same Bybit-held child adopted after process restart; one entry, no duplicate buy; explicit Testnet cleanup completed |

These are runtime observations, not the fake-exchange messages printed by unit tests during a build. The profit/loss branch tests used controlled decision inputs; they do not demonstrate profitable market performance. Natural market-triggered bracket execution, mainnet fills, every exchange failure mode and a browser-click-to-exchange round trip have not been tested.

## Saved owner settings

BTCUSDT mainnet; total allocation 56 USDT; order ceiling 15 USDT; daily realized-loss entry ceiling 10 USDT; estimated net stop trigger 1%; estimated net take-profit trigger 4%; entry slippage ceiling 0.10%. Fees, price and quantity rounding can reduce order notional. Profit is not guaranteed, and a stop trigger does not guarantee a maximum loss.

## Implemented controls

- Authenticated owner Start/Stop. Mainnet Start additionally requires an explicit real-money acknowledgement and the current configuration digest. The browser cannot change the worker's saved configuration through Start.
- Fresh worker-session reports; stale, replaced or restarted sessions invalidate old Start requests. HALTED never automatically restarts.
- Durable order intent before POST, no blind retry, fill and fee reconciliation, account/configuration binding, persistent disk and local process lock.
- Atomic entry-attached Bybit-held market TP/SL. Stop ends the process but keeps existing protective exchange orders. Restart recovers the recorded protective child before any new entry.
- Missing, cancelled or unverifiable protection with tradable holdings halts further entries. Orders can still fail or partially fill; the owner must inspect Bybit when halted.
- Dashboard labels demo balances separately from the execution journal and shows worker-reported saved limits.

## Remaining operational limitations

Use one dedicated account and one worker; avoid concurrent manual trading and other bots. If protection triggers before its first adoption during a long interruption, recovery fails closed and requires inspection. Pending history older than six days also requires manual recovery. Preserve the journal; never delete it to clear uncertainty. Exchange availability, liquidity, gaps and partial fills can cause losses beyond a configured stop. The 10 USDT daily setting prevents later entries based on realized bot losses; it is not an exchange-held account-wide loss cap.

## Local regression checks

90 Python worker tests, 41 Python dashboard tests and 7 JavaScript dashboard tests pass. These are local regressions, separate from the actual Testnet checks above. Mainnet order execution requires the owner's deliberate Start after review.
