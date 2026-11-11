-- Settlement remains the canonical owner of completed assistant-message usage.
-- Guest sessions must not cross their lifetime boundary under concurrent
-- successful terminals; registered settle-only accounting remains unchanged.
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
set search_path = public, argus_private
set timezone = 'UTC'
as $$
declare
  v_result record;
  v_window record;
  v_now timestamptz := now();
  v_updated_rows bigint;
begin
  if p_usage_resource is null then
    raise exception 'settlement requires a resource'
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
    select * from argus_private.validated_usage_windows(
      p_user_id,
      p_usage_resource,
      p_usage_limits,
      v_now
    )
  loop
    if v_window.window_period = 'guest_session' then
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
        v_window.window_period,
        v_window.period_start,
        v_window.period_end,
        1,
        v_window.limit_count
      )
      on conflict (user_id, resource, period, period_start)
      do update set
        used_count = public.usage_counters.used_count + 1,
        limit_count = excluded.limit_count,
        updated_at = now()
      where public.usage_counters.used_count < excluded.limit_count;

      get diagnostics v_updated_rows = row_count;
      if v_updated_rows = 0 then
        raise exception 'guest message allowance exhausted'
          using errcode = 'AG010';
      end if;
    else
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
        v_window.window_period,
        v_window.period_start,
        v_window.period_end,
        1,
        v_window.limit_count
      )
      on conflict (user_id, resource, period, period_start)
      do update set
        used_count = public.usage_counters.used_count + 1,
        limit_count = excluded.limit_count,
        updated_at = now();
    end if;
  end loop;

  return query
    select v_result.message, v_result.source_message, false;
end;
$$;

revoke all on function public.append_conversation_message_settling_usage(
  uuid, uuid, uuid, text, text, jsonb, timestamptz, text, text, jsonb
) from public, anon, authenticated;
grant execute on function public.append_conversation_message_settling_usage(
  uuid, uuid, uuid, text, text, jsonb, timestamptz, text, text, jsonb
) to service_role;
