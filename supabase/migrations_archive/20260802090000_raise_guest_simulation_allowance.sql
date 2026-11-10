-- Raise the guest simulation policy from one completed test to two.
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
      when 'backtest_runs' then 2
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
