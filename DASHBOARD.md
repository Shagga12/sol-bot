# Capital Connect mobile dashboard

The existing password-protected Render dashboard now serves a responsive interface
from `dashboard/index.html`, `dashboard/dashboard.css` and `dashboard/dashboard.js`.
The Python start command remains `python capital_connect_server.py`.

## Views

- Overview: actual demo worker cash, estimated equity, realized/unrealized results,
  commission estimate, monitored pair decisions, open demo positions and recent trades.
- Activity: pair/action filters, closed-trade events, auto-refresh of the view and
  a CSV export of the filtered portion of the latest 100 worker trade events.
- Bybit account: an authenticated, same-origin check of API access, Unified wallet,
  non-borrowed spot availability and current pair minimum. Keys are used transiently
  and are not stored. This check performs GET requests only.
- Trading setup: report freshness, session-only account/funds checks, current demo
  settings and an explicit description of remaining live-execution work.

All balances on the overview/activity screens are simulated. Real account results
are isolated in the account view, and absent data is displayed as unknown. No real
order, withdrawal, transfer or bot-activation endpoint is added by this update.
Pair filters change the display only. Pausing auto-refresh does not stop the bot.
There is no multi-trader signup/invitation system in this owner-only dashboard.

## Access and operation

Existing `CAPITAL_VIEW_PASSWORD` and `CAPITAL_REPORT_TOKEN` remain unchanged. All
dashboard assets and account state require the existing owner login. The health
endpoint exposes only service/version status. Browser responses prohibit caching,
framing and third-party scripts; the page makes no external font or analytics calls.
The account POST requires the configured `CAPITAL_PUBLIC_ORIGIN` (defaulting to the
existing Render URL) and is rate limited. Neither request bodies nor API secrets
are logged by the application.

Worker reports remain in process memory. A new web process waits for the next
scheduled worker report, up to 15 minutes under normal operation. The UI makes
that state explicit and flags scan/report ages over 20 minutes. No data is invented
to fill a restart gap. The authoritative demo ledger stays on the worker's existing
persistent disk. No changes to that worker or its trading settings are included.

Account-check results remain in page memory for the current session only and reset
on reload. Wallet access can succeed while availability/minimum checks fail; those
fields remain unverified. Available funds exceeding the exchange minimum alone do
not prove that a sized order can be accepted, that exits work or that the strategy
is profitable. The separate execution candidate remains an undeployed review draft.

## Verification

```bash
python -m unittest discover -s tests -v
node --test tests/dashboard.test.cjs
node --check dashboard/dashboard.js
python -m compileall -q capital_connect_server.py capital_connect_preflight.py
git diff --check
```

14 Python tests cover authenticated routes/assets, worker ingestion, explicit empty
state, rejection of real/malformed reports, CSRF/rate limits, privacy and read-only
Bybit checks with fake responses. Five JavaScript tests cover unknown balances,
P&L signs, scan freshness, intersecting filters and formula-safe CSV output.

Browser QA uses disposable, local-only fixtures (never deployed). Desktop and
390-pixel phone layouts, navigation, filter empty states, credential clearing and
the account success flow were inspected. This does not constitute an authenticated
check of the owner's actual Bybit account or permission to submit an order.
