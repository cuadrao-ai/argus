-- Private-alpha access allowlist.
-- Source of truth: docs/API_CONTRACT.md and docs/DATA_MODEL.md.

create table if not exists public.private_alpha_allowlist (
  email text primary key check (email = lower(trim(email))),
  role text not null default 'user' check (role in ('admin', 'developer', 'user')),
  disabled_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_private_alpha_allowlist_active
  on public.private_alpha_allowlist(email)
  where disabled_at is null;

alter table public.private_alpha_allowlist enable row level security;

revoke all on table public.private_alpha_allowlist from anon, authenticated;
grant all privileges on table public.private_alpha_allowlist to service_role;

drop trigger if exists set_private_alpha_allowlist_updated_at
  on public.private_alpha_allowlist;
create trigger set_private_alpha_allowlist_updated_at
before update on public.private_alpha_allowlist
for each row execute function public.set_updated_at();
