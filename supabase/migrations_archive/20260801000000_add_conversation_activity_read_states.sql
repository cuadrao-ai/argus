-- Durable conversation operation/attention read truth.
-- This migration changes no conversation, message, job, Run, or artifact sort
-- timestamp and does not introduce a new lifecycle or failure taxonomy.

alter table public.conversations
  add constraint conversations_id_user_id_key unique (id, user_id);

create table public.conversation_read_states (
  user_id uuid not null
    references public.profiles(id) on update cascade on delete cascade,
  conversation_id uuid not null,
  read_through_occurred_at timestamptz,
  read_through_source_kind text,
  read_through_source_id uuid,
  manual_unread_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (user_id, conversation_id),
  constraint conversation_read_states_owner_fk
    foreign key (conversation_id, user_id)
    references public.conversations(id, user_id)
    on update cascade
    on delete cascade,
  constraint conversation_read_states_boundary_shape_check check (
    (
      read_through_occurred_at is null
      and read_through_source_kind is null
      and read_through_source_id is null
    )
    or (
      read_through_occurred_at is not null
      and read_through_source_kind in ('chat_turn', 'backtest_job')
      and read_through_source_id is not null
    )
  )
);

create index chat_turn_lifecycles_activity_operation_idx
  on public.chat_turn_lifecycles (
    user_id, conversation_id, status, updated_at desc, turn_id desc
  )
  where status in ('accepted', 'running');

create index chat_turn_lifecycles_activity_terminal_idx
  on public.chat_turn_lifecycles (
    user_id, conversation_id, status, terminal_at desc, turn_id desc
  )
  where status in (
    'completed', 'recoverable_failed', 'abandoned', 'reconciled'
  );

create index backtest_jobs_activity_operation_idx
  on public.backtest_jobs (
    user_id, conversation_id, status, updated_at desc, id desc
  )
  where conversation_id is not null
    and status in ('queued', 'running', 'succeeded');

create index backtest_jobs_activity_terminal_idx
  on public.backtest_jobs (
    user_id, conversation_id, status, finished_at desc, id desc
  )
  where conversation_id is not null
    and status in ('succeeded', 'failed', 'canceled', 'expired');

alter table public.conversation_read_states enable row level security;

create policy "conversation_read_states_owner_select"
  on public.conversation_read_states
  for select
  to authenticated
  using ((select auth.uid()) = user_id);

revoke all on public.conversation_read_states
  from public, anon, authenticated;
grant select on public.conversation_read_states to authenticated;
grant select, insert, update, delete on public.conversation_read_states
  to service_role;
revoke insert, update, delete on public.conversation_read_states
  from anon, authenticated;

create function public.reconcile_stale_conversation_activity_turns(
  p_user_id uuid,
  p_conversation_ids uuid[]
)
returns setof jsonb
language plpgsql
security invoker
set search_path = public
set timezone = 'UTC'
as $$
declare
  v_turn public.chat_turn_lifecycles%rowtype;
  v_evidence public.messages%rowtype;
  v_outcome text;
  v_failure_code text;
  v_retryable boolean;
  v_result jsonb;
  v_now timestamptz := clock_timestamp();
