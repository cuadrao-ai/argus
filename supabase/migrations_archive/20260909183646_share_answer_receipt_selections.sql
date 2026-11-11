-- Extend the existing immutable receipt pipeline to a selected set of turns.
-- Source arrays stay private and retain provenance after revocation. No grants.
alter table public.public_excerpt_snapshots
  add column kind text not null default 'backtest' check (kind in ('backtest', 'research_answer', 'mixed')),
  add column source_message_ids uuid[] not null default '{}',
  add column source_run_ids uuid[] not null default '{}',
  add column source_artifact_ids uuid[] not null default '{}',
  add column selection_key text check (selection_key ~ '^[0-9a-f]{64}$'),
  add constraint public_excerpt_selection_bounds check (
    (selection_key is null and cardinality(source_message_ids) = 0)
    or (selection_key is not null and cardinality(source_message_ids) between 1 and 4)
  ),
  add constraint public_excerpt_secondary_sources_bounded check (
    cardinality(source_run_ids) <= 4 and cardinality(source_artifact_ids) <= 4
  );
create unique index idx_public_excerpt_snapshots_live_selection
  on public.public_excerpt_snapshots(owner_id, selection_key)
  where revoked_at is null and selection_key is not null;
create index idx_public_excerpt_snapshots_messages on public.public_excerpt_snapshots using gin(source_message_ids) where revoked_at is null;
create index idx_public_excerpt_snapshots_runs on public.public_excerpt_snapshots using gin(source_run_ids) where revoked_at is null;
create index idx_public_excerpt_snapshots_artifacts on public.public_excerpt_snapshots using gin(source_artifact_ids) where revoked_at is null;

create or replace function public.prevent_public_excerpt_immutable_update()
returns trigger
language plpgsql
security invoker
set search_path = public
as $$
begin
  if new.id is distinct from old.id
    or new.public_id is distinct from old.public_id
    or new.owner_id is distinct from old.owner_id
    or new.title is distinct from old.title
    or new.payload is distinct from old.payload
    or new.payload_digest is distinct from old.payload_digest
    or new.created_at is distinct from old.created_at
    or new.kind is distinct from old.kind
    or new.selection_key is distinct from old.selection_key
    or new.source_message_ids is distinct from old.source_message_ids
    or new.source_run_ids is distinct from old.source_run_ids
    or new.source_artifact_ids is distinct from old.source_artifact_ids then
    raise exception 'public_excerpt_snapshots immutable fields cannot be updated'
      using errcode = '23514';
  end if;

  if old.revoked_at is not null
    and (
      new.revoked_at is distinct from old.revoked_at
      or new.revocation_reason is distinct from old.revocation_reason
    ) then
    raise exception 'public_excerpt_snapshots revocation cannot be reversed'
      using errcode = '23514';
  end if;

  return new;
end;
$$;

create or replace function public.enforce_public_excerpt_source_is_live()
returns trigger language plpgsql security definer set search_path = '' as $$
declare
  v_deleted_at timestamptz;
  v_id uuid;
begin
  if new.source_conversation_id is null then
    if new.selection_key is not null then
      raise exception 'public_excerpt_source_missing' using errcode = '23514';
    end if;
    return new;
  end if;
  select deleted_at into v_deleted_at from public.conversations
   where id = new.source_conversation_id and user_id = new.owner_id for share;
  if not found then
    raise exception 'public_excerpt_source_missing' using errcode = '23514';
  end if;
  if v_deleted_at is not null then
    raise exception 'public_excerpt_source_deleted' using errcode = '23514';
  end if;
  -- Deterministic lock order across overlapping selections prevents inversion.
  for v_id in select distinct unnest(new.source_message_ids) order by 1 loop
    perform 1 from public.messages where id = v_id and user_id = new.owner_id
      and conversation_id = new.source_conversation_id and role = 'assistant' for share;
    if not found then
      raise exception 'public_excerpt_source_missing' using errcode = '23514';
    end if;
  end loop;
  if cardinality(new.source_message_ids) <> (select count(distinct id) from unnest(new.source_message_ids) as id) then
    raise exception 'public_excerpt_source_missing' using errcode = '23514';
  end if;
  for v_id in select distinct unnest(new.source_run_ids) order by 1 loop
    perform 1 from public.backtest_runs where id = v_id and user_id = new.owner_id
      and conversation_id = new.source_conversation_id and status = 'completed' for share;
    if not found then
      raise exception 'public_excerpt_source_missing' using errcode = '23514';
    end if;
  end loop;
  for v_id in select distinct unnest(new.source_artifact_ids) order by 1 loop
    perform 1 from public.evidence_artifacts where id = v_id and user_id = new.owner_id
      and source_conversation_id = new.source_conversation_id for share;
    if not found then
      raise exception 'public_excerpt_source_missing' using errcode = '23514';
    end if;
  end loop;
  return new;
