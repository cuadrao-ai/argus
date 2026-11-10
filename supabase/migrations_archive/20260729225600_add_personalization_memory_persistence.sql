-- Registered-only, no-consumer persistence for personalization memory.
--
-- These records are private backend state. Browser/Data API roles, including
-- service_role, have no direct table access. Every backend write is rechecked
-- against canonical Auth and Guest-workspace truth by database triggers.

create schema if not exists argus_private;

create or replace function argus_private.memory_categories_are_valid(
  p_categories text[],
  p_require_nonempty boolean default false
)
returns boolean
language sql
immutable
set search_path = ''
as $$
  select
    (not p_require_nonempty or cardinality(p_categories) > 0)
    and cardinality(p_categories) <= 4
    and cardinality(p_categories) = (
      select count(distinct category)::integer
        from pg_catalog.unnest(p_categories) as category
    )
    and coalesce(
      (
        select bool_and(
          category in (
            'personalization_preference',
            'workflow_preference',
            'explicit_decision_note',
            'past_session_anchor'
          )
        )
          from pg_catalog.unnest(p_categories) as category
      ),
      true
    );
$$;

revoke all on function argus_private.memory_categories_are_valid(text[], boolean)
  from public, anon, authenticated, service_role;

create or replace function argus_private.memory_sensitivity_flags_are_valid(
  p_flags text[]
)
returns boolean
language sql
immutable
set search_path = ''
as $$
  select
    cardinality(p_flags) <= 10
    and cardinality(p_flags) = (
      select count(distinct flag)::integer
        from pg_catalog.unnest(p_flags) as flag
    )
    and coalesce(
      (
        select bool_and(
          flag in (
            'broker_credential',
            'account_balance',
            'exact_holdings',
            'tax_or_legal_status',
            'identifying_financial_detail',
            'health',
            'employment',
            'family',
            'raw_conversation'
          )
        )
          from pg_catalog.unnest(p_flags) as flag
      ),
      true
    );
$$;

revoke all on function argus_private.memory_sensitivity_flags_are_valid(text[])
  from public, anon, authenticated, service_role;

create table public.memory_settings (
  owner_id uuid not null
    references public.profiles(id) on delete cascade,
  category text not null
    check (
      category in (
        'personalization_preference',
        'workflow_preference',
        'explicit_decision_note',
        'past_session_anchor'
      )
    ),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (owner_id, category),
  constraint memory_settings_updated_after_created
    check (updated_at >= created_at)
);

create table public.memory_candidates (
  id text not null
    check (length(id) between 1 and 128),
  owner_id uuid not null
    references public.profiles(id) on delete cascade,
  category text not null
    check (
      category in (
        'personalization_preference',
        'workflow_preference',
        'explicit_decision_note',
        'past_session_anchor'
      )
    ),
  source_label text not null
    check (length(btrim(source_label)) between 1 and 120),
  source_value text not null
    check (length(source_value) between 1 and 4096),
  future_benefit text not null
    check (length(future_benefit) between 1 and 512),
  trigger text not null
    check (
      trigger in (
        'saved_decision',
        'explicit_request',
        'assisted_stable_preference'
      )
    ),
  proposed_context text not null
    check (
      proposed_context in (
        'ordinary',
        'broker',
        'export',
        'restricted_financial'
      )
    ),
  opt_in_scope text[] not null default '{}'::text[]
    check (
      argus_private.memory_categories_are_valid(opt_in_scope, false)
    ),
  sensitivity_status text not null
    check (sensitivity_status in ('unassessed', 'clear', 'restricted')),
  sensitivity_flags text[] not null default '{}'::text[]
    check (
      argus_private.memory_sensitivity_flags_are_valid(sensitivity_flags)
    ),
  sensitivity_policy_version text not null
    check (
      sensitivity_policy_version = 'argus.memory-sensitivity/v1'
    ),
  sensitivity_content_digest text not null
    check (
      sensitivity_content_digest ~ '^sha256:[0-9a-f]{64}$'
    ),
  created_at timestamptz not null default now(),
  primary key (owner_id, id)
);

create index memory_candidates_owner_created_idx
  on public.memory_candidates (owner_id, created_at, id);

