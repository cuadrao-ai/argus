# PR 847 reconciliation with Apple admission, October 5, 2026

Original integration base is `875de09ac2115acec42e09060b92878aa5f18eff`.
The previous reconciled integration base is `7018e0edebbc370b999005a857230bf3c3a1ad8b`.
The published branch entered this pass at `0334808e08e41baa0305fe28a8c167dbb89ebbbc`.
Fetched current integration is `5861a8f1b11cfa053e99e2280ddfcfa264abfd66`.
Normal merge is `376b1c92008cc9160e9957f30a8d970c0faa10ec`.
The verified behavioral source, including two combined-state cases, is
`c07a4051e86fb523112de027f57a19434cc6d228`.
No rebase, reset, clean or stash occurred. A second fetch before publication
confirmed the same integration SHA.

## Semantic overlap and disposition

PR 862, landed as `7c2522fb7`, changed the shared account-deletion service.
It owns new-run admission, parent/identity/credential locking, recovery under
an exact live claim, truthful pending/503/Retry-After responses and atomic
Apple credential removal with its completion receipt. These changes overlap
with this adapter at the deletion lifecycle and run-step store. The clean
service merge preserved all of those changes. The only textual conflict was
between adjacent analytics and Apple-recovery paragraphs in `API_CONTRACT.md`.
Both contracts were retained. `DATA_MODEL.md` merged cleanly; OpenAPI and
response shapes remain exactly as landed by PR 862. No new migration,
permission, financial rule, environment activation or UI state owner was added.

This pass found no combined runtime failure. No production runtime fix was
needed. Two parametrized real-PostgreSQL cases now exercise the combined path:

- Linked Apple identity without its credential rejects admission before any
  analytics request, account ban, deletion run, placeholder or provider revoke.
- After valid capture, Apple revocation commits its receipt while analytics
  stays pending and auth stays locked and present.
- A duplicate live claim cannot submit another analytics request or repeat Apple
  revocation. A lost POST response retries the exact durable submission payload.
- Relaunch polls the saved request. Only a separate GET with matching request
  and submission UUIDs and completed status permits auth deletion. The Apple
  receipt survives and Apple is not revoked twice.

The PostHog adapter, HTTP tests and `.env.example` have the same stable patch ID
`7b10c41ced2e898b1449268293c873cb62c6d1f1` against both the previous and current
integration bases. Compute it with `git diff <integration> <head> --
src/argus/observability/analytics_deletion.py
src/argus/observability/posthog_deletion.py .env.example
tests/test_analytics_deletion_adapter.py | git patch-id --stable`.
Prior provider-contract evidence and review comment
[6001886300](https://github.com/lagarcess/argus/pull/847#issuecomment-6001886300)
remain applicable to the unchanged adapter. Their earlier lifecycle evidence
does not establish this new combination; the affected checks below replace
that acceptance claim for the current context. Native appearance and unrelated
currency/API-privacy changes have no analytics or deletion-state effect.

## Verification

All tests used a stripped environment with `APP_ENV=test`,
`PYTHONPATH=web:src:.`, `/private/tmp/cuadrao-scipy-env-20261005/bin/python`
and `--override-ini addopts=''`. PostgreSQL used only the root-assigned synthetic
local database at port 60332 with authorized loopback access from the first
invocation. Fixtures clean only their generated UUIDs; the root stack was not
stopped, reset or truncated. No root `.env` or real provider credential was loaded.

Final results, recorded in [reconciliation-862-verification.txt](reconciliation-862-verification.txt):

- HTTP/contract: 155 passed, zero failed/skipped/warnings, 2.21 seconds.
  Files: `test_analytics_deletion_adapter.py`, `test_apple_identity.py`,
  `test_apple_sign_in_api.py`, `test_apple_sign_in_client.py`,
  `test_force_account_deletion_step.py`, `test_account_deletion_api.py`.
- PostgreSQL: 89 passed, zero failed/skipped, 54 existing psycopg pool
  default-open deprecation warnings, 52.18 seconds. Files:
  `test_analytics_deletion_postgres.py`, `test_account_deletion_third_parties_postgres.py`,
  `test_account_deletion_postgres.py`, `test_account_deletion_reseal_postgres.py`,
  `test_apple_identity_postgres.py`, `test_apple_sign_in_credentials_postgres.py`,
  `test_account_deletion_apple_admission_postgres.py`, `test_account_deletion_api_postgres.py`.
- The ten-file Mocked Run from `tests/evals/README.md`: 272 passed,
  zero failed/skipped/warnings, 9.26 seconds.
- Focused Ruff, diff whitespace and combined-tree modularity passed.

Initial merged-tree PostgreSQL checks passed 87 tests with 52 warnings before
adding the two combined cases. The focused four-case analytics PostgreSQL check
then passed with four warnings. The final eight-file run above covers the
complete final behavior. No failing product assertion occurred in this pass.
The final evidence-only commit does not alter that verified source tree.

Both deletion flags remain false in `.env.example`. No actual provider call,
customer data, hosted mutation, paid call, device check, scheduled sweep or
notification ran. Actual PostHog event completion/readback, project parity,
credential scopes, alpha availability, request approval and activation remain
external gates under #806/#805/#800. Accepted requests and zero persons never
prove deletion. Failed, pending and operator-needed outcomes remain durable.

This is reconciliation evidence, not a terminal review audit. Independent final
review, exact-head CI and the sole integration merge queue belong to the root.
