# Staging waitlist schedules

The coordinator deploys from the merged integration commit. This function reuses
`marketing/lib/waitlist/email.ts` and the shared account layout. Changes to that
renderer require redeploying this function as well as the marketing service.
Signup sends confirmation immediately. Welcome is sent only after confirmation.

## Deploy from the merged commit

1. Confirm the linked database is `skedzwocnmrhfigiwyzi`. Run the repository's
   migration preflight and inspect the pending list. Apply approved pending
   migrations with `supabase db push`. Do not use MCP DDL or apply this branch.
2. Deploy with `supabase functions deploy waitlist-reminders --project-ref skedzwocnmrhfigiwyzi`. Keep JWT verification enabled. The CLI bundles the relative
   marketing imports; deploy from the repository root.
3. Privately set these Edge secrets using existing approved values:
   `RESEND_API_KEY`, `MARKETING_WAITLIST_FROM`, `MARKETING_POSTAL_ADDRESS`, and
   `CUADRAO_WAITLIST_ORIGIN`. Supabase supplies `SUPABASE_URL` and the existing
   legacy `SUPABASE_SERVICE_ROLE_KEY`. No CAPTCHA secret is needed by this function.
4. Through the existing private staging database connection, use parameterized
   `vault.create_secret` or `vault.update_secret` calls to set the names
   `cuadrao_waitlist_service_role_key` and `cuadrao_waitlist_project_url`.
   Reuse the existing staging service-role credential. The URL must equal
   `https://skedzwocnmrhfigiwyzi.supabase.co`. Never put credential literals in
   SQL files, tool arguments, shell history, logs, or the PR. Set the URL last.
5. Read back secret names only. Check both named jobs and their next real runs.
   Do not release before an actual scheduled retention run and reminder
   invocation succeed on staging. Direct function calls do not satisfy this gate.

The migration installs pg_cron and pg_net. Vault already exists in staging.
It registers two idempotent jobs, without new tables or columns:

- `cuadrao-waitlist-reminders`: every five minutes, at most two due reminders.
- `cuadrao-waitlist-retention`: two minutes later, at most 100 expired rows.

The capacity is 576 reminder reservations and 28,800 deletions per day. This is a
bounded initial waitlist schedule; inspect backlog before changing its limits.
A missing Vault URL or credential fails visibly. The URL guard prevents accidental
activation in an unconfigured database; deployment target verification is still
required. The Edge Function independently refuses any non-staging project URL.

## Check outcomes

Inspect `cron.job_run_details` for the two job IDs. A successful reminder cron
means the HTTP request was queued, not that mail was delivered. Correlate the
logged request ID with `net._http_response` and require a 200 response with
`remindersFailed: 0`. Inspect responses within pg_net's retention window (default
six hours). Any timeout, non-200 response, or failed cron blocks release and needs
operator follow-up. Edge logs contain counts and event names, never addresses or
credentials. Retention logs contain the deleted count.

Unknown provider delivery retains the reservation; a definite refusal releases
only the matching timestamp. The next scheduled run can retry released rows.
The Edge Function never runs retention. The old maintenance CLI remains manual
recovery only and must not be scheduled alongside these jobs.

For rollback, the coordinator disables these two named jobs and the function.
Do not remove the consent columns or undo completed retention deletions.

## Local verification

Use an owned Supabase PostgreSQL container with `pg_cron`, `pg_net`, and
`supabase_vault` preloaded, plus a local Vault key. Apply the original signup,
personal confirmation, and scheduler migrations in that order. Replay the scheduler
migration to check the two job IDs remain stable. Run
`supabase/tests/waitlist-scheduler.sql` and
`marketing/__tests__/waitlist-postgres.sql` with `psql -v ON_ERROR_STOP=1`.
The scheduler test rolls back its pg_net queue insertion before commit, so no
request reaches a hosted project. It uses only a literal local fixture credential.

Run `bun test __tests__`, `bun run typecheck`, and `bun run lint` from `marketing`.
Bundle and serve the actual entrypoint with the Supabase Edge Runtime. Its
credential-free local POST must return 503; fixture handler tests cover authenticated
success, invalid auth, wrong project, removed rows, refusals, and uncertain sends.

## Verification record: October 16, 2026

The lane started from integration `9efdf1473af70f75251f5ff5bbba35b4ad07ae1e`.
Local PostgreSQL 17.6 with Supabase extensions passed the 29 existing waitlist
acceptance checks and the scheduler's Vault, HTTP queue, privilege, and replay
checks. The real local retention schedule succeeded at 18:22:00 UTC and deleted
one expired synthetic signup. Its readback contained zero matching rows.

Supabase Edge Runtime v1.76.2 bundled the actual entrypoint. Its no-configuration
POST returned 503. A fixture transport through the Deno handler exercised the
shared token signer and email renderer and returned one sent reminder; incorrect
authentication returned 401. These are local proofs. Hosted scheduled execution
and real delivery remain the coordinator's release gates.
