-- Public evidence receipts: immutable, sanitized, owner-revocable snapshots.
--
-- A receipt is frozen at creation and the public read never touches the source
-- conversation. The source ids live here only so revocation can follow deletion
-- and so the owner can audit what they shared; they are never selected by the
-- public read path.
--
-- Two rules are enforced by the database rather than by callers:
--   1. Everything except the revocation columns is immutable after insert, and
--      revocation cannot be reversed.
--   2. Deleting the source revokes the receipt. Without this, a user who
--      deletes a chat still has a live public page, which is the failure mode
--      this design exists to avoid.

create table public.public_excerpt_snapshots (
  id uuid primary key default gen_random_uuid(),
  public_id text not null unique
    check (public_id ~ '^[A-Za-z0-9_-]{22,64}$'),
  owner_id uuid not null
    references public.profiles(id) on delete cascade,
  evidence_artifact_id uuid
    references public.evidence_artifacts(id) on delete set null,
  source_conversation_id uuid
    references public.conversations(id) on delete set null,
  source_run_id uuid
    references public.backtest_runs(id) on delete set null,
  title text not null,
  payload jsonb not null,
  payload_digest text not null
    check (payload_digest ~ '^[0-9a-f]{64}$'),
  created_at timestamptz not null default now(),
  revoked_at timestamptz,
  revocation_reason text
    check (revocation_reason in ('owner_revoked', 'source_deleted')),
  constraint public_excerpt_revocation_is_complete
    check ((revoked_at is null) = (revocation_reason is null))
);

-- At most one live receipt per result, so re-sharing returns the existing link
-- instead of minting a second page the owner has to remember to revoke twice.
-- Revoked rows are excluded: revoking a link does not forbid sharing again.
create unique index idx_public_excerpt_snapshots_live_artifact
  on public.public_excerpt_snapshots (owner_id, evidence_artifact_id)
  where revoked_at is null and evidence_artifact_id is not null;

create index idx_public_excerpt_snapshots_owner_created
  on public.public_excerpt_snapshots (owner_id, created_at desc);
create index idx_public_excerpt_snapshots_source_conversation
  on public.public_excerpt_snapshots (source_conversation_id)
  where source_conversation_id is not null and revoked_at is null;
create index idx_public_excerpt_snapshots_source_run
  on public.public_excerpt_snapshots (source_run_id)
  where source_run_id is not null and revoked_at is null;

create or replace function public.prevent_public_excerpt_immutable_update()
returns trigger
language plpgsql
security invoker
set search_path = public
as $$
begin
  if new.id is distinct from old.id
    or new.public_id is distinct from old.public_id
    or new.owner_id is distinct from old.owner_id
    or new.title is distinct from old.title
    or new.payload is distinct from old.payload
    or new.payload_digest is distinct from old.payload_digest
    or new.created_at is distinct from old.created_at then
    raise exception 'public_excerpt_snapshots immutable fields cannot be updated'
      using errcode = '23514';
  end if;

  if old.revoked_at is not null
    and (
      new.revoked_at is distinct from old.revoked_at
      or new.revocation_reason is distinct from old.revocation_reason
    ) then
    raise exception 'public_excerpt_snapshots revocation cannot be reversed'
      using errcode = '23514';
  end if;

  return new;
end;
$$;

drop trigger if exists prevent_public_excerpt_immutable_update
  on public.public_excerpt_snapshots;
create trigger prevent_public_excerpt_immutable_update
before update on public.public_excerpt_snapshots
for each row execute function public.prevent_public_excerpt_immutable_update();

-- A receipt cannot be created for a source the owner already deleted.
--
-- Revocation-on-delete only revokes snapshots that exist when deleted_at changes,
-- so without this a stale result card, or a create racing behind the delete, could
-- publish a page for a conversation the owner had already removed. That is the same
-- trap as leaving a page live after deletion, entered from the other side.
--
-- The row lock is the point. An application check alone is read-then-write: the
-- check could pass and the delete commit before the insert lands. FOR SHARE makes a
-- concurrent soft delete block here, so this transaction then reads its result and
-- refuses.
create or replace function public.enforce_public_excerpt_source_is_live()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_deleted_at timestamptz;
begin
  if new.source_conversation_id is null then
    return new;
  end if;

  select deleted_at
    into v_deleted_at
    from public.conversations
   where id = new.source_conversation_id
     for share;

  if not found then
    raise exception 'public_excerpt_source_missing'
      using errcode = '23514';
  end if;

  if v_deleted_at is not null then
    raise exception 'public_excerpt_source_deleted'
      using errcode = '23514';
  end if;

  return new;
