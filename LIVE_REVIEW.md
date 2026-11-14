# Capital Connect personal spot execution candidate

This is a separate **single-account, single-pair** worker for owner review. It is
not connected to the dashboard and has not been deployed or activated. Automated
tests use a fake exchange; there has been **no authenticated exchange validation
or real/testnet order submission**. Passing these tests does not establish live
readiness or profitability. The running demo remains separate.

## What is implemented

- HMAC-authenticated requests to a fixed Bybit mainnet or testnet host; redirects
  rejected; credentials read from environment variables and never printed.
- Dedicated SpotTrade-only key, account UID, non-borrowed spot availability,
  current instrument minimum/precision/maximum, current spread and taker fee checks.
- Price-bounded immediate-or-cancel (IOC) limit orders, sized with a fee reserve.
  Buy price and quantity are fixed before submission so a later market move cannot
  increase the order's limit-price notional. Orders may partially fill or cancel.
- A persistent journal records each unique order intent before the network write.
  A timed-out submission is never blindly retried. New activity is blocked until
  the existing order is reconciled or the owner resolves it.
- Terminal order and paginated execution reconciliation, including partially
  filled/cancelled orders and base/quote fees. Exchange acceptance is not a fill.
- Only recorded bot holdings can be sold. Existing personal holdings are not
  imported. Dust retains its cost and quantity and can accumulate with later buys.
- One entry scan per 15-minute bucket, based on 30 consecutive completed Bybit
  candles. This differs from the demo's sampled ticker history; it is not evidence
  that demo returns will transfer to live operation.
- User-configured total allocation, order ceiling, daily realized loss limit,
  estimated net stop/profit thresholds and slippage ceiling. The existing strategy
  additionally caps entries at 10 USDT and 10% of unallocated available funds,
  rejects spreads over 0.3%, and blocks entries after a 2% realized daily loss.
  None of those limits guarantees a maximum loss.
- Exit conditions checked every five seconds while the process is running. New
  entries wait four full 15-minute buckets after an exit. Exits still run after
  daily entry limits are reached.
- Local Linux process lock; journal bound to the account and configuration.
  No withdrawal, transfer, margin or derivatives endpoints.

## Important operational limits

**Stops are software checks, not exchange-hosted protective orders.** If the worker
stops, the network fails or an exchange response is uncertain, holdings remain in
Bybit with no exit managed by this worker. Slippage limits can cause partial fills
or cancellations, including on stop exits. The owner must monitor the account and
manage an exit directly in Bybit if required. This candidate is not suitable for
unattended use until those operational limits have been independently assessed.

Use one dedicated account/subaccount and one worker on one persistent Linux host.
Do not run replicas, other bots or manual trades in that account concurrently.
The lock does not coordinate separate hosts or database copies. Do not delete,
replace or restore an old journal to clear a pending order: that can duplicate
orders or lose ownership records. An account/config mismatch is deliberately
rejected. Keep the original journal for recovery and inspect Bybit's actual orders,
fills and balances before restarting a halted worker. Do not configure automatic
restart loops that conceal a HALTED state. SIGTERM stops the process; it does not
liquidate holdings. With an unresolved order, inspect Bybit before taking action.

API restrictions and geographic account eligibility must be respected; this code
does not circumvent them. Check available funds and current minimums instead of
using old wallet amounts. Small balances can fail the minimum after the 10%
allocation cap, fee reserve and precision rounding. No entry is forced to meet a
deadline. This version does not collect a commission or support multiple traders.

## Owner-run validation sequence

Python 3.10+ on Linux; standard library only. No change to the existing demo command
is needed. Keep secrets out of chat, source control, shell history and config JSON.
Set `BYBIT_API_KEY` and `BYBIT_API_SECRET` through your host's secure environment
settings. Use matching testnet credentials for testnet, mainnet credentials for
mainnet; only SpotTrade permission, no withdrawal or transfer permissions.

1. Copy `live-config.template.json` to a private local config path. It is deliberately
   invalid until **you** select each numeric setting. Values must be decimal strings.
   Fractions use `0.01` for 1%; `slippage_percent` uses `0.10` for 0.10%. Initial
   `environment` is `testnet`. Supported symbols: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT;
   choose one. Do not run multiple copies to add pairs.
2. Choose a new, persistent journal path reserved for this account/configuration.
   Keep its parent directory private and writable only by the worker owner.
3. Run a connection and size check. This makes GET requests only:

   ```bash
   python -m capital_connect_v1.live check --config /private/live-config.json --db /var/data/capital-connect-live.sqlite3
   ```

   This can verify connectivity and preview a size; it cannot prove that an order
   will execute, an exit will work or a strategy will make money.
4. Independently validate on testnet, including actual partial/filled/cancelled
   orders, a restart while an order is pending, minimum-size rejection, and both
   profit/loss exits. Owner-run testnet activation is explicit:

   ```bash
   python -m capital_connect_v1.live run --config /private/live-config.json --db /var/data/capital-connect-live.sqlite3 --enable-orders
   ```

   Real exchange validation has not been performed by the author of this change.
   Testnet liquidity and fills do not establish mainnet behavior.
5. Review results, limitations and funding before considering real funds. Mainnet
   requires a **separate configuration and journal**, matching mainnet credentials,
   and your own deliberate activation. The command additionally requires
   `--acknowledge-real-money` when `environment` is `mainnet`. Nothing in this PR
   executes that command or changes a Render start command or environment variable.

Inspect journal state without enabling orders:

```bash
python -m capital_connect_v1.live status --config /private/live-config.json --db /var/data/capital-connect-live.sqlite3
```

If the worker reports HALTED, preserve the journal and inspect the exact order in
Bybit. A missing order after a POST timeout is **unknown**, not a safe-to-repeat
failure. Pending history older than six days requires manual recovery. Unsupported
fee currencies/additional fees also halt for reconciliation. There is no automated
recovery command that silently clears uncertain state.

## Verification performed

`python -m unittest discover -s tests -v` exercises transport signing with a fake
opener, disabled writes, explicit activation gates, account binding, non-borrowed
availability, current limits/rounding, signal waits, durable intent before a failed
submission, restart recovery, partial fills, base/quote fees, overselling prevention,
and exits. Existing demo tests are included. Tests neither use real credentials nor
contact an exchange.

Official API references checked while implementing this candidate:

- https://bybit-exchange.github.io/docs/v5/order/create-order
- https://bybit-exchange.github.io/docs/v5/order/open-order
- https://bybit-exchange.github.io/docs/v5/order/execution
- https://bybit-exchange.github.io/docs/v5/order/spot-borrow-quota
- https://bybit-exchange.github.io/docs/v5/market/instrument
- https://bybit-exchange.github.io/docs/v5/market/kline
- https://bybit-exchange.github.io/docs/v5/account/fee-rate
- https://bybit-exchange.github.io/docs/v5/user/apikey-info
