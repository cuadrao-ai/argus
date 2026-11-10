-- Welcome-email enforcement belongs to the promotion path, not to the
-- allowlist's whole lifecycle. The delivery trigger fires only on the
-- requested -> user promotion edge, the claim-freeze trigger is removed,
-- claims are transient in-flight state deleted on completion, and every
-- recovery path is reachable by service_role.

drop trigger guard_private_alpha_access_welcome_claim
  on public.private_alpha_allowlist;
drop function public.guard_private_alpha_access_welcome_claim();

-- A claim now exists only between claim and completion; there is no
-- consumed terminal state to strand a recipient's primary key.
alter table public.private_alpha_access_welcome_claims
  drop column consumed_at;

create or replace function public.require_private_alpha_access_welcome_delivery()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if old.role = 'requested'
    and new.role = 'user'
    and new.disabled_at is null
    and not exists (
      select 1
      from public.private_alpha_access_welcome_deliveries
      where recipient_email = new.email
        and language = new.language
    ) then
    raise exception 'requested promotion requires welcome delivery'
      using errcode = '23514';
  end if;

  return new;
end;
$$;

create or replace function public.claim_private_alpha_access_welcome(
  p_email text,
  p_language text,
  p_content_version text,
  p_subject text
)
returns table (
  recipient_email text,
  language text,
  content_version text,
  subject text,
  claim_token uuid,
  claimed_at timestamptz,
  send_allowed boolean
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_email text := lower(btrim(p_email));
  v_role text;
  v_language text;
  v_disabled_at timestamptz;
  v_claim public.private_alpha_access_welcome_claims%rowtype;
begin
  select a.role, a.language, a.disabled_at
    into v_role, v_language, v_disabled_at
  from public.private_alpha_allowlist as a
  where a.email = v_email
  for update;

  if not found
    or v_role is distinct from 'requested'
    or v_disabled_at is not null
    or p_language is distinct from v_language
    or p_content_version is distinct from 'private-alpha-access-welcome/v1'
    or char_length(p_subject) not between 1 and 200 then
    return;
  end if;

  select c.*
    into v_claim
  from public.private_alpha_access_welcome_claims as c
  where c.recipient_email = v_email
  for update;

  if found then
    if v_claim.language is distinct from p_language
      or v_claim.content_version is distinct from p_content_version
      or v_claim.subject is distinct from p_subject then
      return;
    end if;
  else
    insert into public.private_alpha_access_welcome_claims (
      recipient_email,
      language,
      content_version,
      subject
    )
    values (
      v_email,
      p_language,
      p_content_version,
      p_subject
    )
    returning * into v_claim;
  end if;

  return query
  select v_claim.recipient_email,
         v_claim.language,
         v_claim.content_version,
         v_claim.subject,
         v_claim.claim_token,
         v_claim.claimed_at,
         v_claim.claimed_at > now() - interval '24 hours';
end;
$$;

revoke all on function public.claim_private_alpha_access_welcome(
  text, text, text, text
) from public, anon, authenticated, service_role;
grant execute on function public.claim_private_alpha_access_welcome(
  text, text, text, text
) to service_role;

create or replace function public.complete_private_alpha_access_welcome(
  p_email text,
  p_language text,
  p_content_version text,
  p_subject text,
  p_provider_receipt text,
  p_claim_token uuid
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_email text := lower(btrim(p_email));
  v_role text;
  v_language text;
  v_disabled_at timestamptz;
  v_claim public.private_alpha_access_welcome_claims%rowtype;
  v_claim_found boolean;
begin
  select a.role, a.language, a.disabled_at
    into v_role, v_language, v_disabled_at
  from public.private_alpha_allowlist as a
  where a.email = v_email
  for update;

  if not found
    or v_disabled_at is not null
    or v_role not in ('requested', 'user')
    or p_language is distinct from v_language then
    return false;
  end if;

  select c.*
    into v_claim
  from public.private_alpha_access_welcome_claims as c
  where c.recipient_email = v_email
  for update;
  v_claim_found := found;

  if p_claim_token is null then
    -- Replay of an already-completed approval. An open claim means a send
    -- is owed for this grant, so the replay path must refuse and let the
    -- caller run the real claim/send path.
    if v_claim_found or v_role is distinct from 'user' then
      return false;
    end if;
    return exists (
      select 1
      from public.private_alpha_access_welcome_deliveries as d
      where d.recipient_email = v_email
        and d.language = p_language
        and d.content_version = p_content_version
        and d.subject = p_subject
    );
  end if;

  if v_claim_found then
    if v_claim.claim_token is distinct from p_claim_token
      or v_claim.language is distinct from p_language
      or v_claim.content_version is distinct from p_content_version
      or v_claim.subject is distinct from p_subject then
      return false;
    end if;

    -- The delivery row records the latest grant's welcome; a fresh grant
    -- after offboarding replaces the stale record instead of failing on it.
    insert into public.private_alpha_access_welcome_deliveries (
      recipient_email,
      language,
      content_version,
      subject,
      provider_receipt
    )
    values (
      v_email,
      p_language,
      p_content_version,
      p_subject,
      p_provider_receipt
    )
    on conflict (recipient_email) do update
      set language = excluded.language,
          content_version = excluded.content_version,
          subject = excluded.subject,
          provider_receipt = excluded.provider_receipt,
          sent_at = now();

    delete from public.private_alpha_access_welcome_claims
    where recipient_email = v_email
      and claim_token = p_claim_token;
    if not found then
      raise exception 'access welcome claim consumption failed'
        using errcode = '40001';
    end if;

    if v_role = 'requested' then
      update public.private_alpha_allowlist
      set role = 'user'
      where email = v_email
        and role = 'requested'
        and disabled_at is null;
      if not found then
        raise exception 'access welcome promotion failed'
          using errcode = '40001';
      end if;
    end if;

    return true;
  end if;

  -- Token supplied but the claim is gone: a concurrent completion already
  -- consumed it. Succeed only when that completion's outcome is in place.
  if v_role is distinct from 'user' then
    return false;
  end if;
  return exists (
    select 1
    from public.private_alpha_access_welcome_deliveries as d
    where d.recipient_email = v_email
      and d.language = p_language
      and d.content_version = p_content_version
      and d.subject = p_subject
  );
end;
$$;

revoke all on function public.complete_private_alpha_access_welcome(
  text, text, text, text, text, uuid
) from public, anon, authenticated, service_role;
grant execute on function public.complete_private_alpha_access_welcome(
  text, text, text, text, text, uuid
) to service_role;

-- Expired claims block SMTP by design; this is the release half. 48 hours
-- keeps a full provider idempotency window plus one scheduled-maintenance
-- day of margin between the block and the release.
create or replace function public.release_expired_private_alpha_access_welcome_claims(
  p_expired_before timestamptz default now() - interval '48 hours'
)
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_released integer;
begin
  delete from public.private_alpha_access_welcome_claims
  where claimed_at <= p_expired_before;
  get diagnostics v_released = row_count;
  return v_released;
end;
$$;

revoke all on function public.release_expired_private_alpha_access_welcome_claims(
  timestamptz
) from public, anon, authenticated, service_role;
grant execute on function public.release_expired_private_alpha_access_welcome_claims(
  timestamptz
) to service_role;

-- Orphan cleanup: claim and delivery rows for an email with no allowlist
-- presence at all. This is the canary teardown and the offboarding repair
-- path; it refuses while any allowlist row exists for the email.
create or replace function public.delete_private_alpha_access_welcome_artifacts(
  p_email text
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_email text := lower(btrim(p_email));
begin
  if exists (
    select 1
    from public.private_alpha_allowlist
    where email = v_email
  ) then
    return false;
  end if;

  delete from public.private_alpha_access_welcome_claims
  where recipient_email = v_email;
  delete from public.private_alpha_access_welcome_deliveries
  where recipient_email = v_email;
  return true;
end;
$$;

revoke all on function public.delete_private_alpha_access_welcome_artifacts(
  text
) from public, anon, authenticated, service_role;
grant execute on function public.delete_private_alpha_access_welcome_artifacts(
  text
) to service_role;
