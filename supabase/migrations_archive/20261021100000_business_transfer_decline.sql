begin;
set local lock_timeout='5s';
set local statement_timeout='60s';
alter table public.business_ownership_transfers drop constraint business_ownership_transfers_status_check;
alter table public.business_ownership_transfers add constraint business_ownership_transfers_status_check
    check(status in ('pending','accepted','cancelled','declined'));
create or replace function argus_private.business_transfer_immutable() returns trigger
language plpgsql set search_path='' as $$
begin
    if (to_jsonb(new)-'status'-'resolved_at') is distinct from (to_jsonb(old)-'status'-'resolved_at')
        or old.status<>'pending' or new.status not in ('accepted','cancelled','declined') then
        raise exception 'business_transfer_history_immutable' using errcode='23514';
    end if;
    return new;
end;
$$;
commit;
