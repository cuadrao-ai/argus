create or replace function public.prevent_idea_version_immutable_update()
returns trigger
language plpgsql
security invoker
set search_path = public
as $$
begin
  if new.id is distinct from old.id
    or new.user_id is distinct from old.user_id
    or new.idea_id is distinct from old.idea_id
    or new.source_conversation_id is distinct from old.source_conversation_id
    or new.source_run_id is distinct from old.source_run_id
    or new.version_number is distinct from old.version_number
    or new.canonical_spec is distinct from old.canonical_spec
    or new.strategy_snapshot is distinct from old.strategy_snapshot
    or new.title is distinct from old.title
    or new.summary is distinct from old.summary
    or new.created_at is distinct from old.created_at then
    raise exception 'idea_versions immutable fields cannot be updated'
      using errcode = '23514';
  end if;

  return new;
end;
$$;

drop trigger if exists prevent_idea_version_immutable_update on public.idea_versions;
drop trigger if exists prevent_idea_versions_immutable_update on public.idea_versions;
create trigger prevent_idea_versions_immutable_update
before update on public.idea_versions
for each row execute function public.prevent_idea_version_immutable_update();

create or replace function public.prevent_evidence_artifact_immutable_update()
returns trigger
language plpgsql
security invoker
set search_path = public
as $$
begin
  if new.id is distinct from old.id
    or new.user_id is distinct from old.user_id
    or new.idea_id is distinct from old.idea_id
    or new.idea_version_id is distinct from old.idea_version_id
    or new.source_conversation_id is distinct from old.source_conversation_id
    or new.source_run_id is distinct from old.source_run_id
    or new.artifact_type is distinct from old.artifact_type
    or new.title is distinct from old.title
    or new.digest is distinct from old.digest
    or new.payload is distinct from old.payload
    or new.created_at is distinct from old.created_at then
    raise exception 'evidence_artifacts immutable fields cannot be updated'
      using errcode = '23514';
  end if;

  return new;
end;
$$;

drop trigger if exists prevent_evidence_artifact_immutable_update
  on public.evidence_artifacts;
drop trigger if exists prevent_evidence_artifacts_immutable_update
  on public.evidence_artifacts;
create trigger prevent_evidence_artifacts_immutable_update
before update on public.evidence_artifacts
for each row execute function public.prevent_evidence_artifact_immutable_update();

revoke all on function public.prevent_idea_version_immutable_update()
  from public, anon, authenticated;
revoke all on function public.prevent_evidence_artifact_immutable_update()
  from public, anon, authenticated;
