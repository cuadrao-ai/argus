-- Retire the research rail's unobserved success score. No rows are rewritten.
-- Legacy discovery and every other source still require a status. Preserve
-- the existing default for older writers: new rail inserts explicitly use NULL.
-- DROP NOT NULL is classified destructive by the promotion gate. The founder
-- applies this migration before promoting the application change.
-- Rollback: revert application code, retaining this compatible schema and all
-- historical rows. Do not restore NOT NULL by rewriting versioned NULL rows.

alter table public.cost_ledger_entries alter column status drop not null;

alter table public.cost_ledger_entries
  add constraint cost_ledger_entries_status_required
  check (status is not null or (source = 'research' and feature_area = 'research_rail'));
