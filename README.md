# Capital Connect

The isolated `capital-connect-ai-quant-v1-clean` branch contains the new demo engine.
The legacy `app.py` is retained for comparison only and must not be used as the new
worker entry point. It contains real-order code; this demo worker does not import it.

## Run the demo worker (Linux)

Python 3.10+ is required. The new worker uses Python's standard library only.

```bash
python -m capital_connect_v1.worker --db /persistent/path/capital-connect-demo.sqlite3
```

For one scan, add `--once`. Set `CAPITAL_CONNECT_DB` instead of `--db` if preferred.
The parent directory must already exist. Keep the SQLite database and its lock on
persistent storage; an ephemeral cloud filesystem loses history on replacement.
Do not start multiple hosts with separate copies of this database. The process lock
and SQLite transactions only coordinate workers sharing the same filesystem.

The worker reads public spot prices for BTC/USDT, ETH/USDT, SOL/USDT and BNB/USDT.
It requires no Bybit credentials and cannot place exchange orders. A failed fetch
skips the complete scan and does not invent a price. SIGTERM/SIGINT stop the loop.

## Simulated behavior

- Initial cash is **1,000 simulated USDT**, not a real account balance.
- Scans run once per 15-minute UTC bucket. Duplicate and older scans are skipped.
- The strategy requires 30 consecutive sampled price buckets (about 7.5 hours).
  These are sampled ticker prices, not exchange candle closes. Missing buckets
  require a new consecutive warmup. During warmup the reason is
  `warming_up_price_history`; scan logs include collected/required samples and remaining minutes. Invalid prices are reported separately as `invalid_market_price`.
- A 10-sample average above the 30-sample average permits a demo buy.
- Size is capped at 10 simulated USDT and 10% of available simulated cash.
- Positions close in simulation after a sampled 1% rise or fall. Stops are checked
  only on scans: they cannot guarantee a fill price or a maximum loss.
- A 0.1% fee per side is a simulation assumption. Spread and slippage are not
  modeled; reported paper results do not establish expected live performance.
- Realized daily losses at 2% of the day's opening marked equity block new entries.
  Exits remain enabled. All ledger timestamps and daily boundaries use UTC.
- Cash, positions, decisions, fees and realized P&L survive worker restarts.
- The commission view estimates 10% of positive cumulative realized paper P&L;
  it neither bills nor transfers money.

Inspect the ledger locally (no web endpoint exposes account state):

```bash
python -c 'from capital_connect_v1.paper import PaperLedger; import json; p=PaperLedger("/persistent/path/capital-connect-demo.sqlite3"); print(json.dumps(p.status(), indent=2)); p.close()'
```

Run verification:

```bash
python -m unittest discover -s tests -v
```

## Current status and remaining work

This is a tested demo ledger and browser-independent worker, not a deployed live
trading system. It has no trader login, account isolation, dashboard integration,
exchange order reconciliation or cross-host worker coordination yet. It is not
ready to host 100 traders. The existing preflight web service is separate.

Before live execution, build and verify authenticated account checks, exchange
minimum sizes and precision, durable order IDs and fill reconciliation, ownership
of existing positions, per-account worker coordination, and explicit live controls.
No deployment or legacy service configuration is changed by this branch update.

## Legacy bot diagnosis from source

The old `app.py` hard-codes its displayed balance and substitutes a fixed SOL price
when price retrieval fails (and when SOL is below a hard-coded threshold). It stores
positions in Streamlit browser-session state, estimates purchased quantity instead
of reconciling fills, and clears a position after a sell attempt even when that
attempt fails. The suspended background worker starts that UI with `python app.py`,
whereas the web service uses `streamlit run app.py`. These are concrete defects;
they do not prove why any particular historical order failed or the worker crashed.
