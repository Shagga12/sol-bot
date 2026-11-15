-- Before an eventual reviewed production rollout, retire the exact legacy demo signup trigger.
-- This statement is included only in this unapplied preparation schema.
drop trigger if exists capital_connect_new_user_demo_account on auth.users;
-- REVIEW SCHEMA ONLY. Not applied to production. Test under BEGIN/ROLLBACK first.
-- No legacy accounts/balances are imported. No deposit keys or addresses generated.
create schema if not exists cc_trader_private;
revoke all on schema cc_trader_private from public,anon,authenticated;
grant usage on schema cc_trader_private to authenticated;
create table if not exists cc_trader_private.owner_registry(
 singleton boolean primary key default true check(singleton),user_id uuid not null unique references auth.users(id));
do $$begin
 if (select count(*) from public.platform_admins)<>1 then raise exception 'Exactly one verified platform owner is required';end if;
end$$;
alter table cc_trader_private.owner_registry enable row level security;
revoke all on cc_trader_private.owner_registry from public,anon,authenticated,service_role;
insert into cc_trader_private.owner_registry(singleton,user_id) select true,user_id from public.platform_admins on conflict(singleton) do nothing;
create or replace function cc_trader_private.is_owner() returns boolean language sql stable security definer set search_path='' as $$
 select auth.uid() is not null and coalesce(auth.jwt()->>'is_anonymous','false')<>'true'
 and exists(select 1 from cc_trader_private.owner_registry where user_id=auth.uid());$$;
revoke all on function cc_trader_private.is_owner() from public,anon,authenticated;
grant execute on function cc_trader_private.is_owner() to authenticated;

create table if not exists public.cc_trader_release(
 id integer primary key check(id=1),approval_reference text not null default '',
 onboarding_enabled boolean not null default false,funding_enabled boolean not null default false,trading_enabled boolean not null default false,
 custody_provider text not null default '',execution_release text not null default '',
 check(not onboarding_enabled or length(trim(approval_reference))>0),
 check(not funding_enabled or (onboarding_enabled and length(trim(custody_provider))>0)),
 check(not trading_enabled or (funding_enabled and length(trim(execution_release))>0)));
insert into public.cc_trader_release(id) values(1) on conflict do nothing;
create table if not exists public.cc_trader_profiles(
 user_id uuid primary key references auth.users(id),display_name text not null check(length(display_name) between 1 and 80),
 status text not null default 'pending' check(status in ('pending','approved','suspended')),
 order_limit_usdt numeric(28,8) not null default 0 check(order_limit_usdt>=0),created_at timestamptz not null default now(),
 check(status<>'approved' or order_limit_usdt>0));
create table if not exists public.cc_trader_wallet_entries(
 id uuid primary key default gen_random_uuid(),user_id uuid not null references public.cc_trader_profiles(user_id),
 asset text not null check(asset='USDT'),amount numeric(28,8) not null check(amount<>0),kind text not null check(kind in ('deposit','withdrawal','trade','commission')),
 provider_event text not null unique,created_at timestamptz not null default now());
create table if not exists public.cc_trader_orders(
 id uuid primary key default gen_random_uuid(),user_id uuid not null references public.cc_trader_profiles(user_id),
 side text not null check(side in ('Buy','Sell')),symbol text not null check(symbol in ('BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT')),
 quantity numeric(28,12) not null check(quantity>0),average_price numeric(28,8),net_realized_pnl numeric(28,8),
 status text not null check(status in ('pending','filled','cancelled','rejected')),provider_order text unique,created_at timestamptz not null default now());
create table if not exists public.cc_trader_commission_state(
 user_id uuid primary key references public.cc_trader_profiles(user_id),net_realized numeric(28,8) not null default 0,
 high_water numeric(28,8) not null default 0 check(high_water>=0),accrued numeric(38,18) not null default 0 check(accrued>=0),
 collected numeric(38,18) not null default 0 check(collected>=0 and collected<=accrued));
