-- Business bank statement lines and suggested matches.
-- Raw lines are immutable. A suggestion is one pair. Retention is 10 years.
-- No delete API. Space removal cascades with the space.

set local lock_timeout = '5s';
set local statement_timeout = '60s';

create table public.business_bank_accounts (
    id uuid primary key default gen_random_uuid(),
    space_id uuid not null references public.spaces (id) on delete cascade,
    account_id uuid not null references public.financial_accounts (id),
    currency text not null check (currency ~ '^[A-Z]{3}$'),
    created_at timestamptz not null default now(),
    unique (space_id),
    unique (id, space_id)
);

create index business_bank_accounts_account_idx
    on public.business_bank_accounts (account_id);

comment on table public.business_bank_accounts is
    'One bank account per Business space. Keep for 10 years. No delete API.';

create table public.business_bank_imports (
    id uuid primary key default gen_random_uuid(),
    space_id uuid not null references public.spaces (id) on delete cascade,
    bank_account_id uuid not null,
    reader_id text not null check (reader_id in (
        'pilot_bank', 'banco_popular', 'bhd', 'mercury', 'sandbox_csv', 'mapped_csv'
    )),
    source_sha256 text not null check (char_length(source_sha256) = 64),
    idempotency_key text not null check (char_length(idempotency_key) between 1 and 128),
    inserted_count integer not null check (inserted_count >= 0),
    unchanged_count integer not null check (unchanged_count >= 0),
    imported_by uuid not null references auth.users (id),
    imported_at timestamptz not null default now(),
    unique (id, space_id),
    unique (space_id, imported_by, idempotency_key),
    foreign key (bank_account_id, space_id)
        references public.business_bank_accounts (id, space_id) on delete cascade
);

create index business_bank_imports_account_idx
    on public.business_bank_imports (bank_account_id);
create index business_bank_imports_actor_idx
    on public.business_bank_imports (imported_by);
create index business_bank_imports_space_idx
    on public.business_bank_imports (space_id);

comment on table public.business_bank_imports is
    'One accepted statement upload. Keep for 10 years. No delete API.';

create table public.business_bank_lines (
    id uuid primary key default gen_random_uuid(),
    space_id uuid not null references public.spaces (id) on delete cascade,
    bank_account_id uuid not null,
    first_import_id uuid not null,
    occurred_on date not null,
    description text not null,
    normalized_description text not null,
    amount numeric(20, 4) not null,
    currency text not null check (currency ~ '^[A-Z]{3}$'),
    raw_line jsonb not null check (jsonb_typeof(raw_line) = 'object'),
    line_hash text not null check (char_length(line_hash) = 64),
    created_at timestamptz not null default now(),
    unique (id, space_id),
    unique (
        bank_account_id, occurred_on, amount, normalized_description, line_hash
    ),
    foreign key (bank_account_id, space_id)
        references public.business_bank_accounts (id, space_id) on delete cascade,
    foreign key (first_import_id, space_id)
        references public.business_bank_imports (id, space_id) on delete cascade
);

create index business_bank_lines_space_occurred_idx
    on public.business_bank_lines (space_id, occurred_on);
create index business_bank_lines_import_idx
    on public.business_bank_lines (first_import_id);

comment on table public.business_bank_lines is
    'Immutable raw statement lines. Keep for 10 years. No delete API. Re-import inserts or returns the existing row.';
comment on column public.business_bank_lines.raw_line is
    'The cells from the source row. Updates are refused.';
comment on column public.business_bank_lines.line_hash is
    'Hash of the raw cells plus the occurrence of that exact row in the file.';

create table public.business_bank_suggestions (
    id uuid primary key default gen_random_uuid(),
    space_id uuid not null references public.spaces (id) on delete cascade,
    line_id uuid not null,
    target_kind text not null check (target_kind in ('receipt', 'venta')),
    target_id text not null check (char_length(target_id) between 1 and 80),
    status text not null default 'pending'
        check (status in ('pending', 'confirmed', 'declined')),
    amount_score numeric(4, 3) not null check (amount_score between 0 and 1),
    date_score numeric(4, 3) not null check (date_score between 0 and 1),
    merchant_score numeric(4, 3) not null check (merchant_score between 0 and 1),
    created_at timestamptz not null default now(),
    decided_at timestamptz,
    decided_by uuid references auth.users (id) on delete set null,
    decision_key text,
    unique (line_id, target_kind, target_id),
    unique (id, space_id),
    foreign key (line_id, space_id)
        references public.business_bank_lines (id, space_id) on delete cascade,
    check (
        (status = 'pending' and decided_at is null and decision_key is null)
        or (
            status in ('confirmed', 'declined')
            and decided_at is not null
            and decision_key is not null
        )
    )
);

create unique index business_bank_suggestions_one_confirmed_idx
    on public.business_bank_suggestions (line_id)
    where status = 'confirmed';