create table public.memory_consent_actions (
  id text not null
    check (length(id) between 1 and 128),
  owner_id uuid not null
    references public.profiles(id) on delete cascade,
  schema_version text not null default 'argus.memory-consent/v1'
    check (schema_version = 'argus.memory-consent/v1'),
  policy_version text not null default 'argus.memory-policy/v1'
    check (policy_version = 'argus.memory-policy/v1'),
  action text not null
    check (action in ('direct_enable', 'candidate_confirmation')),
  candidate_id text
    check (candidate_id is null or length(candidate_id) between 1 and 128),
  requested_scope text[] not null,
  granted_scope text[] not null,
  effective_scope text[] not null,
  recorded_at timestamptz not null default now(),
  idempotency_key text not null
    check (length(idempotency_key) between 1 and 128),
  primary key (owner_id, id),
  unique (owner_id, id, candidate_id),
  unique (owner_id, action, idempotency_key),
  constraint memory_consent_requested_scope_valid
    check (
      argus_private.memory_categories_are_valid(requested_scope, false)
    ),
  constraint memory_consent_granted_scope_valid
    check (
      argus_private.memory_categories_are_valid(granted_scope, false)
    ),
  constraint memory_consent_effective_scope_valid
    check (
      argus_private.memory_categories_are_valid(effective_scope, true)
    ),
  constraint memory_consent_granted_is_requested
    check (granted_scope <@ requested_scope),
  constraint memory_consent_requested_is_effective
    check (requested_scope <@ effective_scope),
  constraint memory_consent_action_candidate_shape
    check (
      (
        action = 'direct_enable'
        and candidate_id is null
        and cardinality(requested_scope) > 0
        and cardinality(granted_scope) > 0
      )
      or (
        action = 'candidate_confirmation'
        and candidate_id is not null
      )
    )
);

create unique index memory_consent_confirmation_candidate_idx
  on public.memory_consent_actions (owner_id, candidate_id)
  where action = 'candidate_confirmation';

create index memory_consent_owner_recorded_idx
  on public.memory_consent_actions (owner_id, recorded_at, id);

create table public.memory_records (
  id text not null
    check (length(id) between 1 and 128),
  owner_id uuid not null
    references public.profiles(id) on delete cascade,
  candidate_id text not null
    check (length(candidate_id) between 1 and 128),
  consent_action_id text not null
    check (length(consent_action_id) between 1 and 128),
  category text not null
    check (
      category in (
        'personalization_preference',
        'workflow_preference',
        'explicit_decision_note',
        'past_session_anchor'
      )
    ),
  label text not null
    check (length(btrim(label)) between 1 and 120),
  value text not null
    check (length(value) between 1 and 4096),
  revision integer not null default 1
    check (revision >= 1),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (owner_id, id),
  unique (owner_id, candidate_id),
  constraint memory_records_consent_action_fkey
    foreign key (owner_id, consent_action_id, candidate_id)
    references public.memory_consent_actions(owner_id, id, candidate_id)
    on delete restrict,
  constraint memory_records_updated_after_created
    check (updated_at >= created_at)
);

create index memory_records_owner_created_idx
  on public.memory_records (owner_id, created_at, id);

create index memory_records_consent_action_idx
  on public.memory_records (owner_id, consent_action_id, candidate_id);

create table public.memory_provenance (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null
    references public.profiles(id) on delete cascade,
  candidate_id text,
  record_id text,
  ordinal integer not null
    check (ordinal >= 0),
  source_kind text not null
    check (
      source_kind in (
        'evidence_artifact',
        'decision_note',
        'idea',
        'idea_version',
        'conversation',
        'message'
      )
    ),
  source_id text not null
    check (length(source_id) between 1 and 512),
  source_version text not null
    check (length(source_version) between 1 and 512),
  created_at timestamptz not null default now(),
  constraint memory_provenance_exactly_one_parent
    check ((candidate_id is null) <> (record_id is null)),
  constraint memory_provenance_candidate_fkey
    foreign key (owner_id, candidate_id)
    references public.memory_candidates(owner_id, id)
    on delete cascade,
  constraint memory_provenance_record_fkey
    foreign key (owner_id, record_id)
    references public.memory_records(owner_id, id)
    on delete cascade
);

create unique index memory_provenance_candidate_ordinal_idx
  on public.memory_provenance (owner_id, candidate_id, ordinal)
  where candidate_id is not null;

create unique index memory_provenance_record_ordinal_idx
  on public.memory_provenance (owner_id, record_id, ordinal)
  where record_id is not null;

