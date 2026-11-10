-- Close the final local public-readiness races around guest conversion and cleanup.

alter table public.guest_workspace_handoffs
  add column destination_email_hash text;

update public.guest_workspace_handoffs as handoff
   set destination_email_hash = encode(
     extensions.digest(
       convert_to(lower(btrim(auth_user.email)), 'UTF8'),
       'sha256'
     ),
     'hex'
   )
  from auth.users as auth_user
 where auth_user.id = handoff.destination_user_id;

alter table public.guest_workspace_handoffs
  alter column destination_email_hash set not null,
  alter column destination_user_id drop not null,
  add constraint guest_workspace_handoff_destination_email_hash
    check (destination_email_hash ~ '^[0-9a-f]{64}$');

alter table public.guest_workspace_handoffs
  drop constraint guest_workspace_handoffs_destination_user_id_fkey,
  add constraint guest_workspace_handoffs_destination_user_id_fkey
    foreign key (destination_user_id)
    references public.profiles(id)
    on delete set null;

create or replace function argus_private.claim_guest_workspace_handoff_by_email(
  p_handoff_id uuid,
  p_secret_hash text,
  p_destination_user_id uuid,
  p_allow_same_destination_replay boolean default false
)
returns table (
  source_user_id uuid,
  destination_user_id uuid,
  conversation_id uuid,
  pending_action jsonb,
  replayed boolean
)
language plpgsql
security definer
set search_path = ''
as $$
#variable_conflict use_column
declare
  v_handoff public.guest_workspace_handoffs%rowtype;
  v_destination_is_anonymous boolean;
  v_destination_email_hash text;
begin
  select *
    into v_handoff
    from public.guest_workspace_handoffs
   where id = p_handoff_id
   for update;

  if not found or v_handoff.secret_hash is distinct from p_secret_hash then
    raise exception 'guest_handoff_invalid' using errcode = 'P0002';
  end if;

  select
    coalesce(auth_user.is_anonymous, false),
    encode(
      extensions.digest(
        convert_to(lower(btrim(auth_user.email)), 'UTF8'),
        'sha256'
      ),
      'hex'
    )
    into v_destination_is_anonymous, v_destination_email_hash
    from auth.users as auth_user
   where auth_user.id = p_destination_user_id
   for update;
  if not found
     or v_destination_is_anonymous
     or v_destination_email_hash is distinct from v_handoff.destination_email_hash then
    raise exception 'guest_handoff_wrong_destination' using errcode = 'P0001';
  end if;

  if v_handoff.status = 'consumed' then
    if p_allow_same_destination_replay
       and v_handoff.destination_user_id is not distinct from p_destination_user_id then
      return query
      select
        v_handoff.source_user_id,
        p_destination_user_id,
        v_handoff.source_conversation_id,
        v_handoff.pending_action,
        true;
      return;
    end if;
    raise exception 'guest_handoff_consumed' using errcode = 'P0001';
  end if;
  if v_handoff.status <> 'pending' then
    raise exception 'guest_handoff_invalid' using errcode = 'P0002';
  end if;
  if v_handoff.expires_at <= now() then
    raise exception 'guest_handoff_expired' using errcode = 'P0001';
  end if;
  if v_handoff.destination_user_id is not null
     and v_handoff.destination_user_id is distinct from p_destination_user_id then
    raise exception 'guest_handoff_wrong_destination' using errcode = 'P0001';
  end if;

  update public.guest_workspace_handoffs
     set destination_user_id = p_destination_user_id
   where id = v_handoff.id;

  return query
  select claimed.*, false
    from argus_private.claim_guest_workspace_handoff(
      p_handoff_id,
      p_secret_hash,
      p_destination_user_id
    ) as claimed;
end;
$$;

revoke all on function argus_private.claim_guest_workspace_handoff_by_email(
  uuid, text, uuid, boolean
) from public, anon, authenticated;
grant execute on function argus_private.claim_guest_workspace_handoff_by_email(
  uuid, text, uuid, boolean
) to service_role;

