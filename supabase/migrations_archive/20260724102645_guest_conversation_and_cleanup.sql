-- Guest conversation replacement and bounded cleanup claim.

create or replace function public.replace_empty_guest_conversation(
  p_user_id uuid,
  p_title text,
  p_title_source text,
  p_language text
)
returns public.conversations
language plpgsql
security definer
set search_path = public
as $$
declare
  v_workspace public.guest_workspaces%rowtype;
  v_conversation public.conversations%rowtype;
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

  if v_workspace.conversation_id is not null then
    if exists (
      select 1 from public.messages
       where conversation_id = v_workspace.conversation_id
    ) or exists (
      select 1 from public.backtest_jobs
       where conversation_id = v_workspace.conversation_id
    ) or exists (
      select 1 from public.backtest_runs
       where conversation_id = v_workspace.conversation_id
    ) then
      raise exception 'guest conversation is not empty'
        using errcode = '23514';
    end if;
    delete from public.conversations
     where id = v_workspace.conversation_id
       and user_id = p_user_id;
  end if;

  insert into public.conversations (
    user_id,
    title,
    title_source,
    language
  ) values (
    p_user_id,
    p_title,
    p_title_source,
    p_language
  )
  returning * into v_conversation;
  return v_conversation;
end;
$$;

revoke all on function public.replace_empty_guest_conversation(
  uuid, text, text, text
) from public, anon, authenticated;
grant execute on function public.replace_empty_guest_conversation(
  uuid, text, text, text
) to service_role;

create or replace function public.claim_expired_guest_workspaces(
  p_limit integer,
  p_dry_run boolean default false
)
returns table (
  user_id uuid,
  conversation_id uuid
)
language plpgsql
security definer
set search_path = public, auth
as $$
declare
  v_candidate record;
begin
  if p_limit < 1 or p_limit > 100 then
    raise exception 'cleanup limit must be between 1 and 100'
      using errcode = '22023';
  end if;

  if p_dry_run then
    return query
      select g.user_id, g.conversation_id
        from public.guest_workspaces as g
        join auth.users as u on u.id = g.user_id
       where g.claimed_by is null
         and g.claimed_at is null
         and g.status in ('active', 'expired')
         and g.expires_at <= now()
         and coalesce(u.is_anonymous, false)
       order by g.expires_at, g.user_id
       limit p_limit;
    return;
  end if;

  for v_candidate in
    select g.user_id, g.conversation_id
      from public.guest_workspaces as g
      join auth.users as u on u.id = g.user_id
     where g.claimed_by is null
       and g.claimed_at is null
       and (
         g.status = 'active'
         or (
           g.status = 'expired'
           and g.updated_at <= now() - interval '5 minutes'
         )
       )
       and g.expires_at <= now()
       and coalesce(u.is_anonymous, false)
     order by g.expires_at, g.user_id
     limit p_limit
     for update of g, u skip locked
  loop
    update public.guest_workspaces as g
       set status = 'expired',
           conversation_id = null,
           updated_at = now()
     where g.user_id = v_candidate.user_id;

    -- Feedback text is user content, not privacy-safe aggregate evidence.
    delete from public.feedback as f
     where f.user_id = v_candidate.user_id;

    if v_candidate.conversation_id is not null then
      -- LangGraph persistence uses the product conversation UUID as thread_id
      -- without a foreign key, so remove its private runtime graph explicitly.
      delete from public.checkpoint_writes
       where thread_id = v_candidate.conversation_id::text;
      delete from public.checkpoint_blobs
       where thread_id = v_candidate.conversation_id::text;
      delete from public.checkpoints
       where thread_id = v_candidate.conversation_id::text;

      delete from public.conversations as c
       where c.id = v_candidate.conversation_id
         and c.user_id = v_candidate.user_id;
    end if;

    user_id := v_candidate.user_id;
    conversation_id := v_candidate.conversation_id;
    return next;
  end loop;
end;
$$;

revoke all on function public.claim_expired_guest_workspaces(integer, boolean)
  from public, anon, authenticated;
grant execute on function public.claim_expired_guest_workspaces(integer, boolean)
  to service_role;