create index business_bank_suggestions_space_idx
    on public.business_bank_suggestions (space_id, status);
create index business_bank_suggestions_target_idx
    on public.business_bank_suggestions (space_id, target_kind, target_id);
create index business_bank_suggestions_decided_by_idx
    on public.business_bank_suggestions (decided_by);

comment on table public.business_bank_suggestions is
    'One suggestion per line and target. Declined pairs stay so they are not offered again. Score parts are the historical offer. Confidence is not stored. Keep for 10 years.';

create function argus_private.business_bank_lines_immutable()
returns trigger
language plpgsql
as $$
begin
    raise exception 'business_bank_lines are immutable' using errcode = '55000';
end;
$$;

create trigger business_bank_lines_no_update
    before update on public.business_bank_lines
    for each row execute function argus_private.business_bank_lines_immutable();

create function argus_private.business_bank_suggestions_guard()
returns trigger
language plpgsql
as $$
begin
    if new.space_id is distinct from old.space_id
        or new.line_id is distinct from old.line_id
        or new.target_kind is distinct from old.target_kind
        or new.target_id is distinct from old.target_id
        or new.amount_score is distinct from old.amount_score
        or new.date_score is distinct from old.date_score
        or new.merchant_score is distinct from old.merchant_score
        or new.created_at is distinct from old.created_at
    then
        raise exception 'business_bank_suggestion offer is immutable'
            using errcode = '55000';
    end if;
    if old.status <> 'pending' and new.status is distinct from old.status then
        raise exception 'business_bank_suggestion decision is final'
            using errcode = '55000';
    end if;
    return new;
end;
$$;

create trigger business_bank_suggestions_guard
    before update on public.business_bank_suggestions
    for each row execute function argus_private.business_bank_suggestions_guard();

alter table public.business_bank_accounts enable row level security;
alter table public.business_bank_imports enable row level security;
alter table public.business_bank_lines enable row level security;
alter table public.business_bank_suggestions enable row level security;

revoke all on public.business_bank_accounts, public.business_bank_imports,
    public.business_bank_lines, public.business_bank_suggestions
    from public, anon, authenticated, service_role;

grant select, insert, update on public.business_bank_accounts,
    public.business_bank_imports, public.business_bank_lines,
    public.business_bank_suggestions to authenticated, service_role;

-- authenticated cannot select business_client_grants. The policy calls this
-- definer, which reads the grant as the function owner.
create function argus_private.business_bank_has_capability(
    target_space uuid,
    capability text
)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select exists (
        select 1
        from public.business_client_grants g
        where g.space_id = target_space
            and g.grantee_id = (select auth.uid())
            and g.revoked_at is null
            and (g.expires_at is null or g.expires_at > pg_catalog.now())
            and capability = any (g.capabilities)
    );
$$;

revoke all on function argus_private.business_bank_has_capability(uuid, text)
    from public, anon;
grant execute on function argus_private.business_bank_has_capability(uuid, text)
    to authenticated;

create policy business_bank_accounts_select on public.business_bank_accounts
    for select to authenticated
    using (argus_private.business_bank_has_capability(space_id, 'read'));

create policy business_bank_accounts_insert on public.business_bank_accounts
    for insert to authenticated
    with check (argus_private.business_bank_has_capability(space_id, 'prepare'));

create policy business_bank_accounts_update on public.business_bank_accounts
    for update to authenticated
    using (argus_private.business_bank_has_capability(space_id, 'prepare'))
    with check (argus_private.business_bank_has_capability(space_id, 'prepare'));

create policy business_bank_imports_select on public.business_bank_imports
    for select to authenticated
    using (argus_private.business_bank_has_capability(space_id, 'read'));

create policy business_bank_imports_insert on public.business_bank_imports
    for insert to authenticated
    with check (argus_private.business_bank_has_capability(space_id, 'prepare'));

create policy business_bank_lines_select on public.business_bank_lines
    for select to authenticated
    using (argus_private.business_bank_has_capability(space_id, 'read'));

create policy business_bank_lines_insert on public.business_bank_lines
    for insert to authenticated
    with check (argus_private.business_bank_has_capability(space_id, 'prepare'));

create policy business_bank_suggestions_select on public.business_bank_suggestions
    for select to authenticated
    using (argus_private.business_bank_has_capability(space_id, 'read'));

create policy business_bank_suggestions_insert on public.business_bank_suggestions
    for insert to authenticated
    with check (argus_private.business_bank_has_capability(space_id, 'prepare'));

create policy business_bank_suggestions_update on public.business_bank_suggestions
    for update to authenticated
    using (argus_private.business_bank_has_capability(space_id, 'prepare'))
    with check (argus_private.business_bank_has_capability(space_id, 'prepare'));

revoke all on function argus_private.business_bank_lines_immutable(),
    argus_private.business_bank_suggestions_guard()
    from public, anon, authenticated;
