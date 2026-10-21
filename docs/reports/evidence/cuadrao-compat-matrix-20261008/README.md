# Compatibility matrix (October 8, 2026)

This is historical evidence for the pinned code and schema states below. The
October 10 documentation correction changes no result, test source, migration,
or hosted state. It does not establish acceptance of the current integration tip.

Local, synthetic, nothing hosted. Throwaway databases on the Supabase CLI's local Postgres 17.6. Candidate `cad1cbe1ec27ff89c08eadbec31718a0e627383c` (the Build 1 freeze). Previous production code is `main` `a9286b21886eb03df7a21f2f4b7d5e79af570679`.

`compat_matrix.py` builds three schema states from a production-equivalent fixture (effects of `main`'s files plus production's 81 ledger rows), each through the real applier, then runs each code version's real-Postgres test files (`tests/*postgres*.py`) against a fresh copy of each state.

| Schema state | Previous production code (34 files) | Build 1 code (73 files) |
| --- | --- | --- |
| **S0** October 8 fixture | 379 passed, 27 skipped, 1 failed | 409 passed, 227 failed, 304 errors (needs the new tables) |
| **S1** after C0 (website migration alone) | 379 passed, 27 skipped, 1 failed | 420 passed, 216 failed, 304 errors (still needs C1) |
| **S2** after C1 (consumer files, plus the unrecorded `20260505000001`) | 379 passed, 27 skipped, 1 failed | **722 passed, 31 skipped, 1 failed, 0 errors** |

## After the first Business step (B1, `20261008100000`), Build 2 candidate `64833f6d284d60562829c0545dc413d5324c9d5a`

Applied on top of C1 with the real applier (`ARGUS_COMPAT_TAIL`), then the same suites:

| Code | Result on C1 + B1 |
| --- | --- |
| Previous production code (`main` `a9286b21`) | 379 passed, 27 skipped, 1 failed |
| Build 1 (`cad1cbe1e`) | 722 passed, 31 skipped, 1 failed, 0 errors |
| Build 2 (`64833f6d2`) | 727 passed, 52 skipped, 1 failed, 0 errors |

