-- gate-destructive: drops the refusal_log view and the refusal_observations table.
--
-- What: removes the private chat refusal evidence store created by
-- 20260908205041_add_refusal_observations. The API stopped writing to it in
-- the same change, and nothing reads it.
-- Why: the clean Business data model keeps no old chat evidence tables before
-- real customer data arrives.
-- One-way: dropped rows cannot be restored from this migration.
-- Rollout: staging first; James applies to production at release.
-- No CASCADE: an unexpected dependent object fails this migration instead of
-- being dropped silently.

begin;
set local lock_timeout = '5s';
set local statement_timeout = '60s';

drop view if exists public.refusal_log;
drop table if exists public.refusal_observations;

commit;
