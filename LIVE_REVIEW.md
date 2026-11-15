# Capital Connect personal spot worker

This branch implements one personal account and one spot pair. It is deployed as a stopped, owner-controlled worker. The demo is separate. See [the dated validation report](TESTNET_VALIDATION_2026-11-15.md) for actual Testnet results and remaining limits; no profitability claim is made.

Entries use completed 15-minute candles, bounded IOC limit prices, current instrument precision/minimums, fees and a saved order ceiling. They carry atomic exchange-held market take-profit/stop-loss instructions. Protective children are journaled and recovered across process restart. A stop trigger is not a guaranteed fill price. Four 15-minute cooldown buckets follow an exit.

The persistent journal records intent before submission. A timeout is uncertain and never blindly retried. Actual fills and base/quote fees determine bot ownership and realized P&L. Dust retains its cost. Unknown fees, unresolved orders, mismatched account/configuration or missing protection block new entries.

Owner Start requires fresh worker readiness, the current configuration digest and explicit real-money acknowledgement. Stop terminates the worker; it does not sell holdings or cancel Bybit-held protection. Loss of dashboard control halts the process. A halted worker does not automatically restart. The dashboard's demo balances are not the exchange wallet or real execution ledger.

Secrets belong only in Render environment settings, never in chat or source control. Bybit reads and writes are restricted to fixed API hosts and spot-order paths; transfers, withdrawals, margin and derivatives writes are unavailable. A Unified-account permission marker is accepted only alongside spot access and without separate contract/options/asset-transfer permissions.

Use one dedicated account and one worker on the original persistent disk. Avoid concurrent manual trades or other bots. Preserve the original journal when halted; inspect Bybit orders, fills, balances and protective orders before recovery. Never delete or restore an old journal to clear pending state. Protection that fills before its first adoption during a long outage, and pending history older than six days, require manual recovery.

The saved daily realized-loss ceiling blocks subsequent entries; it does not guarantee an account-wide maximum loss. TP/SL can fail, partially fill or slip. Testnet differs from mainnet and does not prove profitability. This version neither collects commissions nor activates other traders.

Read-only CLI inspection remains available:

```bash
python -m capital_connect_v1.live status --config /private/live-config.json --db /var/data/execution-journal.sqlite3
```

Do not run a second CLI worker alongside the supervised service. Production activation is the owner's dashboard action.
