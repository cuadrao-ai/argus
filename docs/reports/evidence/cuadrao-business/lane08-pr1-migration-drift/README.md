# Lane08 PR1 migration reconciliation

The repository now names the three historical migrations exactly as staging
recorded them. This changes no application behavior and applies no hosted SQL.
Staging project `skedzwocnmrhfigiwyzi` was the only hosted database inspected.
Production was not accessed.

The branch is `codex/lane08-pr1-migration-drift`. Both the starting and refreshed
integration base are `ebc3cbf762b2512156997a074429f8d81be64e54`.
No integration merge was needed. Runtime code and other lanes are unchanged.

## Acceptance

| Check | Result | Evidence |
| --- | --- | --- |
| Local reset from zero | PASS, all 142 migrations applied | [Reset output](local-reset.log) |
| Linked schema diff is empty | FAIL, unrelated trigger and function drift remains | [Exact diff](staging-drift.sql) |
| Every staging version and name matches a repo filename | PASS, 142 each, zero extras | [MCP ledger snapshot](staging-migrations.json), [comparison script](verify_history.py) |
| Staging dry run has nothing to apply | PASS, `upToDate: true`, `migrations: []` | [Dry-run output](staging-dry-run.log) |
| Focused migration and backend tests | PASS, 193 passed, zero skipped | [Postgres test output](focused-postgres.log) |
| Migration and document source unit tests | PASS, 158 passed, 10 Postgres cases skipped in this offline run | [Unit test output](migration-and-source-tests.log) |
| Modularity and branch ownership | PASS | Commands below |
| Exact-head CI and independent Eval | Pending at commit time | PR contains terminal run IDs and verdict |

The 10 skipped Business spaces cases in the offline run all passed in the
193-test Postgres run. No live model, email, or customer journey was exercised.

## Exact historical bodies

The read-only query selected `version`, `name`, `statements`, and
`md5(array_to_string(statements, E'\n'))` from
`supabase_migrations.schema_migrations`. Each selected row contains one statement
string, so the file bytes can match the stored body without a separator choice.

| Applied filename | MD5 of file and staging body |
| --- | --- |
| `20261016065035_whatsapp_reply_grouping.sql` | `420fbe0db147f6f7b773d65f1fb95b37` |
| `20261016090033_document_source_prefixes.sql` | `9ba6f3044b9d4cc62703d8e02053f0fd` |
| `20261016142927_business_name_prompt.sql` | `426edecbf1aceb65e5a2b3607006ae46` |

WhatsApp was renamed from `20261016010000` with identical bytes. There are zero
repository migrations between that version and `20261016065035`, so the rename
crosses no dependency. No current tests or runtime code reference either old
filename. Historical evidence retains its original filenames.

The document migration was renamed from `20261016180000`. This is its entire
body difference from the old repository file.

```diff
+SET LOCAL lock_timeout = '5s';
+SET LOCAL statement_timeout = '30s';
 -- One row remains one document connection. Each copy has its own reference;
```

The Business prompt backfill is exactly the applied SQL below. The actual body
does not contain `IF NOT EXISTS`, despite the initial task description. The root
coordinator confirmed that exact historical bytes control. No timeout was added.

```sql
alter table public.spaces
    add column business_name_prompt_seen_at timestamptz;
```

The local and staging schema both report a nullable `timestamp with time zone`
column with no default. This history backfill does not enable the planned
Business prompt. PR #1184 owns its application behavior and contains an unapplied
duplicate migration. Its owner must remove that duplicate after this PR lands.
This branch does not alter PR #1184.

## Remaining schema drift

The completed linked diff reports staging's `public.rls_auto_enable()` function,
the `ensure_rls` event trigger, and execution grants. They are absent from the
migration replay. The trigger is enabled for `ddl_command_end` on `CREATE TABLE`,
`CREATE TABLE AS`, and `SELECT INTO`. The security advisor also reports the
function's public execution grants. The diff was retained without applying it.

This fails the required empty-diff gate. It is outside the three approved
historical changes. A possible non-destructive follow-up is a new forward
migration that adopts the existing function and trigger. That option requires
approval to change the pre-deploy nothing-to-apply gate. It is not implemented
here. No staging history repair or unmerged migration apply is permitted.

