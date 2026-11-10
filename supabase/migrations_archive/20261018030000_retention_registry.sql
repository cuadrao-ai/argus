set local lock_timeout = '5s';
set local statement_timeout = '60s';

create table argus_private.retention_policies (
    table_name text primary key
        check (table_name ~ '^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*$'),
    rule text not null check (length(btrim(rule)) > 0),
    basis text not null check (length(btrim(basis)) > 0)
);

create table argus_private.retention_sweeps (
    id uuid primary key default gen_random_uuid(),
    table_name text not null references argus_private.retention_policies(table_name),
    started_at timestamptz not null,
    finished_at timestamptz not null check (finished_at >= started_at),
    outcome text not null check (outcome in ('succeeded', 'failed', 'dry_run')),
    rows_affected bigint check (rows_affected >= 0),
    rule text not null check (length(btrim(rule)) > 0),
    basis text not null check (length(btrim(basis)) > 0),
    check (outcome = 'failed' or rows_affected is not null),
    check (outcome <> 'dry_run' or rows_affected = 0)
);

create index retention_sweeps_table_finished_idx
    on argus_private.retention_sweeps (table_name, finished_at desc);

alter table argus_private.retention_policies enable row level security;
alter table argus_private.retention_sweeps enable row level security;
revoke all on table argus_private.retention_policies,
    argus_private.retention_sweeps from public, anon, authenticated, service_role;
grant usage on schema argus_private to service_role;
grant select, insert, update on table argus_private.retention_policies to service_role;
grant select, insert on table argus_private.retention_sweeps to service_role;

comment on table argus_private.retention_policies is
    'Inventory of existing retention rules and their source owners. Descriptive metadata only; no deletion executor or schedule reads this table.';
comment on table argus_private.retention_sweeps is
    'Append-only terminal sweep evidence. No automatic writer is installed. No user identifiers, raw input, or error payloads belong here; retention of this operational evidence remains undecided.';
comment on column argus_private.retention_sweeps.id is
    'Caller may supply a stable UUID for duplicate-safe recording of one table in one sweep attempt.';
comment on column argus_private.retention_sweeps.rule is
    'Snapshot of the rule used by the attempt, preserved when the registry changes.';
comment on column argus_private.retention_sweeps.basis is
    'Snapshot of the source owner used by the attempt. Store a repository reference, never customer data.';
comment on column argus_private.retention_sweeps.rows_affected is
    'Actual affected rows, zero for dry runs; may be unknown on failure. This is not the count of eligible rows.';

insert into argus_private.retention_policies (table_name, rule, basis) values
    ('public.guest_workspaces',
     'Fixed seven-day expiry. Existing cleanup rechecks anonymous identity and eligibility, removes its permitted graph, and deletes the auth identity transactionally. Converted or permanent accounts are preserved.',
     'docs/DATA_MODEL.md#51-guest_workspaces; scripts/ops/cleanup_expired_guest_workspaces.py; public.claim_expired_guest_workspaces'),
    ('public.visitor_usage_counters',
     'Delete rows whose period_end is at or before the supplied cutoff through purge_expired_visitor_usage. Runs only when the existing guest cleanup operator job reaches this purge.',
     'docs/DATA_MODEL.md#constraints-access-and-retention; src/argus/domain/guest_cleanup.py::EXPIRING_DATA_PURGES; public.purge_expired_visitor_usage'),
    ('public.guest_funnel_milestones',
     'Claims expire 30 days after recording. Delete rows whose expires_at is at or before the supplied cutoff through purge_expired_guest_funnel_milestones when the existing guest cleanup operator job reaches it.',
     'docs/DATA_MODEL.md#constraints-access-and-retention; src/argus/domain/guest_cleanup.py::EXPIRING_DATA_PURGES; public.purge_expired_guest_funnel_milestones'),
    ('public.cuadrao_early_access_signups',
     'Existing cuadrao_waitlist_purge deletes rows with privacy_policy_version set when unconfirmed and at least seven days old, or at least twelve months after created_at. Each call handles at most 100 rows. Existing leave deletes the enrolled row immediately.',
     'supabase/migrations/20261017010000_personal_waitlist_confirmation.sql; public.cuadrao_waitlist_purge; supabase/migrations/20261017020000_waitlist_supabase_scheduling.sql');
