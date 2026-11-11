-- Keep usage counter resources aligned with the Alpha data model and API quota
-- callers. Feedback quota writes use this table before inserting feedback rows.
alter table public.usage_counters
  drop constraint if exists usage_counters_resource_check;

alter table public.usage_counters
  add constraint usage_counters_resource_check
  check (
    resource in (
      'chat_messages',
      'backtest_runs',
      'backtest_jobs',
      'feedback'
    )
  );
