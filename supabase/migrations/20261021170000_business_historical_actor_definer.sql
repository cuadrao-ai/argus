begin;
set local lock_timeout='5s';
set local statement_timeout='60s';

-- The historical-actor checks read auth.users. They must run as the migration
-- owner. A service_role insert cannot see that table, so the check failed as
-- permission denied instead of business_actor_not_found.
create or replace function argus_private.business_historical_actor() returns trigger
language plpgsql security definer set search_path='' as $$
begin
    if not exists(select 1 from auth.users where id=new.actor_id)
       and not exists(select 1 from argus_private.business_custody_reservations
           where space_id=new.space_id and deleted_actor_id=new.actor_id)
       and not exists(select 1 from argus_private.business_departure_aliases
           where space_id=new.space_id and actor_id=new.actor_id) then
        raise exception 'business_actor_not_found' using errcode='23503';
    end if;
    return new;
end;
$$;
create or replace function argus_private.business_historical_owner() returns trigger
language plpgsql security definer set search_path='' as $$
begin
    if not exists(select 1 from auth.users where id=new.owner_id)
       and not exists(select 1 from argus_private.business_custody_reservations
           where space_id=new.space_id and deleted_actor_id=new.owner_id)
       and not exists(select 1 from argus_private.business_departure_aliases
           where space_id=new.space_id and actor_id=new.owner_id) then
        raise exception 'business_historical_owner_not_found' using errcode='23503';
    end if;
    return new;
end;
$$;
revoke all on function argus_private.business_historical_actor() from public,anon,authenticated,service_role;
revoke all on function argus_private.business_historical_owner() from public,anon,authenticated,service_role;
commit;
