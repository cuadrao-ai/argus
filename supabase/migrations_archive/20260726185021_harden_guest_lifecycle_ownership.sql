-- Keep durable chat-turn recovery state inside the same guest ownership and
-- fixed-expiry boundaries as the conversation and messages it describes.

create policy chat_turn_lifecycles_guest_session_active
  on public.chat_turn_lifecycles as restrictive
  for select to authenticated
  using (
    (select auth.jwt() ->> 'is_anonymous') is distinct from 'true'
    or exists (
      select 1
        from public.guest_workspaces as workspace
       where workspace.user_id = chat_turn_lifecycles.user_id
         and workspace.status = 'active'
         and workspace.expires_at > now()
    )
  );

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
      select 1 from public.chat_turn_lifecycles
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
  update public.chat_turn_lifecycles
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