create table public.memory_prompt_history (
  owner_id uuid not null
    references public.profiles(id) on delete cascade,
  category text not null
    check (
      category in (
        'personalization_preference',
        'workflow_preference',
        'explicit_decision_note',
        'past_session_anchor'
      )
    ),
  last_proactive_prompt_at timestamptz,
  last_declined_at timestamptz,
  updated_at timestamptz not null default now(),
  primary key (owner_id, category),
  constraint memory_prompt_history_has_event
    check (
      last_proactive_prompt_at is not null
      or last_declined_at is not null
    ),
  constraint memory_prompt_history_update_order
    check (
      (
        last_proactive_prompt_at is null
        or updated_at >= last_proactive_prompt_at
      )
      and (
        last_declined_at is null
        or updated_at >= last_declined_at
      )
    )
);

create table public.memory_reconciliations (
  owner_id uuid not null
    references public.profiles(id) on delete cascade,
  record_id text not null,
  generation bigint not null
    check (generation >= 1),
  operation text not null
    check (operation in ('create', 'update', 'delete', 'reset')),
  status text not null
    check (status in ('pending', 'running', 'succeeded', 'failed')),
  claim_token text
    check (
      claim_token is null
      or length(claim_token) between 1 and 128
    ),
  lease_expires_at timestamptz,
  attempt_count integer not null default 0
    check (attempt_count >= 0),
  error_code text
    check (
      error_code is null
      or length(error_code) between 1 and 128
    ),
  created_at timestamptz not null default now(),
  completed_at timestamptz,
  primary key (owner_id, record_id, generation),
  constraint memory_reconciliations_operation_record_shape
    check (
      (operation = 'reset' and record_id = '')
      or (
        operation in ('create', 'update', 'delete')
        and length(record_id) between 1 and 128
      )
    ),
  constraint memory_reconciliations_terminal_shape
    check (
      (
        status = 'pending'
        and claim_token is null
        and lease_expires_at is null
        and attempt_count = 0
        and error_code is null
        and completed_at is null
      )
      or (
        status = 'running'
        and claim_token is not null
        and lease_expires_at is not null
        and attempt_count >= 1
        and error_code is null
        and completed_at is null
      )
      or (
        status = 'succeeded'
        and claim_token is null
        and lease_expires_at is null
        and attempt_count >= 1
        and error_code is null
        and completed_at is not null
      )
      or (
        status = 'failed'
        and claim_token is null
        and lease_expires_at is null
        and attempt_count >= 1
        and error_code is not null
        and completed_at is not null
      )
    )
);

create index memory_reconciliations_pending_idx
  on public.memory_reconciliations (owner_id, status, record_id, generation)
  where status in ('pending', 'running');

create table public.memory_provider_projections (
  owner_id uuid not null,
  record_id text not null,
  provider_ref text not null
    check (length(provider_ref) between 1 and 1024),
  generation bigint not null
    check (generation >= 1),
  updated_at timestamptz not null default now(),
  primary key (owner_id, record_id),
  unique (owner_id, provider_ref),
  constraint memory_provider_projections_record_fkey
    foreign key (owner_id, record_id)
    references public.memory_records(owner_id, id)
    on delete cascade
);

create table public.memory_provider_cleanup (
  owner_id uuid not null
    references public.profiles(id) on delete cascade,
  record_id text not null
    check (length(record_id) between 1 and 128),
  provider_ref text not null
    check (length(provider_ref) between 1 and 1024),
  generation bigint not null
    check (generation >= 1),
  status text not null default 'pending'
    check (status in ('pending', 'resolved')),
  created_at timestamptz not null default now(),
  resolved_at timestamptz,
  primary key (owner_id, record_id, provider_ref, generation),
  constraint memory_provider_cleanup_terminal_shape
    check (
      (
        status = 'pending'
        and resolved_at is null
      )
      or (
        status = 'resolved'
        and resolved_at is not null
      )
    )
);

create index memory_provider_cleanup_pending_idx
  on public.memory_provider_cleanup (
    owner_id,
    status,
    created_at,
    record_id
  )
  where status = 'pending';

create index memory_provider_cleanup_reservation_idx
  on public.memory_provider_cleanup (owner_id, provider_ref)
  where status = 'pending';

create or replace function argus_private.is_registered_memory_owner(
  p_owner_id uuid
)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
      from auth.users as auth_user
     where auth_user.id = p_owner_id
       and coalesce(auth_user.is_anonymous, true) is false
  )
  and not exists (
    select 1
      from public.guest_workspaces as workspace
     where workspace.user_id = p_owner_id
       and workspace.status in ('active', 'claiming')
  );