## Verification commands and limits

Supabase CLI `2.118.0` ran against an isolated local project named
`lane08-pr1-20261016`, with database port `57432` and shadow port `57430`.
The temporary config points to the repository migration directory. Commands were
inspected with `--help` and the official CLI reference before use.

```sh
supabase db reset --local --workdir <isolated-local-project>
supabase db diff --linked --project-ref skedzwocnmrhfigiwyzi --workdir <isolated-local-project>
supabase db push --linked --dry-run --skip-vault --project-ref skedzwocnmrhfigiwyzi --workdir <isolated-local-project>
python docs/reports/evidence/cuadrao-business/lane08-pr1-migration-drift/verify_history.py
python .agent/scripts/ownership/verify_branch_ownership.py
python scripts/check_modularity_budget.py
```

The existing CLI access token was invalid. The successful linked checks used the
existing staging session-pooler password in process memory. No credential was
written to evidence, command arguments, or the repository. A first schema-diff
attempt failed because global `PGOPTIONS` also made the local shadow read-only.
The successful attempt used the CLI's read-only linked comparison without that
global setting. The dry run succeeded with read-only transactions enforced.

The Python runtime was `3.10.20`. Its shared environment lacked pinned
`lxml==6.1.3`, so that package was installed only in the lane's temporary directory.
Provider keys were blanked. Postgres tests targeted only localhost port `57432`.

```sh
python -m pytest tests/test_migration_versions_unique.py tests/test_apply_approved_migrations.py tests/test_business_spaces_migration_postgres.py tests/test_whatsapp_intake_postgres.py tests/test_client_grants_postgres.py -q --no-cov
python -m pytest tests/ingestion/test_document_source_objects.py tests/test_*migration*.py -q --no-cov
```

The external coordinator brief received one narrow policy paragraph. Its existing
content was preserved. The brief itself was not copied into this repository.
The repository policy is in [the Supabase README](../../../../../supabase/README.md).

## Advisor baseline for the next lane

[The baseline](advisors-before.json) records only object metadata and counts.
Legacy means the retained `strategies`, `collections`, and `collection_strategies`
tables. Other objects include current product, shared infrastructure, and dormant
features. Their runtime reachability was not audited in this history-only PR.

| Advisor | Total | Retained legacy | Other |
| --- | --- | --- | --- |
| RLS enabled, no policy | 74 | 0 | 74 |
| Mutable function search path | 2 | 0 | 2 |
| Extension in public | 1 | 0 | 1 |
| Anonymous executable definer | 1 | 0 | 1 |
| Authenticated executable definer | 2 | 0 | 2 |
| Leaked password protection | 1 | 0 | 1 |
| Unindexed foreign key | 137 | 2 | 135 |
| RLS initplan | 18 | 3 | 15 |
| No primary key | 1 | 0 | 1 |
| Unused index | 113 | 13 | 100 |

The mutable-path functions are `set_updated_at` and `argus_search_symbol_casefold`.
The exposed definer findings name `rls_auto_enable` and
`is_active_household_member`. No advisor remediation was attempted.

## Local cleanup

The owned database directory measured 81,137,762 bytes before cleanup.
`supabase stop --project-id lane08-pr1-20261016 --no-backup` removed only this
lane's disposable container and volume. Both filtered inventories were empty
afterward. The worktree, temporary config, and evidence remain available.

`df -k /private/tmp` reported 161,600,000 KiB available before work and
160,576,220 KiB afterward. Other lanes shared the filesystem, so that total
change is not a measurement of bytes reclaimed by this cleanup. Docker volume
removal is verified; physical disk reclamation is not separately measured.

## Historical column checklist

- [x] Exact applied version, name, and body retained.
- [x] Nullable column with no default verified locally and on staging.
- [x] All migrations replayed from zero.
- [x] Staging dry run confirmed no pending migration.
- [x] Duplicate in unmerged PR #1184 assigned to its owner for later removal.
- [ ] Empty linked diff. Blocked by the unrelated trigger drift above.
- [ ] Independent Eval and required exact-head CI complete.
