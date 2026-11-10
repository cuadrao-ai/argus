-- Argus Alpha core schema.
-- Source of truth: docs/DATA_MODEL.md.

create extension if not exists pgcrypto;

create or replace function public.set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text not null,
  username text unique,
  display_name text,
  language text not null default 'en' check (language in ('en', 'es-419')),
  locale text not null default 'en-US' check (locale in ('en-US', 'es-419')),
  theme text not null default 'dark' check (theme in ('dark', 'light', 'system')),
  is_admin boolean not null default false,
  onboarding jsonb not null default '{"completed":false,"stage":"language_selection","language_confirmed":false,"primary_goal":null}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.conversations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  title text not null,
  title_source text not null default 'system_default' check (title_source in ('system_default', 'ai_generated', 'user_renamed')),
  language text check (language in ('en', 'es-419')),
  pinned boolean not null default false,
  archived boolean not null default false,
  deleted_at timestamptz,
  last_message_preview text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.conversations(id) on delete cascade,
  user_id uuid not null references public.profiles(id) on delete cascade,
  role text not null check (role in ('user', 'assistant', 'system', 'tool')),
  content text not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.strategies (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  conversation_id uuid references public.conversations(id) on delete set null,
  name text not null,
  name_source text not null default 'system_default' check (name_source in ('system_default', 'ai_generated', 'user_renamed')),
  template text not null,
  asset_class text not null check (asset_class in ('equity', 'crypto')),
  symbols text[] not null check (array_length(symbols, 1) between 1 and 5),
  parameters jsonb not null default '{}'::jsonb,
  metrics_preferences text[] not null default array['total_return_pct','win_rate','max_drawdown_pct'],
  benchmark_symbol text not null,
  pinned boolean not null default false,
  deleted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.collections (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  name text not null,
  name_source text not null default 'system_default' check (name_source in ('system_default', 'ai_generated', 'user_renamed')),
  description text,
  pinned boolean not null default false,
  deleted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.collection_strategies (
  id uuid primary key default gen_random_uuid(),
  collection_id uuid not null references public.collections(id) on delete cascade,
  strategy_id uuid not null references public.strategies(id) on delete cascade,
  user_id uuid not null references public.profiles(id) on delete cascade,
  created_at timestamptz not null default now(),
  unique(collection_id, strategy_id)
);

create table if not exists public.backtest_runs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  conversation_id uuid references public.conversations(id) on delete set null,
  strategy_id uuid references public.strategies(id) on delete set null,
  status text not null default 'queued' check (status in ('queued', 'running', 'completed', 'failed')),
  asset_class text not null check (asset_class in ('equity', 'crypto')),
  symbols text[] not null check (array_length(symbols, 1) between 1 and 5),
  allocation_method text not null default 'equal_weight' check (allocation_method = 'equal_weight'),
  benchmark_symbol text not null,
  config_snapshot jsonb not null,
  metrics jsonb not null default '{"aggregate":{},"by_symbol":{}}'::jsonb,
  conversation_result_card jsonb not null default '{}'::jsonb,
  chart jsonb,
  trades jsonb,
  error jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.feedback (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.profiles(id) on delete set null,
  type text not null check (type in ('bug', 'feature', 'general')),
  message text not null,
  context jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.usage_counters (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  resource text not null check (resource in ('chat_messages', 'backtest_runs')),
  period text not null check (period in ('hour', 'day')),
  period_start timestamptz not null,
  period_end timestamptz not null,
  used_count integer not null default 0,
  limit_count integer not null,
  updated_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  unique(user_id, resource, period, period_start)
);

create index if not exists idx_profiles_username on public.profiles(username);
create index if not exists idx_conversations_user_updated on public.conversations(user_id, updated_at desc);
create index if not exists idx_conversations_archive_delete on public.conversations(user_id, archived, deleted_at);
create index if not exists idx_conversations_pinned on public.conversations(user_id, pinned);
create index if not exists idx_messages_conversation_created on public.messages(conversation_id, created_at desc);
create index if not exists idx_strategies_user_updated on public.strategies(user_id, updated_at desc);
create index if not exists idx_strategies_pinned on public.strategies(user_id, pinned);
create index if not exists idx_strategies_deleted on public.strategies(user_id, deleted_at);
create index if not exists idx_strategies_symbols_gin on public.strategies using gin(symbols);
create index if not exists idx_collections_user_updated on public.collections(user_id, updated_at desc);
create index if not exists idx_collections_pinned on public.collections(user_id, pinned);
create index if not exists idx_collections_deleted on public.collections(user_id, deleted_at);
create index if not exists idx_collection_strategies_collection on public.collection_strategies(collection_id);
create index if not exists idx_collection_strategies_strategy on public.collection_strategies(strategy_id);
create index if not exists idx_backtest_runs_user_created on public.backtest_runs(user_id, created_at desc);
create index if not exists idx_backtest_runs_conversation on public.backtest_runs(conversation_id);
create index if not exists idx_backtest_runs_strategy on public.backtest_runs(strategy_id);
create index if not exists idx_backtest_runs_symbols_gin on public.backtest_runs using gin(symbols);
create index if not exists idx_feedback_user_created on public.feedback(user_id, created_at desc);
create index if not exists idx_usage_counters_user_period on public.usage_counters(user_id, resource, period_start desc);
create index if not exists idx_usage_counters_period_end on public.usage_counters(period_end);

alter table public.profiles enable row level security;
alter table public.conversations enable row level security;
alter table public.messages enable row level security;
alter table public.strategies enable row level security;
alter table public.collections enable row level security;
alter table public.collection_strategies enable row level security;
alter table public.backtest_runs enable row level security;
alter table public.feedback enable row level security;
alter table public.usage_counters enable row level security;

drop policy if exists profiles_owner_select on public.profiles;
create policy profiles_owner_select on public.profiles for select using (id = auth.uid());
drop policy if exists profiles_owner_update on public.profiles;
create policy profiles_owner_update on public.profiles for update using (id = auth.uid());

drop policy if exists conversations_owner_all on public.conversations;
create policy conversations_owner_all on public.conversations for all using (user_id = auth.uid()) with check (user_id = auth.uid());
drop policy if exists messages_owner_all on public.messages;
create policy messages_owner_all on public.messages for all using (user_id = auth.uid()) with check (user_id = auth.uid());
drop policy if exists strategies_owner_all on public.strategies;
create policy strategies_owner_all on public.strategies for all using (user_id = auth.uid()) with check (user_id = auth.uid());
drop policy if exists collections_owner_all on public.collections;
create policy collections_owner_all on public.collections for all using (user_id = auth.uid()) with check (user_id = auth.uid());
drop policy if exists collection_strategies_owner_all on public.collection_strategies;
create policy collection_strategies_owner_all on public.collection_strategies for all using (user_id = auth.uid()) with check (user_id = auth.uid());
drop policy if exists backtest_runs_owner_all on public.backtest_runs;
create policy backtest_runs_owner_all on public.backtest_runs for all using (user_id = auth.uid()) with check (user_id = auth.uid());
drop policy if exists feedback_owner_all on public.feedback;
create policy feedback_owner_all on public.feedback for all using (user_id = auth.uid()) with check (user_id = auth.uid());
drop policy if exists usage_counters_owner_all on public.usage_counters;
create policy usage_counters_owner_all on public.usage_counters for all using (user_id = auth.uid()) with check (user_id = auth.uid());

grant usage on schema public to anon, authenticated, service_role;
grant all privileges on all tables in schema public to service_role;
grant all privileges on all sequences in schema public to service_role;
grant all privileges on all functions in schema public to service_role;
