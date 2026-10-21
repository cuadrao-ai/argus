-- Business search memory, per member and per Business: the searches a member
-- ran (recents) and the records they opened from a result (opens), which rank
-- higher in that member's next search. Only the API reads and writes them,
-- for the signed-in member in the Business their live grant names; clients
-- hold no grant. A row goes with its member or with its Business.

create table public.business_search_recents (
    id uuid primary key default gen_random_uuid(),
    space_id uuid not null references public.spaces (id) on delete cascade,
    user_id uuid not null references auth.users (id) on delete cascade,
    query text not null check (char_length(query) between 1 and 512),
    -- The query folded as search folds it: one recent per meaning.
    query_key text not null check (char_length(query_key) > 0),
    searched_at timestamptz not null default clock_timestamp(),
    unique (space_id, user_id, query_key)
);
create index business_search_recents_member_idx
    on public.business_search_recents (space_id, user_id, searched_at desc);
create index business_search_recents_user_idx
    on public.business_search_recents (user_id);

create table public.business_search_opens (
    space_id uuid not null references public.spaces (id) on delete cascade,
    user_id uuid not null references auth.users (id) on delete cascade,
    kind text not null check (
        kind in (
            'expenses', 'ventas', 'receipts', 'accounts',
            'email_deliveries', 'email_senders'
        )
    ),
    record_id uuid not null,
    opened_count integer not null default 1 check (opened_count > 0),
    last_opened_at timestamptz not null default clock_timestamp(),
    primary key (space_id, user_id, kind, record_id)
);
create index business_search_opens_member_idx
    on public.business_search_opens (space_id, user_id, last_opened_at desc);
create index business_search_opens_user_idx
    on public.business_search_opens (user_id);

alter table public.business_search_recents enable row level security;
alter table public.business_search_opens enable row level security;

revoke all on public.business_search_recents
    from public, anon, authenticated, service_role;
revoke all on public.business_search_opens
    from public, anon, authenticated, service_role;
grant select, insert, update, delete on public.business_search_recents to service_role;
grant select, insert, update, delete on public.business_search_opens to service_role;
