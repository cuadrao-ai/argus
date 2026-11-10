-- Append-only operational cost ledger for Private Alpha measurement slice B3.3.
-- Rollback: drop table if exists public.cost_ledger_entries;

create table if not exists public.cost_ledger_entries (
  id uuid primary key default gen_random_uuid(),
  source text not null check (
    source in (
      'api_turn',
      'render_workflow',
      'eval_harness',
      'manual_reconciliation',
      'runtime_compute',
      'storage',
      'market_data',
      'stt',
      'research'
    )
  ),
  service text not null,
  provider text not null,
  model text,
  feature_area text not null,
  task text,
  user_id uuid references public.profiles(id) on delete set null,
  conversation_id uuid references public.conversations(id) on delete set null,
  message_id uuid references public.messages(id) on delete set null,
  backtest_run_id uuid references public.backtest_runs(id) on delete set null,
  backtest_job_id uuid references public.backtest_jobs(id) on delete set null,
  route_receipt_id uuid references public.route_receipts(id) on delete set null,
  request_id text,
  correlation_id text not null,
  provider_request_id text,
  upstream_id text,
  usage_metadata jsonb not null default '{}'::jsonb,
  input_tokens integer check (input_tokens is null or input_tokens >= 0),
  output_tokens integer check (output_tokens is null or output_tokens >= 0),
  total_tokens integer check (total_tokens is null or total_tokens >= 0),
  billable_unit text not null default 'unknown' check (
    billable_unit in (
      'token',
      'request',
      'compute_second',
      'audio_second',
      'storage_byte',
      'row',
      'unknown'
    )
  ),
  billable_quantity numeric(20, 6) check (
    billable_quantity is null or billable_quantity >= 0
  ),
  cost_amount numeric(18, 8) check (cost_amount is null or cost_amount >= 0),
  cost_currency text not null default 'USD',
  cost_source text not null default 'unavailable' check (
    cost_source in (
      'provider_reported',
      'estimated',
      'derived',
      'reconciled',
      'unavailable'
    )
  ),
  latency_ms integer check (latency_ms is null or latency_ms >= 0),
  status text not null default 'succeeded' check (
    status in ('succeeded', 'failed', 'skipped', 'estimated', 'reconciled')
  ),
  metadata jsonb not null default '{}'::jsonb,
  occurred_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

create index if not exists idx_cost_ledger_entries_user_created
  on public.cost_ledger_entries(user_id, created_at desc);

create index if not exists idx_cost_ledger_entries_conversation_created
  on public.cost_ledger_entries(conversation_id, created_at desc);

create index if not exists idx_cost_ledger_entries_run_created
  on public.cost_ledger_entries(backtest_run_id, created_at desc);

create index if not exists idx_cost_ledger_entries_route_receipt
  on public.cost_ledger_entries(route_receipt_id);

create index if not exists idx_cost_ledger_entries_correlation
  on public.cost_ledger_entries(correlation_id, created_at desc);

create index if not exists idx_cost_ledger_entries_source_created
  on public.cost_ledger_entries(source, created_at desc);

alter table public.cost_ledger_entries enable row level security;

-- Enforce append-only structurally: strip any privileges inherited from
-- Supabase default-privilege grants (which target service_role on new public
-- tables), then grant back insert + select only. Without the revoke, a prior
-- `grant all`/default-privilege grant would leave update/delete reachable for
-- service_role and the append-only guarantee would be convention, not enforced.
revoke all on table public.cost_ledger_entries from anon, authenticated, service_role;

grant insert, select on table public.cost_ledger_entries to service_role;