begin
  if p_conversation_ids is null or cardinality(p_conversation_ids) = 0 then
    return;
  end if;
  if cardinality(p_conversation_ids) > 100 then
    raise exception 'conversation_activity_batch_too_large'
      using errcode = '22023';
  end if;

  for v_turn in
    select l.*
      from public.chat_turn_lifecycles as l
      join public.conversations as c
        on c.id = l.conversation_id
       and c.user_id = l.user_id
       and c.deleted_at is null
     where l.user_id = p_user_id
       and l.conversation_id = any(p_conversation_ids)
       and l.status in ('accepted', 'running')
       and coalesce(l.running_at, l.accepted_at)
         <= v_now - interval '15 minutes'
     order by coalesce(l.running_at, l.accepted_at) asc, l.turn_id asc
     limit 20
     for update of l skip locked
  loop
    if v_turn.status not in ('accepted', 'running')
       or coalesce(v_turn.running_at, v_turn.accepted_at)
         > v_now - interval '15 minutes' then
      continue;
    end if;

    select m.*
      into v_evidence
      from public.messages as m
     where m.user_id = v_turn.user_id
       and m.conversation_id = v_turn.conversation_id
       and m.role = 'assistant'
       and m.metadata #>> '{agent_runtime_turn,turn_id}'
         = v_turn.turn_id::text
       and m.metadata #>> '{agent_runtime_turn,request_id}'
         = v_turn.request_id
       and m.metadata #> '{agent_runtime_turn,terminal}' = 'true'::jsonb
       and m.metadata #>> '{agent_runtime_turn,status}'
         in ('completed', 'recoverable_failed')
       and (
         m.metadata #>> '{agent_runtime_turn,status}' = 'completed'
         or (
           m.metadata #>> '{agent_runtime_turn,status}'
             = 'recoverable_failed'
           and m.metadata -> 'agent_runtime_turn' ? 'failure_code'
           and jsonb_typeof(
             m.metadata #> '{agent_runtime_turn,failure_code}'
           ) in ('string', 'null')
           and m.metadata -> 'agent_runtime_turn' ? 'retryable'
           and jsonb_typeof(
             m.metadata #> '{agent_runtime_turn,retryable}'
           ) = 'boolean'
         )
       )
     order by m.created_at asc,
       case m.metadata #>> '{agent_runtime_turn,status}'
         when 'recoverable_failed' then 0
         else 1
       end asc,
       m.id asc
     limit 1;

    if found then
      v_outcome := v_evidence.metadata #>> '{agent_runtime_turn,status}';
      v_failure_code := case
        when v_outcome = 'recoverable_failed' then
          v_evidence.metadata #>> '{agent_runtime_turn,failure_code}'
        else null
      end;
      v_retryable := case
        when v_outcome = 'recoverable_failed' then
          coalesce(
            v_evidence.metadata #> '{agent_runtime_turn,retryable}'
              = 'true'::jsonb,
            false
          )
        else false
      end;

      select public.transition_chat_turn(
        v_turn.turn_id,
        'reconciled',
        v_evidence.id,
        v_outcome,
        v_failure_code,
        v_retryable
      ) into v_result;
    else
      select public.transition_chat_turn(
        v_turn.turn_id,
        'abandoned',
        null,
        null,
        'turn_abandoned',
        true
      ) into v_result;
    end if;

    if v_result ->> 'outcome' in ('applied', 'noop')
       and v_result -> 'row' is not null then
      return next v_result -> 'row';
    end if;
  end loop;
end;
$$;

