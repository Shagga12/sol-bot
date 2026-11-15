-- Run preparation.sql first, in the SAME explicit transaction; ROLLBACK below is mandatory.
insert into public.cc_trader_profiles(user_id,display_name,order_limit_usdt)
 select user_id,'owner-test-only',15 from cc_trader_private.owner_registry;
insert into public.cc_trader_profiles(user_id,display_name,order_limit_usdt)
 select id,'trader-test-only',15 from auth.users where id not in(select user_id from cc_trader_private.owner_registry) order by id limit 1;
insert into public.cc_trader_wallet_entries(user_id,asset,amount,kind,provider_event)
 select user_id,'USDT',10,'deposit','rollback-test-'||user_id::text from public.cc_trader_profiles;
-- Exact settlement math, high-water recovery and idempotency at the database layer.
do $$declare uid uuid; fee numeric;begin
 select user_id into uid from public.cc_trader_profiles where display_name='trader-test-only';
 fee:=cc_trader_private.record_commission(uid,'test-1',100);if fee<>10 then raise exception '10 percent calculation failed';end if;
 fee:=cc_trader_private.record_commission(uid,'test-2',-30);if fee<>0 then raise exception 'Fee charged on loss';end if;
 fee:=cc_trader_private.record_commission(uid,'test-3',30);if fee<>0 then raise exception 'Recovery double charged';end if;
 fee:=cc_trader_private.record_commission(uid,'test-4',20);if fee<>2 then raise exception 'High-water fee failed';end if;
 fee:=cc_trader_private.record_commission(uid,'test-4',20);if fee<>0 then raise exception 'Duplicate charged';end if;
 if (select accrued from public.cc_trader_commission_state where user_id=uid)<>12 then raise exception 'Accrued total failed';end if;
end$$;
select set_config('request.jwt.claims',jsonb_build_object('sub',(select user_id::text from public.cc_trader_profiles where display_name='trader-test-only'),'role','authenticated','is_anonymous',false)::text,true);
set local role authenticated;
do $$declare changed integer;begin
 if (select count(*) from public.cc_trader_profiles)<>1 then raise exception 'Trader profile isolation failed';end if;
 if (select count(*) from public.cc_trader_wallet_entries)<>1 then raise exception 'Wallet isolation failed';end if;
 if (select count(*) from public.cc_trader_audit)<>0 then raise exception 'Audit access leaked';end if;
 if (public.cc_trader_identity()->>'is_owner')::boolean then raise exception 'Trader became owner';end if;
 update public.cc_trader_profiles set status='approved' where user_id=auth.uid();get diagnostics changed=row_count;
 if changed<>0 then raise exception 'Trader changed their approval status';end if;
 begin
   insert into public.cc_trader_wallet_entries(user_id,asset,amount,kind,provider_event) values(auth.uid(),'USDT',100,'deposit','forbidden-write');
   raise exception 'Trader could create money';
 exception when insufficient_privilege then null;end;
 begin
   perform cc_trader_private.record_commission(auth.uid(),'forbidden-settlement',100);
   raise exception 'Trader could mint commission records';
 exception when insufficient_privilege then null;end;
 begin
   update public.cc_trader_release set funding_enabled=true where id=1;
   raise exception 'Trader could activate funds';
 exception when insufficient_privilege then null;end;
 begin
   perform public.cc_request_trader_account();
   raise exception 'Onboarding should be locked';
 exception when raise_exception then
   if sqlerrm<>'Onboarding awaits approval' then raise;end if;
 end;
end$$;
reset role;
select set_config('request.jwt.claims',jsonb_build_object('sub',(select user_id::text from cc_trader_private.owner_registry),'role','authenticated','is_anonymous',false)::text,true);
set local role authenticated;
do $$begin
 if not (public.cc_trader_identity()->>'is_owner')::boolean then raise exception 'Owner identity missing';end if;
 if (select count(*) from public.cc_trader_profiles)<>2 then raise exception 'Owner listing failed';end if;
 update public.cc_trader_profiles set status='suspended' where user_id<>auth.uid();
 if (select count(*) from public.cc_trader_audit)<>1 then raise exception 'Owner audit missing';end if;
 begin
   update cc_trader_private.owner_registry set user_id=auth.uid();
   raise exception 'Owner registry unexpectedly writable';
 exception when insufficient_privilege then null;end;
 begin
   update public.cc_trader_release set trading_enabled=true where id=1;
   raise exception 'Owner frontend could bypass activation';
 exception when insufficient_privilege then null;end;
end$$;
reset role;
select set_config('request.jwt.claims','{}',true);
set local role anon;
do $$begin
 if (public.cc_trader_public_gate()->>'onboarding_enabled')::boolean then raise exception 'Gate should be closed';end if;
 begin
   perform count(*) from public.cc_trader_profiles;
   raise exception 'Anonymous user read profiles';
 exception when insufficient_privilege then null;end;
end$$;
reset role;
rollback;
select 'ROLLBACK_RLS_AND_COMMISSION_TESTS_PASSED' as result;
