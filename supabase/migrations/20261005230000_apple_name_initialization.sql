alter table public.profiles
  add column name_initialization_closed boolean not null default true;
alter table public.profiles
  alter column name_initialization_closed set default false;

create function public.protect_profile_name_initialization()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if TG_OP = 'INSERT' then
    NEW.name_initialization_closed := NEW.name_initialization_closed
      or NEW.display_name is not null or NEW.preferred_name is not null;
  elsif OLD.name_initialization_closed then
    NEW.name_initialization_closed := true;
  end if;
  return NEW;
end;
$$;

create function public.close_profile_name_initialization()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  NEW.name_initialization_closed := true;
  return NEW;
end;
$$;

create trigger profiles_name_initialization_monotonic
before insert or update on public.profiles
for each row execute function public.protect_profile_name_initialization();
create trigger profiles_name_initialization_explicit_edit
before update of display_name, preferred_name on public.profiles
for each row execute function public.close_profile_name_initialization();

revoke all on function public.protect_profile_name_initialization()
  from public, anon, authenticated;
revoke all on function public.close_profile_name_initialization()
  from public, anon, authenticated;
revoke all (name_initialization_closed) on public.profiles from anon, authenticated;