create function public.read_conversation_activity_sources(
  p_user_id uuid,
  p_conversation_ids uuid[]
)
returns table (
  conversation_id uuid,
  sources jsonb,
  read_state jsonb
)
language plpgsql
stable
security invoker
set search_path = public
set timezone = 'UTC'
as $$
begin
  if p_conversation_ids is null or cardinality(p_conversation_ids) = 0 then
    return;
  end if;
  if cardinality(p_conversation_ids) > 100 then
    raise exception 'conversation_activity_batch_too_large'
      using errcode = '22023';
  end if;

  return query
  with requested as (
    select distinct requested_id
      from unnest(p_conversation_ids) as requested_id
  )
  select
    c.id,
    coalesce(activity.sources, '[]'::jsonb),
    case
      when rs.conversation_id is null then null
      else jsonb_build_object(
        'read_through_occurred_at', rs.read_through_occurred_at,
        'read_through_source_kind', rs.read_through_source_kind,
        'read_through_source_id', rs.read_through_source_id,
        'manual_unread_at', rs.manual_unread_at
      )
    end
  from requested
  join public.conversations as c
    on c.id = requested.requested_id
   and c.user_id = p_user_id
  left join public.conversation_read_states as rs
    on rs.conversation_id = c.id
   and rs.user_id = c.user_id
  left join lateral (
    select jsonb_agg(
      source.payload
      order by source.occurred_at, source.source_kind_rank, source.source_id
    ) as sources
    from (
      (
        select
          jsonb_build_object(
            'conversation_id', l.conversation_id,
            'source_kind', 'chat_turn',
            'source_id', l.turn_id,
            'status', l.status,
            'occurred_at', l.updated_at,
            'stage_outcome', null,
            'result_hydrateable', false
          ) as payload,
          l.updated_at as occurred_at,
          1 as source_kind_rank,
          l.turn_id as source_id
        from public.chat_turn_lifecycles as l
        where l.user_id = c.user_id
          and l.conversation_id = c.id
          and l.status in ('accepted', 'running')
        order by
          case l.status when 'running' then 2 else 1 end desc,
          l.updated_at desc,
          l.turn_id desc
        limit 1
      )
      union all
      (
        select
          jsonb_build_object(
            'conversation_id', l.conversation_id,
            'source_kind', 'chat_turn',
            'source_id', l.turn_id,
            'status', case
              when l.status = 'reconciled' then
                'reconciled:' || l.reconciled_outcome
              else l.status
            end,
            'occurred_at', l.terminal_at,
            'stage_outcome',
              m.metadata ->> 'agent_runtime_stage_outcome',
            'result_hydrateable', false
          ) as payload,
          l.terminal_at as occurred_at,
          1 as source_kind_rank,
          l.turn_id as source_id
        from public.chat_turn_lifecycles as l
        left join public.messages as m
          on m.id = l.assistant_message_id
         and m.user_id = l.user_id
         and m.conversation_id = l.conversation_id
        where l.user_id = c.user_id
          and l.conversation_id = c.id
          and l.status in (
            'completed', 'recoverable_failed', 'abandoned', 'reconciled'
          )
        order by l.terminal_at desc, l.turn_id desc
        limit 1
      )
      union all
      (
        select
          jsonb_build_object(
            'conversation_id', ranked.conversation_id,
            'source_kind', 'backtest_job',
            'source_id', ranked.id,
            'status', ranked.status,
            'occurred_at', ranked.updated_at,
            'stage_outcome', null,
            'result_hydrateable', ranked.result_hydrateable
          ) as payload,
          ranked.updated_at as occurred_at,
          2 as source_kind_rank,
          ranked.id as source_id
        from (
          select
            j.*,
            exists (
              select 1
              from public.backtest_runs as r
              join public.evidence_artifacts as e
                on e.source_run_id = r.id
               and e.user_id = r.user_id
               and e.source_conversation_id = r.conversation_id
              where r.id = j.result_run_id
                and r.user_id = j.user_id
                and r.conversation_id = j.conversation_id
                and r.status = 'completed'
                and r.conversation_result_card
                  ->> 'evidence_artifact_id' = e.id::text
                and r.conversation_result_card
                  ->> 'idea_id' = e.idea_id::text
                and r.conversation_result_card
                  ->> 'idea_version_id' = e.idea_version_id::text
            ) as result_hydrateable
          from public.backtest_jobs as j
          where j.user_id = c.user_id
            and j.conversation_id = c.id
            and j.status in ('queued', 'running', 'succeeded')
        ) as ranked
        where ranked.status <> 'succeeded'
           or not ranked.result_hydrateable
        order by
          case ranked.status
            when 'running' then 3
            when 'queued' then 2
            else 1
          end desc,
          ranked.updated_at desc,
          ranked.id desc
        limit 1
      )
      union all
      (
        select
          jsonb_build_object(
            'conversation_id', ranked.conversation_id,
            'source_kind', 'backtest_job',
            'source_id', ranked.id,
            'status', ranked.status,
            'occurred_at', coalesce(ranked.finished_at, ranked.updated_at),
            'stage_outcome', null,
            'result_hydrateable', ranked.result_hydrateable
          ) as payload,
          coalesce(ranked.finished_at, ranked.updated_at) as occurred_at,
          2 as source_kind_rank,
          ranked.id as source_id
        from (
          select
            j.*,
            exists (
              select 1
              from public.backtest_runs as r
              join public.evidence_artifacts as e
                on e.source_run_id = r.id
               and e.user_id = r.user_id
               and e.source_conversation_id = r.conversation_id
              where r.id = j.result_run_id
                and r.user_id = j.user_id
                and r.conversation_id = j.conversation_id
                and r.status = 'completed'
                and r.conversation_result_card
                  ->> 'evidence_artifact_id' = e.id::text
                and r.conversation_result_card
                  ->> 'idea_id' = e.idea_id::text
                and r.conversation_result_card
                  ->> 'idea_version_id' = e.idea_version_id::text
            ) as result_hydrateable
          from public.backtest_jobs as j
          where j.user_id = c.user_id
            and j.conversation_id = c.id
            and j.status in ('succeeded', 'failed', 'canceled', 'expired')
        ) as ranked
        where ranked.status <> 'succeeded'
           or ranked.result_hydrateable
        order by coalesce(ranked.finished_at, ranked.updated_at) desc,
          ranked.id desc
        limit 1
      )
    ) as source
  ) as activity on true
  order by c.id;
