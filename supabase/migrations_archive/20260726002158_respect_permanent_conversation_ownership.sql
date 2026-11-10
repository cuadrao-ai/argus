-- Retained guest workspace history must not constrain a verified permanent
-- Auth identity after in-place conversion.
create or replace function public.bind_new_guest_conversation()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_is_anonymous boolean;
  v_workspace public.guest_workspaces%rowtype;
begin
  select auth_user.is_anonymous
    into v_is_anonymous
    from auth.users as auth_user
   where auth_user.id = new.user_id;

  if not found then
    raise exception 'conversation owner has no verified Auth identity'
      using errcode = '23503';
  end if;
  if coalesce(v_is_anonymous, false) is false then
    return new;
  end if;

  select *
    into v_workspace
    from public.guest_workspaces
   where user_id = new.user_id
   for update;

  if not found then
    return new;
  end if;
  if v_workspace.status <> 'active'
     or v_workspace.expires_at <= now() then
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

revoke all on function public.bind_new_guest_conversation()
  from public, anon, authenticated;
