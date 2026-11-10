-- Isolate expected row-local cleanup safety outcomes so one poisoned guest
-- cannot prevent healthy expired guests from being removed. Unexpected SQL
-- failures still abort the complete statement.

create or replace function public.claim_expired_guest_workspaces(
  p_limit integer,
  p_dry_run boolean default false
)
returns table (
  user_id uuid,
  conversation_id uuid,
  auth_deleted boolean,
  cleanup_reason text
)
language plpgsql
security definer
set search_path = ''
as $$
#variable_conflict use_column
declare
  v_candidate record;
  v_now timestamptz := now();
  v_selected integer := 0;
  v_deleted_user_id uuid;
begin
  if p_limit < 1 or p_limit > 100 then
    raise exception 'cleanup limit must be between 1 and 100'
      using errcode = '22023';
  end if;

  for v_candidate in
    select
      workspace.user_id,
      workspace.conversation_id,
      case
        when workspace.status = 'claimed' then 'claimed_identity'
        else 'expired_workspace'
      end as reason
      from public.guest_workspaces as workspace
      join auth.users as auth_user on auth_user.id = workspace.user_id
     where coalesce(auth_user.is_anonymous, false)
       and (
         (
           workspace.claimed_by is null
           and workspace.claimed_at is null
           and workspace.expires_at <= v_now
           and (
             workspace.status = 'active'
             or (
               workspace.status = 'expired'
               and workspace.updated_at <= v_now - interval '5 minutes'
             )
           )
         )
         or (
           workspace.status = 'claimed'
           and workspace.claimed_by is not null
           and workspace.claimed_at is not null
           and workspace.updated_at <= v_now - interval '15 minutes'
         )
       )
     order by workspace.updated_at, workspace.user_id
     limit p_limit
     for update of workspace, auth_user skip locked
  loop
    user_id := v_candidate.user_id;
    conversation_id := v_candidate.conversation_id;
    auth_deleted := false;
    cleanup_reason := v_candidate.reason;
    v_selected := v_selected + 1;
    if p_dry_run then
      return next;
      continue;
    end if;

    begin

    -- Deleting the profile would SET NULL references owned by another
    -- workspace. Fail closed instead of mutating another owner's server state.
    if exists (
      select 1
        from public.guest_workspaces as workspace
       where workspace.user_id <> v_candidate.user_id
         and workspace.claimed_by = v_candidate.user_id
    ) or exists (
      select 1
        from public.guest_workspace_handoffs as handoff
       where handoff.source_user_id <> v_candidate.user_id
         and handoff.destination_user_id = v_candidate.user_id
    ) then
      raise exception 'guest_cleanup_unsafe_product_graph'
        using errcode = 'AG001';
    end if;

    -- Feedback contains user prose and is not approved retained evidence.
    -- Its owner FK is SET NULL, so remove it explicitly for every candidate.
    delete from public.feedback as feedback
     where feedback.user_id = v_candidate.user_id;

    if v_candidate.reason = 'expired_workspace' then
      -- A missing workspace pointer means the cleanup owner cannot prove which
      -- conversation/checkpoint graph is safe to delete. Empty and
      -- policy-only workspaces may still clean; product-bearing ones fail
      -- closed for repair.
      if v_candidate.conversation_id is null and exists (
        select 1 from public.conversations
         where user_id = v_candidate.user_id
        union all select 1 from public.messages
         where user_id = v_candidate.user_id
        union all select 1 from public.strategies
         where user_id = v_candidate.user_id
        union all select 1 from public.backtest_runs
         where user_id = v_candidate.user_id
        union all select 1 from public.backtest_jobs
         where user_id = v_candidate.user_id
        union all select 1 from public.ideas
         where user_id = v_candidate.user_id
        union all select 1 from public.idea_versions
         where user_id = v_candidate.user_id
        union all select 1 from public.evidence_artifacts
         where user_id = v_candidate.user_id
        union all select 1 from public.decision_notes
         where user_id = v_candidate.user_id
        union all select 1 from public.context_packets
         where user_id = v_candidate.user_id
        union all select 1 from public.run_context_packets
         where user_id = v_candidate.user_id
        union all select 1 from public.collections
         where user_id = v_candidate.user_id
        union all select 1 from public.collection_strategies
         where user_id = v_candidate.user_id
        union all select 1 from public.guest_workspace_handoffs
         where source_user_id = v_candidate.user_id
      ) then
        raise exception 'guest_cleanup_unsafe_product_graph'
          using errcode = 'AG001';
      end if;

      if v_candidate.conversation_id is not null and (
        not exists (
          select 1
            from public.conversations as conversation
           where conversation.id = v_candidate.conversation_id
             and conversation.user_id = v_candidate.user_id
        )
        or exists (
          select 1
            from public.conversations as conversation
           where conversation.user_id = v_candidate.user_id
             and conversation.id <> v_candidate.conversation_id
        )
        or exists (
          select 1
            from public.messages as message
           where message.conversation_id = v_candidate.conversation_id
             and message.user_id <> v_candidate.user_id
        )
        or exists (
          select 1
            from public.strategies as strategy
           where strategy.conversation_id = v_candidate.conversation_id
             and strategy.user_id <> v_candidate.user_id
        )
        or exists (
          select 1
            from public.backtest_runs as run
           where run.conversation_id = v_candidate.conversation_id
             and run.user_id <> v_candidate.user_id
        )
        or exists (
          select 1
            from public.backtest_jobs as job
           where job.conversation_id = v_candidate.conversation_id
             and job.user_id <> v_candidate.user_id
        )
        or exists (
          select 1
            from public.ideas as idea
           where idea.source_conversation_id = v_candidate.conversation_id
             and idea.user_id <> v_candidate.user_id
        )
        or exists (
          select 1
            from public.idea_versions as version
           where version.source_conversation_id = v_candidate.conversation_id
             and version.user_id <> v_candidate.user_id
        )
        or exists (
          select 1
            from public.evidence_artifacts as evidence
           where evidence.source_conversation_id = v_candidate.conversation_id
             and evidence.user_id <> v_candidate.user_id
        )
        or exists (
          select 1
            from public.decision_notes as decision
           where decision.source_conversation_id = v_candidate.conversation_id
             and decision.user_id <> v_candidate.user_id
        )
        or exists (
          select 1
            from public.guest_workspace_handoffs as handoff
           where handoff.source_conversation_id = v_candidate.conversation_id
             and handoff.source_user_id <> v_candidate.user_id
        )
        or exists (
          select 1
            from public.backtest_runs as run
            join public.strategies as strategy on strategy.id = run.strategy_id
           where (
             run.user_id = v_candidate.user_id
             or strategy.user_id = v_candidate.user_id
           )
             and run.user_id <> strategy.user_id
        )
        or exists (
          select 1
            from public.backtest_jobs as job
            join public.messages as message on message.id = job.request_message_id
           where (
             job.user_id = v_candidate.user_id
             or message.user_id = v_candidate.user_id
           )
             and job.user_id <> message.user_id
        )
        or exists (
          select 1
            from public.backtest_jobs as job
            join public.messages as message
              on message.id = job.confirmation_message_id
           where (
             job.user_id = v_candidate.user_id
             or message.user_id = v_candidate.user_id
           )
             and job.user_id <> message.user_id
        )
        or exists (
          select 1
            from public.backtest_jobs as job
            join public.backtest_runs as run on run.id = job.result_run_id
           where (
             job.user_id = v_candidate.user_id
             or run.user_id = v_candidate.user_id
           )
             and job.user_id <> run.user_id
        )
        or exists (
          select 1
            from public.ideas as idea
            join public.idea_versions as version
              on version.id = idea.active_version_id
           where (
             idea.user_id = v_candidate.user_id
             or version.user_id = v_candidate.user_id
           )
             and idea.user_id <> version.user_id
        )
        or exists (
          select 1
            from public.idea_versions as version
            join public.ideas as idea on idea.id = version.idea_id
           where (
             version.user_id = v_candidate.user_id
             or idea.user_id = v_candidate.user_id
           )
             and version.user_id <> idea.user_id
        )
        or exists (
          select 1
            from public.idea_versions as version
            join public.backtest_runs as run on run.id = version.source_run_id
           where (
             version.user_id = v_candidate.user_id
             or run.user_id = v_candidate.user_id
           )
             and version.user_id <> run.user_id
        )
        or exists (
          select 1
            from public.evidence_artifacts as evidence
            join public.ideas as idea on idea.id = evidence.idea_id
           where (
             evidence.user_id = v_candidate.user_id
             or idea.user_id = v_candidate.user_id
           )
             and evidence.user_id <> idea.user_id
        )
        or exists (
          select 1
            from public.evidence_artifacts as evidence
            join public.idea_versions as version
              on version.id = evidence.idea_version_id
           where (
             evidence.user_id = v_candidate.user_id
             or version.user_id = v_candidate.user_id
           )
             and evidence.user_id <> version.user_id
        )
        or exists (
          select 1
            from public.evidence_artifacts as evidence
            join public.backtest_runs as run on run.id = evidence.source_run_id
           where (
             evidence.user_id = v_candidate.user_id
             or run.user_id = v_candidate.user_id
           )
             and evidence.user_id <> run.user_id
        )
        or exists (
          select 1
            from public.decision_notes as decision
            join public.ideas as idea on idea.id = decision.idea_id
           where (
             decision.user_id = v_candidate.user_id
             or idea.user_id = v_candidate.user_id
           )
             and decision.user_id <> idea.user_id
        )
        or exists (
          select 1
            from public.decision_notes as decision
            join public.idea_versions as version
              on version.id = decision.idea_version_id
           where (
             decision.user_id = v_candidate.user_id
             or version.user_id = v_candidate.user_id
           )
             and decision.user_id <> version.user_id
        )
        or exists (
          select 1
            from public.decision_notes as decision
            join public.evidence_artifacts as evidence
              on evidence.id = decision.evidence_artifact_id
           where (
             decision.user_id = v_candidate.user_id
             or evidence.user_id = v_candidate.user_id
           )
             and decision.user_id <> evidence.user_id
        )
        or exists (
          select 1
            from public.run_context_packets as link
            join public.backtest_runs as run on run.id = link.run_id
           where (
             link.user_id = v_candidate.user_id
             or run.user_id = v_candidate.user_id
           )
             and link.user_id <> run.user_id
        )
        or exists (
          select 1
            from public.run_context_packets as link
            join public.context_packets as packet
              on packet.id = link.context_packet_id
           where (
             link.user_id = v_candidate.user_id
             or packet.user_id = v_candidate.user_id
           )
             and link.user_id <> packet.user_id
        )
        or exists (
          select 1
            from public.collection_strategies as membership
            join public.strategies as strategy on strategy.id = membership.strategy_id
           where (
             membership.user_id = v_candidate.user_id
             or strategy.user_id = v_candidate.user_id
           )
             and membership.user_id <> strategy.user_id
        )
        or exists (
          select 1
            from public.collection_strategies as membership
            join public.collections as collection
              on collection.id = membership.collection_id
           where (
             membership.user_id = v_candidate.user_id
             or collection.user_id = v_candidate.user_id
           )
             and membership.user_id <> collection.user_id
        )
        or exists (
          select 1
            from public.route_receipts as receipt
           where receipt.user_id is not null
             and receipt.user_id <> v_candidate.user_id
             and (
               receipt.conversation_id = v_candidate.conversation_id
               or receipt.message_id in (
                 select message.id
                   from public.messages as message
                  where message.user_id = v_candidate.user_id
               )
               or receipt.run_id in (
                 select run.id
                   from public.backtest_runs as run
                  where run.user_id = v_candidate.user_id
               )
             )
        )
        or exists (
          select 1
            from public.cost_ledger_entries as cost
           where cost.user_id is not null
             and cost.user_id <> v_candidate.user_id
             and (
               cost.conversation_id = v_candidate.conversation_id
               or cost.message_id in (
                 select message.id
                   from public.messages as message
                  where message.user_id = v_candidate.user_id
               )
               or cost.backtest_run_id in (
                 select run.id
                   from public.backtest_runs as run
                  where run.user_id = v_candidate.user_id
               )
               or cost.backtest_job_id in (
                 select job.id
                   from public.backtest_jobs as job
                  where job.user_id = v_candidate.user_id
               )
             )
        )
      ) then
        raise exception 'guest_cleanup_unsafe_product_graph'
          using errcode = 'AG001';
      end if;

      update public.guest_workspaces as workspace
         set status = 'expired',
             conversation_id = null,
             updated_at = v_now
       where workspace.user_id = v_candidate.user_id;

      delete from public.decision_notes as decision
       where decision.user_id = v_candidate.user_id;
      delete from public.evidence_artifacts as evidence
       where evidence.user_id = v_candidate.user_id;
      update public.ideas as idea
         set active_version_id = null
       where idea.user_id = v_candidate.user_id;
      delete from public.idea_versions as version
       where version.user_id = v_candidate.user_id;
      delete from public.ideas as idea
       where idea.user_id = v_candidate.user_id;
      delete from public.run_context_packets as link
       where link.user_id = v_candidate.user_id;
      delete from public.context_packets as packet
       where packet.user_id = v_candidate.user_id;
      delete from public.backtest_jobs as job
       where job.user_id = v_candidate.user_id;
      delete from public.backtest_runs as run
       where run.user_id = v_candidate.user_id;
      delete from public.strategies as strategy
       where strategy.user_id = v_candidate.user_id;
      delete from public.messages as message
       where message.user_id = v_candidate.user_id;

      if v_candidate.conversation_id is not null then
        delete from public.checkpoint_writes
         where thread_id = v_candidate.conversation_id::text;
        delete from public.checkpoint_blobs
         where thread_id = v_candidate.conversation_id::text;
        delete from public.checkpoints
         where thread_id = v_candidate.conversation_id::text;
        delete from public.conversations as conversation
         where conversation.id = v_candidate.conversation_id
           and conversation.user_id = v_candidate.user_id;
      end if;
    elsif exists (
      select 1 from public.conversations where user_id = v_candidate.user_id
      union all select 1 from public.messages where user_id = v_candidate.user_id
      union all select 1 from public.strategies where user_id = v_candidate.user_id
      union all select 1 from public.backtest_runs where user_id = v_candidate.user_id
      union all select 1 from public.backtest_jobs where user_id = v_candidate.user_id
      union all select 1 from public.ideas where user_id = v_candidate.user_id
      union all select 1 from public.idea_versions where user_id = v_candidate.user_id
      union all select 1 from public.evidence_artifacts where user_id = v_candidate.user_id
      union all select 1 from public.decision_notes where user_id = v_candidate.user_id
      union all select 1 from public.context_packets where user_id = v_candidate.user_id
      union all select 1 from public.run_context_packets where user_id = v_candidate.user_id
      union all select 1 from public.collections where user_id = v_candidate.user_id
      union all select 1 from public.collection_strategies where user_id = v_candidate.user_id
    ) then
      raise exception 'claimed guest identity still owns product rows'
        using errcode = 'AG002';
    end if;

    delete from auth.users as auth_user
     where auth_user.id = v_candidate.user_id
       and coalesce(auth_user.is_anonymous, false)
     returning auth_user.id into v_deleted_user_id;
    if v_deleted_user_id is null then
      raise exception 'guest identity changed during cleanup'
        using errcode = '40001';
    end if;
    auth_deleted := true;
    return next;
    v_deleted_user_id := null;
    exception
      when sqlstate 'AG001' then
        auth_deleted := false;
        cleanup_reason := 'unsafe_product_graph';
        update public.guest_workspaces as workspace
           set updated_at = v_now
         where workspace.user_id = v_candidate.user_id;
        return next;
      when sqlstate 'AG002' then
        auth_deleted := false;
        cleanup_reason := 'claimed_identity_has_product_rows';
        update public.guest_workspaces as workspace
           set updated_at = v_now
         where workspace.user_id = v_candidate.user_id;
        return next;
    end;
  end loop;

  if v_selected >= p_limit then
    return;
  end if;

  for v_candidate in
    select auth_user.id as user_id
      from auth.users as auth_user
     where coalesce(auth_user.is_anonymous, false)
       and auth_user.created_at <= v_now - interval '5 minutes'
       and not exists (
         select 1 from public.guest_workspaces as workspace
          where workspace.user_id = auth_user.id
       )
       and not exists (
         select 1 from public.conversations where user_id = auth_user.id
         union all select 1 from public.messages where user_id = auth_user.id
         union all select 1 from public.strategies where user_id = auth_user.id
         union all select 1 from public.backtest_runs where user_id = auth_user.id
         union all select 1 from public.backtest_jobs where user_id = auth_user.id
         union all select 1 from public.ideas where user_id = auth_user.id
         union all select 1 from public.idea_versions where user_id = auth_user.id
         union all select 1 from public.evidence_artifacts where user_id = auth_user.id
         union all select 1 from public.decision_notes where user_id = auth_user.id
         union all select 1 from public.context_packets where user_id = auth_user.id
         union all select 1 from public.run_context_packets where user_id = auth_user.id
         union all select 1 from public.collections where user_id = auth_user.id
         union all select 1 from public.collection_strategies where user_id = auth_user.id
       )
     order by auth_user.created_at, auth_user.id
     limit (p_limit - v_selected)
     for update of auth_user skip locked
  loop
    user_id := v_candidate.user_id;
    conversation_id := null;
    auth_deleted := false;
    cleanup_reason := 'orphan_identity';
    if p_dry_run then
      return next;
      continue;
    end if;

    -- Recheck the same complete product-owner set immediately before Auth
    -- cascade so concurrent detached rows still fail closed.
    if exists (
      select 1 from public.conversations where user_id = v_candidate.user_id
      union all select 1 from public.messages where user_id = v_candidate.user_id
      union all select 1 from public.strategies where user_id = v_candidate.user_id
      union all select 1 from public.backtest_runs where user_id = v_candidate.user_id
      union all select 1 from public.backtest_jobs where user_id = v_candidate.user_id
      union all select 1 from public.ideas where user_id = v_candidate.user_id
      union all select 1 from public.idea_versions where user_id = v_candidate.user_id
      union all select 1 from public.evidence_artifacts where user_id = v_candidate.user_id
      union all select 1 from public.decision_notes where user_id = v_candidate.user_id
      union all select 1 from public.context_packets where user_id = v_candidate.user_id
      union all select 1 from public.run_context_packets where user_id = v_candidate.user_id
      union all select 1 from public.collections where user_id = v_candidate.user_id
      union all select 1 from public.collection_strategies
       where user_id = v_candidate.user_id
    ) then
      raise exception 'guest_cleanup_unsafe_product_graph'
        using errcode = 'AG001';
    end if;

    if exists (
      select 1
        from public.guest_workspaces as workspace
       where workspace.user_id <> v_candidate.user_id
         and workspace.claimed_by = v_candidate.user_id
    ) or exists (
      select 1
        from public.guest_workspace_handoffs as handoff
       where handoff.source_user_id <> v_candidate.user_id
         and handoff.destination_user_id = v_candidate.user_id
    ) then
      raise exception 'guest_cleanup_unsafe_product_graph'
        using errcode = 'AG001';
    end if;

    delete from public.feedback as feedback
     where feedback.user_id = v_candidate.user_id;

    delete from auth.users as auth_user
     where auth_user.id = v_candidate.user_id
       and coalesce(auth_user.is_anonymous, false)
     returning auth_user.id into v_deleted_user_id;
    if v_deleted_user_id is null then
      raise exception 'guest identity changed during cleanup'
        using errcode = '40001';
    end if;
    auth_deleted := true;
    return next;
    v_deleted_user_id := null;
  end loop;
end;
$$;

revoke all on function public.claim_expired_guest_workspaces(integer, boolean)
  from public, anon, authenticated;
grant execute on function public.claim_expired_guest_workspaces(integer, boolean)
  to service_role;
