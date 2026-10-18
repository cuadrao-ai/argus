-- Run only in an isolated local database after the two signup migrations.
begin;
create temporary table waitlist_assertions (name text primary key);
create function pg_temp.check_waitlist(ok boolean, label text) returns void language plpgsql as $$
begin
    if ok is distinct from true then raise exception 'FAIL %', label; end if;
    insert into waitlist_assertions values(label);
end;
$$;
select pg_temp.check_waitlist(not has_table_privilege('anon', 'public.cuadrao_early_access_signups', 'select'), 'anon cannot select');
select pg_temp.check_waitlist(not has_table_privilege('authenticated', 'public.cuadrao_early_access_signups', 'insert'), 'authenticated cannot insert');
select pg_temp.check_waitlist(not has_function_privilege('anon', 'public.cuadrao_waitlist_leave(text)', 'execute'), 'anon cannot invoke leave RPC');
select pg_temp.check_waitlist(not has_function_privilege('authenticated', 'public.cuadrao_waitlist_register(text,text,text,text,text)', 'execute'), 'authenticated cannot register via RPC');
select pg_temp.check_waitlist(has_table_privilege('service_role', 'public.cuadrao_early_access_signups', 'delete'), 'service role can remove whole row');
select pg_temp.check_waitlist((select relrowsecurity from pg_class where oid='public.cuadrao_early_access_signups'::regclass), 'RLS stays on');
select pg_temp.check_waitlist((select count(*)=1 from public.cuadrao_waitlist_register('local@example.test','No los llevo','Orden',repeat('a',64),'2026-10-16')), 'first registration gets one delivery reservation');
select pg_temp.check_waitlist((select count(*)=0 from public.cuadrao_waitlist_register('local@example.test','Otra forma','Do not overwrite',repeat('b',64),'2026-10-16')), 'duplicate within ten minutes sends no email');
select pg_temp.check_waitlist((select count(*)=1 and min(wish)='Orden' and bool_and(confirmed_at is null) from public.cuadrao_early_access_signups), 'one unconfirmed row retains original answers');
update public.cuadrao_early_access_signups set last_confirmation_sent_at=now()-interval '10 minutes';
select pg_temp.check_waitlist((select count(*)=1 from public.cuadrao_waitlist_register('local@example.test',null,null,repeat('b',64),'2026-10-16')), 'new confirmation allowed at ten minutes');
select public.cuadrao_waitlist_release(repeat('a',64),now()-interval '1 second',false);
select pg_temp.check_waitlist((select last_confirmation_sent_at is not null from public.cuadrao_early_access_signups), 'stale refusal cannot release newer send');
select public.cuadrao_waitlist_release(repeat('a',64),now(),false);
select pg_temp.check_waitlist((select last_confirmation_sent_at is null from public.cuadrao_early_access_signups), 'definite refusal releases exact reservation');
select pg_temp.check_waitlist((select count(*)=1 from public.cuadrao_waitlist_register('local@example.test',null,null,repeat('b',64),'2026-10-16')), 'definitely unsent confirmation can retry');
select pg_temp.check_waitlist((select count(*)=0 from public.cuadrao_waitlist_confirm(repeat('a',64),now()-interval '48 hours')), '48 hour confirmation expires');
select pg_temp.check_waitlist((select count(*)=1 from public.cuadrao_waitlist_confirm(repeat('a',64),now())), 'valid confirmation saves confirmed time');
select pg_temp.check_waitlist((select count(*)=0 from public.cuadrao_waitlist_register('local@example.test',null,null,repeat('b',64),'2026-10-16')), 'confirmed address gets no new confirmation');
select public.cuadrao_waitlist_leave(repeat('a',64));
select pg_temp.check_waitlist((select count(*)=0 from public.cuadrao_early_access_signups), 'leave deletes email answers and digest');
select public.cuadrao_waitlist_leave(repeat('a',64));
select pg_temp.check_waitlist((select count(*)=0 from public.cuadrao_early_access_signups), 'repeated leave is harmless');
select pg_temp.check_waitlist((select count(*)=1 from public.cuadrao_waitlist_register('local@example.test',null,null,repeat('c',64),'2026-10-16')), 'explicit new signup works after leaving');
update public.cuadrao_early_access_signups set created_at=now()-interval '24 hours',last_confirmation_sent_at=now()-interval '24 hours';
select pg_temp.check_waitlist((select count(*)=1 from public.cuadrao_waitlist_reminders()), 'one reminder at 24 hours');
select pg_temp.check_waitlist((select count(*)=0 from public.cuadrao_waitlist_reminders()), 'no second reminder');
update public.cuadrao_early_access_signups set created_at=now()-interval '7 days';
select pg_temp.check_waitlist(public.cuadrao_waitlist_purge()=1, 'unconfirmed row purged at seven days');
select count(*) from public.cuadrao_waitlist_register('local@example.test',null,null,repeat('d',64),'2026-10-16');
select count(*) from public.cuadrao_waitlist_confirm(repeat('d',64),now());
update public.cuadrao_early_access_signups set created_at=now()-interval '12 months'+interval '1 second';
select pg_temp.check_waitlist(public.cuadrao_waitlist_purge()=0, 'confirmed row retained until twelve months');
update public.cuadrao_early_access_signups set created_at=now()-interval '12 months';
select pg_temp.check_waitlist(public.cuadrao_waitlist_purge()=1, 'confirmed row purged at twelve months');
insert into public.cuadrao_early_access_signups(email_digest,email,language,consent_version,source,created_at)
values(encode(sha256(convert_to('legacy@example.test','UTF8')),'hex'),'legacy@example.test','en','old','personal-page',now()-interval '2 years');
select pg_temp.check_waitlist(public.cuadrao_waitlist_purge()=0, 'legacy rows outside new consent remain untouched');
select pg_temp.check_waitlist((select count(*)=1 from public.cuadrao_waitlist_register('legacy@example.test','Otra forma',null,repeat('e',64),'2026-10-16')), 'fresh consent upgrades legacy signup');
select pg_temp.check_waitlist((select created_at=now() and privacy_policy_version='2026-10-16' from public.cuadrao_early_access_signups where email='legacy@example.test'), 'new consent resets signup retention start');
do $$
begin
    begin
        update public.cuadrao_early_access_signups set expense_method='other';
        raise exception 'FAIL invalid expense method accepted';
    exception when check_violation then null; end;
    begin
        update public.cuadrao_early_access_signups set wish=repeat('x',281);
        raise exception 'FAIL long wish accepted';
    exception when check_violation then null; end;
end;
$$;
insert into waitlist_assertions values ('invalid expense method rejected'),('long wish rejected');
select count(*) || ' PostgreSQL acceptance checks passed' as result from waitlist_assertions;
rollback;
