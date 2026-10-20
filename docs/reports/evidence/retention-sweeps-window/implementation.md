# Sweep evidence retention follow-up

The cleanup coordinator assigned this Iris-approved add-on to one writer, `/root/retention_sweeps_24_months`. The registry owner remains the cleanup coordinator. Parent PR #1218 and its exact `edca285357242e659d987d19d1f6d45aa889baa0` head remain unchanged. This branch starts at that head and targets `codex/cleanup-m1-retention-registry`. The fetched integration reference remains `651870a54be4e5506dbb38f3902fef1a97eef8df`. Root must land #1218 first, then retarget and reconcile this follow-up. No merge is authorized here.

## Policy and limits

The forward migration seeds `argus_private.retention_sweeps` in the existing registry. Retention is 24 calendar months after `finished_at`. Completion is the engineering anchor because the table records terminal attempts. A future separately approved executor may remove rows when `finished_at + interval '24 months' <= cutoff`. Calendar months preserve the stated window rather than assuming 730 days. February 29, 2024 at noon UTC reaches that threshold on February 28, 2026 at noon UTC.

The seed describes future policy. It adds no writer, scheduler, delete grant, or purge executor. The existing service role still cannot delete evidence. A future purge needs separate authority and design. Replay converges to the approved seed through its primary key. It does not change the four existing policy rows.

The table comment replaces the undecided window. The writer contract permits attempt IDs, affected-row counts, timestamps, outcome, table identifiers, and repository rule/source snapshots. It prohibits PII, user identifiers, customer input, raw errors, and payloads. These are operational records, not literal UUID/count-only rows. The existing `rule` and `basis` text columns remain. PostgreSQL does not detect sensitive prose in those fields. A literal IDs/counts-only shape would require a separate structural decision about these columns and timestamps/outcome/table identity. This change does not claim or add content enforcement.

## Verification

On October 17, 2026 local time, the worker created only `retention_sweeps_window_test` on the root-owned local PostgreSQL server at port 59432. It applied the exact parent migration after a private-schema prerequisite, then the new migration in a transaction. The original four policy rows remained byte-for-byte equal, the fifth seed appeared, and the sweep log stayed empty. This is focused actual PostgreSQL proof, not a full 145-migration rebuild or hosted apply.

The explicit synthetic connection used no environment file. Topology check reported missing root and web environment files. No setup, shared environment repair, service launch, or provider call was needed for this bounded SQL-only check.

Run the focused checks with the repository's disposable-database fixture:

```sh
ARGUS_DISPOSABLE_DATABASE_URL=<disposable-test-database> python -m pytest tests/test_m1_retention_registry_postgres.py -q --no-cov
```

Both tests passed with zero skips. The SQL contract checks five-policy membership, an empty log, RLS, denied client privileges, service-role insert/read, append-only grants, stable IDs, historical snapshots, and invalid row rejection. The replay test applies the forward migration twice, verifies unchanged policies and synthetic evidence, checks the policy text/source, and exercises the leap-date calendar calculation. Synthetic rows contain only fabricated attempt metadata and repository policy snapshots. Both tests roll their writes back. They do not test or claim free-form content rejection.

The migration uses a 5-second lock timeout and a 60-second statement timeout. No columns, constraints, grants, existing migrations, product tables, or waitlist forms change. The branch ownership entry lists exactly the five owned files. Runtime and UI regressions are outside this metadata-only delta.

## Tradeoff and detection

The single registry row owns the descriptive window. No application copy or second deletion engine is added. Operators can detect missing or changed metadata through the exact seed and replay checks. The tradeoff is that this policy alone cannot expire data. A future executor must prove calendar-cutoff handling, permissions, and payload-free evidence before any purge can run.

Model the Domain kept the change as one registry row. Prove It Works required direct PostgreSQL apply, replay, role, and stored-data checks. Independent Eval and full CI belong to the root's fresh-head gate. Receipt-3 remains held. This follow-up does not reopen that gate.

Rollback uses a separately reviewed forward metadata correction. Do not drop the evidence table or run a purge as rollback. The worker drops only its named synthetic test database after the checks and preserves this worktree and evidence. Root owns the shared server lifecycle. Hosted, production, paid calls, and release actions remain outside this assignment.
