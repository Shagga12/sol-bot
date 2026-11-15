-- Applied to the existing Capital Connect project on 2026-11-15.
-- Preserve all historical accounts/trades/commissions; stop scheduled simulation.
begin;
select cron.alter_job(job_id := (select jobid from cron.job where jobname='capital-connect-demo-scheduler'), active := false);
update public.demo_accounts set bot_enabled=false, updated_at=now() where bot_enabled;
commit;
-- Verification: both counts must be zero.
select (select count(*) from cron.job where jobname='capital-connect-demo-scheduler' and active) as active_schedules,
       (select count(*) from public.demo_accounts where bot_enabled) as enabled_accounts;
