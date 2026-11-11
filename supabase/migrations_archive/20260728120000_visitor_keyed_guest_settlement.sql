-- Guest message settlement follows the visitor, not the workspace.
--
-- finalize_chat_turn gains p_visitor_key (default null). When present, the
-- one settled unit goes to visitor_usage_counters inside the same
-- transaction as the terminal message, keeping the settlement atomicity the
-- lifecycle already guarantees. Replays return before the settle block, so
-- retried finalizations never double-charge the visitor.

drop function if exists public.finalize_chat_turn(
  uuid, uuid, uuid, text, uuid, text, text, jsonb, timestamptz, text,
  text, text, boolean, text, jsonb
);

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
  p_usage_limits jsonb,
  p_visitor_key text default null
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
  v_window record;
  v_visitor_windows jsonb;
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
     )
     or (p_visitor_key is not null and p_usage_resource is null) then
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

  if p_usage_resource is not null and p_visitor_key is not null then
    -- Visitor-keyed settlement: append without account settlement, then
    -- settle the visitor windows in this same transaction. Window bounds are
    -- derived here so the charge always lands in the current period.
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

    v_visitor_windows := '[]'::jsonb;
    for v_window in
      select
        (item ->> 'period')::text as window_period,
        (item ->> 'limit')::integer as limit_count
      from jsonb_array_elements(p_usage_limits) as item
    loop
      if v_window.window_period not in ('hour', 'day') then
        raise exception 'Unsupported visitor settlement period.'
          using errcode = '22023';
      end if;
      v_visitor_windows := v_visitor_windows || jsonb_build_object(
        'period', v_window.window_period,
        'limit', v_window.limit_count,
        'period_start', date_trunc(v_window.window_period, now()),
        'period_end', date_trunc(v_window.window_period, now())
          + case v_window.window_period
              when 'hour' then interval '1 hour'
              else interval '1 day'
            end
      );
    end loop;
    perform public.settle_visitor_usage(
      p_visitor_key,
      p_usage_resource,
      v_visitor_windows
    );
  elsif p_usage_resource is not null then
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
  text, text, boolean, text, jsonb, text
) from public;
revoke all on function public.finalize_chat_turn(
  uuid, uuid, uuid, text, uuid, text, text, jsonb, timestamptz, text,
  text, text, boolean, text, jsonb, text
) from anon;
revoke all on function public.finalize_chat_turn(
  uuid, uuid, uuid, text, uuid, text, text, jsonb, timestamptz, text,
  text, text, boolean, text, jsonb, text
) from authenticated;
grant execute on function public.finalize_chat_turn(
  uuid, uuid, uuid, text, uuid, text, text, jsonb, timestamptz, text,
  text, text, boolean, text, jsonb, text
) to service_role;

comment on table public.visitor_usage_counters is
  'Allowances for callers with no durable account. Not FK-bound: the subject '
  'is a visitor, not a profile. A fresh guest session mints a new user_id, '
  'so account-keyed guest allowances reset with it; visitor keys do not.';

-- Entry reads can race at the boundary; the settle transaction is the
-- last enforcer and holds the counter at its cap.
create or replace function public.settle_visitor_usage(
  p_visitor_key text,
  p_resource text,
  p_windows jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_window record;
  v_used integer;
  v_results jsonb := '[]'::jsonb;
begin
  if p_visitor_key is null or length(trim(p_visitor_key)) = 0 then
    raise exception 'visitor key is required';
  end if;

  for v_window in
    select
      (item->>'period')::text as window_period,
      (item->>'limit')::integer as limit_count,
      (item->>'period_start')::timestamptz as period_start,
      (item->>'period_end')::timestamptz as period_end
    from jsonb_array_elements(p_windows) as item
  loop
    if v_window.limit_count < 1 then
      raise exception 'visitor allowance exhausted'
        using errcode = 'P0001';
    end if;

    insert into public.visitor_usage_counters (
      visitor_key, resource, period, period_start, period_end,
      used_count, limit_count
    ) values (
      p_visitor_key, p_resource, v_window.window_period,
      v_window.period_start, v_window.period_end, 1, v_window.limit_count
    )
    on conflict (visitor_key, resource, period, period_start)
    do update set
      used_count = public.visitor_usage_counters.used_count + 1,
      limit_count = excluded.limit_count,
      updated_at = now()
    where public.visitor_usage_counters.used_count < excluded.limit_count
    returning used_count into v_used;

    if v_used is null then
      raise exception 'visitor allowance exhausted'
        using errcode = 'P0001';
    end if;

    v_results := v_results || jsonb_build_object(
      'period', v_window.window_period,
      'used_count', v_used,
      'limit_count', v_window.limit_count
    );
  end loop;

  return jsonb_build_object('settled', true, 'windows', v_results);
end;
$$;

revoke all on function public.settle_visitor_usage(text, text, jsonb)
  from public, anon, authenticated;
grant execute on function public.settle_visitor_usage(text, text, jsonb)
  to service_role;