$$;

revoke all on function argus_private.is_registered_memory_owner(uuid)
  from public, anon, authenticated, service_role;

create or replace function argus_private.enforce_registered_memory_owner()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if tg_op = 'UPDATE' and new.owner_id is distinct from old.owner_id then
    raise exception 'personalization memory owner is immutable'
      using errcode = '23514';
  end if;

  if not argus_private.is_registered_memory_owner(new.owner_id) then
    raise exception
      'personalization memory requires a registered owner without an active Guest workspace'
      using errcode = '23514';
  end if;

  return new;
end;
$$;

revoke all on function argus_private.enforce_registered_memory_owner()
  from public, anon, authenticated, service_role;

create or replace function argus_private.reject_immutable_memory_update()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  raise exception '% is immutable', tg_table_name
    using errcode = '23514';
end;
$$;

revoke all on function argus_private.reject_immutable_memory_update()
  from public, anon, authenticated, service_role;

create or replace function argus_private.protect_memory_record_update()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if new.id is distinct from old.id
     or new.owner_id is distinct from old.owner_id
     or new.candidate_id is distinct from old.candidate_id
     or new.consent_action_id is distinct from old.consent_action_id
     or new.category is distinct from old.category
     or new.created_at is distinct from old.created_at then
    raise exception 'memory record identity and consent are immutable'
      using errcode = '23514';
  end if;

  if new.label is not distinct from old.label
     and new.value is not distinct from old.value then
    raise exception 'memory record edit requires a label or value change'
      using errcode = '23514';
  end if;
  if new.revision <> old.revision + 1
     or new.updated_at <= old.updated_at then
    raise exception 'memory record edits require the next revision and update time'
      using errcode = '23514';
  end if;

  return new;
end;
$$;

revoke all on function argus_private.protect_memory_record_update()
  from public, anon, authenticated, service_role;

create or replace function argus_private.validate_memory_consent_action()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  v_candidate_category text;
begin
  if new.action <> 'candidate_confirmation' then
    return new;
  end if;

  select category
    into v_candidate_category
    from public.memory_candidates
   where owner_id = new.owner_id
     and id = new.candidate_id;

  if not found then
    raise exception
      'candidate confirmation requires an existing same-owner candidate'
      using errcode = '23514';
  end if;

  if not (v_candidate_category = any(new.requested_scope)) then
    raise exception 'candidate category must be in requested scope'
      using errcode = '23514';
  end if;

  return new;
end;
$$;

revoke all on function argus_private.validate_memory_consent_action()
  from public, anon, authenticated, service_role;

create or replace function argus_private.validate_memory_record_consent()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  v_action text;
  v_candidate_id text;
  v_requested_scope text[];
  v_effective_scope text[];
begin
  select action, candidate_id, requested_scope, effective_scope
    into v_action, v_candidate_id, v_requested_scope, v_effective_scope
    from public.memory_consent_actions
   where owner_id = new.owner_id
     and id = new.consent_action_id;

  -- The composite foreign key owns missing/cross-owner linkage failures.
  if not found then
    return new;
  end if;

  if v_action <> 'candidate_confirmation'
     or v_candidate_id is distinct from new.candidate_id
     or not (new.category = any(v_requested_scope))
     or not (new.category = any(v_effective_scope)) then
    raise exception
      'memory record category must be in requested consent scope and match confirmed consent'
      using errcode = '23514';
  end if;

  return new;
end;
$$;

revoke all on function argus_private.validate_memory_record_consent()
  from public, anon, authenticated, service_role;

create or replace function argus_private.protect_memory_child_identity()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if tg_table_name = 'memory_prompt_history' then
    if new.owner_id is distinct from old.owner_id
       or new.category is distinct from old.category then
      raise exception '% identity is immutable', tg_table_name
        using errcode = '23514';
    end if;
  elsif tg_table_name = 'memory_reconciliations' then
    if new.owner_id is distinct from old.owner_id
       or new.record_id is distinct from old.record_id
       or new.generation is distinct from old.generation then
      raise exception '% identity is immutable', tg_table_name
        using errcode = '23514';
    end if;
  elsif tg_table_name = 'memory_provider_projections' then
    if new.owner_id is distinct from old.owner_id
       or new.record_id is distinct from old.record_id then
      raise exception '% identity is immutable', tg_table_name
        using errcode = '23514';
    end if;
  elsif tg_table_name = 'memory_provider_cleanup' then
    if new.owner_id is distinct from old.owner_id
       or new.record_id is distinct from old.record_id
       or new.provider_ref is distinct from old.provider_ref
       or new.generation is distinct from old.generation
       or new.created_at is distinct from old.created_at then
      raise exception '% identity is immutable', tg_table_name
        using errcode = '23514';
    end if;
  else
    raise exception 'unsupported memory child table: %', tg_table_name
      using errcode = '23514';
  end if;

  return new;
