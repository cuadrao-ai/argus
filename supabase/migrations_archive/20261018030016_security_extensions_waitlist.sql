set local lock_timeout = '5s';
set local statement_timeout = '60s';

revoke execute on function public.rls_auto_enable() from public, anon, authenticated;

create or replace function cuadrao_scheduler.remind_waitlist()
returns bigint language plpgsql security invoker set search_path = ''
set lock_timeout = '5s' set statement_timeout = '60s' as $$
declare v_key text; v_request bigint;
begin
    perform cuadrao_scheduler.require_staging();
    select decrypted_secret into v_key from vault.decrypted_secrets
        where name = 'cuadrao_waitlist_scheduler_key';
    if v_key is null or length(btrim(v_key)) = 0 then
        raise exception 'Waitlist scheduler credential is missing';
    end if;
    select net.http_post(
        url := 'https://skedzwocnmrhfigiwyzi.supabase.co/functions/v1/waitlist-reminders',
        headers := jsonb_build_object('Content-Type', 'application/json', 'X-Cuadrao-Waitlist-Scheduler-Key', v_key),
        body := '{}'::jsonb,
        timeout_milliseconds := 120000
    ) into v_request;
    raise log 'waitlist_reminders request_id=%', v_request;
    return v_request;
end;
$$;

revoke all on function cuadrao_scheduler.remind_waitlist() from public, anon, authenticated, service_role;
