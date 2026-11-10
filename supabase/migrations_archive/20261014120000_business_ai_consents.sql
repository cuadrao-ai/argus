-- gate-destructive: drops an empty unused table.
--
-- One Business-wide AI-reading setting, the owner's: the permission that this
-- Business's receipts (uploaded, prepared, arriving by email) are read by the
-- document-extraction model. The text shown is the text stored, and the route
-- names the provider and the model, so a changed wording or model no longer
-- matches and the owner is asked again. Owner only, one active consent per
-- Business, service role only. A row is never edited except to revoke it once.
--
-- It replaces the per-address table 20261014090000 created
-- (business_email_ai_consents), which no merged code wrote to and which holds
-- no rows; that migration stays in the repo as applied, so a fresh database
-- and staging run the same files in order and end identical.

create table public.business_ai_consents (
    id uuid primary key default gen_random_uuid(),
    space_id uuid not null,
    owner_id uuid not null,
    consenting_actor_id uuid not null check (consenting_actor_id = owner_id),
    grant_id uuid not null,
    issuer_id uuid not null,
    scope_version integer not null check (scope_version = 1),
    purpose text not null check (purpose = 'business_ai_receipt_reading'),
    disclosure text not null check (char_length(disclosure) between 1 and 4000),
    route jsonb not null check (jsonb_typeof(route) = 'object' and route <> '{}'::jsonb),
    route_hash text not null check (route_hash ~ '^[0-9a-f]{64}$'),
    idempotency_key text not null check (char_length(idempotency_key) between 1 and 80),
    input_hash text not null check (input_hash ~ '^[0-9a-f]{64}$'),
    consented_at timestamptz not null default clock_timestamp(),
    revoked_at timestamptz,
    revoked_by uuid,
    -- The Business and its owner are one key: a consent can never name
    -- another space or person than the Business it is for.
    constraint business_ai_consents_space_fkey
        foreign key (space_id, owner_id)
        references public.spaces (id, created_by) on delete cascade,
    unique (owner_id, idempotency_key),
    check ((revoked_at is null) = (revoked_by is null)),
    check (revoked_by is null or revoked_by = owner_id),
    check (revoked_at is null or revoked_at >= consented_at)
);
create index business_ai_consents_space_idx
    on public.business_ai_consents(space_id);
create unique index business_ai_consents_active_idx
    on public.business_ai_consents(space_id) where revoked_at is null;

create function argus_private.business_ai_consent_immutable()
returns trigger language plpgsql set search_path = '' as $$
begin
    if tg_op = 'DELETE' then
        if exists (select 1 from public.spaces where id = old.space_id) then
            raise exception 'business_ai_consent_original_immutable' using errcode = '23514';
        end if;
        return old;
    elsif tg_op = 'UPDATE' then
        if (to_jsonb(new) - 'revoked_at' - 'revoked_by')
            is distinct from (to_jsonb(old) - 'revoked_at' - 'revoked_by')
            or (old.revoked_at is not null and
                (new.revoked_at, new.revoked_by) is distinct from (old.revoked_at, old.revoked_by)) then
            raise exception 'business_ai_consent_original_immutable' using errcode = '23514';
        end if;
    else
        perform 1 from public.spaces s
        join auth.users u on u.id = s.created_by
        join public.business_client_grants g on g.id = new.grant_id
            and g.space_id = s.id and g.grantee_id = u.id and g.issuer_id = new.issuer_id
        where s.id = new.space_id and s.created_by = new.owner_id
            and s.kind = 'business' and s.closed_at is null
            and coalesce(u.is_anonymous, false) = false
            and g.revoked_at is null and (g.expires_at is null or g.expires_at > clock_timestamp())
            and 'read' = any(g.capabilities) and 'prepare' = any(g.capabilities)
        for share of s, g;
        if not found or new.revoked_at is not null then
            raise exception 'business_ai_consent_owner_required' using errcode = '23514';
        end if;
        new.consented_at := clock_timestamp();
    end if;
    return new;
end;
$$;
create trigger business_ai_consent_immutable before insert or update or delete
    on public.business_ai_consents for each row
    execute function argus_private.business_ai_consent_immutable();

alter table public.business_ai_consents enable row level security;
revoke all on public.business_ai_consents from public, anon, authenticated;
grant select, insert, update, delete on public.business_ai_consents to service_role;
revoke truncate on public.business_ai_consents from service_role;
revoke all on function argus_private.business_ai_consent_immutable() from public, anon, authenticated;

-- The per-address table: empty, written by no merged code. Its trigger goes
-- with it; the function and the index it alone needed go too.
drop table public.business_email_ai_consents;
drop function argus_private.business_email_consent_immutable();
drop index public.business_email_routes_consent_key;
