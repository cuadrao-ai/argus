# Local proof for the production reset

This proves the destructive reset path missing from the older baseline evidence.
Nothing hosted was connected to or changed. All records and uploads are synthetic.
Committed command logs remove trailing spaces only.
Lucas still performs the manual steps in the [runbook](../../../runbooks/production-reset.md).
The approval record remains NOT APPROVED.

## Source and isolation

The initial fetched base was `5705c81223d3a519446ae61e05e0c0b7ad68dcb0`.
After the founder authorized the six app auth triggers and internal app FK
triggers, the resumed fetched base was
`945307ba3493f2088f18b9b89d34f0217ffbfdfe`.
The branch is `codex/production-reset-runbook` in a sibling worktree.
`source-hashes.json` pins the tested SQL and baseline blobs and the candidate
commit supplied to the apply tool. The final evidence commit adds outputs without changing those SQL blobs.

The two stacks use project IDs `cuadrao-reset-history` and
`cuadrao-reset-baseline`, with ports `5961x` and `5962x`. Both are started by
`supabase start`. Their configs are copies under `temp/`. The tracked
`supabase/config.toml` stays unchanged. No existing local stack is used.
The worktree has its own `.venv`, Python 3.10.20, and a regular `.env` made from
`.env.example` with assignments commented as placeholders. It has no env links.

## Reproduce

From a new sibling worktree with no `temp/history` or `temp/baseline` directory:

```bash
python3 - <<'PYENV'
from pathlib import Path
import re
Path('.env').write_text(re.sub(r'(?m)^([A-Z][A-Z0-9_]*)=.*$',
    r'# \1=<placeholder>', Path('.env.example').read_text()))
PYENV
poetry config virtualenvs.in-project true --local
poetry env use /Users/garces/.local/share/uv/python/cpython-3.10.20-macos-aarch64-none/bin/python3.10
poetry install --with dev
bash docs/reports/evidence/production-reset/prove.sh all
```

The runner starts the stacks, seeds A, inventories it, runs refusal controls,
empties and deletes both buckets through the Storage API, resets A, dry-runs
and applies both baseline files with the approved-migration tool, verifies A,
and compares it with B. It then runs the Postgres/RLS suite. An EXIT trap stops
only these two stacks with `--no-backup`. Start logs, including disposable local
keys, stay in `temp/`; they are never committed. The runbook uses Dashboard
Storage cleanup; the local proof uses the same supported API operations.

A is built from all 207 files in `supabase/migrations_archive/`, as baseline
proof database A was. B is built from the two current migrations. Both receive
`supabase/seed.sql`. Faker creates three auth users with identities and sessions,
three profiles, three Business spaces, and three accounts. The Storage API
uploads one object to each baseline bucket. An extra legacy table, enum, view,
and function test removal of objects the baseline does not know. The final
rehearsal moves one approved auth handler to `public` to prove both allowed
handler namespaces; the baseline restores it to `argus_private`.

The schema comparison reuses `1890-baseline/schema_diff.py`. It runs the
container's `pg_dump --schema-only` across the whole database except the ledger,
plus app seed rows and bucket definitions. It normalizes dump tokens, version
headers, object-block order, and seed clocks. It preserves carriage returns in
SQL literals. The ledger is checked separately by `verify.sql` and the real
production gate comparison. No changed schema line is ignored.

## Results

- `reference.log` checks all 166 expected RLS tables against the baseline source,
  measures 134 public policies and 63 public/99 private non-extension functions
  on B, proves the verifier rejects disabled RLS and an extra function, and
  proves the NOT APPROVED draft is rejected by the approval parser.
- `controls.log` records refusal for the wrong database, absent/wrong marker,
  nonempty Storage, an external view, and an external automatic FK dependency.
  Each refusal preserves the whole-schema hash and the recorded data counts.
- `inventory.log` contains counts and object identities only. `triggers.md` is
  the complete local trigger appendix, generated from the inventory query.
  Retained platform auth triggers are marked separately from drop candidates.
- `reset.log` records a committed reset. The reset retains `public` because it
  owns the preserved `vector` extension. A temporary `sql_drop` event trigger
  rejects collateral drops outside the catalog address allowlist.
- `dry-run.log` plans exactly two RECORD steps; `apply.log` records both commits.
- `verify.log` passes with two ledger versions, zero users, zero objects, and two
  empty recreated buckets. `baseline-verify.log` independently passes on B.
- `diff.log` reports 33,903 normalized lines on each side and zero diff lines.
  `schema.diff` is empty.
- `gate.log` reports `reset: pass stop=[] advisories=[]` and rejects one extra
  ledger row with `unexpected_applied_migrations`. The existing gate helper
  reads the real local ledger and uses the production gate's pinned comparison;
  only its connection factory removes TLS options for the local server.
- `net-client-grants.log` passes the strict network-extension grant probe.
- `postgres-tests.log` and `test-files.txt` record the full selected suite.
  2,899 passed, 5 skipped, and 1 failed across 238 files. The failure is
  `test_search_postgres.py::test_asset_rollup_pair_symbol_normalization_matches_memory_contract`.
  Importing scipy fails in Darwin's `_spropack` loader with a zero-fill section
  error before that test reaches its database assertion. No dependency repair
  or test retry was attempted.

The suite ran on the first successfully reset database. A fresh final reset
rehearsal then covered the final inventory labels, verifier output, and a
synthetic legacy public auth handler. The same baseline schema was rebuilt;
the full suite was not rerun for those inventory/output changes.

The wide `ruff` check and credential checker passed. Modularity budgets passed.
The ownership checker exited successfully but reported no policy for this
branch; it did not enforce a lane assignment.

## Review and limits

Two design passes rejected dropping `public` because that would remove `vector`.
An independent safety review found that inventory also needed retained auth
triggers; that was fixed and the final inventory was exercised locally.
The review found no further reset-boundary defect. A final targeted review
also found no defect after the public-handler compatibility check was added. A separate prose review
clarified retained triggers, service ownership, and the full apply command.

Two development failures are retained. `initial-marker-permission.log` shows
that the local postgres role cannot set an arbitrary database parameter. The
final marker is an app table. `initial-record-alias.log` shows a PL/pgSQL record
alias conflict, corrected before any reset committed. Neither failed attempt
changed persisted schema or data.

The marker is a founder assertion after checking the Dashboard address. It is
not automatic project discovery. Hosted permissions, current production
inventory, maintenance-window isolation, Dashboard clicks, and actual backing
file cleanup in production remain manual. Services stay suspended until the
separate deployment approval. This PR neither runs nor approves hosted work.

## Cleanup

Both proof stacks were stopped with `--no-backup`; no container or volume with
the task project IDs remained. `cleanup.log` records their shutdown. The SQL
author's sibling worktree was removed. The placeholder `.env`, local Poetry
config, `.venv`, scratch directories, and delivery worktree are removed after
the draft PR is verified. Existing unrelated worktrees and stacks are preserved.
