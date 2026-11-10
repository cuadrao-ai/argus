-- Add fixed-lifetime guest allowance windows to the existing atomic owners.

alter table public.usage_counters
  drop constraint if exists usage_counters_period_check;
alter table public.usage_counters
  add constraint usage_counters_period_check
  check (period in ('hour', 'day', 'guest_session'));

create schema if not exists argus_private;
revoke all on schema argus_private from public, anon, authenticated;

create or replace function argus_private.validated_usage_windows(
  p_user_id uuid,
  p_resource text,
  p_usage_limits jsonb,
  p_now timestamptz
)
returns table (
  window_period text,
  limit_count integer,
  period_start timestamptz,
  period_end timestamptz,
  guest_session boolean
)
language plpgsql
security definer
set search_path = public, argus_private
set timezone = 'UTC'
as $$
declare
  v_item jsonb;
  v_period text;
  v_limit integer;
  v_start timestamptz;
  v_end timestamptz;
  v_workspace public.guest_workspaces%rowtype;
  v_expected_limit integer;
  v_is_anonymous boolean;
begin
  if jsonb_typeof(p_usage_limits) is distinct from 'array'
     or jsonb_array_length(p_usage_limits) = 0 then
    raise exception 'allowance windows are required'
      using errcode = '22023';
  end if;

  select coalesce(u.is_anonymous, false)
    into v_is_anonymous
    from auth.users as u
   where u.id = p_user_id;
  if not found then
    raise exception 'allowance owner is not an Auth user'
      using errcode = '23503';
  end if;
  if v_is_anonymous and (
    jsonb_array_length(p_usage_limits) <> 1
    or p_usage_limits -> 0 ->> 'period' <> 'guest_session'
  ) then
    raise exception 'anonymous users require the guest session allowance'
      using errcode = '23514';
  end if;
  if not v_is_anonymous and exists (
    select 1
      from jsonb_array_elements(p_usage_limits) as item
     where item ->> 'period' = 'guest_session'
  ) then
    raise exception 'permanent users cannot use a guest session allowance'
      using errcode = '23514';
  end if;

  for v_item in select value from jsonb_array_elements(p_usage_limits)
  loop
    v_period := v_item ->> 'period';
    v_limit := (v_item ->> 'limit')::integer;
    if v_limit is null or v_limit < 0 then
      raise exception 'invalid allowance limit'
        using errcode = '22023';
    end if;

    if v_period in ('hour', 'day') then
      if v_item ->> 'period_start' is not null
         or v_item ->> 'period_end' is not null then
        raise exception 'registered windows cannot supply explicit bounds'
          using errcode = '22023';
      end if;
      v_start := date_trunc(v_period, p_now);
      v_end := v_start
        + case v_period
            when 'hour' then interval '1 hour'
            else interval '1 day'
          end;
      return query
        select v_period, v_limit, v_start, v_end, false;
      continue;
    end if;

    if v_period <> 'guest_session' then
      raise exception 'unsupported allowance window'
        using errcode = '22023';
    end if;

    select *
      into v_workspace
      from public.guest_workspaces
     where user_id = p_user_id
     for update;
    if not found
       or v_workspace.status <> 'active'
       or v_workspace.expires_at <= p_now then
      raise exception 'guest workspace is not active'
        using errcode = '23514';
    end if;

    v_start := (v_item ->> 'period_start')::timestamptz;
    v_end := (v_item ->> 'period_end')::timestamptz;
    if v_start is distinct from v_workspace.created_at
       or v_end is distinct from v_workspace.expires_at then
      raise exception 'guest allowance bounds do not match workspace'
        using errcode = '23514';
    end if;

    v_expected_limit := case p_resource
      when 'chat_messages' then 10
      when 'backtest_runs' then 1
      when 'feedback' then 5
      else null
    end;
    if v_expected_limit is null or v_limit <> v_expected_limit then
      raise exception 'guest allowance limit does not match policy'
        using errcode = '23514';
    end if;
    return query
      select v_period, v_limit, v_start, v_end, true;
  end loop;
end;
$$;

revoke all on function argus_private.validated_usage_windows(
  uuid, text, jsonb, timestamptz
) from public, anon, authenticated;
grant usage on schema argus_private to service_role;
grant execute on function argus_private.validated_usage_windows(
  uuid, text, jsonb, timestamptz
) to service_role;

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
  v_used integer;
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
    select coalesce(sum(used_count), 0)
      into v_used
      from public.usage_counters
     where user_id = p_user_id
       and resource = p_usage_resource
       and period = v_window.window_period
       and period_start = v_window.period_start;
    if v_used >= v_window.limit_count then
      raise exception 'allowance exhausted'
        using errcode = '23514';
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

create or replace function public.admit_backtest_job(
    p_user_id uuid,
    p_operation_scope text,
    p_idempotency_key text,
    p_identity_hash text,
    p_payload_hash text,
    p_launch_payload jsonb,
    p_initial_status text,
    p_conversation_id uuid,
    p_request_message_id uuid,
    p_confirmation_message_id uuid,
    p_execution_metadata jsonb,
    p_user_running_limit integer,
    p_user_queued_limit integer,
    p_global_running_limit integer,
    p_global_queued_limit integer,
    p_allowance_limits jsonb
) returns jsonb
language plpgsql
security definer
set search_path = public, argus_private
set timezone = 'UTC'
as $$
declare
    v_existing public.backtest_jobs%rowtype;
    v_job public.backtest_jobs%rowtype;
    v_now timestamptz := now();
    v_stale record;
    v_window record;
    v_charged integer;
    v_user_running integer;
    v_user_queued integer;
    v_global_running integer;
    v_global_queued integer;