end;
$$;

revoke all on function argus_private.protect_memory_child_identity()
  from public, anon, authenticated, service_role;

create or replace function argus_private.protect_memory_provider_cleanup_lifecycle()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if tg_op = 'INSERT' then
    if new.status <> 'pending' or new.resolved_at is not null then
      raise exception 'memory provider cleanup must begin pending'
        using errcode = '23514';
    end if;
    return new;
  end if;

  if old.status = 'resolved'
     and (
       new.status is distinct from old.status
       or new.resolved_at is distinct from old.resolved_at
     ) then
    raise exception 'memory provider cleanup terminal state is immutable'
      using errcode = '23514';
  end if;
  if old.status = 'pending'
     and not (
       (
         new.status = 'pending'
         and new.resolved_at is null
       )
       or (
         new.status = 'resolved'
         and new.resolved_at is not null
       )
     ) then
    raise exception 'memory provider cleanup transition is invalid'
      using errcode = '23514';
  end if;

  return new;
end;
$$;

revoke all on function
  argus_private.protect_memory_provider_cleanup_lifecycle()
  from public, anon, authenticated, service_role;

create or replace function argus_private.reserve_memory_provider_ref()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_owner_id uuid;
  v_provider_ref text;
  v_provider_refs text[];
begin
  if tg_table_name = 'memory_provider_projections' then
    v_owner_id := new.owner_id;
    v_provider_refs := array[new.provider_ref];
    if tg_op = 'UPDATE' then
      v_provider_refs := array_append(v_provider_refs, old.provider_ref);
    end if;
  elsif tg_table_name = 'memory_provider_cleanup' then
    v_owner_id := new.owner_id;
    v_provider_refs := array[new.provider_ref];
  else
    raise exception 'unsupported memory provider reservation table: %',
      tg_table_name
      using errcode = '23514';
  end if;

  for v_provider_ref in
    select distinct ref
      from unnest(v_provider_refs) as provider_refs(ref)
     order by ref
  loop
    perform pg_catalog.pg_advisory_xact_lock(
      pg_catalog.hashtextextended(
        'argus:memory-provider-ref:' || v_owner_id::text || ':' || v_provider_ref,
        0
      )
    );
  end loop;

  if tg_table_name = 'memory_provider_projections'
     and exists (
       select 1
         from public.memory_provider_cleanup
        where owner_id = new.owner_id
          and provider_ref = new.provider_ref
          and status = 'pending'
     ) then
    raise exception 'memory provider ref is reserved for pending cleanup'
      using errcode = '23514';
  end if;

  if tg_table_name = 'memory_provider_cleanup'
     and tg_op = 'INSERT'
     and exists (
       select 1
         from public.memory_provider_projections
        where owner_id = new.owner_id
          and provider_ref = new.provider_ref
          and record_id <> new.record_id
     ) then
    raise exception 'memory provider ref belongs to a different live record'
      using errcode = '23514';
  end if;

  return new;
end;
$$;

revoke all on function argus_private.reserve_memory_provider_ref()
  from public, anon, authenticated, service_role;

create or replace function argus_private.lock_memory_record_lifecycle()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_owner_id uuid;
  v_record_id text;
