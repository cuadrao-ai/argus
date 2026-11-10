-- Known-bad changes for schema_diff.py: apply to database B only, diff against A,
-- confirm each marker in diff_controls.expected appears, then rebuild B.
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
