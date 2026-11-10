-- Reuse the private-alpha allowlist for public access requests.
-- Requested rows are service-owned state and do not grant account access.

alter table public.private_alpha_allowlist
  drop constraint if exists private_alpha_allowlist_role_check;

alter table public.private_alpha_allowlist
  add constraint private_alpha_allowlist_role_check
  check (role in ('admin', 'developer', 'user', 'requested'));

alter table public.private_alpha_allowlist
  add column if not exists language text not null default 'en';

alter table public.private_alpha_allowlist
  drop constraint if exists private_alpha_allowlist_language_check;

alter table public.private_alpha_allowlist
  add constraint private_alpha_allowlist_language_check
  check (language in ('en', 'es-419'));

alter table public.private_alpha_allowlist enable row level security;

revoke all on table public.private_alpha_allowlist
  from public, anon, authenticated;
revoke all on table public.private_alpha_allowlist from service_role;
grant select, insert, update, delete on table public.private_alpha_allowlist
  to service_role;
