-- Shared financial records retain one owner; coverage binds exact immutable revisions.
alter table public.financial_records drop constraint financial_records_record_kind_check;
alter table public.financial_records add constraint financial_records_record_kind_check
    check (record_kind in ('opening_balance', 'expense', 'balance_check'));
alter table public.financial_records add constraint financial_records_account_owner_key
    unique (id, account_id, user_id);
alter table public.financial_record_revisions add column details jsonb not null default '{}';
alter table public.financial_record_revisions add constraint financial_revision_owner_key
    unique (record_id, revision, user_id);

create table public.financial_observation_coverage (
    account_id uuid not null,
    user_id uuid not null,
    observation_id uuid not null,
    observation_revision integer not null,
    activity_id uuid not null,
    activity_revision integer not null,
    included boolean not null,
    primary key (observation_id, observation_revision, activity_id, activity_revision),
    check (observation_id <> activity_id),
    foreign key (observation_id, account_id, user_id)
        references public.financial_records(id, account_id, user_id) on delete cascade,
    foreign key (activity_id, account_id, user_id)
        references public.financial_records(id, account_id, user_id) on delete cascade,
    foreign key (observation_id, observation_revision, user_id)
        references public.financial_record_revisions(record_id, revision, user_id) on delete cascade,
    foreign key (activity_id, activity_revision, user_id)
        references public.financial_record_revisions(record_id, revision, user_id) on delete cascade
);
create index financial_observation_coverage_owner_account_idx
    on public.financial_observation_coverage(user_id, account_id);

create table public.financial_operation_receipts (
    user_id uuid not null,
    account_id uuid not null,
    idempotency_key text not null,
    identity_hash text not null,
    record_id uuid not null,
    revision integer not null,
    kind text not null check (kind in ('expense', 'balance_check', 'opening_balance')),
    created_at timestamptz not null default now(),
    primary key (user_id, account_id, idempotency_key),
    foreign key (record_id, account_id, user_id)
        references public.financial_records(id, account_id, user_id) on delete cascade,
    foreign key (record_id, revision, user_id)
        references public.financial_record_revisions(record_id, revision, user_id) on delete cascade
);

alter table public.financial_observation_coverage enable row level security;
alter table public.financial_operation_receipts enable row level security;
create policy financial_observation_coverage_owner_select
    on public.financial_observation_coverage for select to authenticated
    using ((select auth.uid()) = user_id
        and ((select auth.jwt()) ->> 'is_anonymous') is distinct from 'true');
revoke all on public.financial_observation_coverage from public, anon, authenticated;
revoke all on public.financial_operation_receipts from public, anon, authenticated;
grant select on public.financial_observation_coverage to authenticated;
grant all on public.financial_observation_coverage to service_role;
grant all on public.financial_operation_receipts to service_role;
