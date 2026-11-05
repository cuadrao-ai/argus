# Primary currency integration reconciliation

This reconciliation adds no paired-transfer behavior. Original integration base
is `875de09ac2115acec42e09060b92878aa5f18eff`. The previous reviewed head is
`95c01e8c08d8315f5cb2e5439c70e0b467d223e8`, based on
`7018e0edebbc370b999005a857230bf3c3a1ad8b`. Freshly fetched integration is
`2b2d0d9e8ed311c11b7585fbd757fb37f915e12f`. The normal merge completed without
conflicts at `dd2448575e3d9e5db2a931263f028d892937f852`. That merge is the
measured executable head. The subsequent evidence commit changes only this folder.

GitHub inspection and cancellation readback confirmed an open PR targeting
`codex/private-alpha-next` with no auto-merge request or queue entry before the
merge. GitHub CLI is the existing forge. Root owns final review, exact-head CI,
guarded merge and integration landing.

## Semantic overlap

Integration adds the primary-currency setter and profile decoding to the existing
native session and Profile owners. Server profile mutation now writes only
explicitly supplied preference fields, then reads the authoritative profile.
It preserves another preference edited concurrently. The incoming canary change
closes synthetic HTTP response sockets before clients can reuse them.

The shared `SupabaseGateway.update_user` method changes for profile updates.
Paired recording, Planning and Household modules do not call this method.
Their executable trees and fixtures are byte-identical to the previous head.
Primary currency remains a user preference. Transfer legs still own their
explicit currencies and amounts, and Household denomination predicates still
use the activity currency. No exchange rate, guessed amount, forgiveness or
settlement event is introduced.

`docs/api/openapi.yaml`, `.env.example`, `.github/argus-env.sh`,
`.github/private-alpha-release-profile.json` and `render.yaml` are byte-identical
to the previous reviewed head. There is no incoming migration. The paired flag
remains default off. Shared profile and session edits require native acceptance
for their own PR; this worker did not use the Mac or simulator slot.

PR #865 separately changes web environment membership derivation in
`.github/argus-env.sh` and `.github/private-alpha-release-profile.json`.
This PR owns API membership derivation in those same files. They share a
configuration owner even if Git can merge them without conflicts. Root must
serialize those landings and rerun configuration checks after their combination.

## Current checks

Each test command used an empty inherited environment, explicit blank provider
keys, synthetic market data, `PYTHONPATH=web:src:.`, Python 3.11.15 and Bun 1.3.14.
No root environment file, database DSN or hosted credential was used.

- [Boundary checks](reconcile-primary-boundaries.txt) pass 320 tests with three
  expected no-database skips and one existing Starlette cookie warning.
  The modules cover environment scripts, release profile, Blueprint membership,
  Apple identity, client and API, OpenAPI compatibility, home-country profile
  updates and mocked Supabase API behavior.
- [Mocked and pure transfer checks](reconcile-primary-mocked.txt) pass 305 tests
  with 26 expected no-database skips. All 272 canonical mocked eval tests execute;
  the transfer module contributes 33 pure passing tests.
- [Canary checks](reconcile-primary-canary.txt) pass all 23 tests with zero skips.
  They use synthetic transient loopback servers and the unchanged locked web
  dependencies. No real authentication provider or database is contacted.
- [Combined-tree modularity](reconcile-primary-modularity.txt) has zero budget
  violations. `bash -n .github/argus-env.sh` and `git diff --check` pass.

The first expanded command records 332 passes, three skips and 11
[sandbox socket-bind failures](reconcile-primary-sandbox.txt). The permission
rerun records 12 passes and 11 [missing dependency failures](reconcile-primary-dependencies.txt).
Both fail before a meaningful canary assertion. Installing the unchanged
`web/bun.lock` dependencies with `bun install --frozen-lockfile --ignore-scripts`
and permitting transient loopback binds yields the 23-test passing run above.
No source or lock file changed to resolve either environment limitation.

Commands use `python -m pytest --no-cov -q --tb=short`, with module names recorded
in each log. The mocked command follows `tests/evals/README.md`. Modularity uses
`python scripts/check_modularity_budget.py`. The current boundary command does
not include the Supabase-dependent profile currency test and does not claim its
execution.

## Retained proof and remaining gates

The previous 232-test affected PostgreSQL suite with zero skips and its 57 pool
warnings, plus the explicit three-case PostgreSQL run with zero skips, remain
applicable to paired financial behavior because the financial owner trees,
fixtures and runtime configuration are unchanged. Exact-head CI and independent
context review remain required. Current skips do not replace real database proof.

Native paired-entry acceptance, hosted activation and any unresolved financial
contracts remain open. The worker started no persistent service, database or
simulator. Temporary canary servers exited with their test contexts. Locked web
dependencies remain isolated in this recoverable worker checkout. Branch writes
stop after the evidence commit and push.

## Subsequent observer-test landing

PR #868 landed into integration as
`fc4057c8789d3e3504fcb0e980344d6bf51e66c0`, with parent
`2b2d0d9e8ed311c11b7585fbd757fb37f915e12f`. The previous published worker head
was `c986d060deb7bd7ce50ec13093e175371164c7d0`. A fresh fetch and normal merge
completed without conflicts at `8cd9a3a8c484171919da9b9b642b34282405a5ba`.
Pending-merge inspection and cancellation readback again confirmed no auto-merge
or queue request.

The incoming executable diff changes only `tests/test_apple_identity_postgres.py`.
Its observer uses autocommit so each activity-statistics poll can see a fresh
snapshot, and an event deliberately orders the first poll before the capture
attempt. Parent locking, the five-second deadline and denied-credential assertions
remain. All production source, financial fixtures, OpenAPI and release
configuration are byte-identical to the previous worker head. The proof and
PR #865 shared configuration ownership warning above therefore remain valid.

The [focused run](reconcile-observer-focused.txt) passes 44 tests with 38 explicit
no-database skips. The passing tests are 11 pure Apple identity checks and 33 pure
paired-transfer checks. Twelve Apple identity PostgreSQL cases and 26 paired
PostgreSQL cases skip. This run does not claim execution of the changed observer
or substitute for the root's real PostgreSQL acceptance and exact-head CI.
The [combined-tree budget](reconcile-observer-budget.txt) has zero violations.
Whitespace checks pass. Unchanged boundary, mocked, canary and financial proof
above are retained without repeating their runs.

No database lease, simulator, Mac setting, provider or hosted service was used.
This evidence commit is the only post-merge change. Root owns independent final
context review and CI. Worker branch writes stop after publication.
