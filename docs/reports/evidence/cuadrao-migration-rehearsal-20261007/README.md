# Migration rehearsal evidence (October 7, 2026)

Local only, synthetic data, throwaway databases on the Supabase CLI's local Postgres 17.6. No hosted system was written to. Pinned inputs: candidate `93571e593e1677561e1dd38f63b6475574942e2d` (integration) and `main` `a9286b21886eb03df7a21f2f4b7d5e79af570679`. `rehearsal-output.txt` is the retained output of `rehearse_migration_upgrade.py`; `pin-check-output.txt` is the output of `verify_production_ledger_pin.py`.

## What was proven

| Test | Result |
| --- | --- |
| Clean install: all 114 migration files at the candidate, empty database, each file recorded | Applies; 114 ledger rows |
| Production-equivalent fixture: `main`'s 79 files minus the one missing in production (78, effects only, no ledger rows) plus production's actual 81 ledger rows (74 mapped to files, 7 legacy) | The gate reports `blocked` only by `missing_candidate_migrations` (35), the same as the production ledger read |
| Upgrade with `apply_approved_migrations.py`: 1 `--unrecorded` (`20260505000001`), the 35 Cuadrao versions, `--allow-mid-file-commit 20261003120001`, 5 s lock timeout per transaction. Seven files wrapped in their own `begin`/`commit` run as one transaction with the ledger row inside it; `20261003120001` commits inside itself and runs as two transactions | 36 steps applied; the gate then reports `pass`, 0 missing, 0 content drift, 0 name drift; ledger 116 rows |
| The same command run again | Refused: version already in the ledger |
| Catalog comparison, clean install against upgraded fixture | 0 differences in columns (857), constraints (628), indexes (289), triggers (67), functions (102), policies (77), table grants (452), RLS flags (96) |

## Count reconciliation

114 files at the candidate = 79 on `main` + 35 Cuadrao. Production ledger 81 = 74 of `main`'s files + 7 legacy rows with no file. The other 5 `main` files have no ledger row: four with their effects already in the schema, one (`20260505000001`) genuinely missing. Real actions: 36 (35 recorded, 1 unrecorded). Ledger afterwards: 116.

## The production ledger input and the real comparison

`production_ledger_hashes.py` holds, for each of the 81 production ledger rows, the version, name, statement count and statement hash, read from production with catalog `SELECT`s on October 7 (no statements text, no user rows). `verify_production_ledger_pin.py` runs them through the gate's own logic: they reproduce its pinned hand-reconciliation hash `e352a2c003572611f0fb201305e085e3736eefbfae0d62ef29f4322a18062032` exactly, and the offline report for the candidate is `blocked` only by the 35 missing migrations with 0 content drift and 0 name drift (`offline-gate-summary.json`).

Note what the rehearsal itself does and does not compare: in the upgrade fixture the ledger statements are filled from the local files, so "content drift 0" after the upgrade compares the files with themselves. The comparison against **production's** content is the offline gate report above.

## What this does not prove

Real production row counts and lock durations (the databases are empty); hosted Supabase behavior (grants, extensions, pooler, Auth); the official gate run with the database URL, which only the operator can do.