create table if not exists public.cc_trader_commissions(
 user_id uuid not null references public.cc_trader_profiles(user_id),settlement_id text not null,
 net_realized_pnl numeric(28,8) not null,commission_amount numeric(38,18) not null check(commission_amount>=0),
 created_at timestamptz not null default now(),primary key(user_id,settlement_id));
create table if not exists public.cc_trader_audit(
 id bigint generated always as identity primary key,actor uuid,action text not null,target uuid,created_at timestamptz not null default now());

alter table public.cc_trader_release enable row level security;
alter table public.cc_trader_profiles enable row level security;
alter table public.cc_trader_wallet_entries enable row level security;
alter table public.cc_trader_orders enable row level security;
alter table public.cc_trader_commission_state enable row level security;
alter table public.cc_trader_commissions enable row level security;
alter table public.cc_trader_audit enable row level security;
revoke all on public.cc_trader_release,public.cc_trader_profiles,public.cc_trader_wallet_entries,public.cc_trader_orders,public.cc_trader_commission_state,public.cc_trader_commissions,public.cc_trader_audit from public,anon,authenticated;
grant select on public.cc_trader_release,public.cc_trader_profiles,public.cc_trader_wallet_entries,public.cc_trader_orders,public.cc_trader_commission_state,public.cc_trader_commissions,public.cc_trader_audit to authenticated;
grant update(status,order_limit_usdt,display_name) on public.cc_trader_profiles to authenticated;
create policy cc_release_read on public.cc_trader_release for select to authenticated using(auth.uid() is not null and coalesce(auth.jwt()->>'is_anonymous','false')<>'true');
create policy cc_profiles_read on public.cc_trader_profiles for select to authenticated using((user_id=(select auth.uid()) and coalesce(auth.jwt()->>'is_anonymous','false')<>'true') or cc_trader_private.is_owner());
create policy cc_profiles_admin on public.cc_trader_profiles for update to authenticated using(cc_trader_private.is_owner()) with check(cc_trader_private.is_owner());
create policy cc_wallet_read on public.cc_trader_wallet_entries for select to authenticated using((user_id=(select auth.uid()) and coalesce(auth.jwt()->>'is_anonymous','false')<>'true') or cc_trader_private.is_owner());
create policy cc_orders_read on public.cc_trader_orders for select to authenticated using((user_id=(select auth.uid()) and coalesce(auth.jwt()->>'is_anonymous','false')<>'true') or cc_trader_private.is_owner());
create policy cc_state_read on public.cc_trader_commission_state for select to authenticated using((user_id=(select auth.uid()) and coalesce(auth.jwt()->>'is_anonymous','false')<>'true') or cc_trader_private.is_owner());
create policy cc_commissions_read on public.cc_trader_commissions for select to authenticated using((user_id=(select auth.uid()) and coalesce(auth.jwt()->>'is_anonymous','false')<>'true') or cc_trader_private.is_owner());
create policy cc_audit_read on public.cc_trader_audit for select to authenticated using(cc_trader_private.is_owner());

create or replace function public.cc_trader_identity() returns jsonb language sql stable security invoker set search_path='' as $$
 select jsonb_build_object('user_id',auth.uid(),'is_owner',cc_trader_private.is_owner());$$;
revoke all on function public.cc_trader_identity() from public,anon,authenticated;
grant execute on function public.cc_trader_identity() to authenticated;

create or replace function cc_trader_private.profile_audit() returns trigger language plpgsql security definer set search_path='' as $$
begin
 insert into public.cc_trader_audit(actor,action,target) values(auth.uid(),'profile_updated',new.user_id);
 return new;
end$$;
revoke all on function cc_trader_private.profile_audit() from public,anon,authenticated;
create trigger cc_profile_audit after update on public.cc_trader_profiles for each row execute function cc_trader_private.profile_audit();

