set local lock_timeout = '5s';
set local statement_timeout = '60s';

insert into argus_private.retention_policies (table_name, rule, basis) values
    ('argus_private.retention_sweeps',
     'Retain terminal sweep evidence for 24 calendar months after finished_at. A future separately approved executor may delete rows when finished_at + interval ''24 months'' is at or before its cutoff. This policy installs no purge executor or schedule.',
     'supabase/migrations/20261018210000_retention_sweeps_24_month_window.sql; docs/reports/evidence/retention-sweeps-window/implementation.md')
on conflict (table_name) do update
set rule = excluded.rule, basis = excluded.basis;

comment on table argus_private.retention_sweeps is
    'Append-only terminal sweep evidence. Retention window: see argus_private.retention_policies. Operational metadata comprises attempt IDs, row counts, timestamps, outcome, table identifier, and repository rule/source snapshots. No user identifiers, PII, customer input, raw errors, or payloads belong here. This is a writer contract, not a content constraint. No automatic writer, purge executor, or schedule is installed.';
