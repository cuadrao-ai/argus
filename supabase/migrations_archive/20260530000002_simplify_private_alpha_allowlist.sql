-- Keep the private-alpha allowlist as a minimal access gate.
-- Invite/lifecycle tracking can be added later when a real invite workflow exists.

alter table public.private_alpha_allowlist
  drop column if exists display_name,
  drop column if exists invited_at,
  drop column if exists accepted_at,
  drop column if exists last_login_at,
  drop column if exists metadata;
