-- Known-bad changes for schema_diff.py. prove.sh applies them to database C after the
-- real diffs, diffs C against A again, and requires every line of diff_controls.expected.
grant select on public.business_guide_dismissals to anon;
drop policy business_guide_dismissals_insert on public.business_guide_dismissals;
drop trigger refuse_placeholder_email on auth.users;
delete from argus_private.business_custody_deferred_keys
    where constraint_name = 'financial_accounts_owner_space_fkey';
update storage.buckets set file_size_limit = 1 where id = 'profile-images';
alter event trigger ensure_rls disable;
alter default privileges for role postgres in schema public grant select on tables to anon;
comment on table public.spaces is 'control';
alter function public.set_updated_at() set search_path = public;
-- The same index with no carriage return in btrim's set: the diff must be byte-exact.
drop index public.financial_import_events_sale_ncf_idx;
create unique index financial_import_events_sale_ncf_idx
  on public.financial_import_events (
    owner_space_id,
    (upper(btrim(coalesce(
      nullif(resolution->'business'->'facts'->'fiscal'->'ecf'->>'value', ''),
      resolution->'business'->'facts'->'fiscal'->'ncf'->>'value'), E' \t\n')))
  )
  where state in ('accepting', 'accepted')
    and owner_space_id is not null
    and resolution->'business'->'facts'->'kind'->>'value' = 'income'
    and upper(btrim(coalesce(
          nullif(resolution->'business'->'facts'->'fiscal'->'ecf'->>'value', ''),
          resolution->'business'->'facts'->'fiscal'->'ncf'->>'value'), E' \t\n'))
        ~ '^(B[0-9]{10}|E[0-9]{12})$';
