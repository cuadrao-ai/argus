-- Existing selected-turn snapshots also support a plain final answer.
-- No new table, policy, or ownership behavior.
alter table public.public_excerpt_snapshots
  drop constraint if exists public_excerpt_snapshots_kind_check,
  add constraint public_excerpt_snapshots_kind_check
    check (kind in ('backtest', 'research_answer', 'calculation', 'answer', 'mixed'));
