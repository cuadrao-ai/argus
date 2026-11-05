# Business migrations B1 to B4: code and schema compatibility rehearsal

Label: **local rehearsal on a disposable Supabase stack. Not hosted proof.** No hosted project, no `db push`, no provider call and no external network were used.

Run: 2026-10-08, from about 01:50 to 03:22 CDT. Stack: Supabase CLI 2.118.0, Postgres 17.6, project `argus-biz-compat` on ports 57790 to 57799 (API 57791, DB 57792). Python 3.10.20 from `argus-worktrees/private-alpha-next/.venv`. Each code version ran from its own detached worktree under `argus-worktrees/compat-*`, with `PYTHONPATH=src` (`src:.` for probes).

The question this answers comes from the founder. Reverting application code is different from reverting database changes, and "additive" alone does not prove that old code still works. Every cell below is backed by a run of that code against that schema, or by data one version wrote and another version read.

## Code under test

| Name | Commit | Notes |
| --- | --- | --- |
| Build 1 (consumer release) | `5613364d0397766b7b92896bd03208ce57409774` | `origin/codex/private-alpha-next`. Migrations end at 20261005230000. |
| Build 2 | `e43ea7fab75944995a6b276519c5c74005ce3d92` (tree `e771a0bc01376c1293ce2c2a2b57b0852c7d9b41`) | Local, unpushed merge of `origin/claude/business-pilot-storage` `45ede13e79e19379f086f4de1276dfd122c63427` (#905) with Build 1. Adds B1. |
| Activation | `1d3e814b1a3faf0b683b814d3a527c40386cda66` | `origin/claude/business-spaces` (#908, #909, #913, #914). It lacks two integration commits, `ac37ff369` and `5613364d0`. Both touch only `docs/` and `ios/`, so the backend and migrations match activation-on-integration. |

Migrations, applied in this order. The hash is sha256 of the file at the activation commit. Build 2's B1 file is byte-identical.

| Id | Version and file | sha256 | Apply tool class |
| --- | --- | --- | --- |
| B1 | `20261008100000_financial_document_source_objects.sql` | `5af14cc4...0922c77608` | contract-replacing |
| B2 | `20261008110000_document_preparation_jobs.sql` | `56fc96cb...227902e82b` | contract-replacing |
| B3 | `20261008130000_whatsapp_intake.sql` | `fe423e39...8d540e0062` | contract-replacing |
| B4 | `20261008140000_business_spaces.sql` | `adb8d659...54716395b3` | destructive (drops `create_financial_account`) |

Schema states: C is everything through 20261005230000 (115 migrations). +B1 to +B4 add one migration each. "+B4 with Business data" is +B4 after the activation code created a Business space, account, expense and receipts for one person, beside the same person's Personal records.

## Method

1. A new stack started from the repo `config.toml` with a new `project_id`, free ports, Studio and the edge runtime off, and only the 115 C migrations in its folder (`supabase start`).
2. B1, B2, B3 and B4 were applied one at a time onto the live database with the repo tool, which also rehearses it: `scripts/ops/apply_approved_migrations.py --candidate-sha 1d3e814b1... --approved-file approved_<version>.json --allow-host 127.0.0.1 --allow-database postgres --execute`, run from the activation worktree. Data written at one state stays in place for the next. Outputs are in `outputs/apply_B1.txt` to `apply_B4.txt`. Each wrote its ledger row and reported `applied 1 step(s)`.
3. At every state, each version's real-Postgres suites ran (`probes/run_suite.sh`). The file set is every test file that names the disposable database or local Supabase variables, or imports the shared Postgres fixtures: 102 files for Build 1, 103 for Build 2 and 110 for activation (`probes/files_compat-*.txt`). These cover accounts, money, recording, ingestion, documents, search, household, account deletion and client grants. The command is `pytest -q -p no:cacheprovider -o addopts="" -rfE <files>`, with no `.env` in any worktree and `ANTHROPIC_BASE_URL` unset.
4. Probes drove the real API, Auth, Postgres and Storage through FastAPI's `TestClient`, with the same patching as `tests/test_financial_accounts_api_postgres.py`, or drove the services the routes call (`probes/probe_*.py`, run by `probes/probe.sh <worktree> <probe> <subcommand> <label>`). Cross-version probes hand state over in a scratch JSON file that is not committed because it holds generated local test passwords.
5. The stack was then reset to +B3 for one more check. A running Build 2 process kept creating and replaying accounts while B4 was applied under it (`probes/probe_live.py`).

Probe and tool outputs are under `outputs/` as `.txt`, because the repo ignores `*.log`. `outputs/suite-summaries.txt` holds each run's totals, failing test ids and distinct causes. Raw suite logs are not committed because their tracebacks print the local stack's demo keys. The scripts name the session scratchpad path, so a rerun needs that path edited.

## Result

| Code | C | +B1 | +B2 | +B3 | +B4 | +B4 with Business data |
| --- | --- | --- | --- | --- | --- | --- |
| Build 1 | Works. 1245 passed, 2 failed (scipy). | Works on its own data. **Breaks** on documents Build 2 stored: download 422, same-file upload 503, and disconnect and account deletion leave the file in Storage. | Works. 1245 passed. | Works with limits. 1243 passed. Two inventory tests fail, runtime unaffected. | Works with limits. Same as +B3. | **Breaks.** Personal lists, home, totals and search show Business rows. Account deletion leaves 6 Storage objects. |
| Build 2 | **Breaks.** Upload 503 `document_storage_unavailable` (no bucket, no `source_path`). 28 failed, 1 error. | Works. 1271 passed, 2 failed (scipy). Reads Build 1's legacy bytea documents. | Works. 1271 passed. | Works with limits. 1268 passed. The same two inventory tests fail. | Works with limits. Same as +B3. The ten-argument account create resolves to the new function, replay is preserved, and a live process saw no error across the swap. | **Breaks.** Same Personal leak, and its writes cross spaces. A Business account grant answers 500. Account deletion works. |
| Activation | **Breaks.** 312 failed, 91 errors. | **Breaks.** 309 failed, 91 errors. | **Breaks.** 309 failed, 91 errors. | **Breaks.** 308 failed, 91 errors (no `owner_space_id`, `spaces` or eleven-argument function). | Works. 1417 passed, 2 failed (scipy). | Works. 1417 passed. It shows the cross-space rows Build 2 wrote, and a stale job resolves as `document_attempt_superseded`. |

Activation fails before B4 mostly because B4 is missing. The suite does not separate its need for B2 from its need for B3. Its code reads `preparation_job` (B2) in `documents/jobs.py` and the WhatsApp tables (B3) in `whatsapp/store_postgres.py`.

Every "breaks" and "limit", with its cause:

1. **Build 1 after Build 2 stored documents (+B1).** Build 1 reads only `source_bytes`. A Build 2 document lists and opens with `source_available: true`, but `GET /source` answers 422 `document_source_unavailable`. Re-uploading the same file answers 503 `document_extraction_unavailable`. The store-level cause is a `CheckViolation` on `financial_document_extractions_one_source`: Build 1's upsert sets `source_bytes` on a row that already has `source_path` (`outputs/probe_b1_capture.txt`). Disconnect returns 200 and deletes the row, but the Storage object stays. Account deletion returns `done` and deletes the auth user, but the person's Storage object stays with no owner. No code path in any version erases a deleted owner's prefix later.
2. **Build 1 and Build 2 on Business data (+B4).** Their Personal readers do not filter `owner_space_id`. For one person with one Personal and one Business account, both versions return both accounts from `list_accounts`, `storage.read`, search, home recent activity and the canonical activities. The home total `recorded_spending_minor` is 50100, the sum of both 250.50 expenses, where the Personal figure is 25050. Connections, open import events and document drafts include Business receipts, WhatsApp captures and Business jobs. Build 2 also downloads a Business receipt's source through the Personal document path.
3. **Build 2 writes on Business data (+B4).** An expense Build 2 enters into the account it lists as Personal lands in the Business ledger. Activation then lists it among Business expenses, 55.00 "Written by Build 2". Build 2 resolved and accepted a Business receipt's import event into the Personal account. Activation shows that receipt as `confirmed` with no Business expense, and the expense sits in Personal. Sharing the Business account with a household raises `business_account_not_shareable` from the B4 trigger. The household route maps unknown errors with `raise error`, so the user gets a 500. Build 2 has no WhatsApp webhook or link routes, so during a rollback, deliveries and link requests reach no handler.
4. **Build 1 account deletion on Business data (+B4).** It completes, spaces and WhatsApp rows cascade away, and 6 document objects (Personal and Business) stay in Storage.
5. **Inventory limits at +B3 and +B4 (Build 1 and Build 2).** `test_account_deletion_fk_census_postgres::test_sweep_names_every_user_reference_and_the_census_document_matches_it` fails because the census document does not list the three WhatsApp tables' foreign keys. `test_client_grants_postgres::test_every_relation_is_listed_exactly_once` fails because the grants inventory does not list them. Both tests compare a checked-in list with the catalog. At runtime the tables cascade on auth-user delete, which the deletion probes confirm, and B3 sets their grants. Activation's copies of both tests pass.
6. **Code ahead of schema.** Build 2 on C, and activation on anything before +B4, break as the table shows. The hosted order (migration before code) avoids these cells. A schema revert puts the running code in them.

## Scenario 1: Build 1 code on schema through B1

Forward window. Build 1 ran on +B1 with no Build 2 data.

- Suites: 1244 passed, 3 failed, 3 skipped. Two failures are the scipy loader. The third, `test_account_deletion_guards_postgres::test_two_sweeps_at_once_resume_a_run_once`, passed 3 of 3 reruns of its file at +B1 (`outputs/rerun_b1_B1_guards.txt`) and passed in every other Build 1 run. It is a timing flake.
- API cycle (`probe.sh compat-build1 probe_docs.py cycle b1-at-B1`). Upload returned 200 `saved` and wrote 5909 bytes of `source_bytes` with `source_path` null. List, get and source returned 200, and the downloaded bytes matched. The same-file upload replayed. Disconnect returned 200 and removed the row. Account deletion returned 200 `done`. The bucket stayed empty. `outputs/probe_docs_cycle_b1-at-B1.txt`.

Rollback after Build 2 wrote data. Build 2 seeded, then Build 1 read (`probe_docs.py seed` on compat-build2, then `read` on compat-build1).

| Step | Build 1 result |
| --- | --- |
| List | 200, both Build 2 documents, `source_available: true` |
| Get document a | 200 `saved` |
| Download a | 422 `document_source_unavailable`. The row has `source_path`, `source_bytes` null. |
| Re-upload a's file | 503 `document_extraction_unavailable`, from the `one_source` CheckViolation. The row is unchanged. |
| Disconnect b | 200. The row is gone. Its object `8f3afe96.../c010941a.../0afbddff...` remains. |
| Delete account v | 200 `done`. The auth user is gone. Its object `87a7b851.../a81396a7.../bb8f80a6...` remains. |

`outputs/orphans_after_S1.txt` lists both objects as unreferenced, one of them with its owner deleted. If Build 2 is deployed again, it erases the first object when that person deletes their account, because the person still exists. Nothing erases the second.

The forward path works. Build 1 seeded legacy bytea documents and Build 2 read them. Download returned 200, a replay kept the bytea, and disconnect and account deletion completed with an empty bucket (`outputs/probe_docs_*_b1-at-B1.txt`, `probe_docs_*_b2-at-B1.txt`).

## Scenario 2: Build 2 code on schema through B2, B3 and B4

| State | Passed | Failed | Skipped | Failures other than scipy |
| --- | --- | --- | --- | --- |
| +B1 (baseline) | 1271 | 2 | 3 | none |
| +B2 | 1271 | 2 | 3 | none |
| +B3 | 1268 | 5 | 3 | FK census, client grants inventory, conversation activity backlog |
| +B4 | 1268 | 5 | 3 | the same three |
| +B4 with Business data | 1268 | 5 | 3 | the same three |

`test_conversation_activity_postgres::test_cutoff_baseline_reads_existing_terminal_but_not_later_completion` depends on database volume, not on the schema. It calls a baseline function that handles 500 conversations per call. After ten suite runs the database held 1020 leftover conversations. Two back-to-back reruns at +B4 passed and then failed (`outputs/rerun_b2_B4_activity.txt`). Build 1's copy fails the same way at +B4 with Business data.

Every Personal area passed at every state from +B1 on: accounts, money, recording, ingestion, documents, search, household, account deletion and client grants (except the inventory test). The API document cycle passed at +B2, +B3 and +B4 for both builds (`outputs/probe_docs_cycle_build*-at-B*.txt`).

Account creation across B4's drop and recreate:

- Build 2 code calls `select public.create_financial_account(%s, ... 10 placeholders)` from `postgres_repository.py:63`. That is its only caller, and nothing calls it through PostgREST.
- At +B3, Build 2 created key `compat-K1` and stored identity hash `sha256:9d243844...`.
- After B4 the catalog holds only the eleven-argument signature, ending in `p_owner_space_id uuid`. Build 2 then got these results: the same request replayed the same account (`created: false`), a changed request raised `IdempotencyConflict`, and a new key created an account. The stored hash was unchanged, and no account had `owner_space_id` set. `outputs/probe_accounts_*`.
- Activation replayed the same key in Personal scope and got the same account. In Business scope it got `IdempotencyConflict`, which is the design ("a key replayed across spaces conflicts").
- Live swap. One Build 2 process with a single pooled connection created and replayed accounts every 0.2 s for 40 s while B4 was applied. The results were 64 replays and 64 creates against the ten-argument function, then 117 of each against the eleven-argument function. There were zero errors, and a server-side prepared statement for the call was active (`outputs/probe_live_b2.txt`, `outputs/apply_B4-live.txt`).

B4's effect on Personal, forward: none observed. Build 2's results are the same at +B3 and +B4. Personal household grants still succeed with B4's grant trigger in place. The observation trigger passes Personal rows (null equals null). The deletion copy guard fires only for a Business account.

## Scenario 3: rollback from activation code to Build 2 code after Business data exists

1. Activation seeded one person (`probe_business.py seed`, using `World` and `_seed` from `tests/test_business_space_isolation_postgres.py`). It created a Business space, a Personal and a Business account, a 250.50 expense on each, a receipt on each, a WhatsApp link and capture into Business, and three preparation jobs. `scripts/ops/business_space_rows.sql` read `business_accounts 1, business_connections 3, business_import_events 2, business_conversations 0, spaces 2` (`outputs/probe_business_seed_act-at-B4.txt`).
2. Build 1 (read only) and Build 2 read the same person. Both showed the same leak, as listed in breaks 2 above (`outputs/probe_business_read_b1-at-B4biz.txt`, `probe_business_read_b2-at-B4biz.txt`).
3. Build 2 wrote across spaces, as listed in break 3 (`probe_business_writes2_*`, `probe_business_grant_b2-at-B4biz.txt`).
4. Activation, back in place, showed Business expenses `[build2_expense 55.00, business_expense 250.50]` and the Business receipt `confirmed` while its expense is in Personal. Personal accounts read correctly (`outputs/probe_business_verify_act-at-B4biz.txt`).
5. Build 2 account deletion returned `done`. The auth user, space, accounts, WhatsApp link and Storage objects all reached 0, and the run recorded `storage: deleted` (`probe_business_delete_b2-at-B4biz.txt`).

`business_space_rows.sql` detects the condition. It reads non-zero for as long as any Business row exists, which is when a Build 2 rollback leaks, and its counts stayed the same through Build 2's writes. It counts root rows (accounts, connections, import events, conversations) and spaces. It does not count records, Storage objects or WhatsApp links, but none of those exist without a counted root row or space. It also reads non-zero for a space with no rows. Before seeding it read `spaces 1`, a leftover empty space from the account probe, so it blocks conservatively. After both test persons were deleted it read `spaces 1` again, the same leftover space.

## Scenario 4: B2 and B3 under Build 2 code

At +B2 and +B3 no running code writes the job column or the WhatsApp tables. Only activation does, and it needs B4. So the data checks ran at +B4 after activation seeded. That is the rollback case.

- Build 2 lists and reads drafts that carry `preparation_job`, whether `review_ready` or `queued`.
- Build 2 prepared a draft that activation had left `queued` with a pending attempt. It moved the draft to `review_ready` and left the job metadata as it was (`claimed: false`, attempt 1). When activation later ran that attempt, `run_attempt` returned `document_attempt_superseded`. The draft stayed `review_ready` and nothing was extracted twice.
- Build 2 disconnected the WhatsApp-captured Business connection without error. The inbound message row stays `captured` with its connection id, because disconnect does not delete the connection.
- Build 2 account deletion with WhatsApp rows completed, and the rows cascaded away.
- Build 2 suites at +B2 and +B3 matched +B1 except for the inventory and backlog tests.

## Scenario 5: what each code rollback and schema rollback means

Facts are from `outputs/revert_facts.txt` (catalog at +B4 with data) and from the runs above. No revert SQL was written or run. Code X on the state before migration M is the measured result of reverting M while X runs.

**B1, document sources in private Storage.**
Code rollback (Build 2 to Build 1, B1 kept): Build 1 works on its own documents. For documents Build 2 stored, see break 1. Rows Build 1 writes in the window are bytea, and Build 2 serves them after a redeploy.
Schema rollback: it removes the bucket row and file limits, five columns (`source_bucket`, `source_path`, `source_media_type`, `source_size_bytes`, `source_sha256`) and five constraints. Every Storage-backed row (6 at the end of this rehearsal) loses its only pointer. The bucket cannot be dropped while it holds objects (`objects_bucketId_fkey`), so a full revert deletes the files. Build 2 and activation break (Build 2 at C). Build 1 works.

**B2, preparation job column.**
Code rollback (activation to Build 2): works. Build 2 ignores the column. Scenario 4 shows a draft prepared during rollback is not prepared again by activation.
Schema rollback: it drops `preparation_job` and the pending index. In-flight attempt ids are lost (3 rows had one). Build 1 and Build 2 work, as they did at +B1. Activation breaks, from code reading.

**B3, WhatsApp intake tables.**
Code rollback: Build 2 has no `/webhooks/whatsapp` or `/whatsapp` routes, so intake stops. Existing rows sit unused. Disconnect and account deletion work.
Schema rollback: B3 cannot be reverted while B4 is in place. B4 adds `destination_space_id`, `whatsapp_sender_links_destination_space_fkey` and the `fill_sender_link_space` trigger to `whatsapp_sender_links`, and the `whatsapp_capture_same_space` trigger to `whatsapp_inbound_messages`. Dropping the tables loses sender links, so senders must link again. It also loses the provider message digests that de-duplicate redeliveries. Build 1 and Build 2 work (+B2). Activation breaks.

**B4, Business spaces.**
Code rollback (activation to Build 2): the Personal leak and cross-space writes in breaks 2 and 3. `business_space_rows.sql` reading non-zero is the signal. Account deletion still works. B4's triggers still refuse a Business household grant and a capture into a Personal connection, so the database blocks those two paths during a rollback.
Schema rollback: it removes `spaces`, `business_space_of`, `owner_space_id` on accounts, connections, import events and conversations, `destination_space_id`, and the four triggers. It also restores the older `deletion_place_unit` and the ten-argument `create_financial_account`. Dropping the columns turns every Business row into a Personal row with no record of which was which. Deleting the spaces first deletes every Business account, connection, import event, conversation and sender link instead, because all five foreign keys to `spaces` are `on delete cascade`. Build 2 works (+B3). Activation breaks: its eleven-argument call and `spaces` reads fail.

## Test environment notes

- In every run, two tests fail on the macOS scipy loader (`ImportError: dlopen ... _spropack ... zero-fill section`). They are `tests/test_search_postgres.py::test_asset_rollup_pair_symbol_normalization_matches_memory_contract` and `tests/test_guest_auth_local_supabase.py::test_guest_run_through_real_flag_off_tool_corridor_settles_simulation`. The second fails on the same import. `tests/test_home_country.py` is not in the Postgres file set.
- `outputs/probe_business_delete_b1-at-B4biz.txt` ran Build 1 code. Its line is labeled `D_build2_account_deletion` because the label was fixed after that run. The probe now prints `D_account_deletion`.
- At the end the bucket held 40 unreferenced objects. Most are leftovers from test files. This log attributes only the 2 objects from Scenario 1 and the 6 objects from Build 1's deletion of the Business person.

## Cleanup

The stack was stopped with `supabase stop --no-backup` and its containers and volumes removed. The three `compat-*` worktrees were removed. Build 2's local merge commit was never pushed.
