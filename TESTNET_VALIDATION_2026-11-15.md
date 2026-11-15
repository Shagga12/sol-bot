# Capital Connect Testnet validation — 2026-11-15

Runtime evidence: Render service srv-dbsi3ion74is739uto3g, runtime instance srv-dbsi3ion74is739uto3g-vlb5t; lifecycle deploy dep-dbsna45g1s2s73flroj0, source 0ab60619b8d4392449765ed676f8e966ad1f255e. Results below are runtime observations, not build-time unit-test output.

| Check | Observed result | Scope |
|---|---|---|
| Authenticated Testnet sizing check | Passed; approximately 100 virtual USDT initially available | GET requests, 15 USDT configured ceiling |
| Testnet IOC buy and sell | Passed at 08:59:42 UTC | Actual Testnet fills, not mainnet |
| Restart reconciliation | Passed | Buy process exited before reconciliation; separate process reconstructed fills from persisted journal |
| Take-profit exit path | Passed at 09:02:45 UTC | Controlled synthetic decision price; actual order used fresh Testnet price and had sell fills |
| Stop-loss exit path | Passed at 09:02:47 UTC | Controlled synthetic decision price; actual order used fresh Testnet price and had sell fills |
| Process Start and Stop | Passed at 09:02:51 UTC | Actual Testnet worker process started, reported no buy signal, and terminated on Stop |
| Mainnet orders submitted by tests | Zero | Test transport refuses mainnet; separate Testnet keys/journals |

## Limits of this evidence

These tests do not demonstrate natural 4% winning trades or profitability. The lifecycle trigger prices were synthetic; execution prices were live Testnet quotes. Small residual BTC from rounding was retained with its cost (approximately 0.000000769 BTC per roundtrip journal), not written off as profit. The process-control check verified the process supervisor, not an end-to-end owner browser click. Partial-fill, timeout and duplicate-submission protection has automated fake-transport coverage, but this run did not deliberately induce every exchange failure. Testnet liquidity and fills do not establish mainnet execution quality.

## Current state

Production mainnet worker remains STOPPED with execution release unset. No mainnet activation was performed. The configured limits are 56 USDT allocation, 15 USDT order ceiling, 10 USDT daily realized-loss ceiling, 1% estimated net stop trigger, 4% estimated net profit trigger, and 0.10% order price deviation ceiling. The shared signal layer additionally blocks new entries at a 2% realized daily loss, so the effective daily stop can be earlier than the configured 10 USDT.

Stops currently depend on a running process and connectivity; they are not exchange-hosted protective orders. Stop ends that process; it does not liquidate holdings or guarantee cancellation of an uncertain order. Loss of the control connection halts the process, potentially leaving holdings without managed exits. These operational limits require resolution/review before unattended real-funds use.