begin
    if p_operation_scope not in ('chat.run_backtest', 'backtests.run') then
        raise exception 'unsupported operation scope %', p_operation_scope;
    end if;
    if p_initial_status not in ('queued', 'running') then
        raise exception 'unsupported initial status %', p_initial_status;
    end if;

    perform pg_advisory_xact_lock(hashtext('backtest_admission'));

    select * into v_existing
    from public.backtest_jobs
    where user_id = p_user_id
      and operation_scope = p_operation_scope
      and idempotency_key = p_idempotency_key
    for update;
    if found then
        if v_existing.identity_hash is null then
            if v_existing.payload_hash is not null
               and v_existing.payload_hash = p_payload_hash then
                update public.backtest_jobs
                set identity_hash = p_identity_hash,
                    updated_at = v_now
                where id = v_existing.id
                returning * into v_existing;
            else
                return jsonb_build_object('decision', 'conflict');
            end if;
        elsif v_existing.identity_hash <> p_identity_hash then
            return jsonb_build_object('decision', 'conflict');
        end if;
        if p_operation_scope = 'backtests.run'
           and v_existing.status = 'running'
           and v_existing.started_at is not null
           and v_existing.started_at <= v_now - interval '15 minutes' then
            update public.backtest_jobs
            set status = 'failed',
                failure_code = 'direct_execution_abandoned',
                failure_detail = 'execution_interrupted',
                retryable = true,
                finished_at = v_now,
                updated_at = v_now
            where id = v_existing.id
            returning * into v_existing;
        end if;
        return jsonb_build_object(
            'decision', 'replay',
            'job', to_jsonb(v_existing)
        );
    end if;

    if p_operation_scope = 'backtests.run' then
        for v_stale in
            select id from public.backtest_jobs
            where operation_scope = 'backtests.run'
              and status = 'running'
              and started_at is not null
              and started_at <= v_now - interval '15 minutes'
            order by started_at asc, id asc
            limit 20
            for update
        loop
            update public.backtest_jobs
            set status = 'failed',
                failure_code = 'direct_execution_abandoned',
                failure_detail = 'execution_interrupted',
                retryable = true,
                finished_at = v_now,
                updated_at = v_now
            where id = v_stale.id;
        end loop;
    end if;

    for v_window in
        select * from argus_private.validated_usage_windows(
          p_user_id,
          'backtest_runs',
          p_allowance_limits,
          v_now
        )
    loop
        select coalesce(sum(used_count), 0) into v_charged
        from public.usage_counters
        where user_id = p_user_id
          and resource = 'backtest_runs'
          and period = v_window.window_period
          and period_start = v_window.period_start;
        if v_charged >= v_window.limit_count then
            return jsonb_build_object(
              'decision',
              case when v_window.guest_session
                then 'conversion_required'
                else 'allowance_exhausted'
              end
            );
        end if;
    end loop;

    select
        count(*) filter (where status = 'running' and user_id = p_user_id),
        count(*) filter (where status = 'queued' and user_id = p_user_id),
        count(*) filter (where status = 'running'),
        count(*) filter (where status = 'queued')
    into v_user_running, v_user_queued, v_global_running, v_global_queued
    from public.backtest_jobs
    where status in ('queued', 'running');

    if p_operation_scope = 'backtests.run' or p_initial_status = 'running' then
        if v_user_running >= p_user_running_limit then
            return jsonb_build_object('decision', 'per_user_capacity');
        end if;
    end if;
    if p_operation_scope = 'backtests.run' or p_initial_status = 'queued' then
        if v_user_queued >= p_user_queued_limit then
            return jsonb_build_object('decision', 'per_user_capacity');
        end if;
    end if;
    if p_operation_scope = 'backtests.run' or p_initial_status = 'running' then
        if v_global_running >= p_global_running_limit then
            return jsonb_build_object('decision', 'global_capacity');
        end if;
    end if;
    if p_operation_scope = 'backtests.run' or p_initial_status = 'queued' then
        if v_global_queued >= p_global_queued_limit then
            return jsonb_build_object('decision', 'global_capacity');
        end if;
    end if;

    insert into public.backtest_jobs (
        user_id,
        conversation_id,
        request_message_id,
        confirmation_message_id,
        operation_scope,
        idempotency_key,
        identity_hash,
        payload_hash,
        launch_payload,
        status,
        priority,
        attempts,
        max_attempts,
        queued_at,
        started_at,
        execution_metadata
    ) values (
        p_user_id,
        p_conversation_id,
        p_request_message_id,
        p_confirmation_message_id,
        p_operation_scope,
        p_idempotency_key,
        p_identity_hash,
        p_payload_hash,
        p_launch_payload,
        p_initial_status,
        'normal',
        0,
        1,
        v_now,
        case when p_initial_status = 'running' then v_now else null end,
        coalesce(p_execution_metadata, '{}'::jsonb)
    ) returning * into v_job;

    for v_window in
        select * from argus_private.validated_usage_windows(
          p_user_id,
          'backtest_runs',
          p_allowance_limits,
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
            'backtest_runs',
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
        'decision', 'admitted',
        'job', to_jsonb(v_job)
    );
end;
$$;

revoke all on function public.admit_backtest_job(
    uuid, text, text, text, text, jsonb, text, uuid, uuid, uuid, jsonb,
    integer, integer, integer, integer, jsonb
) from public, anon, authenticated;
grant execute on function public.admit_backtest_job(
    uuid, text, text, text, text, jsonb, text, uuid, uuid, uuid, jsonb,
    integer, integer, integer, integer, jsonb
) to service_role;

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
