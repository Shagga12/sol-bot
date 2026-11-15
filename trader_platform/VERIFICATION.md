# Trader preparation verification — 15 November 2026

## Passed

- 24 local tests: commission correctness, losses/recovery, duplicate events, a 1,000-settlement walk, account separation contracts, verified identity handling, owner-only HTTP actions, session expiry/logout, origin protection, rate limiting, locked money routes, bounded Buy/Sell review, and schema/frontend contracts.
- Python compile and JavaScript syntax checks.
- Hosted PostgreSQL rollback verification using the proposed schema and `schema/verify_rollback.sql`. The database returned `ROLLBACK_RLS_AND_COMMISSION_TESTS_PASSED`.
- Database assertions checked trader versus owner access, profile and wallet row isolation, blocked self-approval, denied direct wallet/commission writes, denied activation changes, blocked onboarding, owner-only vetting and audit, anonymous denial, 10% settlement accrual, loss recovery and duplicate protection.
- Independent rollback confirmation: zero `cc_trader_%` tables, zero `cc_trader_private` schemas, one existing owner preserved, legacy signup trigger preserved, and zero active legacy simulation schedules.
- Actual Auth settings endpoint reachable with a publishable key. Email sign-in enabled; email confirmation required.
- Actual Auth `/user` call rejected a deliberately invalid token. No service-role key, existing user password, new account or email notification was used.
- Owner disabled provider-wide new-user signup. Independently verified live Auth settings: `disable_signup=true`, email provider enabled, email confirmation required.

## Still outstanding

- Successful real-user email/password sign-in through the private preparation application and a visual browser review. Browser access could not be established.
- Persistent reviewed schema deployment to an appropriate staging environment; the successful test was rolled back and did not install the application schema.
- Verification that the single protected owner corresponds to Ron’s intended Auth identity before rollout.
- Custody provider selection/integration, per-trader issued destinations and verified funding/withdrawal reconciliation, tenant-bound real execution, and auditable commission collection.
- FSC approval and an explicit reviewed launch. Neither approval alone nor browser edits can enable financial routes in this preparation build.

## Exact owner setting

Open the existing Capital Connect project’s **Authentication → Sign In / Providers**:

https://supabase.com/dashboard/project/mlybldtawwltavngqmul/auth/providers

The owner turned **Allow new users to sign up** OFF and saved; this is now independently verified. Supabase documents that existing users can still sign in when this setting is disabled:

https://supabase.com/docs/guides/auth/general-configuration

Recheck the provider setting before any future launch. Do not disable the project or existing email provider; the personal Bybit worker is separate and was not changed by this work.