end;
$$;

drop trigger if exists enforce_public_excerpt_source_is_live
  on public.public_excerpt_snapshots;
create trigger enforce_public_excerpt_source_is_live
before insert on public.public_excerpt_snapshots
for each row execute function public.enforce_public_excerpt_source_is_live();

-- Source deletion revokes. The source foreign keys are set null, so the
-- tombstone outlives whatever it pointed at.
--
-- Every branch skips rows whose owner profile is already gone. Deleting an
-- account cascades to conversations, which fires this trigger while the profile
-- row no longer exists; revoking there would fail the owner foreign key and take
-- account deletion down with it. Those rows are cascade-deleted moments later, so
-- skipping them reaches the same outcome: the receipt stops resolving.
create or replace function public.revoke_public_excerpts_for_deleted_source()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_now timestamptz := now();
begin
  if tg_op = 'DELETE' then
    if tg_table_name = 'conversations' then
      update public.public_excerpt_snapshots as snapshot
         set revoked_at = v_now,
             revocation_reason = 'source_deleted'
       where snapshot.source_conversation_id = old.id
         and snapshot.revoked_at is null
         and exists (
           select 1 from public.profiles as owner
            where owner.id = snapshot.owner_id
         );
    elsif tg_table_name = 'backtest_runs' then
      update public.public_excerpt_snapshots as snapshot
         set revoked_at = v_now,
             revocation_reason = 'source_deleted'
       where snapshot.source_run_id = old.id
         and snapshot.revoked_at is null
         and exists (
           select 1 from public.profiles as owner
            where owner.id = snapshot.owner_id
         );
    else
      update public.public_excerpt_snapshots as snapshot
         set revoked_at = v_now,
             revocation_reason = 'source_deleted'
       where snapshot.evidence_artifact_id = old.id
         and snapshot.revoked_at is null
         and exists (
           select 1 from public.profiles as owner
            where owner.id = snapshot.owner_id
         );
    end if;
    return old;
  end if;

  if old.deleted_at is null and new.deleted_at is not null then
    update public.public_excerpt_snapshots as snapshot
       set revoked_at = v_now,
           revocation_reason = 'source_deleted'
     where snapshot.source_conversation_id = new.id
       and snapshot.revoked_at is null
       and exists (
         select 1 from public.profiles as owner
          where owner.id = snapshot.owner_id
       );
  end if;
  return new;
end;
$$;

drop trigger if exists revoke_public_excerpts_on_conversation_soft_delete
  on public.conversations;
create trigger revoke_public_excerpts_on_conversation_soft_delete
after update of deleted_at on public.conversations
for each row execute function public.revoke_public_excerpts_for_deleted_source();

drop trigger if exists revoke_public_excerpts_on_conversation_purge
  on public.conversations;
create trigger revoke_public_excerpts_on_conversation_purge
before delete on public.conversations
for each row execute function public.revoke_public_excerpts_for_deleted_source();

drop trigger if exists revoke_public_excerpts_on_run_delete
  on public.backtest_runs;
create trigger revoke_public_excerpts_on_run_delete
before delete on public.backtest_runs
for each row execute function public.revoke_public_excerpts_for_deleted_source();

drop trigger if exists revoke_public_excerpts_on_artifact_delete
  on public.evidence_artifacts;
create trigger revoke_public_excerpts_on_artifact_delete
before delete on public.evidence_artifacts
for each row execute function public.revoke_public_excerpts_for_deleted_source();

alter table public.public_excerpt_snapshots enable row level security;

-- No browser role reaches this table. Both the public read and the owner's list
-- are served by the backend, which is where the audience split is enforced: the
-- public read selects four columns and never the owner or the source ids.
--
-- Deliberately no owner-read policy. A select policy without a matching grant is
-- dead code that reads like protection, and adding the grant would put the owner
-- and source columns one PostgREST call away from the browser for no gain.
revoke all on table public.public_excerpt_snapshots from anon, authenticated;
revoke all on function public.prevent_public_excerpt_immutable_update()
  from public, anon, authenticated;
revoke all on function public.enforce_public_excerpt_source_is_live()
  from public, anon, authenticated;
revoke all on function public.revoke_public_excerpts_for_deleted_source()
  from public, anon, authenticated;
