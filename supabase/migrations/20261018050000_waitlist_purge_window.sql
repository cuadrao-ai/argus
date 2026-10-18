set local lock_timeout = '5s';
set local statement_timeout = '60s';

create or replace function public.cuadrao_waitlist_purge(p_limit integer default 100)
returns integer language plpgsql security invoker set search_path = '' as $$
declare
    v_count integer;
    v_months integer := coalesce(nullif(pg_catalog.current_setting(
        'cuadrao.waitlist_retention_months', true), ''), '12')::integer;
begin
    if v_months not between 1 and 120 then
        raise exception 'Waitlist retention must be between 1 and 120 calendar months'
            using errcode = '22023';
    end if;
    with candidates as materialized (
        select email_digest from public.cuadrao_early_access_signups
        where privacy_policy_version is not null and (
            (confirmed_at is null and created_at <= now() - interval '7 days')
            or created_at + pg_catalog.make_interval(months => v_months) <= now()
        ) order by created_at limit greatest(1, least(p_limit, 100)) for update skip locked
    )
    delete from public.cuadrao_early_access_signups as signup
    using candidates
    where signup.email_digest = candidates.email_digest;
    get diagnostics v_count = row_count;
    return v_count;
end;
$$;

comment on function public.cuadrao_waitlist_purge(integer) is
    'Deletes whole personal-consent rows after 7 days without confirmation or after the configured signup retention. cuadrao.waitlist_retention_months defaults to 12 calendar months and accepts integers 1 through 120. Legacy rows remain outside this purge.';

-- notified_at is a legacy pre-send claim, not proof that an invite was accepted.
-- A future invite sender calls this only after confirmed provider acceptance.
create or replace function public.cuadrao_waitlist_invited(p_verification_id text)
returns integer language plpgsql security invoker set search_path = '' as $$
declare v_count integer;
begin
    delete from public.cuadrao_early_access_signups
    where verification_id = p_verification_id and privacy_policy_version is not null
        and confirmed_at is not null and removed_at is null;
    get diagnostics v_count = row_count;
    return v_count;
end;
$$;

comment on function public.cuadrao_waitlist_invited(text) is
    'Service-only completion hook after a personal launch invite is accepted by the provider. Deletes the entire exact confirmed signup, including its digest and answers. Repeated completion is harmless and an old verification_id cannot delete a new signup. No personal launch sender is wired yet.';

revoke all on function public.cuadrao_waitlist_invited(text) from public, anon, authenticated;
grant execute on function public.cuadrao_waitlist_invited(text) to service_role;