-- Privileged settlement integration only. No grants to user-facing roles or service_role.
-- This accrues a receivable; it does NOT debit wallets or collect funds.
create or replace function cc_trader_private.record_commission(p_user_id uuid,p_event text,p_net numeric) returns numeric language plpgsql security invoker set search_path='' as $$
declare state public.cc_trader_commission_state; prior public.cc_trader_commissions; next_net numeric; fee numeric;
begin
 if p_event is null or length(p_event) not between 1 and 128 or p_net is null or p_net::text in ('NaN','Infinity','-Infinity') or p_net<>round(p_net,8) then raise exception 'Invalid settlement';end if;
 insert into public.cc_trader_commission_state(user_id) values(p_user_id) on conflict do nothing;
 select * into state from public.cc_trader_commission_state where user_id=p_user_id for update;
 select * into prior from public.cc_trader_commissions where user_id=p_user_id and settlement_id=p_event;
 if found then
   if prior.net_realized_pnl<>p_net then raise exception 'Settlement identifier reused';end if;
   return 0;
 end if;
 next_net=state.net_realized+p_net;
 fee=greatest(0,next_net-state.high_water)*0.10;
 insert into public.cc_trader_commissions(user_id,settlement_id,net_realized_pnl,commission_amount) values(p_user_id,p_event,p_net,fee);
 update public.cc_trader_commission_state set net_realized=next_net,high_water=greatest(0,state.high_water,next_net),accrued=state.accrued+fee where user_id=p_user_id;
 return fee;
end$$;
revoke all on function cc_trader_private.record_commission(uuid,text,numeric) from public,anon,authenticated,service_role;

-- Onboarding is explicitly gated; no profile is created merely by signing in.
create or replace function cc_trader_private.request_account() returns uuid language plpgsql security definer set search_path='' as $$
declare uid uuid:=auth.uid();
begin
 if uid is null or coalesce(auth.jwt()->>'is_anonymous','false')='true' then raise exception 'Verified sign-in required';end if;
 if not exists(select 1 from auth.users where id=uid and email_confirmed_at is not null) then raise exception 'Confirm email first';end if;
 if not exists(select 1 from public.cc_trader_release where id=1 and onboarding_enabled and length(trim(approval_reference))>0) then raise exception 'Onboarding awaits approval';end if;
 insert into public.cc_trader_profiles(user_id,display_name) values(uid,'Trader') on conflict do nothing;
 return uid;
end$$;
revoke all on function cc_trader_private.request_account() from public,anon,authenticated;
grant execute on function cc_trader_private.request_account() to authenticated;
create or replace function public.cc_request_trader_account() returns uuid language sql security invoker set search_path='' as $$select cc_trader_private.request_account();$$;
revoke all on function public.cc_request_trader_account() from public,anon,authenticated;
grant execute on function public.cc_request_trader_account() to authenticated;

create index if not exists cc_wallet_user_time on public.cc_trader_wallet_entries(user_id,created_at desc);
create index if not exists cc_orders_user_time on public.cc_trader_orders(user_id,created_at desc);
create index if not exists cc_commissions_user_time on public.cc_trader_commissions(user_id,created_at desc);
-- Public gate exposes only a Boolean, never business/approval records or account data.
create or replace function cc_trader_private.public_gate() returns jsonb language sql stable security definer set search_path='' as $$
 select jsonb_build_object('onboarding_enabled',coalesce((select onboarding_enabled and length(trim(approval_reference))>0 from public.cc_trader_release where id=1),false));$$;
revoke all on function cc_trader_private.public_gate() from public,anon,authenticated;
grant usage on schema cc_trader_private to anon;
grant execute on function cc_trader_private.public_gate() to anon,authenticated;
create or replace function public.cc_trader_public_gate() returns jsonb language sql stable security invoker set search_path='' as $$select cc_trader_private.public_gate();$$;
revoke all on function public.cc_trader_public_gate() from public,anon,authenticated;
grant execute on function public.cc_trader_public_gate() to anon,authenticated;
