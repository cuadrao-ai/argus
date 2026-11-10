-- Allow generation 0 on a projection: the sentinel for a ref attached without
-- a reconciliation claim. Real generations start at 1, so 0 never reads as
-- current. Widening a check only; no existing row becomes invalid.

alter table public.memory_provider_projections
  drop constraint if exists memory_provider_projections_generation_check;

alter table public.memory_provider_projections
  add constraint memory_provider_projections_generation_check
  check (generation >= 0);
