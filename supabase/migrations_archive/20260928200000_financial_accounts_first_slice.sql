-- Financial accounts, first slice: create, reopen, edit, correct the opening.
-- Spec: docs/specs/lanes/financial-accounts-first-slice.md.
--
-- Ownership is one fact, financial_accounts.user_id. Records and revisions
-- carry it too so row-level security stays an indexed equality, and composite
-- foreign keys force the copies to agree with the account. Writes are owned by
-- the two functions below; clients hold no insert or update grant.

create table if not exists public.financial_accounts (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    space_id text not null default 'personal',
    type text not null check (type in (
        'cash', 'checking', 'savings', 'investment', 'credit_card',
        'other_debt', 'property', 'vehicle', 'other_asset'
    )),
    currency text not null check (currency ~ '^[A-Z]{3}$'),
    nickname text check (nickname is null or char_length(nickname) between 1 and 60),
    archived boolean not null default false,
    ownership_share_bps integer not null default 10000
        check (ownership_share_bps between 1 and 10000),
    version integer not null default 1 check (version >= 1),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (id, user_id)
);

create index if not exists financial_accounts_user_created_idx
    on public.financial_accounts (user_id, created_at asc, id asc);

drop trigger if exists set_financial_accounts_updated_at on public.financial_accounts;
create trigger set_financial_accounts_updated_at
before update on public.financial_accounts
for each row execute function public.set_updated_at();

create table if not exists public.financial_records (
    id uuid primary key default gen_random_uuid(),
    account_id uuid not null,
    user_id uuid not null,
    record_kind text not null check (record_kind in ('opening_balance')),
    current_revision integer not null default 1 check (current_revision >= 1),
    created_at timestamptz not null default now(),
    foreign key (account_id, user_id)
        references public.financial_accounts (id, user_id) on delete cascade,
    unique (id, user_id)
);

-- One opening anchor per account.
create unique index if not exists financial_records_one_opening_idx
    on public.financial_records (account_id)
    where record_kind = 'opening_balance';

create table if not exists public.financial_record_revisions (
    id uuid primary key default gen_random_uuid(),
    record_id uuid not null,
    user_id uuid not null,
    revision integer not null check (revision >= 1),
    amount_minor bigint not null,
    as_of timestamptz not null,
    as_of_zone text not null,
    reason text check (reason is null or char_length(reason) between 1 and 200),
    capture_method text not null default 'manual' check (capture_method in ('manual')),
    -- Who made the revision. Kept when that user is later deleted, the way
    -- guest_workspaces.claimed_by is, so history never loses a row.
    recorded_by uuid references auth.users(id) on delete set null,
    recorded_at timestamptz not null default now(),
    foreign key (record_id, user_id)
        references public.financial_records (id, user_id) on delete cascade,
    unique (record_id, revision)
);

create index if not exists financial_record_revisions_user_idx
    on public.financial_record_revisions (user_id);

-- The create reservation, keyed the way backtest admission is:
-- (user_id, operation_scope, idempotency_key). Same identity replays, a
-- different identity conflicts.
create table if not exists public.financial_account_idempotency (
    user_id uuid not null references auth.users(id) on delete cascade,
    operation_scope text not null check (operation_scope in ('financial_accounts.create')),
    idempotency_key text not null,
    identity_hash text not null,
    account_id uuid not null references public.financial_accounts(id) on delete cascade,
    created_at timestamptz not null default now(),
    primary key (user_id, operation_scope, idempotency_key)
);

