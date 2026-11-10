-- Apple Shortcuts device tokens (one per Shortcuts connection).
-- Spec: docs/reports/evidence/ingestion-shortcuts/README.md.
--
-- Only the SHA-256 digest of the device token is stored; the token itself is
-- shown to the person once at enrollment and never kept. The row is deleted
-- when the device is disconnected, and intake also requires the connection to
-- be live. Clients have no access at all: the API checks tokens server-side.

create table if not exists public.financial_shortcut_device_tokens (
    connection_id uuid primary key
        references public.financial_source_connections(id) on delete cascade,
    user_id uuid not null references auth.users(id) on delete cascade,
    token_sha256 bytea not null check (octet_length(token_sha256) = 32),
    created_at timestamptz not null default now()
);

create index if not exists financial_shortcut_device_tokens_user_idx
    on public.financial_shortcut_device_tokens (user_id);

alter table public.financial_shortcut_device_tokens enable row level security;

-- No policies: row level security with none denies every client role.
revoke all on public.financial_shortcut_device_tokens from public, anon, authenticated;
grant all on public.financial_shortcut_device_tokens to service_role;
