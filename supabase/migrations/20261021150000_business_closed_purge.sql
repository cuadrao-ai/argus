begin;
set local lock_timeout='5s';
set local statement_timeout='60s';

create table argus_private.business_purge_runs (
    id uuid primary key default gen_random_uuid(),
    space_id uuid not null unique,
    closed_at timestamptz not null,
    status text not null default 'started' check(status in ('started','data_deleted','done')),
    placeholder_id uuid,
    claim_id uuid,
    claimed_until timestamptz,
    started_at timestamptz not null default clock_timestamp(),
    completed_at timestamptz,
    check((claim_id is null)=(claimed_until is null)),
    check((status='done')=(completed_at is not null)),
    check(status<>'done' or placeholder_id is null)
);
create index business_purge_pending_idx on argus_private.business_purge_runs(started_at) where status<>'done';
create table argus_private.business_purge_objects (
    run_id uuid not null references argus_private.business_purge_runs(id) on delete cascade,
    path text not null,
    deleted_at timestamptz,
    primary key(run_id,path)
);
alter table argus_private.business_purge_runs enable row level security;
alter table argus_private.business_purge_objects enable row level security;
revoke all on argus_private.business_purge_runs,argus_private.business_purge_objects from public,anon,authenticated,service_role;
comment on table argus_private.business_purge_runs is 'Postgres-only day-30 retry receipt. The original close date gates graph deletion. Claims serialize sweep passes. Placeholder ID is erased after verified Auth absence. No Business name or real account ID is retained.';
comment on table argus_private.business_purge_objects is 'Exact original, rebuilt and reserved orphan-copy cleanup plan persisted before Business cascades. Paths are removed at settlement. Shared live references prevent object removal.';
create index spaces_business_purge_due_idx on public.spaces(closed_at,id) where kind='business' and closed_at is not null;
commit;
