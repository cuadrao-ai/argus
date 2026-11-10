-- Guest conversion handoff and atomic product-graph transfer.
--
-- Exact-head foreign-key inventory at c482cae9:
-- * The transferred workspace graph is conversations -> messages,
--   backtest_jobs, backtest_runs, conversation-scoped strategies, ideas,
--   idea_versions, evidence_artifacts, decision_notes, context_packets, and
--   run_context_packets.
-- * LangGraph checkpoint tables have no user owner column. Their thread_id is
--   the unchanged conversation id, so transfer deliberately leaves checkpoint
--   rows and thread identity untouched.
-- * Guest usage_counters and feedback remain with the source anonymous owner.
--   They are deleted only when that Auth user is safely removed after claim.
-- * route_receipts and cost_ledger_entries are immutable audit/operational
--   evidence. Their user attribution is not rewritten as destination activity.
-- * Collections are not a guest capability. A source collection or a product
--   row outside the one bound conversation fails the claim closed.

create schema if not exists argus_private;
revoke all on schema argus_private from public, anon, authenticated;
grant usage on schema argus_private to service_role;

create or replace function argus_private.valid_guest_pending_action(
  p_action jsonb,
  p_conversation_id uuid
)
returns boolean
language plpgsql
immutable
strict
set search_path = ''
as $$
declare
  v_key text;
  v_reason text;
begin
  if jsonb_typeof(p_action) <> 'object' then
    return false;
  end if;
  for v_key in select jsonb_object_keys(p_action)
  loop
    if v_key not in ('reason', 'conversation_id', 'action_id', 'artifact_id') then
      return false;
    end if;
  end loop;

  v_reason := p_action ->> 'reason';
  if v_reason not in (
    'second_simulation',
    'message_limit',
    'save_decision',
    'new_conversation',
    'keep_history'
  ) then
    return false;
  end if;
  if nullif(p_action ->> 'conversation_id', '') is distinct from p_conversation_id::text
     or nullif(p_action ->> 'action_id', '') is null then
    return false;
  end if;
  if v_reason = 'save_decision' then
    return nullif(p_action ->> 'artifact_id', '') is not null;
  end if;
  return not (p_action ? 'artifact_id');
end;
$$;

revoke all on function argus_private.valid_guest_pending_action(jsonb, uuid)
  from public, anon, authenticated;
grant execute on function argus_private.valid_guest_pending_action(jsonb, uuid)
  to service_role;

create table public.guest_workspace_handoffs (
  id uuid primary key default gen_random_uuid(),
  secret_hash text not null unique
    check (secret_hash ~ '^[0-9a-f]{64}$'),
  source_user_id uuid not null
    references public.guest_workspaces(user_id) on delete cascade,
  destination_user_id uuid not null
    references public.profiles(id) on delete restrict,
  source_conversation_id uuid not null
    references public.conversations(id) on delete cascade,
  pending_action jsonb,
  status text not null default 'pending'
    check (status in ('pending', 'consumed', 'revoked')),
  created_at timestamptz not null default now(),
  expires_at timestamptz not null default (now() + interval '10 minutes'),
  consumed_at timestamptz,
  constraint guest_workspace_handoff_fixed_expiry
    check (expires_at = created_at + interval '10 minutes'),
  constraint guest_workspace_handoff_pending_action_valid
    check (
      pending_action is null
      or argus_private.valid_guest_pending_action(
        pending_action,
        source_conversation_id
      )
    ),
  constraint guest_workspace_handoff_consumption_state
    check (
      (status = 'consumed' and consumed_at is not null)
      or (status <> 'consumed' and consumed_at is null)
    )
);

create index guest_workspace_handoffs_pending_expiry_idx
  on public.guest_workspace_handoffs (expires_at, id)
  where status = 'pending';
create index guest_workspace_handoffs_source_idx
  on public.guest_workspace_handoffs (source_user_id, source_conversation_id);
