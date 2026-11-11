-- Business email receiving: the owner's consent that receipts arriving at the
-- Business address are read by the document-extraction model. The text shown
-- is the text stored, and the route names the provider and the model, so a
-- changed wording or model no longer matches and the owner is asked again.
-- Owner only, one active consent per Business, service role only. A row is
-- never edited except to revoke it once. Additive: a new table and one unique
-- index on an existing primary key plus two pinned columns; no row changes.

create unique index business_email_routes_consent_key
    on public.business_email_routes(id, space_id, principal_id);

create table public.business_email_ai_consents (
    id uuid primary key default gen_random_uuid(),
    route_id uuid not null,
    space_id uuid not null,
    owner_id uuid not null,
    consenting_actor_id uuid not null check (consenting_actor_id = owner_id),
    grant_id uuid not null,
    issuer_id uuid not null,
    scope_version integer not null check (scope_version = 1),
    purpose text not null check (purpose = 'business_email_receipt_reading'),
    disclosure text not null check (char_length(disclosure) between 1 and 4000),
    route jsonb not null check (jsonb_typeof(route) = 'object' and route <> '{}'::jsonb),
    route_hash text not null check (route_hash ~ '^[0-9a-f]{64}$'),
    idempotency_key text not null check (char_length(idempotency_key) between 1 and 80),
    input_hash text not null check (input_hash ~ '^[0-9a-f]{64}$'),
    consented_at timestamptz not null default clock_timestamp(),
    revoked_at timestamptz,
    revoked_by uuid,
    -- The route pins the Business and its owner: a consent can never name
    -- another space or person than the address it is for.
    constraint business_email_consent_route_fkey
        foreign key (route_id, space_id, owner_id)
        references public.business_email_routes (id, space_id, principal_id) on delete cascade,
    unique (owner_id, idempotency_key),
    check ((revoked_at is null) = (revoked_by is null)),
    check (revoked_by is null or revoked_by = owner_id),
    check (revoked_at is null or revoked_at >= consented_at)
);
create index business_email_consent_route_idx
    on public.business_email_ai_consents(route_id);
create unique index business_email_consent_active_idx
    on public.business_email_ai_consents(space_id) where revoked_at is null;

create function argus_private.business_email_consent_immutable()
returns trigger language plpgsql set search_path = '' as $$
begin
    if tg_op = 'DELETE' then
        if exists (select 1 from public.business_email_routes where id = old.route_id) then
            raise exception 'email_consent_original_immutable' using errcode = '23514';
        end if;
        return old;
    elsif tg_op = 'UPDATE' then
        if (to_jsonb(new) - 'revoked_at' - 'revoked_by')
            is distinct from (to_jsonb(old) - 'revoked_at' - 'revoked_by')
            or (old.revoked_at is not null and
                (new.revoked_at, new.revoked_by) is distinct from (old.revoked_at, old.revoked_by)) then
            raise exception 'email_consent_original_immutable' using errcode = '23514';
        end if;
    else
        perform 1 from public.business_email_routes r
        join public.spaces s on s.id = r.space_id and s.created_by = r.principal_id
        join auth.users u on u.id = r.principal_id
        join public.business_client_grants g on g.id = new.grant_id
            and g.space_id = s.id and g.grantee_id = u.id and g.issuer_id = new.issuer_id
        where r.id = new.route_id and r.active
            and s.kind = 'business' and s.closed_at is null
            and coalesce(u.is_anonymous, false) = false
            and g.revoked_at is null and (g.expires_at is null or g.expires_at > clock_timestamp())
            and 'read' = any(g.capabilities) and 'prepare' = any(g.capabilities)
        for share of r, s, g;
        if not found or new.revoked_at is not null then
            raise exception 'email_consent_owner_required' using errcode = '23514';
        end if;
        new.consented_at := clock_timestamp();
    end if;
    return new;
end;
$$;
create trigger business_email_consent_immutable before insert or update or delete
    on public.business_email_ai_consents for each row
    execute function argus_private.business_email_consent_immutable();

alter table public.business_email_ai_consents enable row level security;
revoke all on public.business_email_ai_consents from public, anon, authenticated;
grant select, insert, update, delete on public.business_email_ai_consents to service_role;
revoke truncate on public.business_email_ai_consents from service_role;
revoke all on function argus_private.business_email_consent_immutable() from public, anon, authenticated;
