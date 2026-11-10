-- A withheld run's finalized tuple leaves every product-readable table in
-- one transaction. Each part surfaces without a link check (History's run
-- leaf, the latest-completed read, the Omnisearch idea and evidence
-- leaves), so partial removal is itself an observable wrong state; both
-- gateways call this one owner instead of sequencing deletes client-side.
-- Children go first while their source_run_id pointers still exist
-- (decision notes cascade from versions and evidence), an idea left
-- versionless goes with them, one with earlier published versions is
-- repointed to its latest remaining version, and the run row goes last.

create or replace function public.delete_withheld_backtest_result(
    p_user_id uuid,
    p_run_id uuid
) returns boolean
language plpgsql
security definer
set search_path = public
as $$
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
$$;

revoke all on function public.delete_withheld_backtest_result(uuid, uuid)
  from public, anon, authenticated;
grant execute on function public.delete_withheld_backtest_result(uuid, uuid)
  to service_role;
