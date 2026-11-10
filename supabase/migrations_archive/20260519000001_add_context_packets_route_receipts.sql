-- Context packets and LLM route receipts for pre-private-launch hardening.
-- Context packets are contextual snapshots only; they are never simulation truth.

create table if not exists public.context_packets (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  provider text not null check (provider in ('fred', 'alpaca')),
  packet_type text not null check (packet_type in ('macro', 'news', 'corporate_actions', 'market_movers', 'most_actives')),
  scope jsonb not null default '{}'::jsonb,
  source_ids text[] not null default '{}'::text[],
  retrieved_at timestamptz not null,
  coverage_start date,
  coverage_end date,
  freshness text not null default 'unknown' check (freshness in ('fresh', 'stale', 'unknown')),
  facts jsonb not null default '[]'::jsonb,
  limitations text[] not null default '{}'::text[],
  not_for text not null default 'simulation_truth' check (not_for = 'simulation_truth'),
  packet jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.run_context_packets (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  run_id uuid not null references public.backtest_runs(id) on delete cascade,
  context_packet_id uuid not null references public.context_packets(id) on delete restrict,
  explanation_id text,
  attached_at timestamptz not null default now(),
  immutable_snapshot boolean not null default true,
  unique(run_id, context_packet_id)
);

create table if not exists public.route_receipts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.profiles(id) on delete set null,
  conversation_id uuid references public.conversations(id) on delete set null,
  run_id uuid references public.backtest_runs(id) on delete set null,
  message_id uuid references public.messages(id) on delete set null,
  task text not null,
  tier text not null check (tier in ('utility', 'chat', 'structured', 'context')),
  model text,
  fallback_model text,
  mode text not null check (mode in ('json_schema', 'chat_model')),
  schema_name text,
  latency_ms integer not null default 0,
  outcome text not null check (outcome in ('succeeded', 'failed', 'skipped')),
  failure_mode text,
  fallback_used boolean not null default false,
  token_usage jsonb,
  context_packet_ids text[] not null default '{}'::text[],
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_context_packets_user_provider on public.context_packets(user_id, provider, packet_type, retrieved_at desc);
create index if not exists idx_context_packets_scope_gin on public.context_packets using gin(scope);
create index if not exists idx_run_context_packets_run on public.run_context_packets(run_id);
create index if not exists idx_route_receipts_user_created on public.route_receipts(user_id, created_at desc);
create index if not exists idx_route_receipts_conversation on public.route_receipts(conversation_id, created_at desc);

alter table public.context_packets enable row level security;
alter table public.run_context_packets enable row level security;
alter table public.route_receipts enable row level security;

drop policy if exists context_packets_owner_all on public.context_packets;
create policy context_packets_owner_all on public.context_packets for all using (user_id = auth.uid()) with check (user_id = auth.uid());

drop policy if exists run_context_packets_owner_all on public.run_context_packets;
create policy run_context_packets_owner_all on public.run_context_packets for all using (user_id = auth.uid()) with check (user_id = auth.uid());

drop policy if exists route_receipts_owner_all on public.route_receipts;
create policy route_receipts_owner_all on public.route_receipts for all using (user_id = auth.uid()) with check (user_id = auth.uid());

grant all privileges on table public.context_packets to service_role;
grant all privileges on table public.run_context_packets to service_role;
grant all privileges on table public.route_receipts to service_role;
