-- Gmail connector: the sender allowlist each person chooses per mailbox.
-- Spec: docs/specs/lanes/financial-ingestion-connectors.md and
-- docs/reports/evidence/ingestion-gmail/README.md.
--
-- Relevance is the person's choice, not an interpretation of email content:
-- only messages from these addresses or domains (and their subdomains) are
-- read. backfilled_at marks when a sender's lookback window was last searched
-- so a sender added later is searched once. Rows hold sender addresses and
-- domains only, never message content. The owner may read them; every write
-- is server-side, where the API checks the connection is live and theirs.

create table if not exists public.financial_source_gmail_senders (
    connection_id uuid not null
        references public.financial_source_connections(id) on delete cascade,
    user_id uuid not null references auth.users(id) on delete cascade,
    sender text not null check (
        char_length(sender) between 3 and 254
        and sender = lower(sender)
        and sender !~ '[[:space:]()":,<>]'
    ),
    created_at timestamptz not null default now(),
    backfilled_at timestamptz,
    primary key (connection_id, sender)
);

create index if not exists financial_source_gmail_senders_user_idx
    on public.financial_source_gmail_senders (user_id);

alter table public.financial_source_gmail_senders enable row level security;

drop policy if exists financial_source_gmail_senders_owner_select
    on public.financial_source_gmail_senders;
create policy financial_source_gmail_senders_owner_select
    on public.financial_source_gmail_senders for select to authenticated
    using ((select auth.uid()) = user_id
           and ((select auth.jwt())->>'is_anonymous') is distinct from 'true');

revoke all on public.financial_source_gmail_senders from public, anon, authenticated;
grant select (connection_id, user_id, sender, created_at, backfilled_at)
    on public.financial_source_gmail_senders to authenticated;
grant all on public.financial_source_gmail_senders to service_role;
