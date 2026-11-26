DROP TRIGGER business_grant_approve_owner_only ON public.business_client_grants;
ALTER FUNCTION argus_private.business_grant_approve_owner_only() RENAME TO business_grant_role_capabilities;

CREATE OR REPLACE FUNCTION argus_private.business_grant_role_capabilities() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO ''
    AS $$
begin
    if new.business_role is null then
        new.business_role := case
            when 'approve'=any(new.capabilities) and exists (
                select 1 from public.spaces where id=new.space_id and current_owner_id=new.grantee_id
            ) then 'owner'
            when 'approve'=any(new.capabilities) then null
            when 'prepare'=any(new.capabilities) then 'editor'
            else 'viewer' end;
    end if;
    if new.business_role is null then
        raise exception 'business_grant_role_required' using errcode='23514';
    end if;
    new.capabilities := case new.business_role
        when 'admin' then array['read','prepare','approve']
        when 'owner' then array['read','prepare','approve']
        when 'viewer' then array['read']
        else array['read','prepare'] end;
    if new.business_role='owner' and new.revoked_at is null and new.expires_at is not null then
        raise exception 'business_owner_cannot_expire' using errcode='23514';
    end if;
    if tg_op='UPDATE' then
        new.membership_version := old.membership_version + case
            when (new.business_role,new.revoked_at,new.expires_at) is distinct from (old.business_role,old.revoked_at,old.expires_at) then 1 else 0 end;
    end if;
    if tg_op='UPDATE' and old.revoked_at is not null and new.revoked_at is distinct from old.revoked_at then
        raise exception 'business_membership_revocation_final' using errcode='23514';
    end if;
    return new;
end;
$$;

CREATE TRIGGER business_grant_role_capabilities BEFORE INSERT OR UPDATE ON public.business_client_grants
    FOR EACH ROW EXECUTE FUNCTION argus_private.business_grant_role_capabilities();

-- Recompute legacy capabilities without changing role, expiry, or revocation.
UPDATE public.business_client_grants SET business_role=business_role
WHERE business_role='admin' AND NOT ('approve'=ANY(capabilities));

CREATE OR REPLACE FUNCTION public.check_business_receipt_reading_consent() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO ''
    AS $$
begin
    if current_user='postgres' and tg_op='UPDATE' then
        if argus_private.business_custody_identity_change(tg_table_name,to_jsonb(old),to_jsonb(new)) then return new; end if;
    end if;
    if tg_op='INSERT' and not exists (
        select 1 from public.spaces s join public.business_client_grants g on g.space_id=s.id
        where s.id=new.space_id and s.kind='business' and s.closed_at is null
            and g.grantee_id=new.owner_id and 'approve'=any(g.capabilities)
            and g.revoked_at is null and (g.expires_at is null or g.expires_at>clock_timestamp())
    ) then
        raise exception 'Business approval permission required';
    end if;
    if tg_op='UPDATE' and (to_jsonb(new)-'revoked_at') is distinct from (to_jsonb(old)-'revoked_at') then
        raise exception 'Consent generation is immutable';
    end if;
    if tg_op='UPDATE' and old.revoked_at is not null and new.revoked_at is distinct from old.revoked_at then
        raise exception 'Revoked consent cannot be restored';
    end if;
    return new;
end;
$$;

CREATE OR REPLACE FUNCTION argus_private.business_owner_consent_revoked() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO ''
    AS $$
begin
    if 'approve'=any(old.capabilities) and old.revoked_at is null
        and not exists (
            select 1 from public.business_client_grants g
            where g.space_id=old.space_id and g.grantee_id=old.grantee_id
                and 'approve'=any(g.capabilities) and g.revoked_at is null
                and (g.expires_at is null or g.expires_at>clock_timestamp())
        ) then
        update public.business_receipt_reading_consents set revoked_at=clock_timestamp()
            where space_id=old.space_id and owner_id=old.grantee_id and revoked_at is null;
    end if;
    if old.business_role='owner' and old.revoked_at is null
        and (tg_op='DELETE' or new.business_role<>'owner' or new.revoked_at is not null) then
        update public.business_ai_consents set revoked_at=clock_timestamp()
            where space_id=old.space_id and owner_id=old.grantee_id and revoked_at is null;
    end if;
    if tg_op='DELETE' then return old; end if;
    return new;
end;
$$;
