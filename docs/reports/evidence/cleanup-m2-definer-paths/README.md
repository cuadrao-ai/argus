# M2 definer search paths

M2 replaces 21 functions in place with `search_path = ''`. Their bodies already
qualify every relation with its schema. Three composite return types explicitly
name `public` in the migration. PostgreSQL resolves built-in functions and types
through its implicit `pg_catalog` lookup. No application body changes are needed.

The integration base and the final fetched integration SHA are both
`651870a54be4e5506dbb38f3902fef1a97eef8df`. There is no intervening integration
diff and no reconciliation merge. The shared coordinator checkout was untouched.

The staging catalog census ran on October 18, 2026 UTC against project
the named staging project in an explicit read-only transaction. It selected only
`pg_proc`, namespace, definition, owner, config, and privilege metadata. It
returned 21 definers whose search path includes application schemas. This matches
the historical audit count. The `pg_catalog`-pinned `rls_auto_enable` function and
already empty paths are excluded. No waitlist RPC is in the target list.

`repo-before.json` preserves all 21 original definitions, exact identities,
owners, grants, and config from the repository-built local schema. The local
metadata is byte-identical to the corresponding read-only staging census. Only
this aggregate comparison is published. It contains no customer records or credentials.
`CREATE OR REPLACE` retains the existing function objects and permissions. The
migration changes neither an applied migration nor an application caller. It
sets a five-second lock timeout and a sixty-second statement timeout.

The source audit and squaring plan are evidence inputs, not new action grants.
The migration SQL and committed catalog snapshot come from the repo-built local
schema. The repository destination was verified as the public `lagarcess/argus`
GitHub repository. No staging connection reference or customer data is published.
The coordinator assigned only M2 and its unique ownership entry. M1, M3, PKs,
indexes, policies, other advisors, and receipt implementation remain with their
owners. M11 confirmed that the research drop subset is empty. The legacy
functions are retained, including guest replacements, usage accounting, admission,
backtest completion, and withheld-result deletion. No drops are included here.

`equivalence.json` records the local catalog and behavior proof. The test runner
compares all 21 definitions to the repo-built snapshot before the migration. After
the migration it compares the full canonical definitions with only the expected
path substitution, exact bodies, signatures, defaults, ACLs, owners, and function
attributes. It also confirms that unrelated definers did not change.

`supabase/tests/m2-definer-search-paths.sql` exercises each of the 21 functions,
including the two trigger functions through real table writes. The checks cover
account create, replay, conflict, registered-only access, opening revisions,
stale versions, owner isolation, active and departed household membership,
synthetic temporary-table shadowing, guest expiry protection, profile identity,
guest conversation replacement, feedback replay, allowance windows, backtest
admission, missing-result paths, compute limits, usage release, and expiry purges.
Account RPCs execute as `service_role`; the membership predicate executes as
`authenticated`. All synthetic fixture writes roll back.

`regression.txt` records 66 passing existing Postgres tests from
`test_financial_accounts_postgres.py`, `test_client_grants_postgres.py`, and
`test_allowance_accounting_postgres.py` on Python 3.10.20. Live provider keys were
blanked. The first broader run passed 63 tests and failed three bucket checks
because a schema-only dump omits the private bucket seed. Restoring that checked-in
seed into the disposable database resolved those setup failures. No product code
or tests were weakened. The SQL fixture initially used invalid feedback and title
labels; existing constraints rejected them before the baseline proof. The fixture
now uses the actual permitted enum values.

The tests used only `m2_testdb` on the item0 local server at port 59432. The baseline
`postgres` database was read-only. Its active sessions prevented template cloning,
so the test database used a schema-only dump of public, argus_private, auth,
storage, and extensions. Its app extensions were recreated locally. Managed
scheduler extensions and database-global default privileges were excluded from
this isolated clone. Explicit function ACLs, owners, and definitions matched
staging before the proof. This is function-level local proof, not a new full
managed-schema restore claim.

To repeat the equivalence proof, use a fresh local `m2_testdb` containing the
integration schema before M2, then run the following command. The runner rejects
non-local hosts and other database names and applies M2 only to this disposable
database. It requires `psycopg`.

```sh
python scripts/qa/verify_m2_definer_search_paths.py \
  --database-url postgresql://postgres:postgres@127.0.0.1:59432/m2_testdb
```

The SQL behavior file can also run separately on the migrated disposable schema.
Ownership, modularity, Ruff, and whitespace checks pass. Independent exact-head
Eval and terminal CI are pending coordinator review. Receipt gate 3 remains a
merge hold. No staging migration, production action, provider call, environment
file write, or live money write was made. A rollback would be a new forward
migration using the preserved definitions, never an edit to applied history.

The official [Supabase function guidance](https://supabase.com/docs/guides/database/functions)
requires schema names for relations under an empty search path. Its changelog
was checked for relevant database changes before implementation.

## Migration-writer inventory correction

Required CI run `39091406872` found the new migration missing from the exhaustive
backtest-job writer inventory. On the exact integration base
`651870a54be4e5506dbb38f3902fef1a97eef8df`, the original inventory assertion passed
against the exact base migration files. On candidate
`311cf4de12e48417c211e40b1ce85c6d665243a0`, the focused suite reproduced the CI
failure with 1 failed and 2 passed. The failure named only
`20261018040000_harden_definer_search_paths.sql` as unclassified.

The correction classifies that migration without excluding it from the scan.
It finds every recreated function that writes the job table and requires exactly
the existing admission and direct-success functions. Each body then receives its
existing containment assertion. Admission must retain the abandoned-execution
marker and must not attach a result or write success. Direct completion must
retain its row lock and running-state guard. No migration SQL changed.

The focused suite passed all three tests after this correction. Separate mutation
probes confirmed rejection of a missing running guard, an admission result write,
and an unclassified third writer. Python 3.10.20 used a provider-empty synthetic
environment. These static tests need neither application environment files nor a
database. Ruff, formatting, whitespace and the branch ownership gate passed.
The ownership entry adds only the exact invariant test path. Integration was
fetched again and remained at the original base. Fresh exact-head CI and
independent delta Eval remain pending. No CI failure was rerun unchanged.