begin
  if tg_table_schema = 'public'
     and tg_table_name = 'memory_records'
     and tg_op = 'INSERT' then
    v_owner_id := new.owner_id;
    v_record_id := new.id;
  elsif tg_table_schema = 'public'
        and tg_table_name = 'memory_records'
        and tg_op = 'DELETE' then
    if not exists (
      select 1
        from public.profiles
       where id = old.owner_id
    ) then
      return old;
    end if;
    v_owner_id := old.owner_id;
    v_record_id := old.id;
  elsif tg_table_schema = 'public'
        and tg_table_name = 'memory_reconciliations'
        and tg_op in ('INSERT', 'UPDATE') then
    v_owner_id := new.owner_id;
    v_record_id := new.record_id;
  else
    raise exception
      'unsupported memory record lifecycle target: %.% %',
      tg_table_schema,
      tg_table_name,
      tg_op
      using errcode = '23514';
  end if;

  if tg_table_name = 'memory_reconciliations' then
    if new.operation = 'reset' then
      perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(
          'argus:memory-owner:' || v_owner_id::text,
          0
        )
      );
      return new;
    end if;
  end if;

  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(
      'argus:memory-record:'
      || v_owner_id::text
      || ':'
      || v_record_id,
      0
    )
  );

  if tg_table_name = 'memory_records'
     and tg_op = 'INSERT'
     and exists (
       select 1
         from public.memory_reconciliations
        where owner_id = v_owner_id
          and record_id = v_record_id
          and operation = 'delete'
     ) then
    raise exception
      'memory record insert rejected by existing delete reconciliation'
      using errcode = '23514';
  end if;

  if tg_op = 'DELETE' then
    return old;
  end if;
  return new;
end;
$$;

revoke all on function argus_private.lock_memory_record_lifecycle()
  from public, anon, authenticated, service_role;

create or replace function argus_private.guard_memory_record_delete()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if tg_op <> 'DELETE'
     or tg_table_schema <> 'public'
     or tg_table_name <> 'memory_records' then
    raise exception
      'unsupported memory record delete target: %.% %',
      tg_table_schema,
      tg_table_name,
      tg_op
      using errcode = '23514';
  end if;

  if exists (
    select 1
      from public.profiles
     where id = old.owner_id
  )
  and exists (
    select 1
      from public.memory_reconciliations
     where owner_id = old.owner_id
       and record_id = old.id
       and status in ('pending', 'running')
  ) then
    raise exception
      'memory record deletion requires unfinished provider reconciliation to complete'
      using errcode = '23514';
  end if;

  return old;
end;
$$;

revoke all on function argus_private.guard_memory_record_delete()
  from public, anon, authenticated, service_role;

