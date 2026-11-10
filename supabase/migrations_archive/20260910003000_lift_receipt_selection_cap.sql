-- The four-turn cap on a shared selection was never a founder decision; it was
-- written while resolving a spec conflict (conversation-sharing.md section
-- 4.5, since amended). A selection is one or more distinct eligible turns of
-- one conversation, and nothing about its size is a rule. Lifting the upper
-- bounds rewrites no rows and removes no objects other than the two check
-- constraints that carried the cap.
alter table public.public_excerpt_snapshots
  drop constraint public_excerpt_selection_bounds,
  add constraint public_excerpt_selection_bounds check (
    (selection_key is null and cardinality(source_message_ids) = 0)
    or (selection_key is not null and cardinality(source_message_ids) >= 1)
  ),
  drop constraint public_excerpt_secondary_sources_bounded;
