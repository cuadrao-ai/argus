create table public.private_alpha_access_welcome_claims (
  recipient_email text primary key,
  language text not null check (language in ('en', 'es-419')),
  content_version text not null check (
    content_version = 'private-alpha-access-welcome/v1'
  ),
  subject text not null check (char_length(subject) between 1 and 200),
  claim_token uuid not null unique default gen_random_uuid(),
  claimed_at timestamptz not null default now(),
  consumed_at timestamptz,
  check (recipient_email = lower(btrim(recipient_email))),
  check (consumed_at is null or consumed_at >= claimed_at)
);

alter table public.private_alpha_access_welcome_claims
  enable row level security;

revoke all on table public.private_alpha_access_welcome_claims
  from public, anon, authenticated, service_role;

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
    if v_claim.consumed_at is not null
      or v_claim.language is distinct from p_language
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

revoke all on function public.complete_private_alpha_access_welcome(
  text, text, text, text, text
) from public, anon, authenticated, service_role;
drop function public.complete_private_alpha_access_welcome(
  text, text, text, text, text
);

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
  v_delivery_language text;
  v_delivery_content_version text;
  v_delivery_subject text;
  v_delivery_found boolean;
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

  select d.language, d.content_version, d.subject
    into v_delivery_language, v_delivery_content_version, v_delivery_subject
  from public.private_alpha_access_welcome_deliveries as d
  where d.recipient_email = v_email;
  v_delivery_found := found;

  select c.*
    into v_claim
  from public.private_alpha_access_welcome_claims as c
  where c.recipient_email = v_email
    and c.consumed_at is null
  for update;
  v_claim_found := found;

  if v_delivery_found then
    if v_delivery_language is distinct from p_language
      or v_delivery_content_version is distinct from p_content_version
      or v_delivery_subject is distinct from p_subject then
      return false;
    end if;

    if v_claim_found then
      if p_claim_token is null
        or v_claim.claim_token is distinct from p_claim_token
        or v_claim.language is distinct from p_language
        or v_claim.content_version is distinct from p_content_version
        or v_claim.subject is distinct from p_subject then
        return false;
      end if;

      update public.private_alpha_access_welcome_claims
      set consumed_at = now()
      where recipient_email = v_email
        and claim_token = p_claim_token
        and consumed_at is null;
      if not found then
        raise exception 'access welcome claim consumption failed'
          using errcode = '40001';
      end if;
    end if;
  else
    if v_role = 'user'
      or not v_claim_found
      or p_claim_token is null
      or v_claim.claim_token is distinct from p_claim_token
      or v_claim.language is distinct from p_language
      or v_claim.content_version is distinct from p_content_version
      or v_claim.subject is distinct from p_subject then
      return false;
    end if;

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
    );

    update public.private_alpha_access_welcome_claims
    set consumed_at = now()
    where recipient_email = v_email
      and claim_token = p_claim_token
      and consumed_at is null;
    if not found then
      raise exception 'access welcome claim consumption failed'
        using errcode = '40001';
    end if;
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
end;
$$;

revoke all on function public.complete_private_alpha_access_welcome(
  text, text, text, text, text, uuid
) from public, anon, authenticated, service_role;
grant execute on function public.complete_private_alpha_access_welcome(
  text, text, text, text, text, uuid
) to service_role;

revoke insert on table public.private_alpha_access_welcome_deliveries
  from service_role;

create or replace function public.guard_private_alpha_access_welcome_claim()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if exists (
    select 1
    from public.private_alpha_access_welcome_claims as c
    where c.recipient_email = old.email
      and c.consumed_at is null
  ) then
    if tg_op = 'DELETE' then
      raise exception 'pending access welcome claim freezes allowlist state'
        using errcode = '23514';
    end if;

    if new.email is distinct from old.email
      or new.role is distinct from old.role
      or new.language is distinct from old.language
      or new.disabled_at is distinct from old.disabled_at then
      raise exception 'pending access welcome claim freezes allowlist state'
        using errcode = '23514';
    end if;
  end if;

  if tg_op = 'DELETE' then
    return old;
  end if;
  return new;
end;
$$;

revoke all on function public.guard_private_alpha_access_welcome_claim()
  from public, anon, authenticated, service_role;

create trigger guard_private_alpha_access_welcome_claim
before update or delete on public.private_alpha_allowlist
for each row
execute function public.guard_private_alpha_access_welcome_claim();
