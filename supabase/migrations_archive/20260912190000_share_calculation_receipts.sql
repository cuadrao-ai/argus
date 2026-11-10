-- A computed answer is a receipt kind of its own under schema version 2.
-- Additive: the kind check gains 'calculation'; every existing row already
-- satisfies it, and the immutability trigger keeps guarding the column.
alter table public.public_excerpt_snapshots
  drop constraint if exists public_excerpt_snapshots_kind_check,
  add constraint public_excerpt_snapshots_kind_check
    check (kind in ('backtest', 'research_answer', 'calculation', 'mixed'));
