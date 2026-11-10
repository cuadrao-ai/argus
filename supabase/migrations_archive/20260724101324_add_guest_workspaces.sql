-- Guest identity and workspace policy spine.
--
-- Owner graph at integration commit 1ea2ab24:
-- * auth.users -> profiles is the identity root.
-- * profiles.id owns conversations, messages, strategies, collections,
--   collection_strategies, backtest_runs, feedback, usage_counters,
--   context_packets, run_context_packets, route_receipts, backtest_jobs,
--   ideas, idea_versions, evidence_artifacts, and decision_notes.
-- * conversations.id owns messages and backtest_jobs by cascade; strategies,
--   backtest_runs, route_receipts, ideas, idea_versions, evidence_artifacts,
--   decision_notes, and cost_ledger_entries retain nullable provenance.
-- * cost_ledger_entries and route/security evidence are append-only or
--   privacy-safe attribution records, not guest-transfer rows.
-- * LangGraph checkpoint tables use thread_id == conversation_id without a
--   product-table foreign key; cleanup must remove those thread rows
--   explicitly without changing the existing runtime spine.

alter table public.profiles
  alter column email drop not null;

create or replace function public.validate_profile_auth_identity()
returns trigger
language plpgsql
security definer
set search_path = public, auth
as $$
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
$$;

revoke all on function public.validate_profile_auth_identity() from public;

drop trigger if exists validate_profile_auth_identity on public.profiles;
create trigger validate_profile_auth_identity
before insert or update of id, email on public.profiles
for each row execute function public.validate_profile_auth_identity();

create table public.guest_workspaces (
  user_id uuid primary key references public.profiles(id) on delete cascade,
  conversation_id uuid unique
    references public.conversations(id) on delete set null,
  status text not null default 'active'
    check (status in ('active', 'claiming', 'claimed', 'expired')),
  created_at timestamptz not null default now(),
  expires_at timestamptz not null,
  claimed_by uuid references public.profiles(id) on delete set null,
  claimed_at timestamptz,
  updated_at timestamptz not null default now(),
  constraint guest_workspaces_fixed_expiry
    check (expires_at = created_at + interval '7 days')
);

create index guest_workspaces_expiry_idx
  on public.guest_workspaces (expires_at, user_id)
  where status in ('active', 'expired');
create index guest_workspaces_claimed_by_idx
  on public.guest_workspaces (claimed_by)
  where claimed_by is not null;

create or replace function public.protect_guest_workspace_policy_fields()
returns trigger
language plpgsql
security definer
set search_path = public, auth
as $$
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
$$;

revoke all on function public.protect_guest_workspace_policy_fields() from public;

create trigger protect_guest_workspace_policy_fields
before insert or update on public.guest_workspaces
for each row execute function public.protect_guest_workspace_policy_fields();

create or replace function public.bind_new_guest_conversation()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  v_workspace public.guest_workspaces%rowtype;
begin
  select *
    into v_workspace
    from public.guest_workspaces
   where user_id = new.user_id
   for update;

  if not found then
    return new;
  end if;
  if v_workspace.status <> 'active' or v_workspace.expires_at <= now() then
    raise exception 'guest workspace is not active'
      using errcode = '23514';
  end if;
  if v_workspace.conversation_id is not null
     and v_workspace.conversation_id is distinct from new.id then
    raise exception 'guest conversation limit reached'
      using errcode = '23514';
  end if;

  update public.guest_workspaces
     set conversation_id = new.id,
         updated_at = now()
   where user_id = new.user_id;
  return new;
end;
$$;

revoke all on function public.bind_new_guest_conversation() from public;

create trigger bind_new_guest_conversation
after insert on public.conversations
for each row execute function public.bind_new_guest_conversation();

create or replace function public.bind_guest_conversation(
  p_user_id uuid,
  p_conversation_id uuid
)
returns public.guest_workspaces
language plpgsql
security definer
set search_path = public
as $$
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
$$;

revoke all on function public.bind_guest_conversation(uuid, uuid)
  from public, anon, authenticated;
grant execute on function public.bind_guest_conversation(uuid, uuid)
  to service_role;

alter table public.guest_workspaces enable row level security;
revoke all on table public.guest_workspaces from anon, authenticated;
grant select on table public.guest_workspaces to authenticated;
grant all privileges on table public.guest_workspaces to service_role;

create policy guest_workspaces_owner_select
  on public.guest_workspaces
  for select
  to authenticated
  using (
    (select auth.uid()) = user_id
    and (select auth.jwt() ->> 'is_anonymous') = 'true'
    and status = 'active'
    and expires_at > now()
  );

-- Existing user-owned policies remain the owner filter. These restrictive
-- policies add the anonymous-session expiry boundary without changing
-- registered access.
create policy profiles_guest_session_active
  on public.profiles as restrictive
  for all to authenticated
  using (
    (select auth.jwt() ->> 'is_anonymous') is distinct from 'true'
    or exists (
      select 1 from public.guest_workspaces as g
       where g.user_id = profiles.id
         and g.status = 'active'
         and g.expires_at > now()
    )
  )
  with check (
    (select auth.jwt() ->> 'is_anonymous') is distinct from 'true'
    or exists (
      select 1 from public.guest_workspaces as g
       where g.user_id = profiles.id
         and g.status = 'active'
         and g.expires_at > now()
    )
  );

create policy conversations_guest_session_active
  on public.conversations as restrictive
  for all to authenticated
  using (
    (select auth.jwt() ->> 'is_anonymous') is distinct from 'true'
    or exists (
      select 1 from public.guest_workspaces as g
       where g.user_id = conversations.user_id
         and g.status = 'active'
         and g.expires_at > now()
    )
  )
  with check (
    (select auth.jwt() ->> 'is_anonymous') is distinct from 'true'
    or exists (
      select 1 from public.guest_workspaces as g
       where g.user_id = conversations.user_id
         and g.status = 'active'
         and g.expires_at > now()
    )
  );

create policy messages_guest_session_active
  on public.messages as restrictive
  for all to authenticated
  using (
    (select auth.jwt() ->> 'is_anonymous') is distinct from 'true'
    or exists (
      select 1 from public.guest_workspaces as g
       where g.user_id = messages.user_id
         and g.status = 'active'
         and g.expires_at > now()
    )
  )
  with check (
    (select auth.jwt() ->> 'is_anonymous') is distinct from 'true'
    or exists (
      select 1 from public.guest_workspaces as g
       where g.user_id = messages.user_id
         and g.status = 'active'
         and g.expires_at > now()
    )
  );

create policy backtest_jobs_guest_session_active
  on public.backtest_jobs as restrictive
  for select to authenticated
  using (
    (select auth.jwt() ->> 'is_anonymous') is distinct from 'true'
    or exists (
      select 1 from public.guest_workspaces as g
       where g.user_id = backtest_jobs.user_id
         and g.status = 'active'
         and g.expires_at > now()
    )
  );
