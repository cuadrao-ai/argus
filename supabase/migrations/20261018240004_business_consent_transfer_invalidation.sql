begin;
set local lock_timeout='5s';
set local statement_timeout='60s';
alter table public.business_ai_consents add column invalidated_by_transfer_id uuid
    references public.business_ownership_transfers(id) on delete cascade;
create index business_ai_consent_transfer_idx on public.business_ai_consents(invalidated_by_transfer_id)
    where invalidated_by_transfer_id is not null;
alter table public.business_ai_consents drop constraint business_ai_consents_check1;
alter table public.business_ai_consents add constraint business_ai_consent_revocation_origin check (
    (revoked_at is null and revoked_by is null and invalidated_by_transfer_id is null)
    or (revoked_at is not null and (
        (revoked_by=owner_id and invalidated_by_transfer_id is null)
        or (revoked_by is null and invalidated_by_transfer_id is not null)
    ))
);
create or replace function argus_private.business_ai_consent_immutable()
returns trigger language plpgsql set search_path = '' as $$
begin
    if tg_op = 'DELETE' then
        if exists (select 1 from public.spaces where id = old.space_id) then
            raise exception 'business_ai_consent_original_immutable' using errcode = '23514';
        end if;
        return old;
    elsif tg_op = 'UPDATE' then
        if (to_jsonb(new) - 'revoked_at' - 'revoked_by' - 'invalidated_by_transfer_id')
            is distinct from (to_jsonb(old) - 'revoked_at' - 'revoked_by' - 'invalidated_by_transfer_id')
            or (old.revoked_at is not null and
                (new.revoked_at, new.revoked_by, new.invalidated_by_transfer_id) is distinct from (old.revoked_at, old.revoked_by, old.invalidated_by_transfer_id)) then
            raise exception 'business_ai_consent_original_immutable' using errcode = '23514';
        end if;
    else
        perform 1 from public.spaces s
        join auth.users u on u.id = s.current_owner_id
        join public.business_client_grants g on g.id = new.grant_id
            and g.space_id = s.id and g.grantee_id = u.id and g.issuer_id = new.issuer_id
        where s.id = new.space_id and s.current_owner_id = new.owner_id
            and s.kind = 'business' and s.closed_at is null
            and coalesce(u.is_anonymous, false) = false
            and g.revoked_at is null and (g.expires_at is null or g.expires_at > clock_timestamp())
            and 'read' = any(g.capabilities) and 'prepare' = any(g.capabilities)
        for share of s, g;
        if not found or new.revoked_at is not null or new.invalidated_by_transfer_id is not null then
            raise exception 'business_ai_consent_owner_required' using errcode = '23514';
        end if;
        new.consented_at := clock_timestamp();
    end if;
    return new;
end;
$$;

create function argus_private.business_consent_transfer_complete() returns trigger
language plpgsql set search_path='' as $$
begin
    if new.invalidated_by_transfer_id is not null and not exists (
        select 1 from public.business_ownership_transfers t
        where t.id=new.invalidated_by_transfer_id and t.space_id=new.space_id
            and t.owner_id=new.owner_id and t.status='accepted'
    ) then
        raise exception 'business_consent_transfer_not_accepted' using errcode='23514';
    end if;
    return null;
end;
$$;
revoke all on function argus_private.business_consent_transfer_complete() from public,anon,authenticated;
create constraint trigger business_consent_transfer_complete after insert or update
    on public.business_ai_consents deferrable initially deferred
    for each row execute function argus_private.business_consent_transfer_complete();
comment on column public.business_ai_consents.invalidated_by_transfer_id is
    'Automatic invalidation by an accepted ownership transfer. revoked_by is NULL because no person issued a consent-revocation command. Original consenting actor remains unchanged.';
commit;