create unique index guest_workspace_handoffs_one_pending_source_idx
  on public.guest_workspace_handoffs (source_user_id)
  where status = 'pending';
create index guest_workspace_handoffs_destination_idx
  on public.guest_workspace_handoffs (destination_user_id, status);

alter table public.guest_workspace_handoffs enable row level security;
revoke all on table public.guest_workspace_handoffs from public, anon, authenticated;
grant all privileges on table public.guest_workspace_handoffs to service_role;

-- Preserve the evidence spine's immutable payload guarantees while permitting
-- only the owner-id rewrite executed inside the private claim function.
create or replace function public.prevent_idea_version_immutable_update()
returns trigger
language plpgsql
security invoker
set search_path = public
as $$
declare
  v_owner_transfer boolean :=
    current_user = 'postgres'
    and current_setting('argus.owner_transfer', true) = 'on';
begin
  if new.id is distinct from old.id
    or (new.user_id is distinct from old.user_id and not v_owner_transfer)
    or new.idea_id is distinct from old.idea_id
    or new.source_conversation_id is distinct from old.source_conversation_id
    or new.source_run_id is distinct from old.source_run_id
    or new.version_number is distinct from old.version_number
    or new.canonical_spec is distinct from old.canonical_spec
    or new.strategy_snapshot is distinct from old.strategy_snapshot
    or new.title is distinct from old.title
    or new.summary is distinct from old.summary
    or new.created_at is distinct from old.created_at then
    raise exception 'idea_versions immutable fields cannot be updated'
      using errcode = '23514';
  end if;
  return new;
end;
$$;

create or replace function public.prevent_evidence_artifact_immutable_update()
returns trigger
language plpgsql
security invoker
set search_path = public
as $$
declare
  v_owner_transfer boolean :=
    current_user = 'postgres'
    and current_setting('argus.owner_transfer', true) = 'on';
begin
  if new.id is distinct from old.id
    or (new.user_id is distinct from old.user_id and not v_owner_transfer)
    or new.idea_id is distinct from old.idea_id
    or new.idea_version_id is distinct from old.idea_version_id
    or new.source_conversation_id is distinct from old.source_conversation_id
    or new.source_run_id is distinct from old.source_run_id
    or new.artifact_type is distinct from old.artifact_type
    or new.title is distinct from old.title
    or new.digest is distinct from old.digest
    or new.payload is distinct from old.payload
    or new.created_at is distinct from old.created_at then
    raise exception 'evidence_artifacts immutable fields cannot be updated'
      using errcode = '23514';
  end if;
  return new;
end;
$$;

create or replace function argus_private.claim_guest_workspace_handoff(
  p_handoff_id uuid,
  p_secret_hash text,
  p_destination_user_id uuid
)
returns table (
  source_user_id uuid,
  destination_user_id uuid,
  conversation_id uuid,
  pending_action jsonb
)
language plpgsql
security definer
set search_path = ''
as $$
#variable_conflict use_column
declare
  v_handoff public.guest_workspace_handoffs%rowtype;
  v_workspace public.guest_workspaces%rowtype;
  v_source_is_anonymous boolean;
  v_destination_is_anonymous boolean;
  v_destination_email text;
