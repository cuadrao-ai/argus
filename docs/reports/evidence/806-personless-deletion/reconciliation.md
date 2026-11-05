# PR 847 integration reconciliation, October 5, 2026

Original integration base is `875de09ac2115acec42e09060b92878aa5f18eff`.
The published branch entered this pass at `9cf4d9f9b3b45de257b68b5a49269703f7c995f0`.
Fetched integration is `7018e0edebbc370b999005a857230bf3c3a1ad8b`.
Normal reconciliation merge is `2651caecd9542b9cc30ecce85c4b11c09f7362c4`.
No rebase, reset or stash occurred.

## Overlap and retained evidence

PR 858 changes Apple identity capture, credential storage and related API and
data contracts. PR 846 adds credential reseal and operator recovery tests.
Neither changes the analytics adapter or its deletion-service call. Both share
the broader account deletion lifecycle and durable credential boundary, so this
pass reruns the affected local PostgreSQL tests alongside the analytics tests.
PR 857 changes native provider button appearance and has no analytics, migration,
environment or deletion state overlap. Its native evidence is retained.

The normal merge retained all source and documentation changes from PR 858.
The API and data model additions in this pass describe the existing personless
adapter and its evidence fields. They add no retention or activation policy.
No runtime or test source changed after the merge.

The stable patch ID for this lane's runtime, tests and `.env.example` is
`b3cc5292221ea46694679c5a7c4095739447953a` before and after reconciliation.
It was computed with `git diff <integration> <head> --
src/argus/observability src/argus/domain/account_deletion/service.py
tests/test_analytics_deletion_adapter.py tests/test_analytics_deletion_postgres.py
.env.example | git patch-id --stable`.
The prior 49-test evidence remains valid for that unchanged patch. The checks
below cover the reconciled tree and the shared lifecycle overlap.

## Local verification

All commands use `/private/tmp/cuadrao-scipy-env-20261005/bin/python`,
`PYTHONPATH=web:src:.`, a stripped environment and `--override-ini addopts=''`.
Database tests use only the coordinator-assigned disposable local database.
HTTP boundaries use synthetic transport responses. No provider, hosted, paid,
physical-device or real user-data action ran.

- HTTP and contract selection passed 122 tests with zero skips or failures in 2.41s.
  Files were `test_analytics_deletion_adapter.py`, `test_apple_identity.py`,
  `test_apple_sign_in_api.py`, `test_apple_sign_in_client.py` and
  `test_force_account_deletion_step.py`, all under `tests/`.
- The ten-file mocked command in `tests/evals/README.md` passed 272 tests with
  zero skips or failures in 8.90s.
- The initial sandboxed PostgreSQL attempt could not open loopback networking.
  It ended with one setup error before assertions. The retry used authorized
  local-network access. This was an execution-permission error, not a product finding.
- PostgreSQL selection passed 54 tests with zero skips or failures in 34.56s.
  The 19 warnings were existing psycopg pool default-open deprecations.
  Files were `test_analytics_deletion_postgres.py`,
  `test_account_deletion_third_parties_postgres.py`, `test_account_deletion_postgres.py`,
  `test_account_deletion_reseal_postgres.py`, `test_apple_identity_postgres.py` and
  `test_apple_sign_in_credentials_postgres.py`, all under `tests/`.
  Pytest completed all scoped fixture teardowns and exited zero. The local database
  slot was released without broad cleanup, reset or shared row counting.
- Focused Ruff checks and `git diff --check` passed.
- `scripts/check_modularity_budget.py` passed on the reconciled tree with no violations.

The adapter remains default-off. Accepted requests remain pending until an
independent matching completion response arrives. Provider acceptance and
activation remain open. This document is reconciliation evidence, not a terminal
review audit. Independent final review, exact-head CI and the merge queue remain
with the root coordinator.
