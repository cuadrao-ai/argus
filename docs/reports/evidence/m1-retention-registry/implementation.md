# M1 retention registry evidence

The cleanup coordinator assigned one new additive migration, its tests and this report. The source inputs are the founder-provided `staging-data-model-audit.md` and `supabase-squaring-plan.md`. Their M1 proposal supplies a private rule inventory and a sweep log. The current instruction limits this work to recording existing rules.

The fetched integration base is `651870a54be4e5506dbb38f3902fef1a97eef8df`. The worker branch is `codex/cleanup-m1-retention-registry`. Only this worker writes its separate worktree.

## Shape and ownership

`retention_policies` has one row per schema-qualified table. Its text rule and basis identify the existing executor and repository owner. The runtime purge functions remain authoritative. No executor reads this metadata. Updating metadata cannot change deletion behavior.

`retention_sweeps` records one terminal attempt for one table. A caller supplies a stable UUID when recording a retry. Rule and basis snapshots preserve what the attempt used when a later migration changes the registry. The service role may insert and read evidence, but cannot update, delete or truncate it. Failed attempts may have an unknown affected-row count. Dry runs must report zero actual affected rows. There is no scheduler or automatic log writer in this change.

The four seeds describe existing guest-workspace cleanup, visitor-counter expiry, guest-funnel expiry and the current Personal waitlist purge. The waitlist seed uses the currently landed SQL, which already has seven-day and twelve-month rules. Pending M3 may change that rule through its own approved slice. Receipt and account-deletion retention remain undecided and have no seed.

## Verification

On 2026-10-17, the existing item0 local PostgreSQL server was handed off for a separate `m1_testdb`. The baseline database remained unchanged. This worker created only that database and the private-schema prerequisite there. The new migration applied in one transaction with `ON_ERROR_STOP`. All statements succeeded and exactly four policy rows were inserted.

`tests/sql/m1_retention_registry.sql` then passed against that database. Its output ended in `ROLLBACK`. It checks exact seed membership, an empty sweep log, enabled RLS without client policies, client privilege denial, service-role inserts, service-role evidence mutation denial, duplicate run identity rejection, preserved historical snapshots and invalid row rejection. Invalid cases cover unknown policy, reversed time, unfinished outcome, negative or missing count, dry-run effects and blank metadata. All synthetic writes roll back.

This proves the new SQL and constraints on PostgreSQL. It is not a full migration-chain rebuild, hosted apply, scheduled sweep, or customer-readiness result. The pytest wrapper runs the same SQL against the existing CI disposable-database fixture.

## Tradeoffs and detection

Text describes the existing executor instead of duplicating it as executable SQL. This avoids a second deletion engine. The cost is that operators must compare metadata with its named source when an existing rule changes. CI verifies seed membership and registry behavior, not legal or product approval for new windows.

The log stores no subject identifier, payload, free-form error, customer data or token. Its own retention window remains open. No expiry is invented for the new operational metadata. A later approved policy must decide any purge or archival behavior.

A foreign key keeps logged table names attached to the registry. The `(table_name, finished_at desc)` index serves recent-attempt queries. There is no speculative index on payload or outcome. A future table rename needs an explicit forward migration.

Rollback is a new migration after preserving any collected evidence. Do not drop these tables automatically after they acquire evidence. Merge, hosted apply, deployment, production and paid calls remain closed. Independent Eval is pending.

Initial disk availability was 98 GiB. Only the named worktree and small new files were created. The shared local server and its final cleanup belong to the root coordinator.
