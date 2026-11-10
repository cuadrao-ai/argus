create or replace function public.create_feedback_settling_usage(
  p_feedback_id uuid,
  p_user_id uuid,
  p_feedback_type text,
  p_message text,
  p_context jsonb,
  p_usage_resource text,
  p_usage_limits jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = public, argus_private
set timezone = 'UTC'
as $$
declare
  v_existing public.feedback%rowtype;
  v_window record;
  v_now timestamptz := now();
  v_used integer;
begin
  perform pg_advisory_xact_lock(
    hashtextextended(p_user_id::text || ':' || p_usage_resource, 0)
  );

  select *
    into v_existing
    from public.feedback
   where id = p_feedback_id
   for update;
  if found then
    if v_existing.user_id is not distinct from p_user_id
       and v_existing.type is not distinct from p_feedback_type
       and v_existing.message is not distinct from p_message
       and v_existing.context is not distinct from coalesce(p_context, '{}'::jsonb)
    then
      return jsonb_build_object(
        'decision', 'accepted',
        'feedback_id', p_feedback_id,
        'replayed', true
      );
    end if;
    raise exception 'feedback identity collision'
      using errcode = '23505';
  end if;

  for v_window in
    select * from argus_private.validated_usage_windows(
      p_user_id,
      p_usage_resource,
      p_usage_limits,
      v_now
    )
  loop
    select coalesce(sum(used_count), 0)
      into v_used
      from public.usage_counters
     where user_id = p_user_id
       and resource = p_usage_resource
       and period = v_window.window_period
       and period_start = v_window.period_start;
    if v_used >= v_window.limit_count then
      return jsonb_build_object(
        'decision',
        case when v_window.guest_session
          then 'conversion_required'
          else 'allowance_exhausted'
        end
      );
    end if;
  end loop;

  insert into public.feedback (
    id,
    user_id,
    type,
    message,
    context,
    created_at
  ) values (
    p_feedback_id,
    p_user_id,
    p_feedback_type,
    p_message,
    coalesce(p_context, '{}'::jsonb),
    v_now
  );

  for v_window in
    select * from argus_private.validated_usage_windows(
      p_user_id,
      p_usage_resource,
      p_usage_limits,
      v_now
    )
  loop
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
  end loop;

  return jsonb_build_object(
    'decision', 'accepted',
    'feedback_id', p_feedback_id,
    'replayed', false
  );
end;
$$;

revoke all on function public.create_feedback_settling_usage(
  uuid, uuid, text, text, jsonb, text, jsonb
) from public, anon, authenticated;
grant execute on function public.create_feedback_settling_usage(
  uuid, uuid, text, text, jsonb, text, jsonb
) to service_role;
