-- Ordered indexes proven by issue #232 state-page EXPLAIN ANALYZE measurements.

create index if not exists idx_conversations_deleted_page
on public.conversations (user_id, pinned desc, updated_at desc, id desc)
where deleted_at is not null;

create index if not exists idx_strategies_history_page
on public.strategies (user_id, pinned desc, updated_at desc, id desc);

create index if not exists idx_collections_history_page
on public.collections (user_id, pinned desc, updated_at desc, id desc);

-- Rollback (indexes are independently disposable):
-- drop index if exists public.idx_collections_history_page;
-- drop index if exists public.idx_strategies_history_page;
-- drop index if exists public.idx_conversations_deleted_page;
