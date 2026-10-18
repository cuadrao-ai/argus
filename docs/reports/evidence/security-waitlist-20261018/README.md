# Partial security follow-up

This lane starts at integration `651870a54be4e5506dbb38f3902fef1a97eef8df`.
The full security request remains blocked. This change fixes items 2 to 4 only.
It does not claim READY, complete extension isolation, or hosted acceptance.

## Blocked pg_net grants

Item 1 requires removing every `net` schema, function, and table privilege from
`PUBLIC`, `anon`, and `authenticated`, with a passing required CI test.
That result is not delivered. The ordinary Supabase `postgres` role cannot
revoke grants owned by `supabase_admin`. Local `REVOKE` attempts emitted
`no privileges could be revoked`, and the effective privileges stayed true.
Ineffective migration statements were removed.

The [Supabase troubleshooting guide](https://supabase.com/docs/guides/troubleshooting/revoking-access-to-pg_net-objects-has-no-effect-0bbc16)
confirms this platform constraint. It also explains that removing the public
table grants without preserving the scheduler role's access breaks pg_net.
No role escalation, extension removal, or platform setting change was attempted.

The strict [acceptance probe](../../../../supabase/tests/net-client-grants.sql)
still fails against the unmodified extension grants. It is a blocked acceptance
probe, not a passing CI exception. Run it only against a disposable database:

```sh
psql "$ARGUS_DISPOSABLE_DATABASE_URL" -f supabase/tests/net-client-grants.sql
```

The [observed failure](net-client-grants-blocked.txt) contains only catalog
privileges. The decisive output is `ERROR: BLOCKED: net still grants client or
PUBLIC privileges`. A platform-supported resolution and a passing required CI
grant test remain open. Staging API schema exposure was not checked in this lane.

## Implemented behavior

The forward migration revokes client execution of `public.rls_auto_enable()`.
Its original function definition, owner, trigger identity, and automatic RLS
behavior remain verified. Historical migration files are unchanged.

The scheduler reads only Vault's `cuadrao_waitlist_scheduler_key` and sends it in
`X-Cuadrao-Waitlist-Scheduler-Key`. The Edge handler compares fixed-length SHA-256
digests with `timingSafeEqual`. It refuses Authorization bearer credentials and
refuses a scheduler secret equal to the database credential. The database
service-role credential is used only for database requests.

Confirmation and leave GETs display buttons using existing approved Spanish
copy. GET does not read or change signup state or send mail. Explicit POST
performs the action. RFC 8058 one-click POST and existing unsubscribe headers
remain supported. Browser leave POST renders the existing removal result.

## Local verification

The root coordinator approved provider-free tests with explicit fixtures despite
missing unused application environment files. No environment files were written.
Python used the pinned 3.10.20 runtime. The SQL fixture used a schema-only copy
in the owned `security_hardening_testdb_v2` database on the root's local container.
No shared database was reset. No queue insertion was committed.

- Client grant, RLS, and scheduler PostgreSQL tests passed, 46 tests.
- Marketing unit tests passed, 214 tests. Four existing database tests require
  their separate disposable-database configuration and were skipped.
- Marketing typecheck, lint, and production build passed.
- The existing real-handler browser flow passed on desktop and mobile, two tests.
  The actual production Next server used local Supabase and Resend fixtures.
  Scanner GETs preserved confirmation, signup, and email state. Button clicks
  issued POST requests. Removal cleared the fixture row. Repeated one-click POST
  preserved the absent state.
- Branch ownership and modularity checks passed. No watched file exceeded its
  budget.

Browser screenshots remain outside git, as requested by the coordinator, under
`/private/tmp/security-waitlist-browser-evidence`. They are local fixture proof.
They do not prove hosted scheduled execution, real email, or customer readiness.

## Operator setup remains held

The coordinator must obtain Lucas's concrete authorization before these actions:

1. Generate a new scheduler-only random secret with at least 32 bytes of entropy.
2. Privately set Edge `CUADRAO_WAITLIST_SCHEDULER_KEY` and Vault
   `cuadrao_waitlist_scheduler_key` to that same new secret.
3. Rotate the staging `SUPABASE_SERVICE_ROLE_KEY` previously queued through
   pg_net, update its approved consumers, and remove obsolete Vault
   `cuadrao_waitlist_service_role_key`.
4. Apply the approved forward migration and deploy the Edge function with its
   handler-owned authentication setting. Verify actual scheduled outcomes.

No secret was generated, printed, committed, rotated, or set by this lane.
Independent exact-head Eval and user-relayed Rafael retest remain required.
The receipt gates and platform blocker keep the full lane on hold.
