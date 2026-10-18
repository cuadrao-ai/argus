-- Replacing in place preserves ownership, signatures, defaults and EXECUTE grants.
-- All relation references in these bodies already name their owning schema.
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

CREATE OR REPLACE FUNCTION public.write_financial_opening(p_user_id uuid, p_account_id uuid, p_expected_revision integer, p_expected_version integer, p_amount_minor bigint, p_as_of timestamp with time zone, p_zone text, p_reason text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_account public.financial_accounts%rowtype;
    v_record public.financial_records%rowtype;
    v_next integer;
    v_now timestamptz := now();
begin
    if not exists (
        select 1 from auth.users u
        where u.id = p_user_id and coalesce(u.is_anonymous, false) = false
    ) then
        return jsonb_build_object('decision', 'registered_required');
    end if;

    select * into v_account
    from public.financial_accounts
    where id = p_account_id and user_id = p_user_id
    for update;
    if not found then
        return jsonb_build_object('decision', 'not_found');
    end if;
    if v_account.version is distinct from p_expected_version then
        return jsonb_build_object('decision', 'stale');
    end if;

    select * into v_record
    from public.financial_records
    where account_id = p_account_id and record_kind = 'opening_balance'
    for update;

    if (found and v_record.current_revision is distinct from p_expected_revision)
       or (not found and p_expected_revision is not null) then
        return jsonb_build_object('decision', 'stale');
    end if;

    if not found then
        insert into public.financial_records (account_id, user_id, record_kind, created_at)
        values (p_account_id, p_user_id, 'opening_balance', v_now)
        returning * into v_record;
        v_next := 1;
    else
        v_next := v_record.current_revision + 1;
        update public.financial_records
        set current_revision = v_next
        where id = v_record.id;
    end if;

    insert into public.financial_record_revisions (
        record_id, user_id, revision, amount_minor, as_of, as_of_zone,
        reason, recorded_by, recorded_at
    )
    values (
        v_record.id, p_user_id, v_next, p_amount_minor, p_as_of, p_zone,
        p_reason, p_user_id, v_now
    );

    update public.financial_accounts
    set version = version + 1
    where id = p_account_id;

    return jsonb_build_object(
        'decision', 'written', 'record_id', v_record.id, 'revision', v_next
    );
end;
$function$;

CREATE OR REPLACE FUNCTION public.create_financial_account(p_user_id uuid, p_idempotency_key text, p_identity_hash text, p_type text, p_currency text, p_nickname text, p_ownership_share_bps integer, p_opening_amount_minor bigint, p_opening_as_of timestamp with time zone, p_opening_zone text, p_owner_space_id uuid DEFAULT NULL::uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_reserved public.financial_account_idempotency%rowtype;
    v_account_id uuid;
    v_record_id uuid;
    v_now timestamptz := now();
    v_identity_hash text := p_identity_hash
        || coalesce(':space:' || p_owner_space_id::text, '');
begin
    if not exists (
        select 1 from auth.users u
        where u.id = p_user_id and coalesce(u.is_anonymous, false) = false
    ) then
        return jsonb_build_object('decision', 'registered_required');
    end if;

    select * into v_reserved
    from public.financial_account_idempotency
    where user_id = p_user_id
      and operation_scope = 'financial_accounts.create'
      and idempotency_key = p_idempotency_key
    for update;
    if found then
        if v_reserved.identity_hash = v_identity_hash then
            return jsonb_build_object('decision', 'replay', 'account_id', v_reserved.account_id);
        end if;
        return jsonb_build_object('decision', 'conflict');
    end if;

    begin
        insert into public.financial_accounts (
            user_id, owner_space_id, type, currency, nickname, ownership_share_bps,
            created_at, updated_at
        )
        values (
            p_user_id, p_owner_space_id, p_type, p_currency, p_nickname,
            p_ownership_share_bps, v_now, v_now
        )
        returning id into v_account_id;

        if p_opening_amount_minor is not null then
            insert into public.financial_records (account_id, user_id, record_kind, created_at)
            values (v_account_id, p_user_id, 'opening_balance', v_now)
            returning id into v_record_id;
            insert into public.financial_record_revisions (
                record_id, user_id, revision, amount_minor, as_of, as_of_zone,
                reason, recorded_by, recorded_at
            )
            values (
                v_record_id, p_user_id, 1, p_opening_amount_minor, p_opening_as_of,
                p_opening_zone, null, p_user_id, v_now
            );
        end if;

        insert into public.financial_account_idempotency (
            user_id, operation_scope, idempotency_key, identity_hash, account_id, created_at
        )
        values (
            p_user_id, 'financial_accounts.create', p_idempotency_key,
            v_identity_hash, v_account_id, v_now
        );
    exception when unique_violation then
        -- A concurrent request with the same key committed first. Decide from
        -- its committed row; this transaction's account insert rolls back.
        select * into v_reserved
        from public.financial_account_idempotency
        where user_id = p_user_id
          and operation_scope = 'financial_accounts.create'
          and idempotency_key = p_idempotency_key;
        if v_reserved.identity_hash = v_identity_hash then
            return jsonb_build_object('decision', 'replay', 'account_id', v_reserved.account_id);
        end if;
        return jsonb_build_object('decision', 'conflict');
    end;

    return jsonb_build_object('decision', 'created', 'account_id', v_account_id);
end;
$function$;

CREATE OR REPLACE FUNCTION public.is_active_household_member(p_household_id uuid, p_user_id uuid)
 RETURNS boolean
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
    select exists (
        select 1
        from public.household_members m
        where m.household_id = p_household_id
          and m.user_id = p_user_id
          and m.left_at is null
    );
$function$;

CREATE OR REPLACE FUNCTION argus_private.validated_usage_windows(p_user_id uuid, p_resource text, p_usage_limits jsonb, p_now timestamp with time zone)
 RETURNS TABLE(window_period text, limit_count integer, period_start timestamp with time zone, period_end timestamp with time zone, guest_session boolean)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
 SET "TimeZone" TO 'UTC'
AS $function$
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
$function$;

CREATE OR REPLACE FUNCTION public.admit_backtest_job(p_user_id uuid, p_operation_scope text, p_idempotency_key text, p_identity_hash text, p_payload_hash text, p_launch_payload jsonb, p_initial_status text, p_conversation_id uuid, p_request_message_id uuid, p_confirmation_message_id uuid, p_execution_metadata jsonb, p_user_running_limit integer, p_user_queued_limit integer, p_global_running_limit integer, p_global_queued_limit integer, p_allowance_limits jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
 SET "TimeZone" TO 'UTC'
AS $function$
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
$function$;

CREATE OR REPLACE FUNCTION public.bind_guest_conversation(p_user_id uuid, p_conversation_id uuid)
 RETURNS public.guest_workspaces
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  v_workspace public.guest_workspaces%rowtype;
  v_conversation_owner uuid;
begin
  select *
    into v_workspace
    from public.guest_workspaces
   where user_id = p_user_id
   for update;
  if not found
     or v_workspace.status <> 'active'
     or v_workspace.expires_at <= now() then
    raise exception 'guest workspace is not active'
      using errcode = '23514';
  end if;

  select user_id
    into v_conversation_owner
    from public.conversations
   where id = p_conversation_id;
  if not found or v_conversation_owner is distinct from p_user_id then
    raise exception 'conversation is not owned by guest'
      using errcode = '23514';
  end if;
  if v_workspace.conversation_id is not null
     and v_workspace.conversation_id is distinct from p_conversation_id then
    raise exception 'guest conversation limit reached'
      using errcode = '23514';
  end if;

  update public.guest_workspaces
     set conversation_id = p_conversation_id,
         updated_at = now()
   where user_id = p_user_id
  returning * into v_workspace;
  return v_workspace;
end;
$function$;

CREATE OR REPLACE FUNCTION public.claim_guest_compute_usage(p_visitor_key text, p_session_key text, p_resource text, p_visitor_limit integer, p_session_limit integer)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
 SET "TimeZone" TO 'UTC'
AS $function$
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
$function$;

CREATE OR REPLACE FUNCTION public.claim_guest_funnel_milestone(p_subject_key text, p_milestone text, p_expires_at timestamp with time zone)
 RETURNS boolean
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  v_claimed boolean;
begin
  if p_subject_key is null or length(trim(p_subject_key)) = 0 then
    raise exception 'subject key is required';
  end if;
  if p_milestone is null or length(trim(p_milestone)) = 0 then
    raise exception 'milestone is required';
  end if;
  if p_expires_at is null then
    raise exception 'milestone expiry is required';
  end if;

  insert into public.guest_funnel_milestones (
    subject_key, milestone, expires_at
  ) values (
    p_subject_key, p_milestone, p_expires_at
  )
  on conflict (subject_key, milestone) do update set
    recorded_at = now(),
    expires_at = excluded.expires_at
  where public.guest_funnel_milestones.expires_at <= now()
  returning true into v_claimed;

  return coalesce(v_claimed, false);
end;
$function$;

CREATE OR REPLACE FUNCTION public.claim_registered_compute_usage(p_account_key text, p_resource text, p_limit integer)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
 SET "TimeZone" TO 'UTC'
AS $function$
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
$function$;

CREATE OR REPLACE FUNCTION public.claim_research_usage(p_guest_visitor_key text, p_resource text, p_global_visitor_key text, p_global_limit integer, p_guest_limit integer)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
 SET "TimeZone" TO 'UTC'
AS $function$
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

  -- The day charged, so a failed provider call can return exactly this charge.
  return jsonb_build_object(
    'available', true,
    'guest_exhausted', false,
    'period_start', v_period_start
  );
end;
$function$;

CREATE OR REPLACE FUNCTION public.create_feedback_settling_usage(p_feedback_id uuid, p_user_id uuid, p_feedback_type text, p_message text, p_context jsonb, p_usage_resource text, p_usage_limits jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
 SET "TimeZone" TO 'UTC'
AS $function$
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
$function$;

CREATE OR REPLACE FUNCTION public.delete_withheld_backtest_result(p_user_id uuid, p_run_id uuid)
 RETURNS boolean
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_idea_ids uuid[];
    v_deleted_run boolean;
begin
    delete from public.evidence_artifacts
    where user_id = p_user_id
      and source_run_id = p_run_id;

    with removed as (
        delete from public.idea_versions
        where user_id = p_user_id
          and source_run_id = p_run_id
        returning idea_id
    )
    select coalesce(array_agg(distinct idea_id), '{}'::uuid[])
    into v_idea_ids
    from removed;

    delete from public.ideas as idea
    where idea.user_id = p_user_id
      and idea.id = any(v_idea_ids)
      and not exists (
        select 1 from public.idea_versions as v
        where v.idea_id = idea.id
      );

    update public.ideas as idea
    set active_version_id = (
            select v.id from public.idea_versions as v
            where v.user_id = p_user_id
              and v.idea_id = idea.id
            order by v.created_at desc
            limit 1
        ),
        updated_at = now()
    where idea.user_id = p_user_id
      and idea.id = any(v_idea_ids)
      and idea.active_version_id is null;

    delete from public.backtest_runs
    where user_id = p_user_id
      and id = p_run_id
    returning true into v_deleted_run;

    return coalesce(v_deleted_run, false);
end;
$function$;

CREATE OR REPLACE FUNCTION public.finalize_direct_backtest_success(p_user_id uuid, p_job_id uuid, p_execution_identity text, p_run jsonb, p_idea jsonb, p_idea_version jsonb, p_evidence_artifact jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_job public.backtest_jobs%rowtype;
    v_final record;
begin
    select * into v_job
    from public.backtest_jobs
    where user_id = p_user_id
      and id = p_job_id
      and operation_scope = 'backtests.run'
    for update;

    if not found or v_job.status <> 'running' then
        return null;
    end if;

    select * into v_final
    from public.finalize_backtest_completion(
        p_user_id,
        p_execution_identity,
        p_run,
        p_idea,
        p_idea_version,
        p_evidence_artifact
    );

    update public.backtest_jobs
    set status = 'succeeded',
        result_run_id = (v_final.run ->> 'id')::uuid,
        failure_code = null,
        failure_detail = null,
        retryable = false,
        finished_at = now(),
        updated_at = now()
    where id = p_job_id;

    return jsonb_build_object(
        'run', v_final.run,
        'idea', v_final.idea,
        'idea_version', v_final.idea_version,
        'evidence_artifact', v_final.evidence_artifact
    );
end;
$function$;

CREATE OR REPLACE FUNCTION public.protect_guest_workspace_policy_fields()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  v_is_anonymous boolean;
begin
  if tg_op = 'INSERT' then
    select coalesce(u.is_anonymous, false)
      into v_is_anonymous
      from auth.users as u
     where u.id = new.user_id;
    if not found or not v_is_anonymous then
      raise exception 'guest workspace requires an anonymous Auth user'
        using errcode = '23514';
    end if;
    new.expires_at := new.created_at + interval '7 days';
    return new;
  end if;

  if new.user_id is distinct from old.user_id
     or new.created_at is distinct from old.created_at
     or new.expires_at is distinct from old.expires_at then
    raise exception 'guest identity and expiry are immutable'
      using errcode = '23514';
  end if;
  return new;
end;
$function$;

CREATE OR REPLACE FUNCTION public.purge_expired_guest_funnel_milestones(p_before timestamp with time zone DEFAULT now())
 RETURNS integer
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  v_deleted integer;
begin
  delete from public.guest_funnel_milestones where expires_at <= p_before;
  get diagnostics v_deleted = row_count;
  return v_deleted;
end;
$function$;

CREATE OR REPLACE FUNCTION public.purge_expired_visitor_usage(p_before timestamp with time zone DEFAULT now())
 RETURNS integer
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  v_deleted integer;
begin
  delete from public.visitor_usage_counters where period_end <= p_before;
  get diagnostics v_deleted = row_count;
  return v_deleted;
end;
$function$;

CREATE OR REPLACE FUNCTION public.release_research_usage(p_guest_visitor_key text, p_resource text, p_global_visitor_key text, p_period_start timestamp with time zone)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
 SET "TimeZone" TO 'UTC'
AS $function$
declare
  v_released boolean;
begin
  if p_guest_visitor_key is null
     or length(trim(p_guest_visitor_key)) = 0
     or p_resource is null
     or length(trim(p_resource)) = 0
     or p_global_visitor_key is null
     or length(trim(p_global_visitor_key)) = 0
     or p_guest_visitor_key = p_global_visitor_key
     or p_period_start is null then
    raise exception 'Research usage release is invalid.'
      using errcode = '22023';
  end if;

  -- Only the guest's own row for the day that was charged, and never below
  -- zero. The shared row is never touched here.
  update public.visitor_usage_counters
     set used_count = used_count - 1,
         updated_at = now()
   where visitor_key = p_guest_visitor_key
     and resource = p_resource
     and period = 'day'
     and period_start = p_period_start
     and used_count > 0;
  v_released := found;

  return jsonb_build_object('released', v_released);
end;
$function$;

CREATE OR REPLACE FUNCTION public.replace_empty_guest_conversation(p_user_id uuid, p_title text, p_title_source text, p_language text)
 RETURNS public.conversations
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  v_workspace public.guest_workspaces%rowtype;
  v_conversation public.conversations%rowtype;
begin
  select *
    into v_workspace
    from public.guest_workspaces
   where user_id = p_user_id
   for update;
  if not found
     or v_workspace.status <> 'active'
     or v_workspace.expires_at <= now() then
    raise exception 'guest workspace is not active'
      using errcode = '23514';
  end if;

  if v_workspace.conversation_id is not null then
    if exists (
      select 1 from public.messages
       where conversation_id = v_workspace.conversation_id
    ) or exists (
      select 1 from public.backtest_jobs
       where conversation_id = v_workspace.conversation_id
    ) or exists (
      select 1 from public.backtest_runs
       where conversation_id = v_workspace.conversation_id
    ) then
      raise exception 'guest conversation is not empty'
        using errcode = '23514';
    end if;
    delete from public.conversations
     where id = v_workspace.conversation_id
       and user_id = p_user_id;
  end if;

  insert into public.conversations (
    user_id,
    title,
    title_source,
    language
  ) values (
    p_user_id,
    p_title,
    p_title_source,
    p_language
  )
  returning * into v_conversation;
  return v_conversation;
end;
$function$;

CREATE OR REPLACE FUNCTION public.replace_guest_conversation(p_user_id uuid, p_title text, p_title_source text, p_language text)
 RETURNS public.conversations
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
#variable_conflict use_column
declare
  v_workspace public.guest_workspaces%rowtype;
  v_conversation public.conversations%rowtype;
begin
  select *
    into v_workspace
    from public.guest_workspaces
   where user_id = p_user_id
   for update;
  if not found
     or v_workspace.status <> 'active'
     or v_workspace.expires_at <= now()
     or v_workspace.conversation_id is null then
    raise exception 'guest_workspace_unavailable' using errcode = 'P0001';
  end if;

  if not exists (
      select 1 from public.conversations
       where id = v_workspace.conversation_id and user_id = p_user_id
    )
    or exists (
      select 1 from public.conversations
       where user_id = p_user_id and id <> v_workspace.conversation_id
    )
    or exists (
      select 1 from public.messages
       where (user_id = p_user_id and conversation_id <> v_workspace.conversation_id)
          or (conversation_id = v_workspace.conversation_id and user_id <> p_user_id)
    )
    or exists (
      select 1 from public.strategies
       where (user_id = p_user_id and conversation_id is distinct from v_workspace.conversation_id)
          or (conversation_id = v_workspace.conversation_id and user_id <> p_user_id)
    )
    or exists (
      select 1 from public.backtest_runs
       where (user_id = p_user_id and conversation_id is distinct from v_workspace.conversation_id)
          or (conversation_id = v_workspace.conversation_id and user_id <> p_user_id)
    )
    or exists (
      select 1 from public.backtest_jobs
       where (user_id = p_user_id and conversation_id <> v_workspace.conversation_id)
          or (conversation_id = v_workspace.conversation_id and user_id <> p_user_id)
    )
    or exists (
      select 1 from public.ideas
       where (user_id = p_user_id and source_conversation_id is distinct from v_workspace.conversation_id)
          or (source_conversation_id = v_workspace.conversation_id and user_id <> p_user_id)
    )
    or exists (
      select 1 from public.idea_versions
       where (user_id = p_user_id and source_conversation_id is distinct from v_workspace.conversation_id)
          or (source_conversation_id = v_workspace.conversation_id and user_id <> p_user_id)
    )
    or exists (
      select 1 from public.evidence_artifacts
       where (user_id = p_user_id and source_conversation_id is distinct from v_workspace.conversation_id)
          or (source_conversation_id = v_workspace.conversation_id and user_id <> p_user_id)
    )
    or exists (
      select 1 from public.decision_notes
       where (user_id = p_user_id and source_conversation_id is distinct from v_workspace.conversation_id)
          or (source_conversation_id = v_workspace.conversation_id and user_id <> p_user_id)
    )
    or exists (select 1 from public.collections where user_id = p_user_id)
    or exists (select 1 from public.collection_strategies where user_id = p_user_id) then
    raise exception 'guest_start_over_unsafe_product_graph' using errcode = 'P0001';
  end if;

  update public.guest_workspaces
     set conversation_id = null,
         updated_at = now()
   where user_id = p_user_id;

  delete from public.decision_notes where user_id = p_user_id;
  delete from public.evidence_artifacts where user_id = p_user_id;
  update public.ideas set active_version_id = null where user_id = p_user_id;
  delete from public.idea_versions where user_id = p_user_id;
  delete from public.ideas where user_id = p_user_id;
  delete from public.run_context_packets where user_id = p_user_id;
  delete from public.context_packets where user_id = p_user_id;
  delete from public.backtest_jobs where user_id = p_user_id;
  delete from public.backtest_runs where user_id = p_user_id;
  delete from public.strategies where user_id = p_user_id;
  delete from public.messages where user_id = p_user_id;
  delete from public.checkpoint_writes
   where thread_id = v_workspace.conversation_id::text;
  delete from public.checkpoint_blobs
   where thread_id = v_workspace.conversation_id::text;
  delete from public.checkpoints
   where thread_id = v_workspace.conversation_id::text;
  delete from public.conversations
   where id = v_workspace.conversation_id and user_id = p_user_id;

  insert into public.conversations (user_id, title, title_source, language)
  values (p_user_id, p_title, p_title_source, p_language)
  returning * into v_conversation;
  return v_conversation;
end;
$function$;

CREATE OR REPLACE FUNCTION public.settle_visitor_usage(p_visitor_key text, p_resource text, p_windows jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
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
$function$;

CREATE OR REPLACE FUNCTION public.validate_profile_auth_identity()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  v_is_anonymous boolean;
  v_auth_email text;
begin
  select coalesce(u.is_anonymous, false), nullif(btrim(u.email), '')
    into v_is_anonymous, v_auth_email
    from auth.users as u
   where u.id = new.id;

  if not found then
    raise exception 'profile requires a Supabase Auth user'
      using errcode = '23503';
  end if;

  if v_is_anonymous then
    if new.email is not null then
      raise exception 'anonymous profiles cannot store an email'
        using errcode = '23514';
    end if;
  elsif new.email is null
     or v_auth_email is null
     or lower(btrim(new.email)) is distinct from lower(v_auth_email) then
    raise exception 'permanent profiles require the verified Auth email'
      using errcode = '23514';
  end if;

  return new;
end;
$function$;
