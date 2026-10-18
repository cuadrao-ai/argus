\set ON_ERROR_STOP on
begin;
do $$ begin
 if (select count(*) from cron.job where jobname like 'cuadrao-waitlist-%') <> 2 then raise exception 'duplicate cron jobs'; end if;
 if has_function_privilege('anon','cuadrao_scheduler.purge_waitlist()','EXECUTE') or has_function_privilege('service_role','cuadrao_scheduler.remind_waitlist()','EXECUTE') then raise exception 'scheduler privileges exposed'; end if;
 begin
   perform cuadrao_scheduler.purge_waitlist();
   raise exception 'missing configuration was accepted';
 exception when raise_exception then
   if sqlerrm <> 'Waitlist scheduler requires staging configuration' then raise; end if;
 end;
end $$;
select vault.create_secret('https://skedzwocnmrhfigiwyzi.supabase.co','cuadrao_waitlist_project_url');
select vault.create_secret('local-fixture-only','cuadrao_waitlist_scheduler_key');
do $$ declare request bigint; begin
 request := cuadrao_scheduler.remind_waitlist();
 if not exists (select 1 from net.http_request_queue where id=request and url='https://skedzwocnmrhfigiwyzi.supabase.co/functions/v1/waitlist-reminders' and headers->>'X-Cuadrao-Waitlist-Scheduler-Key'='local-fixture-only' and not headers ? 'Authorization' and timeout_milliseconds=120000) then raise exception 'wrong scheduler handoff'; end if;
end $$;
-- Rollback prevents pg_net from sending anything to a hosted service.
rollback;
