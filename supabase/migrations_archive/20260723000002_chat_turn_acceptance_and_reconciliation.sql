-- Compose ordinary-turn acceptance with the existing serialized message append,
-- then reconcile stale current-state rows from immutable terminal messages.

create or replace function public.accept_chat_turn(
  p_user_id uuid,
  p_conversation_id uuid,
  p_message_id uuid,
  p_role text,
  p_content text,
  p_metadata jsonb,
  p_created_at timestamptz,
  p_preview text,
  p_request_id text
)
returns table (
  message jsonb,
  lifecycle jsonb,
  replayed boolean
)
language plpgsql
security invoker
set search_path = public
set timezone = 'UTC'
as $$
declare
  v_appended record;
  v_lifecycle public.chat_turn_lifecycles%rowtype;
  v_now timestamptz := clock_timestamp();
begin
  if p_role is distinct from 'user' then
    raise exception 'Accepted chat-turn message must have user role.'
      using errcode = '22023';
  end if;

  if nullif(btrim(p_request_id), '') is null then
    raise exception 'Lifecycle request id must not be blank.'
      using errcode = '22023';
  end if;

  select appended.message, appended.source_message, appended.replayed
    into v_appended
    from public.append_conversation_message(
      p_user_id,
      p_conversation_id,
      p_message_id,
      p_role,
      p_content,
      p_metadata,
      p_created_at,
      p_preview,
      null::uuid,
      null::jsonb,
      null::text,
      null::jsonb
    ) as appended;

  if v_appended.message is null then
    raise exception 'Serialized message append returned no message.'
      using errcode = 'P0002';
  end if;

  insert into public.chat_turn_lifecycles (
    turn_id,
    user_id,
    conversation_id,
    request_id,
    status,
    accepted_at,
    created_at,
    updated_at
  ) values (
    p_message_id,
    p_user_id,
    p_conversation_id,
    p_request_id,
    'accepted',
    v_now,
    v_now,
    v_now
  )
  on conflict (turn_id) do nothing
  returning * into v_lifecycle;

  if not found then
    select l.*
      into v_lifecycle
      from public.chat_turn_lifecycles as l
     where l.turn_id = p_message_id
     for update;

    if not found
       or v_lifecycle.user_id is distinct from p_user_id
       or v_lifecycle.conversation_id is distinct from p_conversation_id
       or v_lifecycle.request_id is distinct from p_request_id then
      raise exception 'Chat-turn identity collided with a different request.'
        using errcode = '23505';
    end if;
  end if;

  return query select
    v_appended.message,
    to_jsonb(v_lifecycle),
    coalesce(v_appended.replayed, false);
end;
$$;

revoke all on function public.accept_chat_turn(
  uuid, uuid, uuid, text, text, jsonb, timestamptz, text, text
) from public;
revoke all on function public.accept_chat_turn(
  uuid, uuid, uuid, text, text, jsonb, timestamptz, text, text
) from anon;
revoke all on function public.accept_chat_turn(
  uuid, uuid, uuid, text, text, jsonb, timestamptz, text, text
) from authenticated;
grant execute on function public.accept_chat_turn(
  uuid, uuid, uuid, text, text, jsonb, timestamptz, text, text
) to service_role;

create or replace function public.reconcile_stale_chat_turns(
  p_conversation_id uuid,
  p_user_id uuid
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
  for v_turn in
    select l.*
      from public.chat_turn_lifecycles as l
     where l.user_id = p_user_id
       and l.conversation_id = p_conversation_id
       and l.status in ('accepted', 'running')
       and coalesce(l.running_at, l.accepted_at)
         <= v_now - interval '15 minutes'
     order by coalesce(l.running_at, l.accepted_at) asc, l.turn_id asc
     limit 20
     for update skip locked
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
      v_outcome := v_evidence.metadata
        #>> '{agent_runtime_turn,status}';
      v_failure_code := case
        when v_outcome = 'recoverable_failed' then
          v_evidence.metadata #>> '{agent_runtime_turn,failure_code}'
        else null
      end;
      v_retryable := case
        when v_outcome = 'recoverable_failed' then
          coalesce(
            v_evidence.metadata
              #> '{agent_runtime_turn,retryable}' = 'true'::jsonb,
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
      )
      into v_result;
    else
      select public.transition_chat_turn(
        v_turn.turn_id,
        'abandoned',
        null,
        null,
        'turn_abandoned',
        true
      )
      into v_result;
    end if;

    if v_result ->> 'outcome' in ('applied', 'noop')
       and v_result -> 'row' is not null then
      return next v_result -> 'row';
    end if;
  end loop;
end;
$$;

revoke all on function public.reconcile_stale_chat_turns(
  uuid, uuid
) from public;
revoke all on function public.reconcile_stale_chat_turns(
  uuid, uuid
) from anon;
revoke all on function public.reconcile_stale_chat_turns(
  uuid, uuid
) from authenticated;
grant execute on function public.reconcile_stale_chat_turns(
  uuid, uuid
) to service_role;
