-- Connected financial sources (Plaid Items, Gmail mailboxes, Shortcuts devices).
-- Spec: docs/specs/lanes/financial-ingestion-connectors.md.
--
-- One row per person-authorized connection. Status, freshness and the last
-- actionable failure are what the app shows; the cursor and lease serialize
-- provider syncs. Provider credentials live only in secret_ciphertext, sealed
-- by the API (AES-256-GCM bound to source:id), and are cleared on disconnect.
-- Clients may read their own non-secret columns; every write is server-side.

create table if not exists public.financial_source_connections (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    source text not null check (source in ('plaid', 'gmail', 'shortcuts', 'statement')),
    status text not null default 'active'
        check (status in ('active', 'needs_reauth', 'error', 'disconnected')),
    label text check (label is null or char_length(label) between 1 and 80),
    external_ref text not null check (char_length(external_ref) between 1 and 200),
    sync_cursor text check (sync_cursor is null or char_length(sync_cursor) <= 4096),
    secret_ciphertext bytea,
    last_success_at timestamptz,
    last_attempt_at timestamptz,
    last_error_code text check (
        last_error_code is null or last_error_code ~ '^[a-z0-9_]{1,64}$'
    ),
    -- A warning that survives successful syncs (consent expiring); cleared
    -- only by re-authorization or disconnect.
    attention_code text check (
        attention_code is null or attention_code ~ '^[a-z0-9_]{1,64}$'
    ),
    attention_at timestamptz,
    lease_holder text check (lease_holder is null or char_length(lease_holder) <= 64),
    lease_until timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    disconnected_at timestamptz,
    version integer not null default 1 check (version >= 1),
    -- A disconnected row keeps no credential, cursor or lease.
    constraint financial_source_connections_disconnected_is_empty check (
        status <> 'disconnected'
        or (secret_ciphertext is null and sync_cursor is null
            and attention_code is null and lease_holder is null
            and disconnected_at is not null)
    )
);

-- One live connection per provider reference across everyone: a Plaid Item or
-- a mailbox grant never backs two people's connections. Webhooks also resolve
-- by this pair, since they name the provider handle, not the person.
create unique index if not exists financial_source_connections_live_ref_idx
    on public.financial_source_connections (source, external_ref)
    where status <> 'disconnected';

create index if not exists financial_source_connections_user_idx
    on public.financial_source_connections (user_id, created_at, id);

alter table public.financial_source_connections enable row level security;

drop policy if exists financial_source_connections_owner_select
    on public.financial_source_connections;
create policy financial_source_connections_owner_select
    on public.financial_source_connections for select to authenticated
    using ((select auth.uid()) = user_id
           and ((select auth.jwt())->>'is_anonymous') is distinct from 'true');

revoke all on public.financial_source_connections from public, anon, authenticated;
-- Column grant: the credential envelope and lease are never client-readable.
grant select (
    id, user_id, source, status, label, last_success_at, last_attempt_at,
    last_error_code, attention_code, attention_at, created_at, updated_at, disconnected_at, version
) on public.financial_source_connections to authenticated;
grant all on public.financial_source_connections to service_role;
