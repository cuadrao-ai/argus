-- Atomic guest compute claim: one visitor (IP) unit and one session unit,
-- or neither. Conversation turns used to read the visitor counter at entry
-- and increment it only at the terminal, so parallel requests could overshoot.
-- Research already claims before spend; this is the same shape for chat.

create or replace function public.claim_guest_compute_usage(
  p_visitor_key text,
  p_session_key text,
  p_resource text,
  p_visitor_limit integer,
  p_session_limit integer
)
returns jsonb
language plpgsql
security definer
set search_path = public
set timezone = 'UTC'
as $$
declare
  v_period_start timestamptz := date_trunc('day', now());
  v_period_end timestamptz := date_trunc('day', now()) + interval '1 day';
  v_visitor_used integer;
  v_session_used integer;
begin
  if p_resource is null or length(trim(p_resource)) = 0
     or p_visitor_key is null or length(trim(p_visitor_key)) = 0
     or p_session_key is null or length(trim(p_session_key)) = 0
     or p_visitor_key = p_session_key
     or p_visitor_limit is null or p_visitor_limit < 1
     or p_session_limit is null or p_session_limit < 1 then
    raise exception 'Guest compute claim is invalid.'
      using errcode = '22023';
  end if;

  -- Fixed lock order: visitor row, then session row.
  insert into public.visitor_usage_counters (
    visitor_key, resource, period, period_start, period_end,
    used_count, limit_count
  ) values (
    p_visitor_key, p_resource, 'day', v_period_start, v_period_end,
    0, p_visitor_limit
  )
  on conflict (visitor_key, resource, period, period_start) do nothing;

  select used_count
    into v_visitor_used
    from public.visitor_usage_counters
   where visitor_key = p_visitor_key
     and resource = p_resource
     and period = 'day'
     and period_start = v_period_start
   for update;

  insert into public.visitor_usage_counters (
    visitor_key, resource, period, period_start, period_end,
    used_count, limit_count
  ) values (
    p_session_key, p_resource, 'day', v_period_start, v_period_end,
    0, p_session_limit
  )
  on conflict (visitor_key, resource, period, period_start) do nothing;

  select used_count
    into v_session_used
    from public.visitor_usage_counters
   where visitor_key = p_session_key
     and resource = p_resource
     and period = 'day'
     and period_start = v_period_start
   for update;

  if v_visitor_used >= p_visitor_limit then
    return jsonb_build_object(
      'available', false,
      'visitor_exhausted', true,
      'session_exhausted', v_session_used >= p_session_limit
    );
  end if;

  if v_session_used >= p_session_limit then
    return jsonb_build_object(
      'available', false,
      'visitor_exhausted', false,
      'session_exhausted', true
    );
  end if;

  update public.visitor_usage_counters
     set used_count = used_count + 1,
         limit_count = p_visitor_limit,
         period_end = v_period_end,
         updated_at = now()
   where visitor_key = p_visitor_key
     and resource = p_resource
     and period = 'day'
     and period_start = v_period_start;

  update public.visitor_usage_counters
     set used_count = used_count + 1,
         limit_count = p_session_limit,
         period_end = v_period_end,
         updated_at = now()
   where visitor_key = p_session_key
     and resource = p_resource
     and period = 'day'
     and period_start = v_period_start;

  return jsonb_build_object(
    'available', true,
    'visitor_exhausted', false,
    'session_exhausted', false
  );
end;
$$;

revoke all on function public.claim_guest_compute_usage(
  text, text, text, integer, integer
) from public, anon, authenticated;
grant execute on function public.claim_guest_compute_usage(
  text, text, text, integer, integer
) to service_role;

comment on function public.claim_guest_compute_usage(
  text, text, text, integer, integer
) is
  'Atomically claims one visitor and one guest-session daily compute unit, or neither.';
