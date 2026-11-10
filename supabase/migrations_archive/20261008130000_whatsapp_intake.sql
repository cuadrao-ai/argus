-- WhatsApp receipt intake: sender links, one-time link codes, inbound deliveries.
-- Spec: docs/specs/lanes/cuadrao-whatsapp-intake.md.
--
-- destination_owner_id is whoever owns captured receipts. Today that is the
-- signed-in person; under the pending Business boundary it becomes the business
-- principal. Both are auth.users rows, so the column stays neutral.
--
-- reply_language is the web language the owner used when asking for the link
-- code; WhatsApp replies use it, not profiles.language (whose default is en).
--
-- Phone numbers and provider message ids are never stored. Both are kept as
-- HMAC-SHA256 digests under a server key; provider message ids can embed the
-- sender's number. Clients have no access: only the API's service role reads
-- or writes these tables.

create table if not exists public.whatsapp_link_codes (
    id uuid primary key default gen_random_uuid(),
    destination_owner_id uuid not null references auth.users(id) on delete cascade,
    code_digest bytea not null unique check (octet_length(code_digest) = 32),
    reply_language text not null check (reply_language in ('es-419', 'en')),
    created_at timestamptz not null,
    expires_at timestamptz not null,
    consumed_at timestamptz,
    check (expires_at > created_at)
);

create index if not exists whatsapp_link_codes_destination_idx
    on public.whatsapp_link_codes (destination_owner_id);

create table if not exists public.whatsapp_sender_links (
    id uuid primary key default gen_random_uuid(),
    destination_owner_id uuid not null references auth.users(id) on delete cascade,
    wa_id_hash bytea not null check (octet_length(wa_id_hash) = 32),
    last4 text not null check (last4 ~ '^[0-9]{1,4}$'),
    reply_language text not null check (reply_language in ('es-419', 'en')),
    status text not null check (status in ('active', 'revoked')),
    linked_at timestamptz not null,
    revoked_at timestamptz,
    check ((status = 'active') = (revoked_at is null))
);

create index if not exists whatsapp_sender_links_destination_idx
    on public.whatsapp_sender_links (destination_owner_id);

-- One active destination per sender, and one active sender per destination.
create unique index if not exists whatsapp_sender_links_active_sender_idx
    on public.whatsapp_sender_links (wa_id_hash)
    where status = 'active';

create unique index if not exists whatsapp_sender_links_active_destination_idx
    on public.whatsapp_sender_links (destination_owner_id)
    where status = 'active';

create table if not exists public.whatsapp_inbound_messages (
    id uuid primary key default gen_random_uuid(),
    provider_message_key bytea not null unique
        check (octet_length(provider_message_key) = 32),
    sender_hash bytea not null check (octet_length(sender_hash) = 32),
    destination_owner_id uuid references auth.users(id) on delete cascade,
    status text not null
        check (status in ('received', 'linked', 'rejected', 'captured', 'failed')),
    connection_id uuid
        references public.financial_source_connections(id) on delete cascade,
    error_code text check (error_code is null or char_length(error_code) <= 64),
    claim_until timestamptz,
    received_at timestamptz not null,
    updated_at timestamptz not null,
    check (status <> 'captured' or connection_id is not null),
    check (status not in ('captured', 'linked') or destination_owner_id is not null)
);

create index if not exists whatsapp_inbound_messages_destination_idx
    on public.whatsapp_inbound_messages (destination_owner_id)
    where destination_owner_id is not null;

create index if not exists whatsapp_inbound_messages_connection_idx
    on public.whatsapp_inbound_messages (connection_id)
    where connection_id is not null;

alter table public.whatsapp_link_codes enable row level security;
alter table public.whatsapp_sender_links enable row level security;
alter table public.whatsapp_inbound_messages enable row level security;

-- No policies: row level security with none denies every client role.
revoke all on public.whatsapp_link_codes from public, anon, authenticated;
revoke all on public.whatsapp_sender_links from public, anon, authenticated;
revoke all on public.whatsapp_inbound_messages from public, anon, authenticated;
grant all on public.whatsapp_link_codes to service_role;
grant all on public.whatsapp_sender_links to service_role;
grant all on public.whatsapp_inbound_messages to service_role;