create or replace function argus_private.validate_memory_reconciliation_lifecycle()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_record_exists boolean;
begin
  if tg_table_schema <> 'public'
     or tg_table_name <> 'memory_reconciliations'
     or tg_op not in ('INSERT', 'UPDATE') then
    raise exception
      'unsupported reconciliation lifecycle target: %.% %',
      tg_table_schema,
      tg_table_name,
      tg_op
      using errcode = '23514';
  end if;

  if new.operation not in ('create', 'update', 'delete', 'reset') then
    raise exception 'unsupported reconciliation operation: %', new.operation
      using errcode = '23514';
  end if;
  if new.status not in ('pending', 'running', 'succeeded', 'failed') then
    raise exception 'unsupported reconciliation status: %', new.status
      using errcode = '23514';
  end if;
  if (
    new.status in ('pending', 'running')
    and new.completed_at is not null
  )
  or (
    new.status in ('succeeded', 'failed')
    and new.completed_at is null
  ) then
    raise exception 'invalid reconciliation state for status %', new.status
      using errcode = '23514';
  end if;
  if tg_op = 'UPDATE'
     and new.operation is distinct from old.operation then
    raise exception 'memory reconciliation operation is immutable'
      using errcode = '23514';
  end if;

  if (
    new.operation = 'reset'
    and new.record_id <> ''
  )
  or (
    new.operation <> 'reset'
    and length(new.record_id) not between 1 and 128
  ) then
    raise exception 'invalid reconciliation operation and record shape'
      using errcode = '23514';
  end if;
  if new.operation <> 'reset'
     and new.status = 'running'
     and exists (
       select 1
         from public.memory_reconciliations
        where owner_id = new.owner_id
          and operation = 'reset'
     ) then
    raise exception
      'memory provider work is blocked by unresolved owner reset'
      using errcode = '23514';
  end if;
  if tg_op = 'UPDATE'
     and new.created_at is distinct from old.created_at then
    raise exception 'memory reconciliation creation time is immutable'
      using errcode = '23514';
  end if;

  if tg_op = 'INSERT' then
    if new.status <> 'pending'
       or new.claim_token is not null
       or new.lease_expires_at is not null
       or new.attempt_count <> 0
       or new.error_code is not null
       or new.completed_at is not null then
      raise exception 'invalid reconciliation insert transition'
        using errcode = '23514';
    end if;
  elsif old.status = 'pending' and new.status = 'running' then
    if new.claim_token is null
       or new.lease_expires_at is null
       or new.lease_expires_at <= statement_timestamp()
       or new.attempt_count <> old.attempt_count + 1
       or new.error_code is not null
       or new.completed_at is not null then
      raise exception 'running reconciliation requires a fresh claim'
        using errcode = '23514';
    end if;
  elsif old.status = 'running' and new.status = 'running' then
    if old.lease_expires_at is null
       or old.lease_expires_at > statement_timestamp()
       or new.claim_token is null
       or new.claim_token is not distinct from old.claim_token
       or new.lease_expires_at is null
       or new.lease_expires_at <= statement_timestamp()
       or new.attempt_count <> old.attempt_count + 1
       or new.error_code is not null
       or new.completed_at is not null then
      raise exception 'running reconciliation lease is not reclaimable'
        using errcode = '23514';
    end if;
  elsif old.status = 'running'
        and new.status in ('succeeded', 'failed') then
    if old.lease_expires_at is null
       or new.completed_at is null
       or old.lease_expires_at <= statement_timestamp() then
      raise exception 'expired reconciliation claim cannot finish'
        using errcode = '23514';
    end if;
    if new.claim_token is not null
       or new.attempt_count <> old.attempt_count
       or new.lease_expires_at is not null
       or (new.status = 'succeeded' and new.error_code is not null)
       or (new.status = 'failed' and new.error_code is null) then
      raise exception 'invalid % reconciliation terminal transition', new.status
        using errcode = '23514';
    end if;
  else
    raise exception
      'invalid reconciliation transition: % to %',
      old.status,
      new.status
      using errcode = '23514';
  end if;

  select exists (
    select 1
      from public.memory_records
     where owner_id = new.owner_id
       and id = new.record_id
  )
    into v_record_exists;

  if new.operation in ('create', 'update')
     and not v_record_exists then
    raise exception
      '% reconciliation requires a live same-owner record',
      new.operation
      using errcode = '23514';
  end if;
  if new.operation = 'delete'
     and v_record_exists then
    raise exception 'delete reconciliation requires record absence'
      using errcode = '23514';
  end if;

  return new;
end;
$$;

revoke all on function argus_private.validate_memory_reconciliation_lifecycle()
  from public, anon, authenticated, service_role;

create or replace function argus_private.guard_guest_memory_zero_state()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_memory_state_count bigint;
begin
  if old.status not in ('active', 'claiming')
     or new.status <> 'claimed' then
    return new;
  end if;

  select count(*)
    into v_memory_state_count
    from (
      select owner_id
        from public.memory_settings
       where owner_id = new.user_id
      union all
      select owner_id
        from public.memory_candidates
       where owner_id = new.user_id
      union all
      select owner_id
        from public.memory_consent_actions
       where owner_id = new.user_id
      union all
      select owner_id
        from public.memory_records
       where owner_id = new.user_id
      union all
      select owner_id
        from public.memory_provenance
       where owner_id = new.user_id
      union all
      select owner_id
        from public.memory_prompt_history
       where owner_id = new.user_id
      union all
      select owner_id
        from public.memory_reconciliations
       where owner_id = new.user_id
      union all
      select owner_id
        from public.memory_provider_projections
       where owner_id = new.user_id
      union all
      select owner_id
        from public.memory_provider_cleanup
       where owner_id = new.user_id
    ) as memory_state;

  if v_memory_state_count <> 0 then
    raise exception 'Guest personalization memory state must be zero before claim'
      using errcode = '23514';
  end if;

  return new;
end;
$$;

revoke all on function argus_private.guard_guest_memory_zero_state()
  from public, anon, authenticated, service_role;

do $$
declare
  v_table text;
begin
  foreach v_table in array array[
    'memory_settings',
    'memory_candidates',
    'memory_consent_actions',
    'memory_records',
    'memory_provenance',
    'memory_prompt_history',
    'memory_reconciliations',
    'memory_provider_projections',
    'memory_provider_cleanup'
  ]
  loop
    execute format(
      'create trigger enforce_registered_memory_owner'
      ' before insert or update on public.%I'
      ' for each row execute function'
      ' argus_private.enforce_registered_memory_owner()',
      v_table
    );
  end loop;
