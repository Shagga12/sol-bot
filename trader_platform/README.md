# Capital Connect — private trader-platform preparation

**Status: review code, not a customer launch.** This directory is standalone and does not import or change the personal Bybit worker, its journal, credentials, Start/Stop controls or saved trading limits. Do not deploy it onto the running owner dashboard as an incidental update.

## Prepared components

- Existing verified-email sign-in via Supabase Auth, followed by an authoritative Auth user lookup on every authenticated request. No service-role key is accepted.
- Random HttpOnly, SameSite session cookies; HTTPS Secure cookies outside loopback review; no provider tokens in browser storage; same-origin write checks; sign-in throttling and session expiry.
- Account, wallet-entry, order-history and commission views. There are no invented balances, deposit addresses, QR codes or sample traders in the portal.
- Buy/Sell request review with trader-specific saved limits. Reviews are not executable quotes; the submission route is locked.
- Owner-only Super Admin views, trader vetting/limit updates and an append-only status audit. The protected registry permits one owner. User-editable metadata never grants ownership.
- Proposed per-trader database records, row-level ownership policies, no anonymous account reads and no frontend financial write permissions.
- 10% commission accrual logic in Python and a transactionally locked SQL settlement function. Accrual is distinct from collection; collection is unavailable.

## Commission policy

Calculate net realized trading results **after exchange fees and before Capital Connect commission**. Deposits, withdrawals and unrealized market values do not count as trading profit.

For each trader, carry forward cumulative realized results and the prior profit high-water mark. Accrue 10% only when a new settlement exceeds that mark. Losses and recovery below the mark add no fee. Repeated settlement IDs add no second fee; a reused ID with a different result is rejected. Exact sub-cent amounts accumulate; a future collectible total is rounded down to USDT cents. Previously accrued fees are not automatically refunded after subsequent losses. No money is deducted or collected by this preparation build.

Examples: net result +100 → accrue 10; then -30 → accrue 0; then +30 → accrue 0; then +20 → accrue 2. Each trader has separate records and unique settlement IDs within that trader’s account.

## Closed features

New registration, deposit-address issuance, withdrawals, real orders and commission collection return a locked response. Financial routes stay locked even if release flags or the browser are edited. The server has no connected custody or execution adapter. No other trader can use the owner’s personal Bybit credentials.

The proposed database release record also defaults to onboarding/funding/trading OFF. The frontend cannot change this record. Account vetting does not activate financial services.

## Review locally

Use a separate staging database/project when available. Do not reuse the personal worker’s process or disk. The review server binds only to 127.0.0.1:8766 and also requires a separate Basic-auth password (username `ron`). It is not publicly hosted by this change.

Configure these through secure environment settings, not source control or chat:

- `TRADER_SUPABASE_URL`: HTTPS URL of the review project.
- `TRADER_SUPABASE_PUBLISHABLE_KEY`: publishable/anon key only; never service_role or secret.
- `TRADER_REVIEW_PASSWORD`: separate owner review password, at least 12 characters.
- `TRADER_REVIEW_ORIGIN`: `http://127.0.0.1:8766` for loopback review; HTTPS origin for a future protected deployment.

Run:

```bash
python -m trader_platform.server
```

The proposed schema is `schema/preparation.sql`. It is a review script, **not an applied production migration**. It copies the existing single `platform_admins` entry into a protected single-owner registry; verify that this entry is Ron’s correct Auth identity before an eventual rollout. It removes the exact legacy demo-signup trigger only when the script is applied. No existing demo balances or trade records are imported as real assets.

Before applying the schema persistently, use a reviewed migration generated with the supported Supabase CLI workflow, inspect current grants and existing policies, and perform the database tests below. Production onboarding also needs a completed sign-up/email-confirmation implementation and review of any legacy Auth configuration. This preparation UI intentionally does not offer public registration.

## Verification and limits

Passed locally:

```bash
python -m unittest discover -s trader_platform/tests -v
node --check trader_platform/web/portal.js
python -m compileall -q trader_platform
```

24 tests cover commission losses/recovery, exact sub-cent accrual, duplicate events, a deterministic 1,000-settlement walk, separate trader fee books, role spoofing, owner-only actions, session expiry/logout, same-origin checks, throttling, locked money routes, bounded Buy/Sell reviews, transport restrictions and frontend/schema contracts.

HTTP and Auth integration tests use an explicitly fake provider; they do **not** prove live Supabase Auth, SQL policies or provider behavior. No existing user password was requested or used. No sign-up emails were sent.

The hosted database test was **not executed**: automatic approval review could not complete because of a usage limit. This was not a security verdict. `schema/verify_rollback.sql` contains the intended database assertions. Run the preparation schema and this test in one explicit transaction on the chosen review database, confirm all assertions, and verify rollback. Do not claim RLS or live Auth verification until it passes. A visual browser review has not been completed.

## Required before opening to traders

1. Record the actual FSC/regulatory approval and permitted business model, jurisdictions and conditions.
2. Choose and verify the business custody/exchange provider, supported asset/network and segregation model. Implement issued destinations, signed/idempotent deposit events, confirmations/reorg handling, per-trader reconciliation and withdrawals. No personal/shared address is substituted automatically.
3. Apply and test the reviewed schema; verify the sole owner, existing-user migration decisions, Auth/email delivery, session revocation and per-trader access from real clients.
4. Integrate a tenant-bound execution adapter, current market/order-rule validation, confirmation, protective exits and order/fill reconciliation. Never share the personal journal or credentials between traders.
5. Test commission accrual against durable settlement records; add explicit, auditable collection via the approved custody arrangement. Approve the high-water and rounding terms.
6. Perform an independent security/operational review and explicit launch approval. Do not treat FSC approval alone as a switch that completes missing provider integration.

None of these launch steps is silently enabled by this review branch.