end;
$$;

create function public.mutate_conversation_activity_read_state(
  p_user_id uuid,
  p_conversation_id uuid,
  p_action text,
  p_source_kind text,
  p_source_id uuid
)
returns jsonb
language plpgsql
security invoker
set search_path = public
set timezone = 'UTC'
as $$
declare
  v_conversation public.conversations%rowtype;
  v_state public.conversation_read_states%rowtype;
  v_source_occurred_at timestamptz;
  v_source_kind_rank integer;
  v_current_kind_rank integer;
  v_now timestamptz := clock_timestamp();
  v_changed boolean := false;
begin
  if p_action not in ('mark_unread', 'mark_read') then
    return jsonb_build_object('outcome', 'invalid', 'read_state', null);
  end if;
  if p_action = 'mark_unread'
     and (p_source_kind is not null or p_source_id is not null) then
    return jsonb_build_object('outcome', 'invalid', 'read_state', null);
  end if;
  if p_action = 'mark_read'
     and ((p_source_kind is null) <> (p_source_id is null)) then
    return jsonb_build_object('outcome', 'invalid', 'read_state', null);
  end if;
  if p_source_kind is not null
     and p_source_kind not in ('chat_turn', 'backtest_job') then
    return jsonb_build_object('outcome', 'invalid', 'read_state', null);
  end if;

  select c.*
    into v_conversation
    from public.conversations as c
   where c.id = p_conversation_id
     and c.user_id = p_user_id
     and c.deleted_at is null
   for update;

  if not found then
    return jsonb_build_object('outcome', 'missing', 'read_state', null);
  end if;

  select rs.*
    into v_state
    from public.conversation_read_states as rs
   where rs.user_id = p_user_id
     and rs.conversation_id = p_conversation_id
   for update;

  if p_action = 'mark_unread' then
    if found then
      if v_state.manual_unread_at is null then
        update public.conversation_read_states
           set manual_unread_at = v_now,
               updated_at = v_now
         where user_id = p_user_id
           and conversation_id = p_conversation_id
        returning * into v_state;
        v_changed := true;
      end if;
    else
      insert into public.conversation_read_states (
        user_id,
        conversation_id,
        manual_unread_at
      ) values (
        p_user_id,
        p_conversation_id,
        v_now
      )
      on conflict (user_id, conversation_id) do update
        set manual_unread_at = coalesce(
              public.conversation_read_states.manual_unread_at,
              excluded.manual_unread_at
            ),
            updated_at = case
              when public.conversation_read_states.manual_unread_at is null
                then excluded.updated_at
              else public.conversation_read_states.updated_at
            end
      returning * into v_state;
      v_changed := true;
    end if;
    return jsonb_build_object(
      'outcome', case when v_changed then 'applied' else 'noop' end,
      'read_state', to_jsonb(v_state)
    );
  end if;

  if p_source_kind = 'chat_turn' then
    select l.terminal_at
      into v_source_occurred_at
      from public.chat_turn_lifecycles as l
     where l.turn_id = p_source_id
       and l.user_id = p_user_id
       and l.conversation_id = p_conversation_id
       and l.status in (
         'completed', 'recoverable_failed', 'abandoned', 'reconciled'
       )
     for update;
    v_source_kind_rank := 1;
  elsif p_source_kind = 'backtest_job' then
    select coalesce(j.finished_at, j.updated_at)
      into v_source_occurred_at
      from public.backtest_jobs as j
     where j.id = p_source_id
       and j.user_id = p_user_id
       and j.conversation_id = p_conversation_id
       and (
         j.status in ('failed', 'canceled', 'expired')
         or (
           j.status = 'succeeded'
           and exists (
             select 1
             from public.backtest_runs as r
             join public.evidence_artifacts as e
               on e.source_run_id = r.id
              and e.user_id = r.user_id
              and e.source_conversation_id = r.conversation_id
             where r.id = j.result_run_id
               and r.user_id = j.user_id
               and r.conversation_id = j.conversation_id
               and r.status = 'completed'
               and r.conversation_result_card
                 ->> 'evidence_artifact_id' = e.id::text
               and r.conversation_result_card
                 ->> 'idea_id' = e.idea_id::text
               and r.conversation_result_card
                 ->> 'idea_version_id' = e.idea_version_id::text
           )
         )
       )
     for update;
    v_source_kind_rank := 2;
  end if;

  if p_source_id is not null and v_source_occurred_at is null then
    return jsonb_build_object('outcome', 'conflict', 'read_state', null);
  end if;

  if v_state.conversation_id is null then
    if p_source_id is null then
      return jsonb_build_object('outcome', 'noop', 'read_state', null);
    end if;
    insert into public.conversation_read_states (
      user_id,
      conversation_id,
      read_through_occurred_at,
      read_through_source_kind,
      read_through_source_id
    ) values (
      p_user_id,
      p_conversation_id,
      v_source_occurred_at,
      p_source_kind,
      p_source_id
    )
    on conflict (user_id, conversation_id) do nothing
    returning * into v_state;
    if found then
      v_changed := true;
    else
      select rs.*
        into v_state
        from public.conversation_read_states as rs
       where rs.user_id = p_user_id
         and rs.conversation_id = p_conversation_id
       for update;
    end if;
  end if;

  if v_state.manual_unread_at is not null then
    v_changed := true;
  end if;

  if p_source_id is not null then
    v_current_kind_rank := case v_state.read_through_source_kind
      when 'chat_turn' then 1
      when 'backtest_job' then 2
      else null
    end;
    if v_state.read_through_occurred_at is null
       or (
         v_source_occurred_at,
         v_source_kind_rank,
         p_source_id
       ) > (
         v_state.read_through_occurred_at,
         v_current_kind_rank,
         v_state.read_through_source_id
       ) then
      v_changed := true;
      v_state.read_through_occurred_at := v_source_occurred_at;
      v_state.read_through_source_kind := p_source_kind;
      v_state.read_through_source_id := p_source_id;
    end if;
  end if;

  if v_changed then
    update public.conversation_read_states
       set read_through_occurred_at = v_state.read_through_occurred_at,
           read_through_source_kind = v_state.read_through_source_kind,
           read_through_source_id = v_state.read_through_source_id,
           manual_unread_at = null,
           updated_at = v_now
     where user_id = p_user_id
       and conversation_id = p_conversation_id
    returning * into v_state;
  end if;

  return jsonb_build_object(
    'outcome', case when v_changed then 'applied' else 'noop' end,
    'read_state', to_jsonb(v_state)
  );
