-- Settle one message allowance unit in the same transaction as the durable
-- terminal message append. Only a newly inserted row charges the hour and
-- day windows; a replayed or suppressed append charges nothing.

create or replace function public.append_conversation_message_settling_usage(
  p_user_id uuid,
  p_conversation_id uuid,
  p_message_id uuid,
  p_role text,
  p_content text,
  p_metadata jsonb,
  p_created_at timestamptz,
  p_preview text,
  p_usage_resource text,
  p_usage_limits jsonb
)
returns table (
  message jsonb,
  source_message jsonb,
  replayed boolean
)
language plpgsql
security invoker
set search_path = public
set timezone = 'UTC'
as $$
declare
  v_result record;
  v_window record;
  v_now timestamptz := now();
begin
  if p_usage_resource is null
     or jsonb_typeof(p_usage_limits) is distinct from 'array'
     or jsonb_array_length(p_usage_limits) = 0 then
    raise exception 'settlement requires a resource and limit windows'
      using errcode = '22023';
  end if;

  select t.message, t.source_message, t.replayed
    into v_result
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
    ) as t;

  if v_result.message is null then
    return;
  end if;

  if coalesce(v_result.replayed, false) then
    return query
      select v_result.message, v_result.source_message, true;
    return;
  end if;

  for v_window in
    select
      item ->> 'period' as period,
      (item ->> 'limit')::integer as limit_count
    from jsonb_array_elements(p_usage_limits) as item
  loop
    if v_window.period not in ('hour', 'day')
       or v_window.limit_count is null
       or v_window.limit_count < 0 then
      raise exception 'unsupported settlement window'
        using errcode = '22023';
    end if;

    insert into public.usage_counters (
      user_id,
      resource,
      period,
      period_start,
      period_end,
      used_count,
      limit_count
    ) values (
      p_user_id,
      p_usage_resource,
      v_window.period,
      date_trunc(v_window.period, v_now),
      date_trunc(v_window.period, v_now)
        + case v_window.period
            when 'hour' then interval '1 hour'
            else interval '1 day'
          end,
      1,
      v_window.limit_count
    )
    on conflict (user_id, resource, period, period_start)
    do update set
      used_count = public.usage_counters.used_count + 1,
      limit_count = excluded.limit_count,
      updated_at = now();
  end loop;

  return query
    select v_result.message, v_result.source_message, false;
end;
$$;

revoke all on function public.append_conversation_message_settling_usage(
  uuid, uuid, uuid, text, text, jsonb, timestamptz, text, text, jsonb
) from public;
revoke all on function public.append_conversation_message_settling_usage(
  uuid, uuid, uuid, text, text, jsonb, timestamptz, text, text, jsonb
) from anon;
revoke all on function public.append_conversation_message_settling_usage(
  uuid, uuid, uuid, text, text, jsonb, timestamptz, text, text, jsonb
) from authenticated;
grant execute on function public.append_conversation_message_settling_usage(
  uuid, uuid, uuid, text, text, jsonb, timestamptz, text, text, jsonb
) to service_role;
