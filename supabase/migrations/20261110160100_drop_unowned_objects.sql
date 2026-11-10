set local lock_timeout = '5s';
set local statement_timeout = '60s';

-- #1890: nothing outside tests and docs reads these. A database built from the
-- baseline never had them, so each statement does nothing there.
drop function if exists public.baseline_conversation_activity_read_states(timestamptz, uuid, integer);
drop function if exists public.claim_guest_compute_usage(text, text, text, integer, integer);
drop function if exists public.claim_registered_compute_usage(text, text, integer);
drop function if exists public.delete_private_alpha_access_welcome_artifacts(text);
drop table if exists argus_private.retention_sweeps;
drop table if exists argus_private.retention_policies;

-- No job is scheduled and no code calls the network from the database (#1227).
drop extension if exists pg_cron;
drop extension if exists pg_net;
