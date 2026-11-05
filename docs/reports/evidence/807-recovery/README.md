# Deletion recovery proof

Measured October 5, 2026 against integration base
`875de09ac2115acec42e09060b92878aa5f18eff`.

Current PostgreSQL writers already update the sealing fingerprint with the
ciphertext. This slice adds proof without changing runtime behavior.

## Local verification

The provider-free baseline passed 27 tests with no failures or skips.
The final suite passed 48 tests with no failures or skips, including 28 tests
on real disposable PostgreSQL and 20 unit or command tests. The 25 warnings
are existing ConnectionPool default-open deprecations.

The process used `env -i`, this worktree's `src` on `PYTHONPATH`, and only
`ARGUS_DISPOSABLE_DATABASE_URL` for the isolated database on port 60332.
No root `.env`, provider credentials, hosted records, model calls, simulator
or phone were used. Every new fixture owns synthetic UUID rows and removes
them. Three initial synthetic Apple fixtures were removed after correcting
cleanup for the restrictive foreign key. Initial fixture mistakes were an
invalid connection status and missing Apple-row cleanup, not runtime defects.

Run with the repository Python environment and `--no-cov -q`:

```text
python -m pytest tests/ingestion/test_secrets.py \
  tests/test_force_account_deletion_step.py \
  tests/test_resume_account_deletions.py \
  tests/test_account_deletion_key_fingerprint_postgres.py \
  tests/test_account_deletion_reseal_postgres.py \
  tests/test_account_deletion_third_parties_postgres.py --no-cov -q
```

The new tests exercise K1-to-K2 writes through `set_secret`, Apple `upsert`
and Apple recapture. They check decryptability and persisted fingerprints,
including a legacy writer supplying no fingerprint. The real PostgreSQL
force-step tests compare the entire run row before and after an early refusal
or an eligible dry run, retain the Auth row, and assert no provider dispatch.
Refused script coordinates never construct a deletion service.

Temporary mutations demonstrate the assertions detect the requested defects.
Plain SHA-256 produced one failed test. A stale connection fingerprint produced
four failed tests. A stale Apple fingerprint produced two failed tests. All
mutated production files were restored. Ruff, diff checks and the modularity
budget pass. Comment review removed one new test module docstring.
Independent final code review and exact-head CI belong to the release captain.

## Operational boundaries

The runbook now includes rollback processes in the prohibition on rotating
keys while old writers can run. Preserve old-key access for outstanding
credentials. Rotation does not revoke those credentials or complete deletion.

No cron, operator assignment or live alert destination was added. #807 remains
open for its full scope. An operator duty owner and escalation delivery still
need approval. Read-only hosted worker-concurrency verification and provider
configuration remain external gates. #805 and #806 still block deletion
activation. Physical Apple authorization/revocation, phone journeys and hosted
acceptance remain unverified. Nothing was enabled or deleted on a hosted
service.

Sequence Work into Verifiable Units limited this PR to recovery proof and one
runbook correction. Test Behavior, Not Implementation required persisted-row
and absent-dispatch assertions. Model the Domain retained the existing
credential repositories and deletion command as their authoritative owners.
