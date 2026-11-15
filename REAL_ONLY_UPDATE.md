# Real-only dashboard update — 15 November 2026

Removed simulated balances, commission estimates, sampled demo-market cards, demo position/trade history and demo settings from the owner dashboard. Overview and Activity now use only fresh mainnet execution telemetry; unverified data is shown as unavailable. CSV exports and history identify cumulative realized P&L and reconciliation times. The live journal, real-order code, credentials and saved limits were not modified.

Legacy /api/status and /api/report return 410. The Render simulation worker now idles without opening its historical database, fetching prices, scanning or reporting. Its service and disk still exist; this change does not cancel its hosting charges.

Also disabled the old Supabase capital-connect-demo-scheduler and all legacy demo account bot flags. Both old demo bot Edge Functions now return 410 without accessing credentials, the ledger or the exchange. Verified zero active simulation schedules/accounts and preserved historical trades. An automatic review blocked replacing the separately named legacy capital-connect-dashboard Edge Function due to potential live-dashboard impact; it was left unchanged.

45 Python dashboard checks and 11 JavaScript checks passed, including retired endpoints, real-only HTML, rendering genuine Buy/Sell fills and clearing stale records. Both Render deployments became live. The actual personal execution worker was verified STOPPED afterward, with no automatic Start sent. Existing exchange-held protection is not cancelled by Stop. The owner must deliberately resume through Trading setup.

This update provides personal real-money trade history, not multi-trader custody or manual Buy/Sell endpoints. The existing Capital Connect Supabase project contains authentication accounts and legacy demo tables; these are not a funded real-money trader ledger. Separate trader sign-in, authorization and funding require further implementation. No trader deposit address, wallet or custodial funding mechanism was created.
