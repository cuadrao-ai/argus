-- Visitor-scoped usage counters.
--
-- usage_counters.user_id is a foreign key to profiles(id), which is correct for
-- account-owned allowances but cannot express "this visitor". A guest workspace
-- lives ten minutes and renewal mints a new user_id, so an account-keyed guest
-- allowance resets on a timer -- the hole this table closes.
--
-- The subject here is deliberately opaque text, not a uuid and not a foreign
-- key: it identifies a caller we have no account for.
--
-- visitor_key holds a keyed digest, never a raw address. The counter needs to
-- tell visitors apart, not to name them, and a raw IP in a primary key would be
-- a durable record of who visited. Rows are disposable, but period_end is not a
-- timer: nothing in the database acts on it. The row has no owner to cascade
-- from, so it is deleted only when a successful non-dry-run of the guest
-- cleanup job (argus.domain.guest_cleanup, run by
-- scripts/ops/cleanup_expired_guest_workspaces.py) reaches
-- purge_expired_visitor_usage. Retention holds exactly as often as that job is
-- run.

create table if not exists public.visitor_usage_counters (
  visitor_key text not null,
  resource text not null,
  period text not null,
  period_start timestamptz not null,
  period_end timestamptz not null,
  used_count integer not null default 0,
  limit_count integer not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (visitor_key, resource, period, period_start)
);

comment on table public.visitor_usage_counters is
  'Allowances for callers with no durable account. Not FK-bound: the subject is a visitor, not a profile.';

-- Reads and settlement are always scoped to the current window.
create index if not exists visitor_usage_counters_window_idx
  on public.visitor_usage_counters (visitor_key, resource, period_end);

alter table public.visitor_usage_counters enable row level security;

-- No policies: service_role bypasses RLS, and nothing else may read or write
-- visitor allowances. Enabling RLS without policies is the deny-all default.

revoke all on table public.visitor_usage_counters from public, anon, authenticated;
grant select, insert, update, delete on table public.visitor_usage_counters to service_role;


-- One settlement charge for a visitor, mirroring the account-scoped path.
-- Returns the used_count after charging so the caller can log truthfully.
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
    returning used_count into v_used;

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


-- Bounded retention. Nothing here is worth keeping past its window, and a
-- counter table with no cleanup path becomes an accidental visitor log.
create or replace function public.purge_expired_visitor_usage(
  p_before timestamptz default now()
)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  v_deleted integer;
begin
  delete from public.visitor_usage_counters where period_end <= p_before;
  get diagnostics v_deleted = row_count;
  return v_deleted;
end;
$$;

revoke all on function public.purge_expired_visitor_usage(timestamptz)
  from public, anon, authenticated;
grant execute on function public.purge_expired_visitor_usage(timestamptz)
  to service_role;