end;
$$;

create or replace function public.revoke_public_excerpts_for_deleted_source()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_now timestamptz := now();
begin
  if tg_op = 'DELETE' then
    if tg_table_name = 'conversations' then
      update public.public_excerpt_snapshots as snapshot
         set revoked_at = v_now,
             revocation_reason = 'source_deleted'
       where snapshot.source_conversation_id = old.id
         and snapshot.revoked_at is null
         and exists (
           select 1 from public.profiles as owner
            where owner.id = snapshot.owner_id
         );
    elsif tg_table_name = 'backtest_runs' then
      update public.public_excerpt_snapshots as snapshot
         set revoked_at = v_now,
             revocation_reason = 'source_deleted'
       where (snapshot.source_run_id = old.id or old.id = any(snapshot.source_run_ids))
         and snapshot.revoked_at is null
         and exists (
           select 1 from public.profiles as owner
            where owner.id = snapshot.owner_id
         );
    elsif tg_table_name = 'messages' then
      update public.public_excerpt_snapshots as snapshot
         set revoked_at = v_now, revocation_reason = 'source_deleted'
       where old.id = any(snapshot.source_message_ids)
         and snapshot.revoked_at is null
         and exists (select 1 from public.profiles as owner where owner.id = snapshot.owner_id);
    else
      update public.public_excerpt_snapshots as snapshot
         set revoked_at = v_now,
             revocation_reason = 'source_deleted'
       where (snapshot.evidence_artifact_id = old.id or old.id = any(snapshot.source_artifact_ids))
         and snapshot.revoked_at is null
         and exists (
           select 1 from public.profiles as owner
            where owner.id = snapshot.owner_id
         );
    end if;
    return old;
  end if;

  if old.deleted_at is null and new.deleted_at is not null then
    update public.public_excerpt_snapshots as snapshot
       set revoked_at = v_now,
           revocation_reason = 'source_deleted'
     where snapshot.source_conversation_id = new.id
       and snapshot.revoked_at is null
       and exists (
         select 1 from public.profiles as owner
          where owner.id = snapshot.owner_id
       );
  end if;
  return new;
end;
$$;

create trigger revoke_public_excerpts_on_message_delete before delete on public.messages
for each row execute function public.revoke_public_excerpts_for_deleted_source();

-- Retain the table and trigger-function access boundary.
revoke all on table public.public_excerpt_snapshots from anon, authenticated;
-- Backend access must not depend on environment-specific default privileges.
grant select, insert, update on table public.public_excerpt_snapshots to service_role;
revoke all on function public.prevent_public_excerpt_immutable_update() from public, anon, authenticated;
revoke all on function public.enforce_public_excerpt_source_is_live() from public, anon, authenticated;
revoke all on function public.revoke_public_excerpts_for_deleted_source() from public, anon, authenticated;

alter table public.public_excerpt_snapshots
  drop constraint public_excerpt_snapshots_revocation_reason_check,
  add constraint public_excerpt_snapshots_revocation_reason_check
    check (revocation_reason in ('owner_revoked', 'source_deleted', 'removed_by_argus'));

-- Generated from GuestPendingAction and GUEST_PENDING_ACTION_IDENTITIES.
create or replace function argus_private.valid_guest_pending_action(
  p_action jsonb, p_conversation_id uuid
)
returns boolean language plpgsql immutable strict set search_path = '' as $$
declare v_key text; v_reason text;
begin
  if jsonb_typeof(p_action) <> 'object' then return false; end if;
  for v_key in select jsonb_object_keys(p_action) loop
    if v_key not in ('reason', 'conversation_id', 'action_id', 'artifact_id', 'message_id') or jsonb_typeof(p_action -> v_key) <> 'string' then
      return false;
    end if;
  end loop;
  v_reason := p_action ->> 'reason';
  if v_reason is null or v_reason not in ('second_simulation', 'simulation_limit', 'message_limit', 'save_decision', 'new_conversation', 'keep_history', 'discovery_searches', 'share_result') then return false; end if;
  if nullif(p_action ->> 'conversation_id', '') is distinct from p_conversation_id::text
     or nullif(p_action ->> 'action_id', '') is null then return false; end if;
  if v_reason = 'save_decision' then
    if nullif(p_action ->> 'artifact_id', '') is null then return false; end if;
  elsif p_action ? 'artifact_id' then
    return false;
  end if;
  if v_reason = 'share_result' then
    if nullif(p_action ->> 'message_id', '') is null then return false; end if;
  elsif p_action ? 'message_id' then
    return false;
  end if;
  return true;
end;
$$;
revoke all on function argus_private.valid_guest_pending_action(jsonb, uuid) from public, anon, authenticated;
grant execute on function argus_private.valid_guest_pending_action(jsonb, uuid) to service_role;
