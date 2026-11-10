# One Cuadrao baseline (#1890)

A fresh database now builds from one file,
`supabase/migrations/20261110160000_cuadrao_baseline.sql`, plus one forward
migration, `20261110160100_drop_unowned_objects.sql`. The 207 files it replaces
are in `supabase/migrations_archive/`, unchanged. Everything here ran on
throwaway local Supabase stacks; no hosted database was read or changed.

## Files

| File | What it is |
| --- | --- |
| `inventory.py` | Lists every object the history creates and names its owner. Writes `inventory.md` and `inventory.json`. |
| `build_baseline.py` | Writes the baseline from a database that ran the history and the drops. |
| `schema_diff.py` | Compares two databases: whole-database schema, grants, triggers, buckets and seed rows. |
| `schema.diff` | The diff between the two builds. Every line is explained below. |
| `explain_checks.py` | Shows each differing CHECK is the history's text as Postgres re-reads it. |
| `diff_controls.sql`, `diff_controls.expected` | Known-bad changes the diff must catch, one of them a lone carriage return. |
| `reset_ledger.sql` | The production reset step: the empty migration ledger, recreated. |
| `gate_on_reset.py` | Runs the production gate's comparison against a reset database. |
| `splitter_equivalence.py` | Shows the faster migration splitter splits every file exactly as before. |
| `prove.sh` | Rebuilds the three databases, runs the staging alignment and the production reset, and checks every diff. |

## Rerun

```bash
docs/reports/evidence/1890-baseline/prove.sh temp/1890-proof
```

It starts three stacks with their own project ids and ports (5981x, 5982x and
5983x), builds A from `supabase/migrations_archive/`, aligns A the way staging
will be aligned (baseline recorded without running, drop migration run, both
through `scripts/ops/apply_approved_migrations.py`), builds B from
`supabase/migrations/`, and builds C the way the production reset will: no
migrations, `reset_ledger.sql`, then both files from the committed tree through
the apply tool. It exits 0 only when the A to B diff equals `schema.diff`, every
CHECK line is explained, the `net` grant probe passes on A and B, the apply tool
names the missing ledger table on C before it exists, the production gate
passes on C and blocks on one extra ledger row, the A to C diff equals
`schema.diff` too, and every marker in `diff_controls.expected` shows after
`diff_controls.sql` runs on C. It also rewrites `inventory.md` and
`inventory.json` from A before alignment, so `git status` shows any drift. Pass
`--keep` to leave the stacks running (C then holds the controls; B is as built).

The scripts read `pg_dump` as bytes and split on `\n` only. Postgres stores
`E' \t\r\n'` from the archived `20261021050000_business_sale_ncf_once.sql` as a
raw carriage return inside the index definition, and universal newlines or
`str.splitlines()` would drop it from the baseline while hiding the loss from
the diff. `.gitattributes` exempts the baseline from line-ending conversion for
the same reason.

## Inventory

See `inventory.md` for every table, view, function and type with its owner at
file and line. Triggers, policies, indexes and constraints belong to their
table.

| Class | Tables | Functions | Types |
| --- | ---: | ---: | ---: |
| kept | 109 | 96 | 1 |
| unsure | 57 | 66 | 0 |
| removed | 2 | 4 | 0 |

