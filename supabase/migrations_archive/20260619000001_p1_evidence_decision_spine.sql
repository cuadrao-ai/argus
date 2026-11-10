create table if not exists public.ideas (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  source_conversation_id uuid references public.conversations(id) on delete set null,
  title text not null,
  summary text not null default '',
  lifecycle text not null default 'captured' check (lifecycle in ('captured', 'reviewed', 'saved', 'decided', 'archived', 'discarded')),
  active_version_id uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.idea_versions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  idea_id uuid not null references public.ideas(id) on delete cascade,
  source_conversation_id uuid references public.conversations(id) on delete set null,
  source_run_id uuid references public.backtest_runs(id) on delete set null,
  version_number integer not null default 1,
  canonical_spec jsonb not null default '{}'::jsonb,
  strategy_snapshot jsonb not null default '{}'::jsonb,
  title text not null,
  summary text not null default '',
  lifecycle text not null default 'captured' check (lifecycle in ('captured', 'reviewed', 'saved', 'decided', 'archived', 'discarded')),
  created_at timestamptz not null default now(),
  unique(user_id, idea_id, version_number)
);

alter table public.ideas
  drop constraint if exists ideas_active_version_id_fkey;

alter table public.ideas
  add constraint ideas_active_version_id_fkey
  foreign key (active_version_id) references public.idea_versions(id) on delete set null;

create table if not exists public.evidence_artifacts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  idea_id uuid not null references public.ideas(id) on delete cascade,
  idea_version_id uuid not null references public.idea_versions(id) on delete cascade,
  source_conversation_id uuid references public.conversations(id) on delete set null,
  source_run_id uuid references public.backtest_runs(id) on delete set null,
  artifact_type text not null default 'backtest' check (artifact_type in ('backtest')),
  lifecycle text not null default 'captured' check (lifecycle in ('captured', 'reviewed', 'saved', 'decided', 'archived', 'discarded')),
  title text not null,
  digest text not null default '',
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(user_id, source_run_id)
);

create table if not exists public.decision_notes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  idea_id uuid not null references public.ideas(id) on delete cascade,
  idea_version_id uuid not null references public.idea_versions(id) on delete cascade,
  evidence_artifact_id uuid not null references public.evidence_artifacts(id) on delete cascade,
  source_conversation_id uuid references public.conversations(id) on delete set null,
  decision_state text not null check (decision_state in ('watching', 'promising', 'rejected', 'revisit_later')),
  note text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_ideas_user_updated on public.ideas(user_id, updated_at desc);
create index if not exists idx_ideas_user_lifecycle on public.ideas(user_id, lifecycle);
create index if not exists idx_idea_versions_user_idea on public.idea_versions(user_id, idea_id, created_at desc);
create index if not exists idx_evidence_artifacts_user_updated on public.evidence_artifacts(user_id, updated_at desc);
create index if not exists idx_evidence_artifacts_source_run on public.evidence_artifacts(user_id, source_run_id);
create index if not exists idx_decision_notes_user_updated on public.decision_notes(user_id, updated_at desc);
create index if not exists idx_decision_notes_artifact on public.decision_notes(user_id, evidence_artifact_id);
create index if not exists idx_decision_notes_state on public.decision_notes(user_id, decision_state);

alter table public.decision_notes
  drop constraint if exists decision_notes_user_artifact_unique;

alter table public.decision_notes
  add constraint decision_notes_user_artifact_unique
  unique(user_id, evidence_artifact_id);

drop trigger if exists set_ideas_updated_at on public.ideas;
create trigger set_ideas_updated_at
before update on public.ideas
for each row execute function public.set_updated_at();

drop trigger if exists set_evidence_artifacts_updated_at on public.evidence_artifacts;
create trigger set_evidence_artifacts_updated_at
before update on public.evidence_artifacts
for each row execute function public.set_updated_at();

drop trigger if exists set_decision_notes_updated_at on public.decision_notes;
create trigger set_decision_notes_updated_at
before update on public.decision_notes
for each row execute function public.set_updated_at();

alter table public.ideas enable row level security;
alter table public.idea_versions enable row level security;
alter table public.evidence_artifacts enable row level security;
alter table public.decision_notes enable row level security;

drop policy if exists ideas_owner_all on public.ideas;
create policy ideas_owner_all on public.ideas
  for all
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

drop policy if exists idea_versions_owner_all on public.idea_versions;
create policy idea_versions_owner_all on public.idea_versions
  for all
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

drop policy if exists evidence_artifacts_owner_all on public.evidence_artifacts;
create policy evidence_artifacts_owner_all on public.evidence_artifacts
  for all
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

drop policy if exists decision_notes_owner_all on public.decision_notes;
create policy decision_notes_owner_all on public.decision_notes
  for all
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

create or replace function public.upsert_current_decision_note(
  p_user_id uuid,
  p_evidence_artifact_id uuid,
  p_decision_id uuid,
  p_decision_state text,
  p_note text
)
returns table (
  decision jsonb,
  evidence_artifact jsonb,
  idea jsonb,
  idea_version jsonb
)
language plpgsql
security invoker
set search_path = public
as $$
declare
  artifact_row public.evidence_artifacts%rowtype;
  decision_row public.decision_notes%rowtype;
  idea_row public.ideas%rowtype;
  version_row public.idea_versions%rowtype;
begin
  select *
    into artifact_row
    from public.evidence_artifacts
   where user_id = p_user_id
     and id = p_evidence_artifact_id
   for update;

  if not found then
    raise exception 'Evidence artifact not found or not owned by user.'
      using errcode = 'P0002';
  end if;

  insert into public.decision_notes (
    id,
    user_id,
    idea_id,
    idea_version_id,
    evidence_artifact_id,
    source_conversation_id,
    decision_state,
    note
  )
  values (
    p_decision_id,
    p_user_id,
    artifact_row.idea_id,
    artifact_row.idea_version_id,
    artifact_row.id,
    artifact_row.source_conversation_id,
    p_decision_state,
    p_note
  )
  on conflict (user_id, evidence_artifact_id)
  do update set
    decision_state = excluded.decision_state,
    note = excluded.note,
    updated_at = now()
  returning * into decision_row;

  update public.evidence_artifacts
     set lifecycle = 'decided',
         updated_at = now()
   where user_id = p_user_id
     and id = artifact_row.id
  returning * into artifact_row;

  update public.ideas
     set lifecycle = 'decided',
         updated_at = now()
   where user_id = p_user_id
     and id = artifact_row.idea_id
  returning * into idea_row;

  update public.idea_versions
     set lifecycle = 'decided'
   where user_id = p_user_id
     and id = artifact_row.idea_version_id
  returning * into version_row;

  return query select
    to_jsonb(decision_row),
    to_jsonb(artifact_row),
    to_jsonb(idea_row),
    to_jsonb(version_row);
end;
$$;

grant all privileges on table public.ideas to service_role;
grant all privileges on table public.idea_versions to service_role;
grant all privileges on table public.evidence_artifacts to service_role;
grant all privileges on table public.decision_notes to service_role;
revoke all on function public.upsert_current_decision_note(uuid, uuid, uuid, text, text) from public;
revoke all on function public.upsert_current_decision_note(uuid, uuid, uuid, text, text) from anon;
revoke all on function public.upsert_current_decision_note(uuid, uuid, uuid, text, text) from authenticated;
grant execute on function public.upsert_current_decision_note(uuid, uuid, uuid, text, text) to service_role;
