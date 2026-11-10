-- Create a permanent Auth user for guest registration, then move the guest
-- workspace through the existing atomic claim boundary. The browser receives
-- the handoff cookie before signup; an Auth insert trigger binds the new UUID
-- in the same transaction that creates it.

alter table public.guest_workspace_handoffs
  add column handoff_kind text not null default 'existing_account'
    check (handoff_kind in ('existing_account', 'new_account_signup'));

alter table public.guest_workspace_handoffs
  drop constraint guest_workspace_handoff_fixed_expiry,
  add constraint guest_workspace_handoff_fixed_expiry
    check (
      (
        handoff_kind = 'existing_account'
        and expires_at = created_at + interval '10 minutes'
      )
      or (
        handoff_kind = 'new_account_signup'
        and expires_at > created_at
        and expires_at <= created_at + interval '7 days'
      )
    );

alter table public.guest_workspace_handoffs
  drop constraint guest_workspace_handoffs_destination_user_id_fkey,
  add constraint guest_workspace_handoffs_destination_user_id_fkey
    foreign key (destination_user_id)
    references auth.users(id)
    on delete set null;

create or replace function argus_private.prepare_guest_workspace_handoff(
  p_source_user_id uuid,
  p_destination_email_hash text,
  p_source_conversation_id uuid,
  p_pending_action jsonb,
  p_secret_hash text,
  p_existing_secret_hash text default null,
  p_handoff_kind text default 'existing_account'
)
returns table (
  id uuid,
  expires_at timestamptz,
  destination_user_id uuid,
  reused_secret boolean
)
language plpgsql
security definer
set search_path = ''
as $$
#variable_conflict use_column
declare
  v_handoff public.guest_workspace_handoffs%rowtype;
  v_workspace public.guest_workspaces%rowtype;
  v_source_is_anonymous boolean;
  v_expires_at timestamptz;
  v_reused_secret boolean := false;
begin
  if p_handoff_kind not in ('existing_account', 'new_account_signup')
     or p_destination_email_hash !~ '^[0-9a-f]{64}$'
     or p_secret_hash !~ '^[0-9a-f]{64}$'
     or (
       p_existing_secret_hash is not null
       and p_existing_secret_hash !~ '^[0-9a-f]{64}$'
     ) then
    raise exception 'guest_handoff_invalid' using errcode = '22023';
  end if;

  -- Serialize every preparation for one source before taking row locks. Claim
  -- takes the handoff then workspace locks in the same order.
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('guest-handoff:' || p_source_user_id::text, 0)
  );

  select *
    into v_handoff
    from public.guest_workspace_handoffs
   where source_user_id = p_source_user_id
     and status = 'pending'
   for update;

  select coalesce(is_anonymous, false)
    into v_source_is_anonymous
    from auth.users
   where auth.users.id = p_source_user_id
   for update;
  if not found or v_source_is_anonymous is not true then
    raise exception 'guest_handoff_source_not_anonymous' using errcode = 'P0001';
  end if;

  select *
    into v_workspace
    from public.guest_workspaces
   where user_id = p_source_user_id
   for update;
  if not found
     or v_workspace.status <> 'active'
     or v_workspace.expires_at <= now()
     or v_workspace.conversation_id is distinct from p_source_conversation_id
     or not exists (
       select 1
         from public.conversations
        where conversations.id = p_source_conversation_id
          and conversations.user_id = p_source_user_id
     ) then
    raise exception 'guest_handoff_workspace_unavailable' using errcode = 'P0001';
  end if;

  if p_pending_action is not null
     and not argus_private.valid_guest_pending_action(
       p_pending_action,
       p_source_conversation_id
     ) then
    raise exception 'guest_handoff_invalid' using errcode = '22023';
  end if;

  if v_handoff.id is not null then
    if v_handoff.handoff_kind = 'new_account_signup'
       and v_handoff.destination_user_id is not null
       and v_handoff.destination_email_hash is distinct from p_destination_email_hash then
      raise exception 'guest_signup_destination_bound' using errcode = 'P0001';
    end if;

    -- Once signup has created an Auth user, the person's later password login
    -- must reuse this bound ticket. The browser cannot inspect the HttpOnly
    -- cookie to know that its ordinary login preparation is a continuation.
    if v_handoff.handoff_kind = 'new_account_signup'
       and v_handoff.destination_email_hash is not distinct from p_destination_email_hash
       and (
         p_handoff_kind = 'new_account_signup'
         or v_handoff.destination_user_id is not null
       ) then
      v_reused_secret := p_existing_secret_hash is not null
        and v_handoff.secret_hash is not distinct from p_existing_secret_hash;
      update public.guest_workspace_handoffs
         set secret_hash = case
               when v_reused_secret then secret_hash
               else p_secret_hash
             end,
             source_conversation_id = p_source_conversation_id,
             pending_action = p_pending_action,
             expires_at = v_workspace.expires_at
       where guest_workspace_handoffs.id = v_handoff.id
       returning * into v_handoff;

      return query
      select
        v_handoff.id,
        v_handoff.expires_at,
        v_handoff.destination_user_id,
        v_reused_secret;
      return;
    end if;

    update public.guest_workspace_handoffs
       set status = 'revoked'
     where guest_workspace_handoffs.id = v_handoff.id;
  end if;

  v_expires_at := case
    when p_handoff_kind = 'new_account_signup' then v_workspace.expires_at
    else now() + interval '10 minutes'
  end;

  insert into public.guest_workspace_handoffs (
    secret_hash,
    source_user_id,
    destination_email_hash,
    destination_user_id,
    source_conversation_id,
    pending_action,
    handoff_kind,
    created_at,
    expires_at
  ) values (
    p_secret_hash,
    p_source_user_id,
    p_destination_email_hash,
    null,
    p_source_conversation_id,
    p_pending_action,
    p_handoff_kind,
    now(),
    v_expires_at
  )
  returning * into v_handoff;

  return query
  select
    v_handoff.id,
    v_handoff.expires_at,
    v_handoff.destination_user_id,
    false;
