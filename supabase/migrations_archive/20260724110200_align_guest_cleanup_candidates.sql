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
  v_now timestamptz := now();
begin
  if p_limit < 1 or p_limit > 100 then
    raise exception 'cleanup limit must be between 1 and 100'
      using errcode = '22023';
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
           and g.updated_at <= v_now - interval '5 minutes'
         )
       )
       and g.expires_at <= v_now
       and coalesce(u.is_anonymous, false)
     order by g.expires_at, g.user_id
     limit p_limit
     for update of g, u skip locked
  loop
    user_id := v_candidate.user_id;
    conversation_id := v_candidate.conversation_id;
    if p_dry_run then
      return next;
      continue;
    end if;

    update public.guest_workspaces as g
       set status = 'expired',
           conversation_id = null,
           updated_at = v_now
     where g.user_id = v_candidate.user_id;

    -- Feedback text is user content, not privacy-safe aggregate evidence.
    delete from public.feedback as f
     where f.user_id = v_candidate.user_id;

    if v_candidate.conversation_id is not null then
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

    return next;
  end loop;
end;
$$;

revoke all on function public.claim_expired_guest_workspaces(integer, boolean)
  from public, anon, authenticated;
grant execute on function public.claim_expired_guest_workspaces(integer, boolean)
  to service_role;
