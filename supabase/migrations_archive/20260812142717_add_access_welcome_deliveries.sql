create table public.private_alpha_access_welcome_deliveries (
  recipient_email text primary key,
  language text not null check (language in ('en', 'es-419')),
  content_version text not null check (
    content_version = 'private-alpha-access-welcome/v1'
  ),
  subject text not null check (char_length(subject) between 1 and 200),
  provider_receipt text not null check (
    char_length(provider_receipt) between 1 and 256
  ),
  sent_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  check (recipient_email = lower(btrim(recipient_email)))
);

alter table public.private_alpha_access_welcome_deliveries
  enable row level security;

revoke all on table public.private_alpha_access_welcome_deliveries
  from public, anon, authenticated, service_role;
grant select, insert on table public.private_alpha_access_welcome_deliveries
  to service_role;

create or replace function public.complete_private_alpha_access_welcome(
  p_email text,
  p_language text,
  p_content_version text,
  p_subject text,
  p_provider_receipt text
)
returns boolean
language plpgsql
security invoker
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
begin
  select role, language, disabled_at
    into v_role, v_language, v_disabled_at
  from public.private_alpha_allowlist
  where email = v_email
  for update;

  if not found
    or v_disabled_at is not null
    or v_role not in ('requested', 'user')
    or p_language is distinct from v_language then
    return false;
  end if;

  select language, content_version, subject
    into v_delivery_language, v_delivery_content_version, v_delivery_subject
  from public.private_alpha_access_welcome_deliveries
  where recipient_email = v_email;

  if found
    and (
      v_delivery_language is distinct from p_language
      or v_delivery_content_version is distinct from p_content_version
      or v_delivery_subject is distinct from p_subject
    ) then
    return false;
  end if;

  if not found and v_role = 'user' then
    return false;
  end if;

  if not found then
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
    on conflict (recipient_email) do nothing;

    select language, content_version, subject
      into v_delivery_language, v_delivery_content_version, v_delivery_subject
    from public.private_alpha_access_welcome_deliveries
    where recipient_email = v_email;
  end if;

  if not found
    or v_delivery_language is distinct from p_language
    or v_delivery_content_version is distinct from p_content_version
    or v_delivery_subject is distinct from p_subject then
    return false;
  end if;

  if v_role = 'requested' then
    update public.private_alpha_allowlist
    set role = 'user'
    where email = v_email
      and role = 'requested'
      and disabled_at is null;

    if not found then
      return false;
    end if;
  end if;

  return true;
end;
$$;

revoke all on function public.complete_private_alpha_access_welcome(
  text, text, text, text, text
) from public, anon, authenticated, service_role;
grant execute on function public.complete_private_alpha_access_welcome(
  text, text, text, text, text
) to service_role;

create or replace function public.require_private_alpha_access_welcome_delivery()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if new.role = 'user'
    and new.disabled_at is null
    and (
      old.role is distinct from 'user'
      or old.disabled_at is not null
    )
    and not exists (
      select 1
      from public.private_alpha_access_welcome_deliveries
      where recipient_email = new.email
        and language = new.language
    ) then
    raise exception 'active private-alpha user requires welcome delivery'
      using errcode = '23514';
  end if;

  return new;
end;
$$;

revoke all on function public.require_private_alpha_access_welcome_delivery()
  from public, anon, authenticated, service_role;

create trigger require_private_alpha_access_welcome_delivery
before update on public.private_alpha_allowlist
for each row
execute function public.require_private_alpha_access_welcome_delivery();
