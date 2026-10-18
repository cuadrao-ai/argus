# Age confirmation delivery record

This branch adds the approved 18+ checkbox on account signup. It stores one client attestation instant, never a birthday or raw Apple
age range. The shared API field is `age_confirmed_at`. The iOS writer agreed to
that field before implementation.

The PR is held. Iris approved the exact English and Spanish account-creation disclosure. Independent exact-head review,
three passing receipt-gate runs, and root merge authority remain required.
There is no hosted, production, TestFlight, real signup or provider proof here.

## Technical contract

- The checkbox says `I confirm I'm 18 or older.` in English and `Confirmo que tengo 18 años o más.` in Spanish.
- `POST /api/v1/auth/signup` and `POST /api/v1/auth/guest/signup` require a
  timestamp with an explicit timezone. `POST /api/v1/auth/guest` does not accept
  or require it.
- The API rejects non-string, naive, malformed and more-than-five-minutes-future
  values. It normalizes valid offsets to UTC. Account creation sends the checkbox
  instant on that request. The browser does not store it.
- Existing admission, CAPTCHA, email confirmation and guest handoff behavior
  remain.
- Supabase Auth metadata carries the unverified timestamp for interrupted first
  profile creation. Profile creation validates it again. An existing profile is
  never backfilled from editable metadata. Signup initializes a legacy null value
  only from the validated request, with a conditional first write. Authorization
  never reads this field.
- The first stored profile value is immutable. Backend initialization is allowed;
  direct authenticated initialization and future or infinite values are refused.

## New column checklist

| Question | Answer |
| --- | --- |
| Need | Retain the explicit 18+ attestation through account creation and recovery. |
| Grain and history | One nullable instant per profile. Existing profiles stay null until an explicit request attests. No new history table. |
| Constraints | `timestamptz`, backend-only initialization, first value immutable, finite, bounded future skew. |
| Retention | Profile deletion follows existing Auth cascade. The browser does not keep the confirmation. |
| Raw input | No birthday, numeric age or Apple range. Only the checkbox instant. |
| Idempotency | Duplicate profile creation rereads the existing row. Existing metadata does not replace the first value. |
| Query cost | Existing profile primary-key access. No new index or background task. |

## Evidence

- Backend route, gateway, guest conversion, OpenAPI and fingerprint regression
  selection passed 199 tests. No prompt or field-description fingerprint changed.
- The full web unit suite passed all 2699 tests after the approved privacy copy.
- Focused web auth and guest selection passed 145 tests.
- Chromium fixture probes at an earlier head covered a guest browser gate. That gate and its stored confirmation are removed. Signup still requires the checkbox and submits the instant on the account request.
- The guest, signup, and privacy screenshots are not stored in the repository.
- The isolated Next production build passed. It used process-only fixture
  settings and a separate build directory. No environment file changed.
- Local real Postgres tests passed four cases for immutability, direct-client
  refusal, future/infinite refusal and deletion. Migration
  `20261019010000_profile_age_confirmation.sql` applied only to the owned
  `age_confirmation_testdb`.
- That local database was cloned from `business_close_testdb`. It contains the
  shared 145-migration baseline plus that lane's unmerged Business migrations.
  It proves the focused constraints, not a pristine age-branch schema reset.
  Exact-head CI must independently reset the complete candidate migration set.

## Reconciliation and review

Original integration base and latest fetched integration are both
`651870a54be4e5506dbb38f3902fef1a97eef8df`. No integration merge was needed at this
checkpoint. Modularity budgets pass on this same would-be merged tree. The
existing signup method moved to `supabase_signup.py` to keep the gateway within
its budget without raising the limit.

Frozen auth diagnostic PR #1176 remains untouched at
`4a4a3346c01375a7fb822326ef00520559d65ec0`. This branch retains existing handoff
cookie diagnostics and generic auth failure handling. Root must inspect the
combined tree before any promotion with that PR.

Independent Eval and terminal CI are pending. This is a technical WIP checkpoint,
not READY. The owner is `age_web_api`, using the assigned GPT-6.1-sol high model.
No nested helper was started. Model and provider calls were not used.

## Detection and cleanup

The main risk is old clients missing a now-required signup field. A missing
field returns `422` with `age_confirmation_required`. An invalid or unsavable
timestamp returns `422` with `age_confirmation_invalid`.
Existing sessions and login remain available. Rollback reverts the code while
leaving the nullable column in place, then removes the forward migration only
before any shared application. No staging migration was applied.

The local browser server and owned disposable database are retained while the
review checkpoint is open. The root coordinator owns final cleanup.
No other simulator, database, checkout, environment or service was changed.

## Migration timeout correction

The unapplied age migration now begins with `set local lock_timeout = '5s'`
and `set local statement_timeout = '60s'`. No trigger, function, grant or column
behavior changed.

The exact amended migration applied inside one transaction in the owned local
`age_confirmation_testdb`, created from `template0` with minimal Auth and profile
tables. The approved container is `supabase_db_cuadrao-schema-item0-20261017`
on port 59432. The shared `postgres` baseline was inspected only and retained
145 applied migrations. No shared database was cloned, reset or written.

The SQL probe ran after the migration and before commit:

```sql
select current_database(), current_setting('lock_timeout'),
       current_setting('statement_timeout');
-- age_confirmation_testdb | 5s | 1min
```

Assertions verified both values and verified that commit restored both settings
to their original `0` values. The four existing tests in
`tests/test_age_confirmation_postgres.py` passed on Python 3.10.20 against that
fixture. This proves the amended migration and age constraints, not a complete
Supabase reset or hosted readiness. Ownership, modularity and whitespace checks
passed. Only this owned disposable database was dropped after verification.

The earlier browser, web and API evidence is retained because this correction
changes only migration transaction limits. Root owns the independent delta
review and terminal CI follow-up. The receipt gate and merge hold remain.
The correction owner used GPT-6.1-sol low, with no nested helpers.

## Anonymous Auth CI fixture correction

CI run `39100232222` at `bfac2d9e99c3787c43129259b00ce08929bd7250`
reported one failure and 12 passes in the pinned local anonymous Auth matrix.
The same-username concurrency test omitted `age_confirmed_at`, so request
validation refused the first signup before Auth could set its completion event.
One local reproduction using the original fixture payload and the API returned
HTTP 422 with missing `body.age_confirmed_at` and zero signup provider calls.

The positive fixture now includes `2026-01-01T00:00:00Z`, as the other positive
Auth fixtures do. The concurrency assertions and missing-confirmation rejection
tests remain intact. No runtime gate, legal copy or migration changed.

The corrected payload passed schema validation. The focused age, guest Auth,
guest conversion and prompt fingerprint selection passed 65 tests. The full
documented mocked evaluation harness passed 276 tests. Local Python was 3.10.20.
The installed SciPy 1.15.3 arm64 binary failed to load; the mocked run used a
temporary SciPy 1.13.1 wheel with a verified `scipy.linalg` import. Missing lxml
and zxing dependencies were also supplied in the owned temporary test directory.
No shared environment or dependency lockfile changed.

Integration remains `651870a54be4e5506dbb38f3902fef1a97eef8df`, already an
ancestor of the candidate, so no merge was needed. Ownership, modularity and
whitespace checks passed. No local Supabase stack was started. Fresh exact-head
CI must prove the complete real Auth concurrency case, and independent Eval
must review the new final head. The receipt-first review and merge hold remain.
Frozen PR #1176 remains untouched at its recorded head.
