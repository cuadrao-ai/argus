set local lock_timeout = '5s';
set local statement_timeout = '60s';

create extension if not exists pg_cron;
create extension if not exists pg_net with schema extensions;

create schema if not exists cuadrao_scheduler;
revoke all on schema cuadrao_scheduler from public, anon, authenticated, service_role;

-- Activation requires an explicit staging URL in Vault. No credential is embedded
-- in cron.job, migration history, or application logs.
create or replace function cuadrao_scheduler.require_staging()
returns void language plpgsql security invoker set search_path = '' as $$
begin
    if (select decrypted_secret from vault.decrypted_secrets
        where name = 'cuadrao_waitlist_project_url') is distinct from
        'https://skedzwocnmrhfigiwyzi.supabase.co' then
        raise exception 'Waitlist scheduler requires staging configuration';
    end if;
end;
$$;

create or replace function cuadrao_scheduler.purge_waitlist()
returns integer language plpgsql security invoker set search_path = ''
set lock_timeout = '5s' set statement_timeout = '60s' as $$
declare v_count integer;
begin
    perform cuadrao_scheduler.require_staging();
    select public.cuadrao_waitlist_purge(100) into v_count;
    raise log 'waitlist_retention purged=%', v_count;
    return v_count;
end;
$$;

create or replace function cuadrao_scheduler.remind_waitlist()
returns bigint language plpgsql security invoker set search_path = ''
set lock_timeout = '5s' set statement_timeout = '60s' as $$
declare v_key text; v_request bigint;
begin
    perform cuadrao_scheduler.require_staging();
    select decrypted_secret into v_key from vault.decrypted_secrets
        where name = 'cuadrao_waitlist_service_role_key';
    if v_key is null or length(btrim(v_key)) = 0 then
        raise exception 'Waitlist scheduler credential is missing';
    end if;
    select net.http_post(
        url := 'https://skedzwocnmrhfigiwyzi.supabase.co/functions/v1/waitlist-reminders',
        headers := jsonb_build_object('Content-Type', 'application/json', 'Authorization', 'Bearer ' || v_key),
        body := '{}'::jsonb,
        timeout_milliseconds := 120000
    ) into v_request;
    raise log 'waitlist_reminders request_id=%', v_request;
    return v_request;
end;
$$;

revoke all on all functions in schema cuadrao_scheduler from public, anon, authenticated, service_role;

-- Named schedules replace their own definition on replay, without duplicate jobs.
select cron.schedule('cuadrao-waitlist-retention', '2-59/5 * * * *',
    'select cuadrao_scheduler.purge_waitlist();');
select cron.schedule('cuadrao-waitlist-reminders', '*/5 * * * *',
    'select cuadrao_scheduler.remind_waitlist();');
