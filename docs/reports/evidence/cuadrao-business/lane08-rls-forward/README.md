# Adopt the staging RLS event trigger

Staging already has `public.rls_auto_enable()` and `ensure_rls`, but the
repository did not recreate them. This forward migration closes that schema
drift after PR #1185. It preserves the observed function body, owner, grants,
search path, event tags, and enabled state. It changes no existing table or row.

The only hosted project inspected was staging `skedzwocnmrhfigiwyzi`.
No hosted SQL write or migration apply occurred. Production was not accessed.
Advisor hardening belongs to lane08 PR2. The existing public execution grants
remain, including the advisor warnings for `anon` and `authenticated`.

## Evidence

| Check | Result |
| --- | --- |
| Baseline local test | 7 failed, 1 passed before implementation |
| Full local reset | 143 migrations applied |
| Focused migration, Business spaces, and guest Postgres tests | 102 passed, zero skipped |
| Exact function and trigger parity | Captured staging definition matches local catalog |
| Apply twice to existing artifacts | Same definition, ACL, settings, and object identities |
| Public CREATE TABLE, CREATE TABLE AS, SELECT INTO, partitioned table | RLS enabled |
| Private and temporary tables | RLS unchanged |
| Public table without a policy | Both client roles read zero rows |
| Unexpected existing trigger configuration | Migration raises and rolls back |
| Linked schema diff | No schema changes found |
| Staging read-only dry run | Exactly `20261016154607_adopt_staging_rls_auto_enable.sql` pending |
| Staging catalog readback | 142 applied migrations, one function, one trigger; forward migration unapplied |
| Branch ownership and modularity | Passed |
| Exact-head CI and independent Eval | Pending at commit time; root owns the final verdict |

The baseline failure is committed before the fix as `f17ec3514`.
The [captured catalog](staging-artifact.json) comes from read-only MCP queries
on October 16, 2026. The regression uses that observed definition as its expected
result. The function's existing exception logging behavior is preserved exactly.

The [reset](local-reset.log), [focused tests](focused-tests.log),
[linked diff](staging-diff.log), and [dry run](staging-dry-run.log) contain the
command results. The dry run is intentionally not empty. Root can apply the new
file only after this PR merges into integration.

## Reproduce

Use a disposable local Supabase project with the candidate migrations.
The proof used CLI 2.118.0, PostgreSQL 17, Python 3.10.20, local project
`lane08-rls-forward`, database port 59532, and shadow port 59530.

```sh
supabase db reset --local --no-seed --workdir <isolated-project>
ARGUS_DISPOSABLE_DATABASE_URL=<localhost-only-dsn> python -m pytest \
  tests/test_rls_auto_enable_postgres.py tests/test_migration_versions_unique.py \
  tests/test_business_spaces_migration_postgres.py tests/test_guest_*_postgres.py \
  -q --no-cov
supabase db diff --linked --project-ref skedzwocnmrhfigiwyzi --workdir <isolated-project>
supabase db push --linked --dry-run --skip-vault \
  --project-ref skedzwocnmrhfigiwyzi --workdir <isolated-project>
```

The staging checks used the existing staging session-pooler credential only in
process memory. The dry run enforced read-only transactions. The schema diff
creates a local shadow database and reads staging. No secret is in this evidence.
Provider keys were blanked for the local tests. No live model calls were needed.

## Scope and handoff

Starting and refreshed integration base are both
`bc16c70c8e1e01271090695648bdb30f5c38b1a9`. No reconciliation merge was needed.
Only the new migration, focused test, evidence, and ownership entry changed.
The `Model the Domain` principle kept the shape to the two observed catalog
objects. `Make Operations Idempotent` required repeated application to preserve
their identities. There is no API, application, prompt, or UI change.

The new-table and new-column checklist is N/A. There are no new tables, columns,
indexes, policies, data backfills, defaults, nullability changes, or API payloads.
The migration has the required local lock and statement timeouts. No destructive
table or data operation is present. Preserve this migration after apply; any
later correction requires another reviewed forward migration.

The owned test database container and volume are removed after verification.
The worktree, ignored local config, and evidence remain for independent review.
Root must run a fresh independent Eval against the final PR head before landing.
