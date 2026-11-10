-- LangGraph checkpoint tables store runtime thread memory, not product records
-- meant for Supabase client access. Keep direct Postgres owner access for the
-- API checkpointer, but enable RLS in the exposed public schema and make the
-- browser-facing roles explicitly unable to read or mutate checkpoint rows.

create table if not exists public.checkpoint_migrations (
  v integer primary key
);

create table if not exists public.checkpoints (
  thread_id text not null,
  checkpoint_ns text not null default '',
  checkpoint_id text not null,
  parent_checkpoint_id text,
  type text,
  checkpoint jsonb not null,
  metadata jsonb not null default '{}',
  primary key (thread_id, checkpoint_ns, checkpoint_id)
);

create table if not exists public.checkpoint_blobs (
  thread_id text not null,
  checkpoint_ns text not null default '',
  channel text not null,
  version text not null,
  type text not null,
  blob bytea,
  primary key (thread_id, checkpoint_ns, channel, version)
);

create table if not exists public.checkpoint_writes (
  thread_id text not null,
  checkpoint_ns text not null default '',
  checkpoint_id text not null,
  task_id text not null,
  idx integer not null,
  channel text not null,
  type text,
  blob bytea not null,
  task_path text not null default '',
  primary key (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);

alter table public.checkpoint_blobs alter column blob drop not null;
alter table public.checkpoint_writes
  add column if not exists task_path text not null default '';

create index if not exists checkpoints_thread_id_idx
  on public.checkpoints(thread_id);
create index if not exists checkpoint_blobs_thread_id_idx
  on public.checkpoint_blobs(thread_id);
create index if not exists checkpoint_writes_thread_id_idx
  on public.checkpoint_writes(thread_id);

revoke all on table public.checkpoint_blobs from public, anon, authenticated;
revoke all on table public.checkpoint_migrations from public, anon, authenticated;
revoke all on table public.checkpoint_writes from public, anon, authenticated;
revoke all on table public.checkpoints from public, anon, authenticated;

alter table public.checkpoint_blobs enable row level security;
alter table public.checkpoint_migrations enable row level security;
alter table public.checkpoint_writes enable row level security;
alter table public.checkpoints enable row level security;