end;
$$;

create function public.baseline_conversation_activity_read_states(
  p_cutoff timestamptz,
  p_after_id uuid,
  p_limit integer
)
returns jsonb
language plpgsql
security invoker
set search_path = public
set timezone = 'UTC'
as $$
declare
  v_batch_ids uuid[];
  v_limit integer := least(greatest(coalesce(p_limit, 500), 1), 500);
begin
  if p_cutoff is null then
    raise exception 'conversation_activity_baseline_cutoff_required'
      using errcode = '22023';
  end if;

  select array_agg(batch.id order by batch.id)
    into v_batch_ids
    from (
      select c.id
        from public.conversations as c
       where p_after_id is null or c.id > p_after_id
       order by c.id
       limit v_limit
    ) as batch;

  if v_batch_ids is null or cardinality(v_batch_ids) = 0 then
    return jsonb_build_object('processed', 0, 'last_id', null);
  end if;

  insert into public.conversation_read_states (
    user_id,
    conversation_id,
    read_through_occurred_at,
    read_through_source_kind,
    read_through_source_id
  )
  select
    c.user_id,
    c.id,
    boundary.occurred_at,
    boundary.source_kind,
    boundary.source_id
  from public.conversations as c
  left join lateral (
    select candidate.occurred_at, candidate.source_kind, candidate.source_id
    from (
      select
        l.terminal_at as occurred_at,
        'chat_turn'::text as source_kind,
        l.turn_id as source_id,
        1 as source_kind_rank
      from public.chat_turn_lifecycles as l
      where l.user_id = c.user_id
        and l.conversation_id = c.id
        and l.status in (
          'completed', 'recoverable_failed', 'abandoned', 'reconciled'
        )
        and l.terminal_at <= p_cutoff
      union all
      select
        coalesce(j.finished_at, j.updated_at) as occurred_at,
        'backtest_job'::text as source_kind,
        j.id as source_id,
        2 as source_kind_rank
      from public.backtest_jobs as j
      where j.user_id = c.user_id
        and j.conversation_id = c.id
        and coalesce(j.finished_at, j.updated_at) <= p_cutoff
        and (
          j.status in ('failed', 'canceled', 'expired')
          or (
            j.status = 'succeeded'
            and exists (
              select 1
              from public.backtest_runs as r
              join public.evidence_artifacts as e
                on e.source_run_id = r.id
               and e.user_id = r.user_id
               and e.source_conversation_id = r.conversation_id
              where r.id = j.result_run_id
                and r.user_id = j.user_id
                and r.conversation_id = j.conversation_id
                and r.status = 'completed'
                and r.conversation_result_card
                  ->> 'evidence_artifact_id' = e.id::text
                and r.conversation_result_card
                  ->> 'idea_id' = e.idea_id::text
                and r.conversation_result_card
                  ->> 'idea_version_id' = e.idea_version_id::text
            )
          )
        )
    ) as candidate
    order by candidate.occurred_at desc,
      candidate.source_kind_rank desc,
      candidate.source_id desc
    limit 1
  ) as boundary on true
  where c.id = any(v_batch_ids)
  on conflict (user_id, conversation_id) do nothing;

  return jsonb_build_object(
    'processed', cardinality(v_batch_ids),
    'last_id', v_batch_ids[cardinality(v_batch_ids)]
  );
