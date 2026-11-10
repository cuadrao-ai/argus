-- Durable asynchronous execution jobs for the private-alpha backtest boundary.
-- Jobs are lifecycle records only. Completed simulation truth remains in
-- public.backtest_runs.

create table if not exists public.backtest_jobs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  conversation_id uuid not null references public.conversations(id) on delete cascade,
  request_message_id uuid references public.messages(id) on delete set null,
  confirmation_message_id uuid references public.messages(id) on delete set null,
  idempotency_key text,
  payload_hash text not null,
  launch_payload jsonb not null,
  status text not null default 'queued' check (
    status in ('queued', 'running', 'succeeded', 'failed', 'canceled', 'expired')
  ),
  priority text not null default 'normal' check (priority in ('normal')),
  attempts integer not null default 0 check (attempts >= 0),
  max_attempts integer not null default 1 check (max_attempts >= 1),
  queued_at timestamptz not null default now(),
  started_at timestamptz,
  finished_at timestamptz,
  result_run_id uuid references public.backtest_runs(id) on delete set null,
  failure_code text,
  failure_detail text,
  retryable boolean not null default false,
  execution_metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_backtest_jobs_user_status_queued
  on public.backtest_jobs(user_id, status, queued_at desc);

create index if not exists idx_backtest_jobs_conversation_created
  on public.backtest_jobs(conversation_id, created_at desc);

create index if not exists idx_backtest_jobs_result_run
  on public.backtest_jobs(result_run_id);

create unique index if not exists idx_backtest_jobs_user_idempotency_key
  on public.backtest_jobs(user_id, idempotency_key)
  where idempotency_key is not null;

create index if not exists idx_backtest_jobs_user_payload_hash
  on public.backtest_jobs(user_id, payload_hash, created_at desc);

alter table public.backtest_jobs enable row level security;

drop policy if exists backtest_jobs_owner_select on public.backtest_jobs;
create policy backtest_jobs_owner_select
  on public.backtest_jobs
  for select
  to authenticated
  using (user_id = auth.uid());

grant select on table public.backtest_jobs to authenticated;
grant all privileges on table public.backtest_jobs to service_role;
