-- Atomically publish one completed backtest and its P1 evidence spine.
-- The service-role-only RPC is the shared commit boundary for local/API and
-- Render workflow execution. Replays return the already committed tuple.

create or replace function public.finalize_backtest_completion(
  p_user_id uuid,
  p_execution_identity text,
  p_run jsonb,
  p_idea jsonb,
  p_idea_version jsonb,
  p_evidence_artifact jsonb
)
returns table (
  run jsonb,
  idea jsonb,
  idea_version jsonb,
  evidence_artifact jsonb
)
language plpgsql
security invoker
set search_path = public
as $$
declare
  v_run_id uuid;
  v_idea_id uuid;
  v_idea_version_id uuid;
  v_evidence_artifact_id uuid;
  v_conversation_id uuid;
  v_strategy_id uuid;
  v_input_chart jsonb;
  v_input_trades jsonb;
  v_card jsonb;
  v_run public.backtest_runs%rowtype;
  v_idea public.ideas%rowtype;
  v_idea_version public.idea_versions%rowtype;
  v_evidence_artifact public.evidence_artifacts%rowtype;
begin
  if nullif(btrim(p_execution_identity), '') is null then
    raise exception 'Backtest execution identity must not be blank.'
      using errcode = '22023';
  end if;
  if (p_run ->> 'status') is distinct from 'completed' then
    raise exception 'Backtest finalization requires a completed run.'
      using errcode = '22023';
  end if;

  v_run_id := nullif(p_run ->> 'id', '')::uuid;
  v_idea_id := nullif(p_idea ->> 'id', '')::uuid;
  v_idea_version_id := nullif(p_idea_version ->> 'id', '')::uuid;
  v_evidence_artifact_id := nullif(p_evidence_artifact ->> 'id', '')::uuid;
  if v_run_id is null
    or v_idea_id is null
    or v_idea_version_id is null
    or v_evidence_artifact_id is null then
    raise exception 'Backtest finalization ids must not be blank.'
      using errcode = '22023';
  end if;

  if nullif(p_idea_version ->> 'idea_id', '')::uuid is distinct from v_idea_id
    or nullif(p_idea_version ->> 'source_run_id', '')::uuid
      is distinct from v_run_id
    or nullif(p_evidence_artifact ->> 'idea_id', '')::uuid
      is distinct from v_idea_id
    or nullif(p_evidence_artifact ->> 'idea_version_id', '')::uuid
      is distinct from v_idea_version_id
    or nullif(p_evidence_artifact ->> 'source_run_id', '')::uuid
      is distinct from v_run_id then
    raise exception 'Backtest finalization sidecar identity is inconsistent.'
      using errcode = '22023';
  end if;

  -- Serialize retries for the same owner/execution pair before inspecting or
  -- creating any row. The application also derives a stable run id from this
  -- execution identity, so a replay converges on one durable tuple.
  perform pg_advisory_xact_lock(
    hashtextextended(p_user_id::text || ':' || btrim(p_execution_identity), 0)
  );

  v_conversation_id := nullif(p_run ->> 'conversation_id', '')::uuid;
  v_strategy_id := nullif(p_run ->> 'strategy_id', '')::uuid;
  if v_conversation_id is not null and not exists (
    select 1
      from public.conversations as c
     where c.id = v_conversation_id
       and c.user_id = p_user_id
  ) then
    raise exception 'Conversation not found or not owned by user.'
      using errcode = 'P0002';
  end if;
  if v_strategy_id is not null and not exists (
    select 1
      from public.strategies as s
     where s.id = v_strategy_id
       and s.user_id = p_user_id
  ) then
    raise exception 'Strategy not found or not owned by user.'
      using errcode = 'P0002';
  end if;
  if exists (
    select 1
      from public.backtest_runs as br
     where br.id = v_run_id
       and br.user_id <> p_user_id
  ) then
    raise exception 'Backtest run is owned by another user.'
      using errcode = '42501';
  end if;

  v_input_chart := case
    when p_run -> 'chart' = 'null'::jsonb then null
    else p_run -> 'chart'
  end;
  v_input_trades := case
    when p_run -> 'trades' = 'null'::jsonb then null
    else p_run -> 'trades'
  end;

  select br.*
    into v_run
    from public.backtest_runs as br
   where br.user_id = p_user_id
     and br.id = v_run_id
   for update;

  if found and (
    v_run.status is distinct from 'completed'
    or v_run.conversation_id is distinct from v_conversation_id
    or v_run.strategy_id is distinct from v_strategy_id
    or v_run.asset_class is distinct from (p_run ->> 'asset_class')
    or v_run.symbols is distinct from array(
      select jsonb_array_elements_text(coalesce(p_run -> 'symbols', '[]'::jsonb))
    )
    or v_run.allocation_method is distinct from (p_run ->> 'allocation_method')
    or v_run.benchmark_symbol is distinct from (p_run ->> 'benchmark_symbol')
    or v_run.metrics is distinct from coalesce(p_run -> 'metrics', '{}'::jsonb)
    or v_run.config_snapshot is distinct from
      coalesce(p_run -> 'config_snapshot', '{}'::jsonb)
    or v_run.chart is distinct from v_input_chart
    or v_run.trades is distinct from v_input_trades
  ) then
    raise exception 'Backtest run identity collided with different immutable payload.'
      using errcode = '23505';
  end if;

  select ea.*
    into v_evidence_artifact
    from public.evidence_artifacts as ea
   where ea.user_id = p_user_id
     and ea.source_run_id = v_run_id
   for update;

  if found then
    select i.*
      into v_idea
      from public.ideas as i
     where i.user_id = p_user_id
       and i.id = v_evidence_artifact.idea_id;
    if not found then
      raise exception 'Existing backtest finalization is missing its idea.'
        using errcode = '23514';
    end if;

    select iv.*
      into v_idea_version
      from public.idea_versions as iv
     where iv.user_id = p_user_id
       and iv.id = v_evidence_artifact.idea_version_id;
    if not found
      or v_idea_version.idea_id is distinct from v_idea.id
      or v_idea_version.source_run_id is distinct from v_run_id then
      raise exception 'Existing backtest finalization tuple is incomplete.'
        using errcode = '23514';
    end if;

    v_card := coalesce(v_run.conversation_result_card, '{}'::jsonb)
      || jsonb_build_object(
        'idea_id', v_idea.id,
        'idea_version_id', v_idea_version.id,
        'evidence_artifact_id', v_evidence_artifact.id,
        'evidence_lifecycle', v_evidence_artifact.lifecycle,
        'artifact_type', v_evidence_artifact.artifact_type
      );
    update public.backtest_runs as br
       set conversation_result_card = v_card,
           updated_at = now()
     where br.user_id = p_user_id
       and br.id = v_run_id
    returning br.* into v_run;

    return query select
      to_jsonb(v_run),
      to_jsonb(v_idea),
      to_jsonb(v_idea_version),
      to_jsonb(v_evidence_artifact);
    return;
  end if;

  if v_run.id is null then
    insert into public.backtest_runs (
      id,
      user_id,
      conversation_id,
      strategy_id,
      status,
      asset_class,
      symbols,
      allocation_method,
      benchmark_symbol,
      metrics,
      config_snapshot,
      conversation_result_card,
      chart,
      trades,
      created_at
    )
    values (
      v_run_id,
      p_user_id,
      v_conversation_id,
      v_strategy_id,
      'completed',
      p_run ->> 'asset_class',
      array(
        select jsonb_array_elements_text(coalesce(p_run -> 'symbols', '[]'::jsonb))
      ),
      p_run ->> 'allocation_method',
      p_run ->> 'benchmark_symbol',
      coalesce(p_run -> 'metrics', '{}'::jsonb),
      coalesce(p_run -> 'config_snapshot', '{}'::jsonb),
      coalesce(p_run -> 'conversation_result_card', '{}'::jsonb),
      v_input_chart,
      v_input_trades,
      coalesce((p_run ->> 'created_at')::timestamptz, now())
    )
    returning * into v_run;
  end if;

  insert into public.ideas (
    id,
    user_id,
    source_conversation_id,
    title,
    summary,
    lifecycle,
    active_version_id,
    created_at,
    updated_at
  )
  values (
    v_idea_id,
    p_user_id,
    nullif(p_idea ->> 'source_conversation_id', '')::uuid,
    p_idea ->> 'title',
    coalesce(p_idea ->> 'summary', ''),
    coalesce(p_idea ->> 'lifecycle', 'captured'),
    null,
    coalesce((p_idea ->> 'created_at')::timestamptz, now()),
    coalesce((p_idea ->> 'updated_at')::timestamptz, now())
  )
  returning * into v_idea;

  insert into public.idea_versions (
    id,
    user_id,
    idea_id,
    source_conversation_id,
    source_run_id,
    version_number,
    canonical_spec,
    strategy_snapshot,
    title,
    summary,
    lifecycle,
    created_at
  )
  values (
    v_idea_version_id,
    p_user_id,
    v_idea_id,
    nullif(p_idea_version ->> 'source_conversation_id', '')::uuid,
    v_run_id,
    coalesce((p_idea_version ->> 'version_number')::integer, 1),
    coalesce(p_idea_version -> 'canonical_spec', '{}'::jsonb),
    coalesce(p_idea_version -> 'strategy_snapshot', '{}'::jsonb),
    p_idea_version ->> 'title',
    coalesce(p_idea_version ->> 'summary', ''),
    coalesce(p_idea_version ->> 'lifecycle', 'captured'),
    coalesce((p_idea_version ->> 'created_at')::timestamptz, now())
  )
  returning * into v_idea_version;

  update public.ideas as i
     set active_version_id = v_idea_version_id,
         updated_at = now()
   where i.user_id = p_user_id
     and i.id = v_idea_id
  returning i.* into v_idea;

  insert into public.evidence_artifacts (
    id,
    user_id,
    idea_id,
    idea_version_id,
    source_conversation_id,
    source_run_id,
    artifact_type,
    lifecycle,
    title,
    digest,
    payload,
    created_at,
    updated_at
  )
  values (
    v_evidence_artifact_id,
    p_user_id,
    v_idea_id,
    v_idea_version_id,
    nullif(p_evidence_artifact ->> 'source_conversation_id', '')::uuid,
    v_run_id,
    coalesce(p_evidence_artifact ->> 'artifact_type', 'backtest'),
    coalesce(p_evidence_artifact ->> 'lifecycle', 'captured'),
    p_evidence_artifact ->> 'title',
    coalesce(p_evidence_artifact ->> 'digest', ''),
    coalesce(p_evidence_artifact -> 'payload', '{}'::jsonb),
    coalesce((p_evidence_artifact ->> 'created_at')::timestamptz, now()),
    coalesce((p_evidence_artifact ->> 'updated_at')::timestamptz, now())
  )
  returning * into v_evidence_artifact;

  v_card := coalesce(v_run.conversation_result_card, '{}'::jsonb)
    || jsonb_build_object(
      'idea_id', v_idea.id,
      'idea_version_id', v_idea_version.id,
      'evidence_artifact_id', v_evidence_artifact.id,
      'evidence_lifecycle', v_evidence_artifact.lifecycle,
      'artifact_type', v_evidence_artifact.artifact_type
    );
  update public.backtest_runs as br
     set conversation_result_card = v_card,
         updated_at = now()
   where br.user_id = p_user_id
     and br.id = v_run_id
  returning br.* into v_run;

  return query select
    to_jsonb(v_run),
    to_jsonb(v_idea),
    to_jsonb(v_idea_version),
    to_jsonb(v_evidence_artifact);
end;
$$;

revoke all on function public.finalize_backtest_completion(
  uuid, text, jsonb, jsonb, jsonb, jsonb
) from public;
revoke all on function public.finalize_backtest_completion(
  uuid, text, jsonb, jsonb, jsonb, jsonb
) from anon;
revoke all on function public.finalize_backtest_completion(
  uuid, text, jsonb, jsonb, jsonb, jsonb
) from authenticated;
grant execute on function public.finalize_backtest_completion(
  uuid, text, jsonb, jsonb, jsonb, jsonb
) to service_role;
