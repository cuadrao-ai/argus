-- A Render workflow proof job is not conversation work.
--
-- workflows/proof.py seeded proof jobs without an operation_scope, so the
-- column default 'chat.run_backtest' applied, and the proof task then flipped
-- each row to succeeded with no run, by design. To every activity reader that
-- row was a finished chat backtest whose result could not be hydrated, so the
-- settle rule (argus.domain.job_settlement, rendered as
-- argus_private.backtest_job_result_hydrateable) projected 'checking' for as
-- long as the row existed. One such row landed per canary warmup. Production
-- 2026-09-04: 148 seeded proof rows across 18 conversations.
--
-- The settle rule is unchanged: a succeeded chat job without a readable run
-- must keep reading as unsettled. What was wrong was the row's claim to be a
-- chat job at all. A proof job now carries its own scope and no conversation,
-- and every activity reader joins jobs to a conversation, so the row is
-- unrepresentable as conversation activity rather than filtered out of it.
--
-- The constraint block below is rendered from
-- argus.domain.backtest_job_scopes.render_scope_check_constraint and pinned to
-- it by tests/test_workflow_proof_jobs_migration.py; the scope tuple there is
-- the one owner of every scope value.
--
-- The seeder's rows are reclassified by its own signature,
-- launch_payload.created_by. Chat jobs that a proof-shadow deployment once
-- dispatched to the proof task keep their scope and conversation: they were
-- chat runs, and their settlement is owed to their linked run.

alter table public.backtest_jobs
    drop constraint if exists backtest_jobs_operation_scope_check;

alter table public.backtest_jobs
    add constraint backtest_jobs_operation_scope_check
        check (
            operation_scope in (
                'chat.run_backtest',
                'backtests.run',
                'chat.research',
                'workflows.proof'
            )
        );

update public.backtest_jobs
   set operation_scope = 'workflows.proof',
       conversation_id = null,
       updated_at = now()
 where launch_payload ->> 'created_by' = 'workflows.proof_cli'
   and (
     operation_scope <> 'workflows.proof'
     or conversation_id is not null
   );
