-- Forward-only indexes proven by issue #232 EXPLAIN ANALYZE measurements.

create index if not exists idx_conversations_active_page
on public.conversations (user_id, pinned desc, updated_at desc, id desc)
where deleted_at is null;

-- The predicate is intentionally a superset of both reload and lifecycle
-- artifact filters. Their stricter value checks remain query-owned.
create index if not exists idx_messages_reload_artifact_page
on public.messages (user_id, conversation_id, created_at, id)
where role = 'assistant'
  and (
      metadata->>'active_confirmation_reference' <> ''
      or metadata->>'backtest_job' <> ''
      or metadata->>'backtest_job_id' <> ''
      or metadata->>'confirmation_card' <> ''
      or metadata->>'confirmation_payload' <> ''
      or metadata->>'latest_run_id' <> ''
      or metadata->>'result_card' <> ''
      or metadata->>'result_run_id' <> ''
      or metadata->'artifact_references'
          @> '[{"artifact_kind": "confirmation"}]'::jsonb
      or metadata->'artifact_references'
          @> '[{"artifact_kind": "result"}]'::jsonb
      or metadata->'artifact_references'
          @> '[{"artifact_kind": "backtest_result"}]'::jsonb
      or metadata->'artifact_references'
          @> '[{"artifact_kind": "backtest_job"}]'::jsonb
  );

create index if not exists idx_decision_notes_idea_latest
on public.decision_notes (user_id, idea_id, updated_at desc, id desc);

-- Rollback:
-- drop index if exists public.idx_decision_notes_idea_latest;
-- drop index if exists public.idx_messages_reload_artifact_page;
-- drop index if exists public.idx_conversations_active_page;
