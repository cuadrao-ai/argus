-- Atomic signed-in compute claim: one account-keyed daily unit, or none.
-- Guest turns already claim before spend (#674). Signed-in accounts had no
-- chat ceiling, so one login could run unbounded LLM spend. This is the
-- same forced-reject shape for a single visitor_usage_counters row.

create or replace function public.claim_registered_compute_usage(
  p_account_key text,
  p_resource text,
  p_limit integer
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
  v_used integer;
begin
  if p_resource is null or length(trim(p_resource)) = 0
     or p_account_key is null or length(trim(p_account_key)) = 0
     or p_limit is null or p_limit < 1 then
    raise exception 'Registered compute claim is invalid.'
      using errcode = '22023';
  end if;

  insert into public.visitor_usage_counters (
    visitor_key, resource, period, period_start, period_end,
    used_count, limit_count
  ) values (
    p_account_key, p_resource, 'day', v_period_start, v_period_end,
    0, p_limit
  )
  on conflict (visitor_key, resource, period, period_start) do nothing;

  select used_count
    into v_used
    from public.visitor_usage_counters
   where visitor_key = p_account_key
     and resource = p_resource
     and period = 'day'
     and period_start = v_period_start
   for update;

  if v_used >= p_limit then
    return jsonb_build_object('available', false);
  end if;

  update public.visitor_usage_counters
     set used_count = used_count + 1,
         limit_count = p_limit,
         period_end = v_period_end,
         updated_at = now()
   where visitor_key = p_account_key
     and resource = p_resource
     and period = 'day'
     and period_start = v_period_start;

  return jsonb_build_object('available', true);
end;
$$;

revoke all on function public.claim_registered_compute_usage(
  text, text, integer
) from public, anon, authenticated;
grant execute on function public.claim_registered_compute_usage(
  text, text, integer
) to service_role;

comment on function public.claim_registered_compute_usage(
  text, text, integer
) is
  'Atomically claims one signed-in daily compute unit, or none.';
