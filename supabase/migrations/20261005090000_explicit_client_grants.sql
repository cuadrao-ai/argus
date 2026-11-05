-- State the client grants on the early public tables instead of inheriting
-- them from the image's default privileges, which differ between hosted,
-- CLI 2.109.0 and newer images (#811). Privileges only: no data, row-level
-- security policy or table changes, and service_role is untouched.

alter default privileges for role postgres in schema public
  revoke all on tables from anon, authenticated;
alter default privileges for role postgres in schema public
  revoke all on sequences from anon, authenticated;
alter default privileges for role postgres in schema public
  revoke all on functions from anon, authenticated;

-- A table-level revoke also removes the column grants on profiles; they are
-- granted back below.
revoke all on table
  public.backtest_jobs,
  public.backtest_runs,
  public.collection_strategies,
  public.collections,
  public.context_packets,
  public.conversations,
  public.decision_notes,
  public.evidence_artifacts,
  public.feedback,
  public.idea_versions,
  public.ideas,
  public.messages,
  public.profiles,
  public.route_receipts,
  public.run_context_packets,
  public.strategies,
  public.usage_counters
from anon, authenticated;

grant select on table public.backtest_jobs to authenticated;
grant select (id, avatar_theme, country, currency_override, preferred_name)
  on table public.profiles to authenticated;
grant update (avatar_theme, country, currency_override, preferred_name)
  on table public.profiles to authenticated;

revoke execute on function public.is_active_household_member(uuid, uuid)
  from anon;
revoke execute on function public.validate_profile_auth_identity()
  from anon, authenticated;
revoke execute on function public.protect_guest_workspace_policy_fields()
  from anon, authenticated;
