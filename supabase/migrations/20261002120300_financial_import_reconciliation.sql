-- Import reconciliation: connector evidence grouped into reviewable events.
-- Spec: docs/specs/lanes/financial-ingestion-connectors.md.
--
-- Observations are what each source said; events group observations of the
-- same real-world fact and hold the person's review. None of these rows is a
-- financial record: canonical activity is written only through the existing
-- money service after the person confirms, and an event then points at it.
-- Clients may read their own rows; every write is server-side.

create table if not exists public.financial_import_events (
    id uuid primary key,
    user_id uuid not null references auth.users(id) on delete cascade,
    state text not null check (state in ('open', 'accepting', 'accepted', 'dismissed')),
    evidence text not null check (evidence in (
        'transaction', 'balance', 'statement_period', 'due_notice',
        'payment_notice', 'unclassified'
    )),
    anchor_on date,
    attention text check (attention is null or attention in (
        'source_changed', 'source_removed', 'possible_duplicate', 'ambiguous_match'
    )),
    attention_detail jsonb,
    possible_duplicates uuid[] not null default '{}',
    resolution jsonb not null default '{}'::jsonb,
    activity_id uuid,
    accept_key text check (accept_key is null or char_length(accept_key) between 1 and 80),
    created_at timestamptz not null,
    updated_at timestamptz not null,
    version integer not null check (version >= 1),
    -- An accepted event always names its record; an open one never does.
    constraint financial_import_events_activity_matches_state check (
        (state = 'accepted') = (activity_id is not null)
    ),
    unique (id, user_id)
);

-- One import event per recorded activity: the same purchase cannot be
-- accepted, or linked, twice.
create unique index if not exists financial_import_events_activity_idx
    on public.financial_import_events (user_id, activity_id)
    where activity_id is not null;
create index if not exists financial_import_events_anchor_idx
    on public.financial_import_events (user_id, anchor_on);
create index if not exists financial_import_events_state_idx
    on public.financial_import_events (user_id, state, created_at, id);

create table if not exists public.financial_import_observations (
    id uuid primary key,
    user_id uuid not null,
    event_id uuid not null,
    connection_id uuid not null
        references public.financial_source_connections(id) on delete cascade,
    source text not null check (source in ('plaid', 'gmail', 'shortcuts', 'statement')),
    external_id text not null check (char_length(external_id) between 1 and 200),
    fingerprint text not null check (fingerprint ~ '^[0-9a-f]{64}$'),
    candidate jsonb not null,
    live boolean not null,
    revisions integer not null check (revisions >= 1),
    first_seen_at timestamptz not null,
    updated_at timestamptz not null,
    foreign key (event_id, user_id)
        references public.financial_import_events (id, user_id) on delete cascade,
    unique (user_id, connection_id, external_id)
);

create index if not exists financial_import_observations_event_idx
    on public.financial_import_observations (event_id);
create index if not exists financial_import_observations_connection_idx
    on public.financial_import_observations (user_id, connection_id);

-- A person-confirmed mapping from a source's account hint to their account.
create table if not exists public.financial_import_account_links (
    user_id uuid not null,
    connection_id uuid not null
        references public.financial_source_connections(id) on delete cascade,
    account_key text not null check (char_length(account_key) between 1 and 220),
    account_id uuid not null,
    created_at timestamptz not null,
    primary key (user_id, connection_id, account_key),
    foreign key (account_id, user_id)
        references public.financial_accounts (id, user_id) on delete cascade
);

alter table public.financial_import_events enable row level security;
alter table public.financial_import_observations enable row level security;
alter table public.financial_import_account_links enable row level security;

drop policy if exists financial_import_events_owner_select on public.financial_import_events;
create policy financial_import_events_owner_select on public.financial_import_events
    for select to authenticated
    using ((select auth.uid()) = user_id
           and ((select auth.jwt())->>'is_anonymous') is distinct from 'true');
drop policy if exists financial_import_observations_owner_select
    on public.financial_import_observations;
create policy financial_import_observations_owner_select
    on public.financial_import_observations for select to authenticated
    using ((select auth.uid()) = user_id
           and ((select auth.jwt())->>'is_anonymous') is distinct from 'true');
drop policy if exists financial_import_account_links_owner_select
    on public.financial_import_account_links;
create policy financial_import_account_links_owner_select
    on public.financial_import_account_links for select to authenticated
    using ((select auth.uid()) = user_id
           and ((select auth.jwt())->>'is_anonymous') is distinct from 'true');

revoke all on public.financial_import_events, public.financial_import_observations,
    public.financial_import_account_links from public, anon, authenticated;
grant select on public.financial_import_events, public.financial_import_observations,
    public.financial_import_account_links to authenticated;
grant all on public.financial_import_events, public.financial_import_observations,
    public.financial_import_account_links to service_role;