end;
$$;

create trigger protect_memory_candidate_update
before update on public.memory_candidates
for each row execute function argus_private.reject_immutable_memory_update();

create trigger protect_memory_consent_action_update
before update on public.memory_consent_actions
for each row execute function argus_private.reject_immutable_memory_update();

create trigger validate_memory_consent_action
before insert on public.memory_consent_actions
for each row execute function argus_private.validate_memory_consent_action();

create trigger validate_memory_record_consent
before insert on public.memory_records
for each row execute function argus_private.validate_memory_record_consent();

create trigger protect_memory_record_update
before update on public.memory_records
for each row execute function argus_private.protect_memory_record_update();

create trigger protect_memory_provenance_update
before update on public.memory_provenance
for each row execute function argus_private.reject_immutable_memory_update();

create trigger protect_memory_prompt_history_identity
before update on public.memory_prompt_history
for each row execute function argus_private.protect_memory_child_identity();

create trigger protect_memory_reconciliation_identity
before update on public.memory_reconciliations
for each row execute function argus_private.protect_memory_child_identity();

create trigger protect_memory_provider_projection_identity
before update on public.memory_provider_projections
for each row execute function argus_private.protect_memory_child_identity();

create trigger reserve_memory_provider_projection_ref
before insert or update on public.memory_provider_projections
for each row execute function argus_private.reserve_memory_provider_ref();

create trigger protect_memory_provider_cleanup_identity
before update on public.memory_provider_cleanup
for each row execute function argus_private.protect_memory_child_identity();

create trigger reserve_memory_provider_cleanup_ref
before insert or update on public.memory_provider_cleanup
for each row execute function argus_private.reserve_memory_provider_ref();

create trigger validate_memory_provider_cleanup_lifecycle
before insert or update on public.memory_provider_cleanup
for each row execute function
  argus_private.protect_memory_provider_cleanup_lifecycle();

create trigger a_lock_memory_record_lifecycle_delete
before delete on public.memory_records
for each row execute function argus_private.lock_memory_record_lifecycle();

create trigger lock_memory_record_lifecycle_insert
before insert on public.memory_records
for each row execute function argus_private.lock_memory_record_lifecycle();

create trigger guard_memory_record_delete
before delete on public.memory_records
for each row execute function argus_private.guard_memory_record_delete();

create trigger lock_memory_record_reconciliation_lifecycle
before insert or update on public.memory_reconciliations
for each row execute function argus_private.lock_memory_record_lifecycle();

create trigger validate_memory_reconciliation_lifecycle
before insert or update on public.memory_reconciliations
for each row execute function
  argus_private.validate_memory_reconciliation_lifecycle();

create trigger guard_guest_memory_zero_state
before update on public.guest_workspaces
for each row execute function argus_private.guard_guest_memory_zero_state();

alter table public.memory_settings enable row level security;
alter table public.memory_settings force row level security;
alter table public.memory_candidates enable row level security;
alter table public.memory_candidates force row level security;
alter table public.memory_consent_actions enable row level security;
alter table public.memory_consent_actions force row level security;
alter table public.memory_records enable row level security;
alter table public.memory_records force row level security;
alter table public.memory_provenance enable row level security;
alter table public.memory_provenance force row level security;
alter table public.memory_prompt_history enable row level security;
alter table public.memory_prompt_history force row level security;
alter table public.memory_reconciliations enable row level security;
alter table public.memory_reconciliations force row level security;
alter table public.memory_provider_projections enable row level security;
alter table public.memory_provider_projections force row level security;
alter table public.memory_provider_cleanup enable row level security;
alter table public.memory_provider_cleanup force row level security;

revoke all on table public.memory_settings
  from public, anon, authenticated, service_role;
revoke all on table public.memory_candidates
  from public, anon, authenticated, service_role;
revoke all on table public.memory_consent_actions
  from public, anon, authenticated, service_role;
revoke all on table public.memory_records
  from public, anon, authenticated, service_role;
revoke all on table public.memory_provenance
  from public, anon, authenticated, service_role;
revoke all on table public.memory_prompt_history
  from public, anon, authenticated, service_role;
revoke all on table public.memory_reconciliations
  from public, anon, authenticated, service_role;
revoke all on table public.memory_provider_projections
  from public, anon, authenticated, service_role;
revoke all on table public.memory_provider_cleanup
  from public, anon, authenticated, service_role;