create or replace function public.claim_guest_workspace_handoff_by_email(
  p_handoff_id uuid,
  p_secret_hash text,
  p_destination_user_id uuid,
  p_allow_same_destination_replay boolean default false
)
returns table (
  source_user_id uuid,
  destination_user_id uuid,
  conversation_id uuid,
  pending_action jsonb,
  replayed boolean
)
language sql
security invoker
set search_path = ''
as $$
  select *
    from argus_private.claim_guest_workspace_handoff_by_email(
      p_handoff_id,
      p_secret_hash,
      p_destination_user_id,
      p_allow_same_destination_replay
    );
$$;

revoke all on function public.claim_guest_workspace_handoff_by_email(
  uuid, text, uuid, boolean
) from public, anon, authenticated;
grant execute on function public.claim_guest_workspace_handoff_by_email(
  uuid, text, uuid, boolean
) to service_role;

create or replace function argus_private.finalize_linked_guest_identity()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if coalesce(new.is_anonymous, false) is false
     and nullif(btrim(new.email), '') is not null
     and exists (
       select 1
         from public.guest_workspaces
        where user_id = new.id
          and status in ('active', 'claiming')
     ) then
    update public.profiles
       set email = lower(btrim(new.email)),
           updated_at = now()
     where id = new.id;

    update public.guest_workspaces
       set status = 'claimed',
           claimed_by = new.id,
           claimed_at = coalesce(claimed_at, now()),
           updated_at = now()
     where user_id = new.id
       and status in ('active', 'claiming');
  end if;
  return new;
end;
$$;

revoke all on function argus_private.finalize_linked_guest_identity()
  from public, anon, authenticated;

drop trigger if exists finalize_linked_guest_identity on auth.users;
create trigger finalize_linked_guest_identity
after update of email, is_anonymous on auth.users
for each row execute function argus_private.finalize_linked_guest_identity();

drop function public.claim_expired_guest_workspaces(integer, boolean);

create function public.claim_expired_guest_workspaces(
  p_limit integer,
  p_dry_run boolean default false
)
returns table (
  user_id uuid,
  conversation_id uuid,
  auth_deleted boolean,
  cleanup_reason text
)
language plpgsql
security definer
set search_path = ''
as $$
#variable_conflict use_column
declare
  v_candidate record;
  v_now timestamptz := now();
  v_selected integer := 0;
  v_deleted_user_id uuid;
