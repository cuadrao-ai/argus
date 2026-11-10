-- Direct-run success is one serialized boundary: the run/evidence tuple and
-- the succeeded job flip commit together, only while the job is still
-- running. A reconciled job returns null and commits nothing.

create or replace function public.finalize_direct_backtest_success(
    p_user_id uuid,
    p_job_id uuid,
    p_execution_identity text,
    p_run jsonb,
    p_idea jsonb,
    p_idea_version jsonb,
    p_evidence_artifact jsonb
) returns jsonb
language plpgsql
security definer
set search_path = public
as $$
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
$$;

revoke all on function public.finalize_direct_backtest_success(
    uuid, uuid, text, jsonb, jsonb, jsonb, jsonb
) from public, anon, authenticated;
grant execute on function public.finalize_direct_backtest_success(
    uuid, uuid, text, jsonb, jsonb, jsonb, jsonb
) to service_role;