-- Create an account, and its opening when a balance was given, or replay.
-- The reservation row is written last inside the same transaction, so a
-- concurrent duplicate blocks on the primary key and then re-reads.
create or replace function public.create_financial_account(
    p_user_id uuid,
    p_idempotency_key text,
    p_identity_hash text,
    p_type text,
    p_currency text,
    p_nickname text,
    p_ownership_share_bps integer,
    p_opening_amount_minor bigint,
    p_opening_as_of timestamptz,
    p_opening_zone text
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_reserved public.financial_account_idempotency%rowtype;
    v_account_id uuid;
    v_record_id uuid;
    v_now timestamptz := now();
begin
    if not exists (
        select 1 from auth.users u
        where u.id = p_user_id and coalesce(u.is_anonymous, false) = false
    ) then
        return jsonb_build_object('decision', 'registered_required');
    end if;

    select * into v_reserved
    from public.financial_account_idempotency
    where user_id = p_user_id
      and operation_scope = 'financial_accounts.create'
      and idempotency_key = p_idempotency_key
    for update;
    if found then
        if v_reserved.identity_hash = p_identity_hash then
            return jsonb_build_object('decision', 'replay', 'account_id', v_reserved.account_id);
        end if;
        return jsonb_build_object('decision', 'conflict');
    end if;

    begin
        insert into public.financial_accounts (
            user_id, type, currency, nickname, ownership_share_bps, created_at, updated_at
        )
        values (p_user_id, p_type, p_currency, p_nickname, p_ownership_share_bps, v_now, v_now)
        returning id into v_account_id;

        if p_opening_amount_minor is not null then
            insert into public.financial_records (account_id, user_id, record_kind, created_at)
            values (v_account_id, p_user_id, 'opening_balance', v_now)
            returning id into v_record_id;
            insert into public.financial_record_revisions (
                record_id, user_id, revision, amount_minor, as_of, as_of_zone,
                reason, recorded_by, recorded_at
            )
            values (
                v_record_id, p_user_id, 1, p_opening_amount_minor, p_opening_as_of,
                p_opening_zone, null, p_user_id, v_now
            );
        end if;

        insert into public.financial_account_idempotency (
            user_id, operation_scope, idempotency_key, identity_hash, account_id, created_at
        )
        values (
            p_user_id, 'financial_accounts.create', p_idempotency_key,
            p_identity_hash, v_account_id, v_now
        );
    exception when unique_violation then
        -- A concurrent request with the same key committed first. Decide from
        -- its committed row; this transaction's account insert rolls back.
        select * into v_reserved
        from public.financial_account_idempotency
        where user_id = p_user_id
          and operation_scope = 'financial_accounts.create'
          and idempotency_key = p_idempotency_key;
        if v_reserved.identity_hash = p_identity_hash then
            return jsonb_build_object('decision', 'replay', 'account_id', v_reserved.account_id);
        end if;
        return jsonb_build_object('decision', 'conflict');
    end;

    return jsonb_build_object('decision', 'created', 'account_id', v_account_id);
end;
$$;

revoke all on function public.create_financial_account(
    uuid, text, text, text, text, text, integer, bigint, timestamptz, text
) from public, anon, authenticated;
grant execute on function public.create_financial_account(
    uuid, text, text, text, text, text, integer, bigint, timestamptz, text
) to service_role;

-- Record a first opening (p_expected_revision null) or append a correction
-- (p_expected_revision = the current revision). The caller must supply the
-- account version it saw when composing the write (p_expected_version); that
-- version is compared under the account lock so a concurrent currency/type
-- edit cannot apply under metadata the caller never saw. Any mismatch writes
-- nothing.
create or replace function public.write_financial_opening(
    p_user_id uuid,
    p_account_id uuid,
    p_expected_revision integer,
    p_expected_version integer,
    p_amount_minor bigint,
    p_as_of timestamptz,
    p_zone text,
    p_reason text
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_account public.financial_accounts%rowtype;
    v_record public.financial_records%rowtype;
    v_next integer;
    v_now timestamptz := now();
begin
    if not exists (
        select 1 from auth.users u
        where u.id = p_user_id and coalesce(u.is_anonymous, false) = false
    ) then
        return jsonb_build_object('decision', 'registered_required');
    end if;

    select * into v_account
    from public.financial_accounts
    where id = p_account_id and user_id = p_user_id
    for update;
    if not found then
        return jsonb_build_object('decision', 'not_found');
    end if;
    if v_account.version is distinct from p_expected_version then
        return jsonb_build_object('decision', 'stale');
    end if;

    select * into v_record
    from public.financial_records
    where account_id = p_account_id and record_kind = 'opening_balance'
    for update;

    if (found and v_record.current_revision is distinct from p_expected_revision)
       or (not found and p_expected_revision is not null) then
        return jsonb_build_object('decision', 'stale');
    end if;

    if not found then
        insert into public.financial_records (account_id, user_id, record_kind, created_at)
        values (p_account_id, p_user_id, 'opening_balance', v_now)
        returning * into v_record;
        v_next := 1;
    else
        v_next := v_record.current_revision + 1;
        update public.financial_records
        set current_revision = v_next
        where id = v_record.id;
    end if;

    insert into public.financial_record_revisions (
        record_id, user_id, revision, amount_minor, as_of, as_of_zone,
        reason, recorded_by, recorded_at
    )
    values (
        v_record.id, p_user_id, v_next, p_amount_minor, p_as_of, p_zone,
        p_reason, p_user_id, v_now
    );

    update public.financial_accounts
    set version = version + 1
    where id = p_account_id;

    return jsonb_build_object(
        'decision', 'written', 'record_id', v_record.id, 'revision', v_next
    );
end;
$$;

revoke all on function public.write_financial_opening(
    uuid, uuid, integer, integer, bigint, timestamptz, text, text
) from public, anon, authenticated;
grant execute on function public.write_financial_opening(
    uuid, uuid, integer, integer, bigint, timestamptz, text, text
) to service_role;

-- Owner-only, registered-only reads. Supabase anonymous users share the
-- authenticated role, so the trusted JWT claim keeps guests out, the same
-- shape profiles use for preferred_name. Writes have no client path.
alter table public.financial_accounts enable row level security;
alter table public.financial_records enable row level security;
alter table public.financial_record_revisions enable row level security;
alter table public.financial_account_idempotency enable row level security;

drop policy if exists financial_accounts_owner_select on public.financial_accounts;
create policy financial_accounts_owner_select
    on public.financial_accounts
    for select
    to authenticated
    using (
        (select auth.uid()) = user_id
        and ((select auth.jwt()) ->> 'is_anonymous') is distinct from 'true'
    );

drop policy if exists financial_records_owner_select on public.financial_records;
create policy financial_records_owner_select
    on public.financial_records
    for select
    to authenticated
    using (
        (select auth.uid()) = user_id
        and ((select auth.jwt()) ->> 'is_anonymous') is distinct from 'true'
    );

drop policy if exists financial_record_revisions_owner_select on public.financial_record_revisions;
create policy financial_record_revisions_owner_select
    on public.financial_record_revisions
    for select
    to authenticated
    using (
        (select auth.uid()) = user_id
        and ((select auth.jwt()) ->> 'is_anonymous') is distinct from 'true'
    );

revoke all on table public.financial_accounts from public, anon, authenticated;
revoke all on table public.financial_records from public, anon, authenticated;
revoke all on table public.financial_record_revisions from public, anon, authenticated;
revoke all on table public.financial_account_idempotency from public, anon, authenticated;
grant select on table public.financial_accounts to authenticated;
grant select on table public.financial_records to authenticated;
grant select on table public.financial_record_revisions to authenticated;
grant all privileges on table public.financial_accounts to service_role;
grant all privileges on table public.financial_records to service_role;
grant all privileges on table public.financial_record_revisions to service_role;
grant all privileges on table public.financial_account_idempotency to service_role;