begin
  if p_limit < 1 or p_limit > 100 then
    raise exception 'cleanup limit must be between 1 and 100'
      using errcode = '22023';
  end if;

  for v_candidate in
    select
      workspace.user_id,
      workspace.conversation_id,
      case
        when workspace.status = 'claimed' then 'claimed_identity'
        else 'expired_workspace'
      end as reason
      from public.guest_workspaces as workspace
      join auth.users as auth_user on auth_user.id = workspace.user_id
     where coalesce(auth_user.is_anonymous, false)
       and (
         (
           workspace.claimed_by is null
           and workspace.claimed_at is null
           and workspace.expires_at <= v_now
           and (
             workspace.status = 'active'
             or (
               workspace.status = 'expired'
               and workspace.updated_at <= v_now - interval '5 minutes'
             )
           )
         )
         or (
           workspace.status = 'claimed'
           and workspace.claimed_by is not null
           and workspace.claimed_at is not null
           and workspace.updated_at <= v_now - interval '15 minutes'
         )
       )
     order by workspace.updated_at, workspace.user_id
     limit p_limit
     for update of workspace, auth_user skip locked
  loop
    user_id := v_candidate.user_id;
    conversation_id := v_candidate.conversation_id;
    auth_deleted := false;
    cleanup_reason := v_candidate.reason;
    v_selected := v_selected + 1;
    if p_dry_run then
      return next;
      continue;
    end if;

    if v_candidate.reason = 'expired_workspace' then
      update public.guest_workspaces as workspace
         set status = 'expired',
             conversation_id = null,
             updated_at = v_now
       where workspace.user_id = v_candidate.user_id;

      delete from public.feedback as feedback
       where feedback.user_id = v_candidate.user_id;

      if v_candidate.conversation_id is not null then
        delete from public.checkpoint_writes
         where thread_id = v_candidate.conversation_id::text;
        delete from public.checkpoint_blobs
         where thread_id = v_candidate.conversation_id::text;
        delete from public.checkpoints
         where thread_id = v_candidate.conversation_id::text;
        delete from public.conversations as conversation
         where conversation.id = v_candidate.conversation_id
           and conversation.user_id = v_candidate.user_id;
      end if;
    elsif exists (
      select 1 from public.conversations where user_id = v_candidate.user_id
      union all select 1 from public.messages where user_id = v_candidate.user_id
      union all select 1 from public.strategies where user_id = v_candidate.user_id
      union all select 1 from public.backtest_runs where user_id = v_candidate.user_id
      union all select 1 from public.backtest_jobs where user_id = v_candidate.user_id
      union all select 1 from public.ideas where user_id = v_candidate.user_id
      union all select 1 from public.idea_versions where user_id = v_candidate.user_id
      union all select 1 from public.evidence_artifacts where user_id = v_candidate.user_id
      union all select 1 from public.decision_notes where user_id = v_candidate.user_id
      union all select 1 from public.context_packets where user_id = v_candidate.user_id
      union all select 1 from public.run_context_packets where user_id = v_candidate.user_id
      union all select 1 from public.collections where user_id = v_candidate.user_id
      union all select 1 from public.collection_strategies where user_id = v_candidate.user_id
    ) then
      raise exception 'claimed guest identity still owns product rows'
        using errcode = '23514';
    end if;

    delete from auth.users as auth_user
     where auth_user.id = v_candidate.user_id
       and coalesce(auth_user.is_anonymous, false)
     returning auth_user.id into v_deleted_user_id;
    if v_deleted_user_id is null then
      raise exception 'guest identity changed during cleanup'
        using errcode = '40001';
    end if;
    auth_deleted := true;
    return next;
    v_deleted_user_id := null;
  end loop;

  if v_selected >= p_limit then
    return;
  end if;

  for v_candidate in
    select auth_user.id as user_id
      from auth.users as auth_user
     where coalesce(auth_user.is_anonymous, false)
       and auth_user.created_at <= v_now - interval '5 minutes'
       and not exists (
         select 1 from public.guest_workspaces as workspace
          where workspace.user_id = auth_user.id
       )
       and not exists (
         select 1 from public.conversations where user_id = auth_user.id
         union all select 1 from public.messages where user_id = auth_user.id
         union all select 1 from public.backtest_runs where user_id = auth_user.id
         union all select 1 from public.backtest_jobs where user_id = auth_user.id
       )
     order by auth_user.created_at, auth_user.id
     limit (p_limit - v_selected)
     for update of auth_user skip locked
  loop
    user_id := v_candidate.user_id;
    conversation_id := null;
    auth_deleted := false;
    cleanup_reason := 'orphan_identity';
    if p_dry_run then
      return next;
      continue;
    end if;

    delete from auth.users as auth_user
     where auth_user.id = v_candidate.user_id
       and coalesce(auth_user.is_anonymous, false)
     returning auth_user.id into v_deleted_user_id;
    if v_deleted_user_id is null then
      raise exception 'guest identity changed during cleanup'
        using errcode = '40001';
    end if;
    auth_deleted := true;
    return next;
    v_deleted_user_id := null;
  end loop;
end;
$$;

revoke all on function public.claim_expired_guest_workspaces(integer, boolean)
  from public, anon, authenticated;
grant execute on function public.claim_expired_guest_workspaces(integer, boolean)
  to service_role;