end;
$$;

revoke all on function public.reconcile_stale_conversation_activity_turns(
  uuid, uuid[]
) from public;
revoke all on function public.reconcile_stale_conversation_activity_turns(
  uuid, uuid[]
) from anon;
revoke all on function public.reconcile_stale_conversation_activity_turns(
  uuid, uuid[]
) from authenticated;
grant execute on function public.reconcile_stale_conversation_activity_turns(
  uuid, uuid[]
) to service_role;

revoke all on function public.read_conversation_activity_sources(
  uuid, uuid[]
) from public;
revoke all on function public.read_conversation_activity_sources(
  uuid, uuid[]
) from anon;
revoke all on function public.read_conversation_activity_sources(
  uuid, uuid[]
) from authenticated;
grant execute on function public.read_conversation_activity_sources(
  uuid, uuid[]
) to service_role;

revoke all on function public.mutate_conversation_activity_read_state(
  uuid, uuid, text, text, uuid
) from public;
revoke all on function public.mutate_conversation_activity_read_state(
  uuid, uuid, text, text, uuid
) from anon;
revoke all on function public.mutate_conversation_activity_read_state(
  uuid, uuid, text, text, uuid
) from authenticated;
grant execute on function public.mutate_conversation_activity_read_state(
  uuid, uuid, text, text, uuid
) to service_role;

revoke all on function public.baseline_conversation_activity_read_states(
  timestamptz, uuid, integer
) from public;
revoke all on function public.baseline_conversation_activity_read_states(
  timestamptz, uuid, integer
) from anon;
revoke all on function public.baseline_conversation_activity_read_states(
  timestamptz, uuid, integer
) from authenticated;
grant execute on function public.baseline_conversation_activity_read_states(
  timestamptz, uuid, integer
) to service_role;

do $activity_baseline$
declare
  v_cutoff timestamptz := clock_timestamp();
  v_after_id uuid;
  v_result jsonb;
begin
  loop
    select public.baseline_conversation_activity_read_states(
      v_cutoff,
      v_after_id,
      500
    ) into v_result;
    exit when coalesce((v_result ->> 'processed')::integer, 0) = 0;
    v_after_id := (v_result ->> 'last_id')::uuid;
  end loop;
end;
$activity_baseline$;