- **Removed.** `argus_private.retention_policies` and `argus_private.retention_sweeps`
  (a descriptive registry no code reads), and four functions whose last callers
  were deleted with the chat routes (#1625):
  `baseline_conversation_activity_read_states`, `claim_guest_compute_usage`,
  `claim_registered_compute_usage`, `delete_private_alpha_access_welcome_artifacts`.
  Their tests went with them.
- **Unsure, so kept.** 57 tables and 66 functions of the old chat, backtest,
  household, guest, personal-money and private-alpha products. No Business
  feature reads them, but code still names them: mounted routers
  (`conversations`, `households`, `personalization_memory`, the `auth` guest
  handoff), the Business code that sweeps rows on close, transfer and account
  deletion (`custody_graph.py`, `purge.py`, `account_deletion/service.py`), and
  database functions. Each needs its own cleanup slice under #1577.
- **Old tables pinned by kept schema.** 18 of the 109 kept tables are old chat,
  memory and guest tables that a kept object needs. The restrictive
  `profiles_guest_session_active` policy on `profiles` reads `guest_workspaces`;
  its foreign key and triggers reach `conversations` and the nine `memory_*`
  tables; the excerpt-revocation trigger on `conversations` reaches `messages`,
  `backtest_runs`, `public_excerpt_snapshots` and through them `strategies`,
  `ideas`, `idea_versions` and `evidence_artifacts`. Dropping them changes a
  Business table's policy or triggers, which #1890 does not do.
- **Extensions.** `pgcrypto` is kept (the Business custody functions call
  `extensions.digest`). `pg_trgm` (8 trigram indexes on old chat tables) and
  `vector` (`argus_memory_vectors`) stay with the tables that use them. `pg_cron` and `pg_net`
  are removed. `pg_stat_statements`, `supabase_vault` and `uuid-ossp` come with
  the Supabase image.
- **Cron jobs.** None. The two waitlist jobs were removed by
  `20261103010000_remove_waitlist.sql`.
- **Storage buckets.** `financial-document-sources` and `profile-images`, both
  kept and created by the baseline.
- **Event trigger.** `ensure_rls`, kept, created last in the baseline so it
  does not enable row security on a table the history left without it.

## pg_net, pg_cron and #1227

No live code or database function uses them. A search of `src`, `workflows`,
`scripts`, `web`, `marketing`, `render.yaml`, `.github` and the config for
`pg_net`, `pg_cron`, `net.http_*` and `cron.*` finds no caller, every database
function body in the history was checked for `net.http` and `cron.`, and
`cron.job` is empty. The baseline does not create either extension; the drop
migration removes both where the history installed them. With no `net` schema,
no client role can reach pg_net, so #1227 is resolved by removal. The strict
probe `supabase/tests/net-client-grants.sql` now passes when the `net` schema is
absent. Its grant check is unchanged, so a database that has `net` with client
grants still fails.

## Proof

- **Schema diff.** A (history, then the drop migration) and B (baseline alone)
  produce 33,903 normalized lines each. The diff is 14 changed lines: seven CHECK
  constraints whose history text nests an `AND`, for example
  `((a AND b) AND c)`, while the baseline stores `(a AND b AND c)`.
  `explain_checks.py` adds each history text to a copy of its table and reads it
  back: 7 of 7 come back exactly as the baseline text. This is how Postgres
  stores an expression it reads from text, not a schema difference.
- **Controls.** `diff_controls.sql` makes ten known-bad changes on C (a grant,
  a policy, an auth trigger, a seed row, a bucket, the event trigger, default
  privileges, a comment, a function setting, and the sale NCF index with no
  carriage return in its `btrim` set). `prove.sh` requires the diff to show all
  ten.
- **Staging rehearsal.** On A built from the history, the apply tool recorded
  the baseline without running it and ran the drop migration; the result
  diffs against B as above.
- **Production reset rehearsal.** C is a database with no migrations. Without
  the ledger table the apply tool stops with
  `the migration ledger table supabase_migrations.schema_migrations is missing;
  create it first: ...`. After `reset_ledger.sql` it runs both files from the
  committed tree, about one second. `gate_on_reset.py` then reads C's ledger
  the way the production gate does and gets `pass` with no advisory, and
  `blocked` with `unexpected_applied_migrations` once one row the tree does not
  have is added. C diffs against A as above.
- **Postgres tests on B.** Every test file that reads
  `ARGUS_DISPOSABLE_DATABASE_URL` or the local Supabase URL (236 files, wider
  than the pull-request set in CI) ran against B: 2,952 passed, 5 skipped (four
  `[memory]` variants and one email-change proof that needs mail settings),
  1 failed. The failure,
  `test_search_postgres.py::test_asset_rollup_pair_symbol_normalization_matches_memory_contract`,
  is an ImportError: scipy's `_spropack` does not load on this Mac (Darwin 27).
  It never reaches the database.
- **Splitter.** `production_migration_gate.py` took 101 s to split the
  baseline because `_ends_begin_atomic` regex-searched the whole prefix at every
  `c`. It now scans back from the character. `splitter_equivalence.py` splits all
  209 files with both versions: identical statements in every file.

## Staging alignment plan (not run, not approved)

Staging ran the full history. These steps record the baseline without running
it and drop the six removed objects and two extensions. Nothing else changes.

1. Merge this PR into `codex/private-alpha-next`. Call the merge commit `M`.
2. Lucas approves. In a docs PR, fill
   `docs/release-manifests/2026-11-10-staging-baseline-apply.json`: set
   `candidate_sha` to `M`, `issued_at` and `expires_at` to a window of at most
   three days, `approved_by` to `founder`, and the approval reference. Leave the
   digest: it covers `docs/release-manifests/2026-11-10-staging-baseline-versions.json`
   with `20261110160000` recorded without running. Merge that PR.
3. Dry run from the merged tree, with the staging URL in
   `ARGUS_APPLY_DATABASE_URL`:

   ```bash
   poetry run python scripts/ops/apply_approved_migrations.py \
     --candidate-sha M \
     --approved-file docs/release-manifests/2026-11-10-staging-baseline-versions.json \
     --record-only 20261110160000 \
     --allow-host db.skedzwocnmrhfigiwyzi.supabase.co \
     --allow-host aws-0-us-east-1.pooler.supabase.com \
     --allow-database postgres \
     --hosted-approval docs/release-manifests/2026-11-10-staging-baseline-apply.json \
     --ssl-root-cert <ca-bundle>
   ```

   Expect exactly `RECORD-ONLY 20261110160000 cuadrao_baseline` and
   `RECORD 20261110160100 drop_unowned_objects`. The tool refuses before
   anything runs unless staging's ledger holds all 207 archived versions.
4. Run the same command with `--hosted-confirm staging-apply-1890-baseline
   --execute`. The baseline row is inserted with no DDL. The drop migration
   runs in one transaction; if it fails (for example, a permission error on
   `drop extension pg_net`), it rolls back, the baseline row stays, and nothing
   else changed.
5. Verify read-only: both versions are in
   `supabase_migrations.schema_migrations`; `to_regclass` is null for both
   retention tables; the four functions are gone; `pg_extension` has no
   `pg_cron` or `pg_net`; `supabase/tests/net-client-grants.sql` passes.

The 207 history rows stay in staging's ledger as the record of what ran. The
apply tool only plans versions above them, so they need no repair.

## Production (#1789)

- **Reset.** After the founder empties the database, run `reset_ledger.sql` on
  it as `postgres`:

  ```sql
  create schema if not exists supabase_migrations;
  create table if not exists supabase_migrations.schema_migrations (
      version text primary key,
      statements text[],
      name text
  );
  ```

  A reset that kept the table empty needs nothing; one that dropped the schema
  gets it back. Then apply both versions with the apply tool and a production
  approval record, without `--record-only`. If the table is still missing the
  tool stops before anything runs and says
  `the migration ledger table supabase_migrations.schema_migrations is missing;
  create it first: create schema if not exists supabase_migrations; create table
  supabase_migrations.schema_migrations (version text primary key, statements
  text[], name text)`.
- **In place.** If production keeps its history instead, it needs the staging
  steps. The tool refuses unless production's ledger holds every archived
  version, and its hand-reconciled history may not. That case needs a decision
  first.
- **Gate.** `scripts/ops/production_migration_gate.py` pins what the tree and
  the ledger hold at or below `20260811210000`. The tree now holds nothing
  there, so the candidate catalog pin is the digest of an empty history,
  `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` (sha256
  of `[]`), and that digest joins the production ledger pins beside the two
  pre-reset histories, which stay so a gate run against production before the
  reset reports `missing_candidate_migrations` rather than pin drift. On a
  reset production with both files applied the report is `pass`
  (`gate_on_reset.py` on C), and a ledger row the tree lacks still blocks.

## If another migration merges first

A migration with a version above `20261110160100` applies on top of the
baseline unchanged, unless it touches a removed object. One with a lower
version would run before the baseline and fail: move it into the archive,
rebuild a database from the archive, run the drop migration, then rerun
`build_baseline.py` and `prove.sh`.
