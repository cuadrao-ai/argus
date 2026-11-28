-- A person can own several open Businesses (#2512).
begin;

set local lock_timeout = '5s';
set local statement_timeout = '60s';

drop index public.spaces_one_open_business_idx;

-- With the index gone a person can hold several open marked rows, so the
-- resolver names one on purpose: a row the person created, then the oldest.
create or replace function public.business_space_of(p_owner uuid) returns uuid
    language sql stable
    set search_path to ''
    as $$
    select s.id from public.spaces s
    where s.current_owner_id=p_owner and s.kind='business'
        and s.closed_at is null and s.business_legacy_default
        and exists (
            select 1 from public.business_client_grants g
            where g.space_id=s.id and g.grantee_id=p_owner
                and g.revoked_at is null
                and (g.expires_at is null or g.expires_at>clock_timestamp())
        )
    order by (s.created_by=p_owner) desc, s.created_at, s.id
    limit 1;
$$;

commit;
