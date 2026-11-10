-- Where the user lives, and the currency they count in when it is not their
-- country's. Research sends the country as the reader's location; a user with
-- no country sends no location.
--
-- Stated, never inferred (decision 8). Nothing writes these but the user's own
-- settings edit, and nothing derives them from conversation, IP or behavior.
-- Null means not chosen.
--
-- The currency a profile resolves to is not stored: it is the override when
-- there is one and otherwise derives from the country, so only the override is
-- a column. The constraints check the code's shape; which codes are assigned
-- moves with the standards and is checked where the edit is accepted.

alter table public.profiles
  add column if not exists country text,
  add column if not exists currency_override text;

alter table public.profiles
  drop constraint if exists profiles_country_shape;
alter table public.profiles
  add constraint profiles_country_shape
  check (country is null or country ~ '^[A-Z]{2}$');

alter table public.profiles
  drop constraint if exists profiles_currency_override_shape;
alter table public.profiles
  add constraint profiles_currency_override_shape
  check (currency_override is null or currency_override ~ '^[A-Z]{3}$');

-- Registered-only, the same shape preferred_name uses. Supabase anonymous Auth
-- users share the authenticated database role, so the restrictive policies read
-- the trusted JWT claim to keep this off the guest surface while preserving
-- strict owner-only access for accounts.
drop policy if exists profiles_registered_home_country_select on public.profiles;
create policy profiles_registered_home_country_select
  on public.profiles
  as restrictive
  for select
  to authenticated
  using (
    (select auth.uid()) = id
    and ((select auth.jwt()) ->> 'is_anonymous') is distinct from 'true'
  );

drop policy if exists profiles_registered_home_country_update on public.profiles;
create policy profiles_registered_home_country_update
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

grant select (id, country, currency_override), update (country, currency_override)
  on table public.profiles to authenticated;
