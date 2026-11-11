-- Claim research capacity before provider work starts.
--
-- The earlier read-then-settle flow held the stored counter at its cap but
-- allowed concurrent requests to spend before either settlement happened.
-- This function locks the shared daily row and the optional guest row in one
-- transaction, checks both bounds, and increments both or neither.

create or replace function public.claim_research_usage(
  p_guest_visitor_key text,
  p_resource text,
  p_global_visitor_key text,
  p_global_limit integer,
  p_guest_limit integer
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
  v_global_used integer;
  v_guest_used integer;
begin
  if p_resource is null or length(trim(p_resource)) = 0
     or p_global_visitor_key is null
     or length(trim(p_global_visitor_key)) = 0
     or p_global_limit is null
     or p_global_limit < 1
     or (
       p_guest_visitor_key is not null
       and (
         length(trim(p_guest_visitor_key)) = 0
         or p_guest_visitor_key = p_global_visitor_key
         or p_guest_limit is null
         or p_guest_limit < 1
       )
     ) then
    raise exception 'Research usage claim is invalid.'
      using errcode = '22023';
  end if;

  -- Every claim takes the shared row first. The fixed order prevents a guest
  -- claim and a signed-in claim from acquiring the same rows in reverse.
  insert into public.visitor_usage_counters (
    visitor_key, resource, period, period_start, period_end,
    used_count, limit_count
  ) values (
    p_global_visitor_key, p_resource, 'day', v_period_start, v_period_end,
    0, p_global_limit
  )
  on conflict (visitor_key, resource, period, period_start) do nothing;

  select used_count
    into v_global_used
    from public.visitor_usage_counters
   where visitor_key = p_global_visitor_key
     and resource = p_resource
     and period = 'day'
     and period_start = v_period_start
   for update;

  if p_guest_visitor_key is not null then
    insert into public.visitor_usage_counters (
      visitor_key, resource, period, period_start, period_end,
      used_count, limit_count
    ) values (
      p_guest_visitor_key, p_resource, 'day', v_period_start, v_period_end,
      0, p_guest_limit
    )
    on conflict (visitor_key, resource, period, period_start) do nothing;

    select used_count
      into v_guest_used
      from public.visitor_usage_counters
     where visitor_key = p_guest_visitor_key
       and resource = p_resource
       and period = 'day'
       and period_start = v_period_start
     for update;

    if v_guest_used >= p_guest_limit then
      return jsonb_build_object(
        'available', false,
        'guest_exhausted', true
      );
    end if;
  end if;

  if v_global_used >= p_global_limit then
    return jsonb_build_object(
      'available', false,
      'guest_exhausted', false
    );
  end if;

  update public.visitor_usage_counters
     set used_count = used_count + 1,
         limit_count = p_global_limit,
         period_end = v_period_end,
         updated_at = now()
   where visitor_key = p_global_visitor_key
     and resource = p_resource
     and period = 'day'
     and period_start = v_period_start;

  if p_guest_visitor_key is not null then
    update public.visitor_usage_counters
       set used_count = used_count + 1,
           limit_count = p_guest_limit,
           period_end = v_period_end,
           updated_at = now()
     where visitor_key = p_guest_visitor_key
       and resource = p_resource
       and period = 'day'
       and period_start = v_period_start;
  end if;

  return jsonb_build_object(
    'available', true,
    'guest_exhausted', false
  );
end;
$$;

revoke all on function public.claim_research_usage(
  text, text, text, integer, integer
) from public, anon, authenticated;
grant execute on function public.claim_research_usage(
  text, text, text, integer, integer
) to service_role;

comment on function public.claim_research_usage(
  text, text, text, integer, integer
) is
  'Atomically claims shared and optional guest daily research capacity before provider work.';
