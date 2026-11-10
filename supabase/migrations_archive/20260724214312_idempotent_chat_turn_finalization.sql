-- Make terminal chat-turn finalization safe to retry. The lifecycle row and
-- immutable assistant message are the replay identity; usage settlement
-- arguments are intentionally ignored after the first terminal commit.

create or replace function public.finalize_chat_turn(
  p_user_id uuid,
  p_conversation_id uuid,
  p_turn_id uuid,
  p_request_id text,
  p_message_id uuid,
  p_role text,
  p_content text,
  p_metadata jsonb,
  p_created_at timestamptz,
  p_preview text,
  p_to_status text,
  p_failure_code text,
  p_retryable boolean,
  p_usage_resource text,
  p_usage_limits jsonb
)
returns table (message jsonb)
language plpgsql
security invoker
set search_path = public
set timezone = 'UTC'
as $$
declare
  v_turn public.chat_turn_lifecycles%rowtype;
  v_existing public.messages%rowtype;
  v_appended record;
  v_transition jsonb;
  v_retryable boolean := coalesce(p_retryable, false);
begin
  select l.*
    into v_turn
    from public.chat_turn_lifecycles as l
   where l.turn_id = p_turn_id
   for update;

  if not found
     or v_turn.user_id is distinct from p_user_id
     or v_turn.conversation_id is distinct from p_conversation_id
     or v_turn.request_id is distinct from p_request_id then
    raise exception 'Chat-turn finalization conflict.'
      using errcode = 'P0002';
  end if;

  if p_role is distinct from 'assistant'
     or p_to_status not in ('completed', 'recoverable_failed')
     or (
       p_to_status = 'completed'
       and (p_failure_code is not null or v_retryable)
     )
     or (
       p_to_status = 'recoverable_failed'
       and p_usage_resource is not null
     )
     or (
       (p_usage_resource is null) is distinct from
       (p_usage_limits is null)
     ) then
    raise exception 'Chat-turn terminal payload is invalid.'
      using errcode = '22023';
  end if;

  if v_turn.status in ('completed', 'recoverable_failed') then
    select m.*
      into v_existing
      from public.messages as m
     where m.id = p_message_id;

    if not found
       or v_turn.status is distinct from p_to_status
       or v_turn.assistant_message_id is distinct from p_message_id
       or v_turn.reconciled_outcome is not null
       or v_turn.failure_code is distinct from p_failure_code
       or v_turn.retryable is distinct from v_retryable
       or v_existing.user_id is distinct from p_user_id
       or v_existing.conversation_id is distinct from p_conversation_id
       or v_existing.role is distinct from p_role
       or v_existing.content is distinct from p_content
       or v_existing.metadata is distinct from coalesce(p_metadata, '{}'::jsonb)
    then
      raise exception 'Chat-turn finalization conflict.'
        using errcode = '40001';
    end if;

    return query select to_jsonb(v_existing);
    return;
  end if;

  if v_turn.status not in ('accepted', 'running') then
    raise exception 'Chat-turn finalization conflict.'
      using errcode = '40001';
  end if;

  if p_usage_resource is not null then
    select appended.message, appended.source_message, appended.replayed
      into v_appended
      from public.append_conversation_message_settling_usage(
        p_user_id,
        p_conversation_id,
        p_message_id,
        p_role,
        p_content,
        p_metadata,
        p_created_at,
        p_preview,
        p_usage_resource,
        p_usage_limits
      ) as appended;
  else
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
  end if;

  if v_appended.message is null then
    raise exception 'Chat-turn terminal message was not persisted.'
      using errcode = 'P0002';
  end if;

  select public.transition_chat_turn(
    p_turn_id,
    p_to_status,
    p_message_id,
    null,
    p_failure_code,
    v_retryable
  )
  into v_transition;

  if v_transition ->> 'outcome' not in ('applied', 'noop') then
    raise exception 'Chat-turn finalization conflict.'
      using errcode = '40001';
  end if;

  return query select v_appended.message;
end;
$$;

revoke all on function public.finalize_chat_turn(
  uuid, uuid, uuid, text, uuid, text, text, jsonb, timestamptz, text,
  text, text, boolean, text, jsonb
) from public;
revoke all on function public.finalize_chat_turn(
  uuid, uuid, uuid, text, uuid, text, text, jsonb, timestamptz, text,
  text, text, boolean, text, jsonb
) from anon;
revoke all on function public.finalize_chat_turn(
  uuid, uuid, uuid, text, uuid, text, text, jsonb, timestamptz, text,
  text, text, boolean, text, jsonb
) from authenticated;
grant execute on function public.finalize_chat_turn(
  uuid, uuid, uuid, text, uuid, text, text, jsonb, timestamptz, text,
  text, text, boolean, text, jsonb
) to service_role;
