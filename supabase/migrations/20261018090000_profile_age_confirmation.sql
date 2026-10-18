alter table public.profiles
  add column age_confirmed_at timestamptz;

comment on column public.profiles.age_confirmed_at is
  'First client 18+ attestation instant, not verified age. No birthday or raw age range.';

create function public.protect_profile_age_confirmation()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if TG_OP = 'UPDATE' and OLD.age_confirmed_at is not null then
    if NEW.age_confirmed_at is distinct from OLD.age_confirmed_at then
      raise exception 'age confirmation is immutable' using errcode = '23514';
    end if;
  end if;
  if NEW.age_confirmed_at is not null then
    if current_user in ('anon', 'authenticated') and
       (TG_OP = 'INSERT' or OLD.age_confirmed_at is distinct from NEW.age_confirmed_at) then
      raise exception 'age confirmation requires backend initialization' using errcode = '42501';
    end if;
    if not pg_catalog.isfinite(NEW.age_confirmed_at) or
       NEW.age_confirmed_at > pg_catalog.now() + interval '5 minutes' then
      raise exception 'invalid age confirmation instant' using errcode = '23514';
    end if;
  end if;
  return NEW;
end;
$$;

create trigger profiles_age_confirmation_first_write
before insert or update of age_confirmed_at on public.profiles
for each row execute function public.protect_profile_age_confirmation();

revoke all on function public.protect_profile_age_confirmation()
  from public, anon, authenticated;
revoke all (age_confirmed_at) on public.profiles from anon, authenticated;
