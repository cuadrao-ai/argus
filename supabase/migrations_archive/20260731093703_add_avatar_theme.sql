-- Curated, durable presentation preference for registered profile monograms.
-- RLS is table-scoped rather than column-scoped, so the restrictive policies
-- below protect every direct profile read/update for anonymous-auth guests.

do $$
begin
  create type public.avatar_theme as enum (
    'ocean',
    'plum',
    'teal',
    'ember',
    'gold',
    'indigo',
    'slate'
  );
exception
  when duplicate_object then null;
end
$$;

alter table public.profiles
  add column if not exists avatar_theme public.avatar_theme not null default 'ocean';

-- Make the row-owner checks explicit before adding the registered-only gate.
drop policy if exists profiles_owner_select on public.profiles;
create policy profiles_owner_select
  on public.profiles
  for select
  to authenticated
  using ((select auth.uid()) = id);

drop policy if exists profiles_owner_update on public.profiles;
create policy profiles_owner_update
  on public.profiles
  for update
  to authenticated
  using ((select auth.uid()) = id)
  with check ((select auth.uid()) = id);

-- Supabase anonymous Auth users share the authenticated database role. These
-- restrictive policies use the trusted JWT claim to keep this durable setting
-- off the guest surface while preserving strict owner-only access for accounts.
drop policy if exists profiles_registered_avatar_theme_select on public.profiles;
create policy profiles_registered_avatar_theme_select
  on public.profiles
  as restrictive
  for select
  to authenticated
  using (
    (select auth.uid()) = id
    and ((select auth.jwt()) ->> 'is_anonymous') is distinct from 'true'
  );

drop policy if exists profiles_registered_avatar_theme_update on public.profiles;
create policy profiles_registered_avatar_theme_update
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

grant select (id, avatar_theme), update (avatar_theme)
  on table public.profiles to authenticated;