The one failure is the same scipy import trap in every run. Build 2 skips 21 more tests than Build 1: they need a running local Storage service, which a plain database does not have, so Storage behavior itself (bucket limits, object delete on disconnect and on account deletion) is **not** exercised here; Business proved it against a local Storage stack (#905, #914 evidence). The rehearsal databases get the `storage` schema from the local container, as hosted always has it.

## After all four Business steps (B1 to B4), final integration code `f5a2007cd6f8e169a27cb1e6e3827ccbaa1bfb9a`

C1 plus `20261008100000`, `20261008110000`, `20261008130000` and `20261008140000`, each through the real applier, then the same suites (`results_tail_b1_b4.json`; the "build2" row in that file is the final integration code, not the earlier Build 2 candidate):

| Code | Result on C1 + B1 to B4 |
| --- | --- |
| Previous production code (`main` `a9286b21`) | 379 passed, 27 skipped, 1 failed |
| Build 1 (`cad1cbe1e`) | 720 passed, 31 skipped, 3 failed |
| Final integration (`f5a2007cd`) | 771 passed, 84 skipped, 2 failed |

Failures, read one by one. Four kinds, kept apart:

**1. Environment, not schema.** `test_asset_rollup_pair_symbol_normalization_matches_memory_contract` fails in every row: the local `scipy` import trap (#852).

**2. Outdated census tests, not a demonstrated runtime incompatibility.** Build 1 also fails `test_account_deletion_fk_census_postgres.py::test_sweep_names_every_user_reference_and_the_census_document_matches_it` and `test_client_grants_postgres.py::test_every_relation_is_listed_exactly_once`. Both compare Build 1's own documented lists (the deletion foreign-key census and the client-grants relations) with the live schema, so they fail whenever the schema grows (`spaces`, `whatsapp_*`, rows keyed by `owner_space_id`). They show that Build 1 does not *know about* the B2 to B4 tables. They do not show that Build 1 fails to read or delete anything: no test here runs Build 1 code against rows in those tables. That is a gap, not a pass. The final code's versions of these two tests pass.

**3. Order-dependent failure: cause found, test-fixture race, no production-recovery impact.** The final integration code failed `test_document_jobs_postgres.py::test_two_running_instances_recover_a_dead_worker_without_restart` (`needs_attention` instead of `review_ready`). Business found the cause: without `ARGUS_LOCAL_SUPABASE_URL`, `tests/document_sources_support.py` built a new in-memory source bucket per call, so the test's two simulated API instances had separate buckets and a redispatch could miss the upload (`document_source_unavailable`, then `needs_attention`). It is a coin flip (6 of 12 runs alone), not run order. This rehearsal did not set that variable, which is why it failed here; Linux CI sets it, shares real Storage and passes. Production always uses `SupabaseSourceObjects`, so recovery is unaffected. The fix is PR #924 (one shared in-memory store, test-only). Cause and impact recorded here before the release that carries #908, as required.

**4. The intermittent Storage disconnect failure: test interference, CLOSED by the founder's acceptance of Business's durable evidence.** With local Storage set, `test_document_source_objects_postgres.py::test_disconnect_removes_the_object_and_keeps_confirmed_activity` failed intermittently with `document_version_conflict` (about 1 in 3 on unmodified #905 code). It is **not** resolved by the separate document-jobs fixture diagnosis (item 3); it is its own question: can disconnect leave a Storage object or an import behind? It was held as a blocker until Business established its cause and showed a fix or evidence that it is test-only; the founder has now accepted that evidence.

Business's current report, not independently reproduced here: a hung run of the old jobs test kept two sweepers alive on the real clock while the Storage tests lease on a fixed 2026-09-20 clock, so they saw live leases as expired and advanced the draft mid-preparation (15 of 20 failures with the hung process attached, 20 of 20 passes away from it); production's API and sweeper share one clock, a held lease is respected, an expired lease ends `document_lease_lost`, and disconnect marks the connection first with every Storage write checking that status under a lock. A deterministic test, `test_disconnect_during_preparation_leaves_no_object_and_no_row`, covers the mid-preparation case. The test-only fixes landed in #924 (`cd3231baa` on integration). **Evidence received from Business (commit `b757fc9a0`, branch `claude/evidence-storage-disconnect`, folder `docs/reports/evidence/cuadrao-business-owner-pilot/2026-10-08-storage-disconnect-proof`).** On integration `826ace6d4`, unmodified, with a dedicated fresh stack and local Storage set, each run started with `env -i` (command and redacted env in the folder): the Storage file alone, 20 fresh runs, both disconnect tests 20 of 20; the jobs file first and then Storage, 20 runs, both 20 of 20; `ps` and `pg_stat_activity` at start and end showing only the stack's own sessions; a control with a foreign real-clock sweeper on the same database reproduced `document_version_conflict` in 3 of 5 runs, which confirms the cause; and a file:line audit (`audit.md`) of every path that can advance a draft or run a sweeper. Business's conclusion: within one pytest process nothing can advance these drafts on the real clock any more, and the residual exposure is operational (a second process sharing the database; one database per pytest process). I checked the result files by inspection, not by re-running: the 40 runs without the foreign sweeper contain no failure or error, and the three failing files are control runs 1, 4 and 5, all with `document_version_conflict`.

**Status: closed for this specific finding (founder, October 8).** This does **not** authorize hosted receipt access, and it does **not** replace the separate hosted storage and deletion smoke test (one synthetic document stored, the synthetic account deleted, the Storage object confirmed gone), which stays a separate founder approval required before receipt access is enabled.

**The minimum-version rule, stated by stored data.** A code version is a safe runtime only for stored data it can both read and delete:
- Previous production code: Personal chat data only.
- Build 1 (`cad1cbe1e`): Personal data plus the financial tables C1 added, including the financial-data deletion path. It has no knowledge of B1 to B4 data. It is not a supported runtime once any B1 to B4 table holds rows.
- Build 2 (`64833f6d2`) and later: also documents and their Storage objects (B1), with read and delete of those, and account deletion in every state.
- Code that reads or deletes B2 to B4 data (spaces, WhatsApp links, preparation jobs): the later integration code that carries it, as named in the enable request for each flag.
The first hosted write of new-format data in a table sets the minimum for that table. Rolling back below the code that can read and delete it means turning that feature's flag off and fixing forward.

## What it shows

- **Deploy order.** Build 1 code needs C1 first. On today's schema, or after C0 only, it fails on the missing tables. C1 must be applied and verified before Build 1 deploys.
- **Old code on the new schema.** Previous production code gives the same result on S0, S1 and S2: C0 and C1 do not break what it already did, in these suites. Reverting the application code after C1 is therefore possible at the database level, until new-format data is written (the minimum compatible code version applies from the first hosted financial write).
- **Client grants.** Comparing `anon` and `authenticated` grants between S0 and S2 on tables, columns and routines: 0 removed. 19 table grants, 161 column grants and 1 routine grant added, all on the new financial tables and `is_active_household_member`. Old code reaching the database as a client sees no lost access.
- **The one failing test**, in all six runs, is `tests/test_search_postgres.py::test_asset_rollup_pair_symbol_normalization_matches_memory_contract`. It fails with a local `scipy` import error (`dlopen ... _spropack`), the macOS arm64 runtime trap tracked in #852. It is an environment failure, not a schema one.

## What it does not show

- These are database-level suites. They do not drive the old or new API end to end, and they do not cover the web client.
- The first table covers C0 and C1. The later tables record local B1 to B4 database results, including their failures and skips. They do not prove Business end-to-end behavior or Build 1 read/delete compatibility with new-format rows. Business's separate evidence is on #914.
- Hosted behavior (pooler, extensions, Auth) is not covered.
