-- Accountants never approve: the database refuses a client grant that carries
-- 'approve' for anyone but the Business owner (public.spaces.created_by), on
-- insert and on update, whoever writes it. Additive: no existing row changes
-- (on staging every grant with approve belongs to its space's owner).

create function argus_private.business_grant_approve_owner_only()
returns trigger language plpgsql set search_path = '' as $$
begin
    if 'approve' = any(new.capabilities) and not exists (
        select 1 from public.spaces s
        where s.id = new.space_id and s.created_by = new.grantee_id
    ) then
        raise exception 'business_grant_approve_owner_only' using errcode = '23514';
    end if;
    return new;
end;
$$;
create trigger business_grant_approve_owner_only before insert or update
    on public.business_client_grants for each row
    execute function argus_private.business_grant_approve_owner_only();
revoke all on function argus_private.business_grant_approve_owner_only() from public, anon, authenticated;