end;
$$;

revoke all on function argus_private.prepare_guest_workspace_handoff(
  uuid, text, uuid, jsonb, text, text, text
) from public, anon, authenticated;
grant execute on function argus_private.prepare_guest_workspace_handoff(
  uuid, text, uuid, jsonb, text, text, text
) to service_role;

create or replace function public.prepare_guest_workspace_handoff(
  p_source_user_id uuid,
  p_destination_email_hash text,
  p_source_conversation_id uuid,
  p_pending_action jsonb,
  p_secret_hash text,
  p_existing_secret_hash text default null,
  p_handoff_kind text default 'existing_account'
)
returns table (
  id uuid,
  expires_at timestamptz,
  destination_user_id uuid,
  reused_secret boolean
)
language sql
security invoker
set search_path = ''
as $$
  select *
    from argus_private.prepare_guest_workspace_handoff(
      p_source_user_id,
      p_destination_email_hash,
      p_source_conversation_id,
      p_pending_action,
      p_secret_hash,
      p_existing_secret_hash,
      p_handoff_kind
    );
$$;

revoke all on function public.prepare_guest_workspace_handoff(
  uuid, text, uuid, jsonb, text, text, text
) from public, anon, authenticated;
grant execute on function public.prepare_guest_workspace_handoff(
  uuid, text, uuid, jsonb, text, text, text
) to service_role;

create or replace function argus_private.bind_guest_signup_handoff()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_marker jsonb := new.raw_user_meta_data -> 'argus_guest_signup';
  v_key text;
  v_handoff_id uuid;
  v_proof text;
  v_handoff public.guest_workspace_handoffs%rowtype;
  v_workspace public.guest_workspaces%rowtype;
  v_source_is_anonymous boolean;
  v_destination_email_hash text;
begin
  if v_marker is null then
    return new;
  end if;

  if jsonb_typeof(v_marker) <> 'object' then
    raise exception 'guest_signup_handoff_invalid' using errcode = '22023';
  end if;
  for v_key in select jsonb_object_keys(v_marker)
  loop
    if v_key not in ('handoff_id', 'proof') then
      raise exception 'guest_signup_handoff_invalid' using errcode = '22023';
    end if;
  end loop;

  begin
    v_handoff_id := nullif(v_marker ->> 'handoff_id', '')::uuid;
  exception when invalid_text_representation then
    raise exception 'guest_signup_handoff_invalid' using errcode = '22023';
  end;
  v_proof := nullif(v_marker ->> 'proof', '');

  if v_handoff_id is null
     or v_proof is null
     or v_proof !~ '^[0-9a-f]{64}$'
     or coalesce(new.is_anonymous, false)
     or nullif(btrim(new.email), '') is null then
    raise exception 'guest_signup_handoff_invalid' using errcode = '22023';
  end if;

  select *
    into v_handoff
    from public.guest_workspace_handoffs
   where id = v_handoff_id
   for update;
  if not found
     or v_handoff.secret_hash is distinct from v_proof
     or v_handoff.handoff_kind <> 'new_account_signup'
     or v_handoff.status <> 'pending'
     or v_handoff.expires_at <= now()
     or v_handoff.destination_user_id is not null then
    raise exception 'guest_signup_handoff_invalid' using errcode = 'P0001';
  end if;

  v_destination_email_hash := encode(
    extensions.digest(
      convert_to(lower(btrim(new.email)), 'UTF8'),
      'sha256'
    ),
    'hex'
  );
  if v_destination_email_hash is distinct from v_handoff.destination_email_hash then
    raise exception 'guest_signup_handoff_wrong_email' using errcode = 'P0001';
  end if;

  select coalesce(is_anonymous, false)
    into v_source_is_anonymous
    from auth.users
   where auth.users.id = v_handoff.source_user_id
   for update;
  if not found or v_source_is_anonymous is not true then
    raise exception 'guest_handoff_source_not_anonymous' using errcode = 'P0001';
  end if;

  select *
    into v_workspace
    from public.guest_workspaces
   where user_id = v_handoff.source_user_id
   for update;
  if not found
     or v_workspace.status <> 'active'
     or v_workspace.expires_at <= now()
     or v_workspace.expires_at is distinct from v_handoff.expires_at
     or v_workspace.conversation_id is distinct from v_handoff.source_conversation_id then
    raise exception 'guest_handoff_workspace_unavailable' using errcode = 'P0001';
  end if;

  update public.guest_workspace_handoffs
     set destination_user_id = new.id
   where id = v_handoff.id;

  -- raw_user_meta_data is user-editable and must never become durable proof.
  -- The marker has served its one purpose once the destination is bound.
  update auth.users
     set raw_user_meta_data = coalesce(raw_user_meta_data, '{}'::jsonb)
       - 'argus_guest_signup'
   where id = new.id;

  return new;
end;
$$;

revoke all on function argus_private.bind_guest_signup_handoff()
  from public, anon, authenticated;

drop trigger if exists bind_guest_signup_handoff on auth.users;
create trigger bind_guest_signup_handoff
after insert on auth.users
for each row execute function argus_private.bind_guest_signup_handoff();

-- Keep finalize_linked_guest_identity temporarily. It has no new runtime
-- producer, but it lets anonymous email-change confirmations already in flight
-- when this migration lands finish without stranding their existing workspace.
