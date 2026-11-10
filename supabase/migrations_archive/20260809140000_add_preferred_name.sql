-- What the user asked Argus to call them, which is not who their account says
-- they are. `display_name` is an identity field people fill with a legal name,
-- so a greeting reusing it addresses the account rather than the person.
--
-- Optional by design: being addressed by name is not universally welcome, and a
-- dedicated field makes it a choice the user made rather than a side effect of
-- having an account. Null means the greeting uses no name.
--
-- Stated, never inferred. Nothing writes this but the user's own settings edit.

alter table public.profiles
  add column if not exists preferred_name text;

alter table public.profiles
  drop constraint if exists profiles_preferred_name_length;
alter table public.profiles
  add constraint profiles_preferred_name_length
  check (preferred_name is null or char_length(preferred_name) between 1 and 40);

-- Registered-only, the same shape avatar_theme uses. Supabase anonymous Auth
-- users share the authenticated database role, so the restrictive policies read
-- the trusted JWT claim to keep this off the guest surface while preserving
-- strict owner-only access for accounts.
drop policy if exists profiles_registered_preferred_name_select on public.profiles;
create policy profiles_registered_preferred_name_select
  on public.profiles
  as restrictive
  for select
  to authenticated
  using (
    (select auth.uid()) = id
    and ((select auth.jwt()) ->> 'is_anonymous') is distinct from 'true'
  );

drop policy if exists profiles_registered_preferred_name_update on public.profiles;
create policy profiles_registered_preferred_name_update
  on public.profiles
  as restrictive
  for update
  to authenticated
  using (
    (select auth.uid()) = id
    and ((select auth.jwt()) ->> 'is_anonymous') is distinct from 'true'
  )
  with check (
    (select auth.uid()) = id
    and ((select auth.jwt()) ->> 'is_anonymous') is distinct from 'true'
  );

grant select (id, preferred_name), update (preferred_name)
  on table public.profiles to authenticated;
