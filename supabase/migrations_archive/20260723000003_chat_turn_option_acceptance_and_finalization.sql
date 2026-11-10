-- Extend ordinary-turn acceptance for response-option compare-and-append, and
-- add atomic terminal assistant persistence. The earlier migration is already
-- deployed, so replace its signature forward instead of rewriting history.

drop function if exists public.accept_chat_turn(
  uuid, uuid, uuid, text, text, jsonb, timestamptz, text, text
);

create function public.accept_chat_turn(
  p_user_id uuid,
  p_conversation_id uuid,
  p_message_id uuid,
  p_role text,
  p_content text,
  p_metadata jsonb,
  p_created_at timestamptz,
  p_preview text,
  p_request_id text,
  p_expected_source_assistant_id uuid default null,
  p_expected_source_metadata jsonb default null,
  p_option_id text default null,
  p_replacement_values jsonb default null,
  p_request_message_id uuid default null
)
returns table (
  message jsonb,
  lifecycle jsonb,
  replayed boolean,
  source_message jsonb
)
language plpgsql
security invoker
set search_path = public
set timezone = 'UTC'
as $$
declare
  v_appended record;
  v_lifecycle public.chat_turn_lifecycles%rowtype;
  v_original public.messages%rowtype;
  v_retry_lifecycle public.chat_turn_lifecycles%rowtype;
  v_source public.messages%rowtype;
  v_latest public.messages%rowtype;
  v_existing public.messages%rowtype;
  v_existing_lifecycle public.chat_turn_lifecycles%rowtype;
  v_canonical_metadata jsonb;
  v_canonical_content text;
  v_canonical_preview text;
  v_retry boolean := p_request_message_id is not null;
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

  if v_retry then
    if p_message_id = p_request_message_id then
      return;
    end if;

    select l.*
      into v_retry_lifecycle
      from public.chat_turn_lifecycles as l
     where l.turn_id = p_request_message_id
       and l.user_id = p_user_id
       and l.conversation_id = p_conversation_id
     for update;
    if not found then
      return;
    end if;

    perform 1
      from public.conversations as c
     where c.id = p_conversation_id
       and c.user_id = p_user_id
     for update;
    if not found then
      return;
    end if;

    select m.*
      into v_original
      from public.messages as m
     where m.id = p_request_message_id
       and m.user_id = p_user_id
       and m.conversation_id = p_conversation_id
       and m.role = 'user';

    if v_original.id is null
       or v_retry_lifecycle.turn_id is null
       or v_retry_lifecycle.retryable is distinct from true
       or not (
         v_retry_lifecycle.status in ('recoverable_failed', 'abandoned')
         or (
           v_retry_lifecycle.status = 'reconciled'
           and v_retry_lifecycle.reconciled_outcome = 'recoverable_failed'
         )
       )
       or jsonb_typeof(v_original.metadata -> 'chat_action')
         is distinct from 'object'
       or v_original.metadata -> 'chat_action' ->> 'type'
         is distinct from 'select_response_option'
       or jsonb_typeof(
         v_original.metadata -> 'chat_action' -> 'payload'
       ) is distinct from 'object'
       or nullif(btrim(
         v_original.metadata -> 'chat_action' -> 'payload' ->> 'option_id'
       ), '') is null
       or jsonb_typeof(
         v_original.metadata -> 'chat_action' -> 'payload'
           -> 'replacement_values'
       ) is distinct from 'object' then
      return;
    end if;

    select m.*
      into v_source
      from public.messages as m
     where m.user_id = p_user_id
       and m.conversation_id = p_conversation_id
       and m.role = 'assistant'
       and (
         m.created_at < v_original.created_at
         or (
           m.created_at = v_original.created_at
           and m.id < v_original.id
         )
       )
       and exists (
         select 1
           from jsonb_array_elements(
             case
               when jsonb_typeof(
                 m.metadata -> 'clarification' -> 'options'
               ) = 'array'
               then m.metadata -> 'clarification' -> 'options'
               else '[]'::jsonb
             end
           ) as response_option
          where response_option ->> 'id' = (
            v_original.metadata -> 'chat_action' -> 'payload' ->> 'option_id'
          )
            and response_option -> 'replacement_values' = (
              v_original.metadata -> 'chat_action' -> 'payload'
                -> 'replacement_values'
            )
       )
     order by m.created_at desc, m.id desc
     limit 1;
    if not found then
      return;
    end if;

    v_canonical_content := v_original.content;
    v_canonical_metadata := (
      coalesce(p_metadata, '{}'::jsonb)
      - 'chat_action'
      - 'mentions'
      - 'resolution_provenance'
    ) || jsonb_build_object(
      'chat_action',
      v_original.metadata -> 'chat_action'
    );
    v_canonical_preview := case
      when v_canonical_content = '__ONBOARDING_SKIP__'
        or v_canonical_content like '__ONBOARDING_GOAL__:%'
      then null
      else left(
        regexp_replace(btrim(v_canonical_content), '\s+', ' ', 'g'),
        180
      )
    end;

    select m.*
      into v_existing
      from public.messages as m
     where m.id = p_message_id;
    if found then
      select l.*
        into v_existing_lifecycle
        from public.chat_turn_lifecycles as l
       where l.turn_id = p_message_id
         and l.user_id = p_user_id
         and l.conversation_id = p_conversation_id;
      if not found
         or v_existing.user_id is distinct from p_user_id
         or v_existing.conversation_id is distinct from p_conversation_id
         or v_existing.role is distinct from p_role
         or v_existing.content is distinct from v_canonical_content
         or v_existing.metadata is distinct from v_canonical_metadata
         or v_existing_lifecycle.request_id is distinct from p_request_id then
        return;
      end if;
      return query select
        to_jsonb(v_existing),
        to_jsonb(v_existing_lifecycle),
        true,
        to_jsonb(v_source);
      return;
    end if;

    select m.*
      into v_latest
      from public.messages as m
     where m.user_id = p_user_id
       and m.conversation_id = p_conversation_id
     order by m.created_at desc, m.id desc
     limit 1;
    if not found
       or (
         v_retry_lifecycle.status = 'abandoned'
         and v_latest.id is distinct from v_original.id
       )
       or (
         v_retry_lifecycle.status <> 'abandoned'
         and v_latest.id is distinct from
           v_retry_lifecycle.assistant_message_id
       ) then
      return;
    end if;
  else
    v_canonical_content := p_content;
    v_canonical_metadata := p_metadata;
    v_canonical_preview := p_preview;
  end if;

  select appended.message, appended.source_message, appended.replayed
    into v_appended
    from public.append_conversation_message(
      p_user_id,
      p_conversation_id,
      p_message_id,
      p_role,
      v_canonical_content,
      v_canonical_metadata,
      p_created_at,
      v_canonical_preview,
      case when v_retry then null else p_expected_source_assistant_id end,
      case when v_retry then null else p_expected_source_metadata end,
      case when v_retry then null else p_option_id end,
      case when v_retry then null else p_replacement_values end
    ) as appended;

  if v_appended.message is null then
    if p_expected_source_assistant_id is not null then
      return;
    end if;
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
    coalesce(v_appended.replayed, false),
    case
      when v_retry then to_jsonb(v_source)
      else v_appended.source_message
    end;
end;
$$;

revoke all on function public.accept_chat_turn(
  uuid, uuid, uuid, text, text, jsonb, timestamptz, text, text,
  uuid, jsonb, text, jsonb, uuid
) from public;
revoke all on function public.accept_chat_turn(
  uuid, uuid, uuid, text, text, jsonb, timestamptz, text, text,
  uuid, jsonb, text, jsonb, uuid
) from anon;
revoke all on function public.accept_chat_turn(
  uuid, uuid, uuid, text, text, jsonb, timestamptz, text, text,
  uuid, jsonb, text, jsonb, uuid
) from authenticated;
grant execute on function public.accept_chat_turn(
  uuid, uuid, uuid, text, text, jsonb, timestamptz, text, text,
  uuid, jsonb, text, jsonb, uuid
) to service_role;

-- Terminal assistant persistence, successful-turn allowance settlement, and
-- lifecycle transition share one lifecycle-first transaction. Locking the
-- lifecycle before the conversation/message writer serializes finalization
-- with stale reconciliation without exposing transition rows to the API.
create function public.finalize_chat_turn(
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
