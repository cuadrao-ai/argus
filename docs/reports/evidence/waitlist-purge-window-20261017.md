# Waitlist purge window

M3 is a local implementation from integration `651870a54be4e5506dbb38f3902fef1a97eef8df`.
The assigned forward migration is `20261018050000_waitlist_purge_window.sql`.
No staging migration, hosted purge, email, provider call or app environment write ran.
The form and `/api/waitlist` routes have no changes.

## Data model review

The existing table remains the only waitlist. Its grain is one normalized email.
`created_at` is the canonical signup time. `confirmed_at` records email confirmation,
not a launch invitation. `notified_at` is a legacy reservation made before sending.
A refusal or uncertain provider outcome can leave that reservation present.
Consequently, retention never treats `notified_at` as proof that an invitation went out.

The new migration adds no table, column, segment, purge timestamp, index or suppression
record. It replaces the existing bounded purge function and adds one completion RPC.
The existing RLS, service-role table privileges, seven-day unconfirmed expiry and
whole-row leave remain in force. Legacy rows without a personal privacy version
retain their current behavior.

The purge reads the PostgreSQL setting `cuadrao.waitlist_retention_months`.
Missing or empty means 12 calendar months. Integers 1 through 120 are accepted.
Invalid values fail before deletion. This is database configuration, not a secret or
an app environment variable. A later authorized operator can persist it with
`ALTER DATABASE <database> SET cuadrao.waitlist_retention_months = '12'`.
New sessions, including the scheduler connection, read the database default.
An override for one session or transaction affects only that session or transaction.
No setting was persisted during this work.

The existing cron wrapper and application caller continue calling
`public.cuadrao_waitlist_purge(100)`. Each call deletes at most 100 eligible personal
rows, including the digest and answers. It uses the existing skip-locked selection.
Age is measured from signup, even when confirmation happened later.

## Invite completion and its limit

`public.cuadrao_waitlist_invited(p_verification_id text)` is service-role only.
The caller must first establish that the provider accepted the real launch invite.
The function deletes the entire matching confirmed personal signup and returns 1,
or returns 0 when it is absent or ineligible. Repeated calls are harmless.
An old verification ID cannot erase a later signup for the same email.
Unconfirmed and legacy rows are ineligible. Confirmation, welcome and reminder
emails never call this hook.

The personal launch-invite sender does not exist in the current app. The legacy
operator notice sender explicitly excludes current personal-consent rows. This PR
does not add or extend a sender. The hook is **not wired**. Automatic invite-triggered
deletion remains pending the future invite caller and its provider-acceptance proof.
This PR does not establish that end-to-end capability.

Whole-row deletion intentionally leaves no receipt or suppression digest in this
table. A future sender must keep its provider idempotency key stable, preserve an
uncertain send outcome until it can verify acceptance, and call completion with
the original immutable verification ID. It must handle leave and expiry between
selection and send. Database deletion cannot cancel a message already accepted by
an external provider.

## Local verification

Only `cleanup_m3_waitlist` on the coordinator-owned PostgreSQL at local port 59432
was changed. It contains the two existing waitlist migrations and the new migration.
It does not clone or reset the coordinator's baseline database. The new tests use
transactions with rollback; the concurrency case cleans its committed fixture.

- Before the migration, the new PostgreSQL suite reported 14 failed and 5 passed.
  Failures established the missing configuration behavior and completion hook.
- `tests/test_waitlist_purge_window_postgres.py` and
  `tests/test_cuadrao_early_access_postgres.py` passed all 39 tests after migration.
  Coverage includes calendar-month windows, seven-day boundaries, invalid settings,
  whole-row leave, stale invite completion after a fresh signup, legacy preservation,
  service-role permissions, the 100-row cap and concurrent skip-locked behavior.
- `marketing/__tests__/waitlist-postgres.sql` passed its 29 existing checks.
- The waitlist store, service, operator notice and scheduler Bun suites passed
  all 45 tests. They used mocked transports. No email was sent.

These checks prove local SQL behavior and preserve the existing caller contracts.
Hosted scheduler readback and an actual invite sender remain separate work.

## Rollback

Before application, hold the migration and leave integration unchanged. After a
later authorized application, restore the prior purge body through a new forward
migration and revoke or remove the unused completion hook if needed. Returning the
setting to 12 restores the default retention window. Deleted rows cannot be
recovered by a code rollback, so staging activation remains a coordinator action.

## Batch-limit correction after independent Eval

The earlier passing local cap checks did not establish the cap across PostgreSQL
plans. Independent Eval on `927a3bdba2de4db040c53028808ed10aa2229137`
observed 160 deletions for a requested batch of 80. Required CI run
`39091376245` independently observed 101 deletions for a cap of 100.
[Independent Eval](https://github.com/lagarcess/argus/pull/1219#issuecomment-6244965569)
records the failing observations and their limits.

The integration function has the same limited locking `IN` subquery shape.
New local probes of both the exact base body and the unchanged candidate returned
80 for 160 eligible rows with a requested batch of 80. Default, nested-loop,
non-materializing, analyzed and stale-eligibility-statistics probes did not
reproduce the over-deletion locally. The eight new boundary and worker cases also
passed before this correction. No fresh local failing-before result is claimed,
and this evidence does not establish that M3 introduced the defect.

The unapplied M3 migration now materializes one bounded set of locked candidate
keys before deleting through that set. Eligibility, calendar-month configuration,
whole-row deletion, the 100-row cap and `SKIP LOCKED` stay unchanged. No previously
applied migration was edited.

The new regression cases check requested batches of 1 and 80 and the hard cap of
100 against 160 eligible rows. Each runs with the normal planner and with hash
and merge joins disabled. A two-worker case keeps both transactions open, verifies
80 deletions per worker, and verifies a third call cannot take their locked rows.
The existing single-row lock check remains.

Corrected verification used only `fix_m3_db` at local port 59432, built from the two
existing waitlist migrations and the new M3 migration. Python 3.10.20 ran with an
empty environment apart from the local database URL, source path and synthetic
provider mode. The two waitlist PostgreSQL modules passed all 46 tests, with no
skips. The unchanged SQL acceptance script passed all 29 checks. Ruff and
`git diff --check` passed. Integration was fetched again and remained
`651870a54be4e5506dbb38f3902fef1a97eef8df`, so no reconciliation merge was needed.
These local proofs require fresh exact-head CI and an independent delta Eval.
