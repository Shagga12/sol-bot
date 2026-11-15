# Live market and personal execution charts

Overview now contains a private BTCUSDT price chart (1h/6h/24h), reconciled real-order markers, recorded entry cost / BTC and attached protective levels, plus a separate realized execution P&L chart.

Prices are public Bybit mainnet spot five-minute candle closes, fetched through a fixed read-only endpoint and cached for 30 seconds. The latest candle is still forming. Prices older than 90 seconds are hidden. This is polling, not a streaming tick feed. A failed feed cannot change order execution.

The execution chart reads the original persistent journal in read-only mode. It excludes unfilled/cancelled entries with zero fills and uses actual executed value / quantity for average fill prices. Marker timestamps are reconciliation times rather than precise execution times. P&L is cumulative realized journal P&L including recorded fees, not wallet equity or unrealized returns. The latest 100 filled orders are shown; cumulative amounts retain earlier results. Demo and Testnet trades are never presented as real-money results. Stale execution telemetry hides trade overlays and P&L instead of inventing balances.

No trading configuration, order logic, API permissions or secrets changed for these charts. Dashboard deployment resets its in-memory command broker to Stop; worker deployment creates a new stopped session. After this coordinated update, the owner must review the saved limits and explicitly press Start trading again. Existing exchange-held protection is not cancelled by deployment.

Checks: 92 worker Python tests, 44 dashboard Python tests and 9 JavaScript tests passed, including read-only ledger projection, cumulative P&L, no-fill exclusion, account/config binding, public-price cache, malformed chart rejection and rendering of real versus Testnet/stale states. Render runtime confirmed 300 public candles. A visual browser review could not be completed because the connected browser session was unavailable.
