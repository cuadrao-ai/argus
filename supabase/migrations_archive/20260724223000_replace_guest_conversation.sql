-- Atomically replace a non-empty temporary conversation after explicit consent.
-- Guest identity, fixed expiry, feedback, and lifetime allowance counters remain.

create or replace function public.replace_guest_conversation(
  p_user_id uuid,
  p_title text,
  p_title_source text,
  p_language text
)
returns public.conversations
language plpgsql
security definer
set search_path = public
as $$
#variable_conflict use_column
declare
  v_workspace public.guest_workspaces%rowtype;
  v_conversation public.conversations%rowtype;
begin
  select *
    into v_workspace
    from public.guest_workspaces
   where user_id = p_user_id
   for update;
  if not found
     or v_workspace.status <> 'active'
     or v_workspace.expires_at <= now()
     or v_workspace.conversation_id is null then
    raise exception 'guest_workspace_unavailable' using errcode = 'P0001';
  end if;

  if not exists (
      select 1 from public.conversations
       where id = v_workspace.conversation_id and user_id = p_user_id
    )
    or exists (
      select 1 from public.conversations
       where user_id = p_user_id and id <> v_workspace.conversation_id
    )
    or exists (
      select 1 from public.messages
       where (user_id = p_user_id and conversation_id <> v_workspace.conversation_id)
          or (conversation_id = v_workspace.conversation_id and user_id <> p_user_id)
    )
    or exists (
      select 1 from public.strategies
       where (user_id = p_user_id and conversation_id is distinct from v_workspace.conversation_id)
          or (conversation_id = v_workspace.conversation_id and user_id <> p_user_id)
    )
    or exists (
      select 1 from public.backtest_runs
       where (user_id = p_user_id and conversation_id is distinct from v_workspace.conversation_id)
          or (conversation_id = v_workspace.conversation_id and user_id <> p_user_id)
    )
    or exists (
      select 1 from public.backtest_jobs
       where (user_id = p_user_id and conversation_id <> v_workspace.conversation_id)
          or (conversation_id = v_workspace.conversation_id and user_id <> p_user_id)
    )
    or exists (
      select 1 from public.ideas
       where (user_id = p_user_id and source_conversation_id is distinct from v_workspace.conversation_id)
          or (source_conversation_id = v_workspace.conversation_id and user_id <> p_user_id)
    )
    or exists (
      select 1 from public.idea_versions
       where (user_id = p_user_id and source_conversation_id is distinct from v_workspace.conversation_id)
          or (source_conversation_id = v_workspace.conversation_id and user_id <> p_user_id)
    )
    or exists (
      select 1 from public.evidence_artifacts
       where (user_id = p_user_id and source_conversation_id is distinct from v_workspace.conversation_id)
          or (source_conversation_id = v_workspace.conversation_id and user_id <> p_user_id)
    )
    or exists (
      select 1 from public.decision_notes
       where (user_id = p_user_id and source_conversation_id is distinct from v_workspace.conversation_id)
          or (source_conversation_id = v_workspace.conversation_id and user_id <> p_user_id)
    )
    or exists (select 1 from public.collections where user_id = p_user_id)
    or exists (select 1 from public.collection_strategies where user_id = p_user_id) then
    raise exception 'guest_start_over_unsafe_product_graph' using errcode = 'P0001';
  end if;

  update public.guest_workspaces
     set conversation_id = null,
         updated_at = now()
   where user_id = p_user_id;

  delete from public.decision_notes where user_id = p_user_id;
  delete from public.evidence_artifacts where user_id = p_user_id;
  update public.ideas set active_version_id = null where user_id = p_user_id;
  delete from public.idea_versions where user_id = p_user_id;
  delete from public.ideas where user_id = p_user_id;
  delete from public.run_context_packets where user_id = p_user_id;
  delete from public.context_packets where user_id = p_user_id;
  delete from public.backtest_jobs where user_id = p_user_id;
  delete from public.backtest_runs where user_id = p_user_id;
  delete from public.strategies where user_id = p_user_id;
  delete from public.messages where user_id = p_user_id;
  delete from public.checkpoint_writes
   where thread_id = v_workspace.conversation_id::text;
  delete from public.checkpoint_blobs
   where thread_id = v_workspace.conversation_id::text;
  delete from public.checkpoints
   where thread_id = v_workspace.conversation_id::text;
  delete from public.conversations
   where id = v_workspace.conversation_id and user_id = p_user_id;

  insert into public.conversations (user_id, title, title_source, language)
  values (p_user_id, p_title, p_title_source, p_language)
  returning * into v_conversation;
  return v_conversation;
end;
$$;

revoke all on function public.replace_guest_conversation(
  uuid, text, text, text
) from public, anon, authenticated;
grant execute on function public.replace_guest_conversation(
  uuid, text, text, text
) to service_role;