begin
  select *
    into v_handoff
    from public.guest_workspace_handoffs
   where id = p_handoff_id
   for update;

  if not found or v_handoff.secret_hash is distinct from p_secret_hash then
    raise exception 'guest_handoff_invalid' using errcode = 'P0002';
  end if;
  if v_handoff.status = 'consumed' then
    raise exception 'guest_handoff_consumed' using errcode = 'P0001';
  end if;
  if v_handoff.status <> 'pending' then
    raise exception 'guest_handoff_invalid' using errcode = 'P0002';
  end if;
  if v_handoff.expires_at <= now() then
    raise exception 'guest_handoff_expired' using errcode = 'P0001';
  end if;
  if v_handoff.destination_user_id is distinct from p_destination_user_id then
    raise exception 'guest_handoff_wrong_destination' using errcode = 'P0001';
  end if;

  select coalesce(is_anonymous, false)
    into v_source_is_anonymous
    from auth.users
   where id = v_handoff.source_user_id;
  select coalesce(is_anonymous, false), nullif(btrim(email), '')
    into v_destination_is_anonymous, v_destination_email
    from auth.users
   where id = p_destination_user_id;
  if not found or v_destination_is_anonymous or v_destination_email is null then
    raise exception 'guest_handoff_wrong_destination' using errcode = 'P0001';
  end if;
  if v_source_is_anonymous is not true then
    raise exception 'guest_handoff_source_not_anonymous' using errcode = 'P0001';
  end if;

  select *
    into v_workspace
    from public.guest_workspaces
   where user_id = v_handoff.source_user_id
   for update;
  if not found
     or v_workspace.status <> 'active'
     or v_workspace.expires_at <= now()
     or v_workspace.conversation_id is distinct from v_handoff.source_conversation_id then
    raise exception 'guest_handoff_workspace_unavailable' using errcode = 'P0001';
  end if;

  -- Every user-owned product row must belong to this one guest conversation,
  -- and every row anchored to that conversation must belong to the source.
  if exists (
      select 1 from public.conversations
       where (user_id = v_handoff.source_user_id and id <> v_handoff.source_conversation_id)
          or (id = v_handoff.source_conversation_id and user_id <> v_handoff.source_user_id)
    )
    or not exists (
      select 1 from public.conversations
       where id = v_handoff.source_conversation_id
         and user_id = v_handoff.source_user_id
    )
    or exists (
      select 1 from public.messages
       where (user_id = v_handoff.source_user_id and conversation_id <> v_handoff.source_conversation_id)
          or (conversation_id = v_handoff.source_conversation_id and user_id <> v_handoff.source_user_id)
    )
    or exists (
      select 1 from public.strategies
       where (user_id = v_handoff.source_user_id and conversation_id is distinct from v_handoff.source_conversation_id)
          or (conversation_id = v_handoff.source_conversation_id and user_id <> v_handoff.source_user_id)
    )
    or exists (
      select 1 from public.backtest_runs
       where (user_id = v_handoff.source_user_id and conversation_id is distinct from v_handoff.source_conversation_id)
          or (conversation_id = v_handoff.source_conversation_id and user_id <> v_handoff.source_user_id)
    )
    or exists (
      select 1 from public.backtest_jobs
       where (user_id = v_handoff.source_user_id and conversation_id <> v_handoff.source_conversation_id)
          or (conversation_id = v_handoff.source_conversation_id and user_id <> v_handoff.source_user_id)
    )
    or exists (
      select 1 from public.ideas
       where (user_id = v_handoff.source_user_id and source_conversation_id is distinct from v_handoff.source_conversation_id)
          or (source_conversation_id = v_handoff.source_conversation_id and user_id <> v_handoff.source_user_id)
    )
    or exists (
      select 1 from public.idea_versions
       where (user_id = v_handoff.source_user_id and source_conversation_id is distinct from v_handoff.source_conversation_id)
          or (source_conversation_id = v_handoff.source_conversation_id and user_id <> v_handoff.source_user_id)
    )
    or exists (
      select 1 from public.evidence_artifacts
       where (user_id = v_handoff.source_user_id and source_conversation_id is distinct from v_handoff.source_conversation_id)
          or (source_conversation_id = v_handoff.source_conversation_id and user_id <> v_handoff.source_user_id)
    )
    or exists (
      select 1 from public.decision_notes
       where (user_id = v_handoff.source_user_id and source_conversation_id is distinct from v_handoff.source_conversation_id)
          or (source_conversation_id = v_handoff.source_conversation_id and user_id <> v_handoff.source_user_id)
    )
    or exists (
      select 1
        from public.run_context_packets as link
        join public.backtest_runs as run on run.id = link.run_id
       where (link.user_id = v_handoff.source_user_id and run.user_id <> v_handoff.source_user_id)
          or (run.user_id = v_handoff.source_user_id and link.user_id <> v_handoff.source_user_id)
    )
    or exists (
      select 1 from public.collections where user_id = v_handoff.source_user_id
    )
    or exists (
      select 1 from public.collection_strategies where user_id = v_handoff.source_user_id
    ) then
    raise exception 'guest_handoff_unsafe_product_graph' using errcode = 'P0001';
  end if;

  perform set_config('argus.owner_transfer', 'on', true);

  update public.conversations
     set user_id = p_destination_user_id
   where id = v_handoff.source_conversation_id
     and user_id = v_handoff.source_user_id;
  update public.messages
     set user_id = p_destination_user_id
   where conversation_id = v_handoff.source_conversation_id
     and user_id = v_handoff.source_user_id;
  update public.strategies
     set user_id = p_destination_user_id
   where conversation_id = v_handoff.source_conversation_id
     and user_id = v_handoff.source_user_id;
  update public.backtest_runs
     set user_id = p_destination_user_id
   where conversation_id = v_handoff.source_conversation_id
     and user_id = v_handoff.source_user_id;
  update public.backtest_jobs
     set user_id = p_destination_user_id
   where conversation_id = v_handoff.source_conversation_id
     and user_id = v_handoff.source_user_id;
  update public.ideas
     set user_id = p_destination_user_id
   where source_conversation_id = v_handoff.source_conversation_id
     and user_id = v_handoff.source_user_id;
  update public.idea_versions
     set user_id = p_destination_user_id
   where source_conversation_id = v_handoff.source_conversation_id
     and user_id = v_handoff.source_user_id;
  update public.evidence_artifacts
     set user_id = p_destination_user_id
   where source_conversation_id = v_handoff.source_conversation_id
     and user_id = v_handoff.source_user_id;
  update public.decision_notes
     set user_id = p_destination_user_id
   where source_conversation_id = v_handoff.source_conversation_id
     and user_id = v_handoff.source_user_id;
  update public.context_packets
     set user_id = p_destination_user_id
   where user_id = v_handoff.source_user_id;
  update public.run_context_packets
     set user_id = p_destination_user_id
   where user_id = v_handoff.source_user_id;

  update public.guest_workspaces
     set status = 'claimed',
         claimed_by = p_destination_user_id,
         claimed_at = now(),
         updated_at = now()
   where user_id = v_handoff.source_user_id;
  update public.guest_workspace_handoffs
     set status = 'consumed',
         consumed_at = now()
   where id = v_handoff.id;

  return query
  select
    v_handoff.source_user_id,
    p_destination_user_id,
    v_handoff.source_conversation_id,
    v_handoff.pending_action;
end;
$$;

revoke all on function argus_private.claim_guest_workspace_handoff(uuid, text, uuid)
  from public, anon, authenticated;
grant execute on function argus_private.claim_guest_workspace_handoff(uuid, text, uuid)
  to service_role;

create or replace function public.claim_guest_workspace_handoff(
  p_handoff_id uuid,
  p_secret_hash text,
  p_destination_user_id uuid
)
returns table (
  source_user_id uuid,
  destination_user_id uuid,
  conversation_id uuid,
  pending_action jsonb
)
language sql
security invoker
set search_path = ''
as $$
  select *
    from argus_private.claim_guest_workspace_handoff(
      p_handoff_id,
      p_secret_hash,
      p_destination_user_id
    );
$$;

revoke all on function public.claim_guest_workspace_handoff(uuid, text, uuid)
  from public, anon, authenticated;
grant execute on function public.claim_guest_workspace_handoff(uuid, text, uuid)
  to service_role;
