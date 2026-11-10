-- Thorough research runs ride the existing job lifecycle (spec
-- 2026-08-07-research-to-test-rail.md section 3: one progress mechanism, not
-- two). The scope check must admit the research scope; the admission RPC keeps
-- rejecting it because research jobs are created directly, never admitted as
-- backtests.

alter table public.backtest_jobs
    drop constraint if exists backtest_jobs_operation_scope_check;

alter table public.backtest_jobs
    add constraint backtest_jobs_operation_scope_check
        check (
            operation_scope in (
                'chat.run_backtest',
                'backtests.run',
                'chat.research'
            )
        );
