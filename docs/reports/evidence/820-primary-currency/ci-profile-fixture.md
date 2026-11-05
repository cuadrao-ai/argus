# CI profile fixture repair

The real profile test failed before reaching the profile update. CI exports
`ARGUS_DISPOSABLE_DATABASE_URL`, while `api_state.DATABASE_URL` captures
`DATABASE_URL` at import. The test bound only the Supabase gateway. Its temporary
construction environment did not configure the separate session verifier.

The fix binds `api_state.DATABASE_URL` to the same disposable database for the
test scope. Authentication, session revocation checks, PostgREST writes,
concurrent preference preservation, invalid input refusal, and unauthenticated
refusal still run through their existing owners. No assertion, skip condition,
grant, production source, or native source changed.

## Reproduction and verification

All checks used the isolated local stack with synthetic identities, empty
provider credentials, and the locked healthy Python 3.11.15 environment on macOS
arm64. Production `DATABASE_URL` was explicitly empty before imports, matching
CI's absence of that setting. Local credentials were supplied only through
`ARGUS_LOCAL_SUPABASE_*` and `ARGUS_DISPOSABLE_DATABASE_URL`. No shared database
reset or migration was performed.

| Check | Result |
| --- | --- |
| Existing currency test on frozen `ed90df58bdd510cefcd559c676464d73cf037100` | 1 failed, 0 skipped in 2.21s. First PATCH returned `503`, expected `200`. |
| Same test and environment with the scoped binding | 1 passed, 0 skipped in 2.94s. A temporary diagnostic confirmed all session checks received a database URL. |
| Required mocked eval selection from `tests/evals/README.md` | 272 passed, 0 skipped in 13.05s. |
| Original full `tests/test_*_postgres.py` selection | 625 passed, 3 failed, 0 skipped, 49 warnings in 332.00s. The currency case passed. |
| New integration recovery file plus secrets and force-step tests | 26 passed, 0 skipped in 0.54s, including all 9 newly added PostgreSQL cases. |
| Three failing full-run cases on unchanged integration `26c0692d634953bd542a6cca6504138e6e420e6c` | 2 failed, 1 passed, 0 skipped in 9.39s. |
| Merged-tree modularity, fixture Ruff lint and format, diff whitespace | Passed. |

The two search failures reproduce unchanged on integration. SQL/Python parity
reported `537` text mismatches and `40` symbol mismatches, both against expected
zero. This local runtime uses Unicode 14.0.0; the SQL normalization data is
pinned to Python 3.10 semantics. [Issue #859](https://github.com/lagarcess/argus/issues/859)
assigns the runtime follow-up to Shared Foundations and links #852 and #832.

The household global-count case observed an increase of two when it expected
one, then passed alone on unchanged integration. Other workers used the same
disposable database. Concurrent interference is an inference because the writer
was not traced. This is not classified as a pre-existing runtime defect.
The 49 warnings concern the existing `ConnectionPool` default `open` parameter.
The full local matrix is not green. Serial Linux/Python 3.10 CI owns final
acceptance; neither failure was excluded or weakened.

## Reconciliation and review boundary

Original integration base is `875de09ac2115acec42e09060b92878aa5f18eff`.
Current integration is `26c0692d634953bd542a6cca6504138e6e420e6c`.
The one-way reconciliation merge is `869931e28b221c62593c261edc607badb2a884e9`.
That integration delta adds recovery tests and documentation, with no profile,
auth runtime, API/data contract, migration, environment setting, or native change.
The 628-case process had already collected before reconciliation; its files
were unchanged, and the nine newly added PostgreSQL cases passed separately.

The existing native evidence is retained because its implementation and
contracts are unchanged. This report records local evidence, not a READY verdict
or terminal audit. The release coordinator owns fresh review of the fixture
delta, final PR head verification, and terminal CI. Comment review found no
comments or suppressions in the three-line code delta and no open findings.
