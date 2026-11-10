set local lock_timeout = '5s';
set local statement_timeout = '60s';

-- One-way: removes the Personal waitlist (#1554). The marketing site stopped
-- reading it when its routes and reminder function were deleted. The whole
-- migration runs in one transaction, so a refusal below leaves every object
-- exactly as it was.

-- Refuse while any row exists. The lock holds writers off until the drop, so no
-- row can arrive between the check and the table going away.
do $$
declare
    v_rows bigint;
begin
    if to_regclass('public.cuadrao_early_access_signups') is not null then
        lock table public.cuadrao_early_access_signups in access exclusive mode;
        select count(*) into v_rows from public.cuadrao_early_access_signups;
        if v_rows > 0 then
            raise exception 'Refusing to remove the waitlist: public.cuadrao_early_access_signups holds % row(s)', v_rows
                using hint = 'Export or delete the rows under a separate approval, then run this migration again.';
        end if;
    end if;
end;
$$;

-- A job that is already gone is not an error.
do $$
begin
    if to_regclass('cron.job') is not null then
        perform cron.unschedule(jobid) from cron.job
            where jobname in ('cuadrao-waitlist-retention', 'cuadrao-waitlist-reminders');
    end if;
end;
$$;

drop function if exists cuadrao_scheduler.purge_waitlist();
drop function if exists cuadrao_scheduler.remind_waitlist();
drop function if exists cuadrao_scheduler.require_staging();
drop schema if exists cuadrao_scheduler;

drop function if exists public.cuadrao_waitlist_register(text, text, text, text, text);
drop function if exists public.cuadrao_waitlist_confirm(text, timestamptz);
drop function if exists public.cuadrao_waitlist_reminders(integer);
drop function if exists public.cuadrao_waitlist_release(text, timestamptz, boolean);
drop function if exists public.cuadrao_waitlist_leave(text);
drop function if exists public.cuadrao_waitlist_purge(integer);

-- Constraints, indexes, grants and comments go with the table.
drop table if exists public.cuadrao_early_access_signups;

do $$
begin
    if to_regclass('argus_private.retention_policies') is not null then
        delete from argus_private.retention_policies
            where table_name = 'public.cuadrao_early_access_signups';
    end if;
end;
$$;
