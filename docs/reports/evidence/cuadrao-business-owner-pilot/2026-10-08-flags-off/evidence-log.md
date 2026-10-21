# Flags-off rehearsal for the Business pilot and document intake

The rehearsal ran on 2026-10-08 against branch `claude/business-spaces` at head `76273cf2c` (the activation code), read-only from its worktree. Everything ran on a disposable local Supabase stack. Nothing hosted was touched.

The founder asked for proof, before activation, that turning the flags off keeps Personal and Business apart and still lets people delete their files and accounts. The founder also asked what people can still read and download. This log answers both questions for four flag states (S1 to S4) and for the web flag.

## Answer

- **Separation holds in every state.** No Personal read showed a Business row or counted a Business amount. Every `/api/v1/business/*` and WhatsApp route answered 404, signed in and signed out. Owner B saw nothing of owner A's.
- **Deletion works in every state.** For each state, a freshly seeded owner with Personal and Business data was deleted with `POST /api/v1/account/delete` while Business was off. Each run finished `done` on the first call. Every Personal table, every Business table and the Storage prefix went to zero, and owners A and B did not change.
- **Turning the flags back on restores Business intact.** After S1, A's Business counts, receipts, expense-to-receipt links and totals matched the pre-S1 snapshot exactly.
- **One latent defect.** Personal conversation reads do not filter `conversations.owner_space_id`. No route on this branch writes a Business conversation, so nothing leaks today. See D1.
- **S3 (the Build 2 rollback lever) hides Personal documents too.** With document extraction off, A can no longer open or download a Personal document original, although A can still delete it. This is a product decision, not a code defect. See O1.

## Setup

- **Stack.** Supabase CLI 2.118.0, `project_id` `argus-biz-flagsoff`, config copied from the `argus-biz-spaces` stack with new ports. API 57791, DB 57792, shadow 57790, Studio 57793, mail 57794, analytics 57797, inspector 57798, pooler 57799. Studio, edge runtime, imgproxy, vector, logflare and supavisor were excluded at start.
- **Migrations.** All 119 of the branch's migrations were applied by `supabase start`, the last being `20261008140000_business_spaces.sql`. The private bucket `financial-document-sources` existed.
- **API.** `harness/launcher.py` runs the branch's `argus.api.main:app` on 127.0.0.1:8641 with real local Supabase persistence and auth. Two seams are replaced, as in the earlier isolation rehearsal. The document extractor is a stub that returns fixed reads keyed by sha256. WhatsApp media is served from local files. Outbound WhatsApp is off. `HTTP_PROXY`, `HTTPS_PROXY` and `ALL_PROXY` point at a dead local port. `PYTHONDONTWRITEBYTECODE=1` keeps the worktree free of bytecode.
- **Restarts.** `harness/api.sh` stops the API and starts it again for every state. The launcher prints the effective flags at start. `results/api-flag-lines.txt` holds the nine start lines.

### Seeded data

All seeding went through the real API with every flag on (`harness/seed.py`). The receipts are synthetic PNGs marked "SAMPLE DATA".

- **Owner A, Personal.** One checking account, one 1,200.00 DOP expense through `/financial-activities` (preview, then write), one document uploaded to `/financial-documents` without AI (stored in private Storage), and one conversation from `POST /conversations`. That route makes no model call.
- **Owner A, Business.** A started space and one Business checking account. One web receipt was uploaded with AI consent, read by the stub, reviewed and confirmed as a 1,850.00 DOP expense, with its original kept. One receipt was uploaded without AI and left unconfirmed in the Inbox. A WhatsApp link was made from a link code redeemed by a signed text delivery. One receipt was captured from a signed image delivery, with local media.
- **Owner B, bystander.** One Personal account, expense and document. One Business space and account, a hand-entered Business expense and one Inbox receipt.
- **Owners D_S1 to D_S4.** Each was seeded like A, with every flag on, right before its state. These owners are the ones disconnected and deleted. A stays a read-only subject across all states.

### Environment per state

Every state also set `ARGUS_FINANCIAL_ACCOUNTS_ENABLED=true`, `ARGUS_ACCOUNT_DELETION_ENABLED=true`, `ARGUS_WHATSAPP_OUTBOUND_ENABLED=false` and `APP_ENV=local`.

| Flag | ON | S1 | S2 | S3 | S4 |
|---|---|---|---|---|---|
| `ARGUS_INGESTION_ENABLED` | true | true | true | true | false |
| `ARGUS_DOCUMENT_EXTRACTION_ENABLED` | true | true | true | false | false |
| `ARGUS_DOCUMENT_JOBS_ENABLED` | true | true | true | true | false |
| `ARGUS_BUSINESS_PILOT_ENABLED` | true | false | false | false | false |
| `ARGUS_WHATSAPP_INTAKE_ENABLED` | true | true | false | true | false |

The web check ran with `NEXT_PUBLIC_BUSINESS_PILOT_ENABLED` unset and the API in S1.

## Method

`harness/probe.py <STATE>` runs every check below and writes `results/<STATE>.json`. The same script ran with every flag on first (`results/ON.json`) as a positive control. That run proved the Business routes answer 200 and each Business original downloads with a matching sha256, so the later 404s mean "off", not "broken".

The leak scan looks for ids, merchant names and account names inside each JSON response. `results/instrument-check.txt` shows the scan finding A's own Personal ids in A's Personal reads, so an empty result means absent, not an unread body.

Counts come from `harness/counts.py`. They are row counts per owner, split by `owner_space_id` (null means Personal), plus Storage objects counted by name prefix. No object content was read. The only bytes read were API downloads, compared by sha256.

## Checks

| Id | Check | ON | S1 | S2 | S3 | S4 |
|---|---|---|---|---|---|---|
| 1.1 | 18 Personal reads as A show no Business row and nothing of B or D (accounts, home, purchases, activity options, documents, connections, imports, accepted imports, plan, conversations, account activity, six financial searches, conversation search) | PASS 18/18 | PASS 18/18 | PASS 18/18 | PASS 18/18 | PASS 18/18 |
| 1.2 | Home totals are Personal only: DOP gross purchases 120000 minor, one account | PASS | PASS | PASS | PASS | PASS |
| 1.3 | Positive control: A's own Personal rows appear on the same reads | PASS | PASS | PASS | PASS | PASS |
| 1.4 | Personal routes answer 404 for A's Business account, its activity, the Business expense and its history, the Business import event, each Business receipt and its original, and an expense preview on the Business account | PASS | PASS | PASS | PASS | PASS |
| 1.5 | Every `/business/*` and WhatsApp route answers 404, signed in and signed out (44 requests). With flags on, the Business GET routes answer 200 | PASS | PASS | PASS | PASS | PASS |
| 1.6 | A signed WhatsApp image delivery from A's linked number is refused and nothing is recorded | n/a | PASS | PASS | PASS | PASS |
| 1.7 | Owner B sees nothing of A's or D's, and A's ids answer 404 to B | PASS | PASS | PASS | PASS | PASS |
| 2.1 | Personal document. S1 and S2: read and download with a matching sha256. S3 and S4: read and download answer 404, with no other route exposing the file | PASS | PASS | PASS | PASS | PASS |
| 2.2 | Business receipts cannot be listed or downloaded through any route. With flags on, each original downloads with a matching sha256 | PASS | PASS | PASS | PASS | PASS |
| 3.1 | D's Business receipt and WhatsApp receipt cannot be disconnected through the Personal route, and no row changes | n/a | PASS | PASS | PASS | PASS |
| 3.2 | D's Personal document disconnect removes its Storage object (prefix count 1 to 0). In S4 the route answers 404 and the object stays until account deletion | n/a | PASS | PASS | PASS | PASS |
| 3.3 | Account deletion of D, who has Business data, finishes `done` while Business is off | n/a | PASS (rerun) | PASS | PASS | PASS |
| 3.4 | After deletion, zero rows for D in every table counted and zero Storage objects under D's prefix | n/a | PASS (rerun) | PASS | PASS | PASS |
| 3.5 | Owners A and B unchanged by D's disconnect and deletion | n/a | PASS | PASS | PASS | PASS |
| 4.1 | After S1, flags back on: A's Business data is identical to the pre-S1 snapshot | n/a | PASS | n/a | n/a | n/a |
| 5.1 | Web with the Business flag unset: `/biz` shows the not-found page, no Business navigation, no Business or WhatsApp API call | n/a | PASS | n/a | n/a | n/a |

The totals were ON 25/25, S1 29/31 on the first run plus 29/29 on the deletion rerun, S2 31/31, S3 31/31 and S4 31/31. Checks 4.1 and 5.1 ran once each.

S1 "rerun" means this. The first S1 deletion call came from the harness without the required `{"confirm": true}` body, so the API answered 422 six times and then 429 twice. No deletion run started and D_S1 kept all its rows (`results/S1.json`). The harness was fixed and `probe.py S1 --delete-only` deleted the same owner (`results/S1-delete.json`). That rerun's 3.3 first read FAIL because the harness looked the run up by `subject_hash`, which a finished run sets to null by design (`src/argus/domain/account_deletion/service.py:1085`). The stack held exactly one run row, created by that call, with status `done`. The record was corrected by hand with a note, and the lookup now also matches finished runs by time.

## What A can read, download and delete

"Read" and "download" were tested on A. "Delete" was tested on that state's D owner. Account deletion removed every item in every state, so it is not repeated in each cell.

| A's item | ON (control) | S1 | S2 | S3 | S4 |
|---|---|---|---|---|---|
| Personal account | readable | readable | readable | readable | readable |
| Personal expense | readable | readable | readable | readable | readable |
| Personal conversation | readable | readable | readable | readable | readable |
| Personal document | readable, downloadable | readable, downloadable, deletable by disconnect | readable, downloadable, deletable by disconnect | hidden (404); still listed in `/financial-connections`; deletable by disconnect | hidden (404); no disconnect (ingestion 404); removed only by account deletion |
| Business account | readable (Business routes only) | hidden | hidden | hidden | hidden |
| Business expense from the receipt | readable (Business routes only) | hidden | hidden | hidden | hidden |
| Business receipt, confirmed | readable, downloadable (Business route) | hidden, not downloadable, not deletable alone | same as S1 | same as S1 | same as S1 |
| Business receipt, Inbox | readable, downloadable (Business route) | hidden, not downloadable, not deletable alone | same as S1 | same as S1 | same as S1 |
| Business receipt, WhatsApp | readable, downloadable (Business route) | hidden, not downloadable, not deletable alone | same as S1 | same as S1 | same as S1 |
| WhatsApp link | readable | hidden; revoke answers 404 | same as S1 | same as S1 | same as S1 |

"Hidden" means every Personal route answers 404 for the id and every Business and WhatsApp route answers 404 outright. With flags on, Personal routes already answered 404 for Business ids. A Business receipt has no single-delete route in any state. In S1 to S4 the Personal disconnect route refused it.

## Deletion counts

Counts for each D owner. "Seeded" is before any step in that state. "At deletion" is after the Personal document disconnect. "After" is after `POST /account/delete`.

| Table or object | Seeded | At deletion, S1 to S3 | At deletion, S4 | After, every state |
|---|---|---|---|---|
| `auth.users` | 1 | 1 | 1 | 0 |
| `spaces` (created_by) | 1 | 1 | 1 | 0 |
| `financial_accounts`, Personal / Business | 1 / 1 | 1 / 1 | 1 / 1 | 0 / 0 |
| `financial_source_connections`, Personal / Business | 1 / 3 | 1 / 3 | 1 / 3 | 0 / 0 |
| `financial_import_events`, Personal / Business | 0 / 1 | 0 / 1 | 0 / 1 | 0 / 0 |
| `financial_import_observations` | 1 | 1 | 1 | 0 |
| `financial_records` | 2 | 2 | 2 | 0 |
| `financial_document_extractions` | 4 | 3 | 4 | 0 |
| `conversations`, Personal / Business | 1 / 0 | 1 / 0 | 1 / 0 | 0 / 0 |
| `whatsapp_link_codes` | 1 | 1 | 1 | 0 |
| `whatsapp_sender_links` | 1 | 1 | 1 | 0 |
| `whatsapp_inbound_messages` to D | 2 | 2 | 2 | 0 |
| `whatsapp_inbound_messages` from D's linked senders | 2 | 2 | 2 | 0 |
| Storage objects under `<D id>/` | 4 | 3 | 4 | 0 |

The 3-row `financial_document_extractions` figure was measured for S1. For S2 and S3 only the Storage count was measured after disconnect (3). Every accepted deletion call answered `200 done []` the first time. Each run row reads `status=done`, `storage=deleted` and `analytics=recorded_by_fake`. The fake analytics adapter is allowed only because `APP_ENV=local`. A deployed environment without the PostHog deletion settings would leave `analytics` pending.

At the end, the stack held exactly owners A and B. Two auth users, six Storage objects (A 4, B 2), two spaces, one WhatsApp link, one link code and three inbound messages, all A's. Four deletion runs, all `done`. B's counts equal the counts recorded right after B was seeded (`results/final-counts.json`).

## Flags back on after S1

The API went from S1 back to every flag on. `harness/flagsback.py compare pre-S1` found no difference from the snapshot taken before S1 (`results/flagsback-S1.txt`).

- The counts were unchanged. A still had 1 space, 1 Business account, 3 Business receipts, 1 Business import event, 1 sender link and 4 Storage objects.
- The one expense `6363e120` still links to receipt `bf47ba3b` for 1,850.00 DOP on the same account.
- The receipts were one `confirmed` (web) and two `saved` (web Inbox, WhatsApp Inbox). The Inbox held the same two ids.
- The overview totals were DOP 1,850.00 for 1 expense. The WhatsApp link was active.
- The fingerprint of the database link map was `f70030d25256ae8c` before and after.

## WhatsApp deliveries while intake is off

In S1 to S4 a correctly signed delivery answered `404 whatsapp_unavailable`. No inbound record, connection or Storage object was written, so the delivery was refused, not ignored. The flag check runs before the signature check (`src/argus/api/whatsapp.py:227`).

After S1, with flags on, the delivery S1 had refused was posted again. It answered 200 and a new `captured` inbound record pointed at A's existing WhatsApp receipt. The media bytes matched that receipt, so no new receipt appeared (`results/replay-S1.txt`). A delivery refused while intake is off is captured if the provider redelivers it after intake comes back. Whether Meta redelivers a 404'd webhook, and for how long, was not tested.

## Web flag

`results/web-flag-off.json` and two screenshots record the web run. The web ran under `next dev` on port 3641 against the API in S1.

- A signed in through the login form. The home page showed no Business navigation and no Business merchant or account name.
- `/biz` signed in rendered the Next.js not-found page with HTTP 200 and no Business navigation.
- A signed-out `GET /biz` also returned the not-found page with HTTP 200. A path with no route answered 404.
- The web made no `/business` or `/whatsapp` API call.

The 200 status on the not-found page is a `next dev` behavior already noted in the isolation rehearsal. A production build was not checked.

## Defects

### D1. Personal conversation reads ignore `owner_space_id` (latent, P2)

The schema allows a Business conversation (`conversations.owner_space_id`, migration `20261008140000_business_spaces.sql:669`). The Personal conversation reads filter only on `user_id`.

- `src/argus/domain/supabase_gateway.py:608` holds the list query.
- `src/argus/domain/supabase_gateway.py:644` holds `get_conversation`.
- `src/argus/domain/postgres_keyset_reader.py:43`, `:75` and `:88` hold the keyset list queries.
- The conversation search behind `GET /api/v1/search` returns the same rows.

No route on this branch writes a Business conversation, so no real data leaks on the activation code. The gap becomes real when a build writes Business conversations, for example the Business chats lane. Under the founder's rollback model, the minimum compatible code for that data must filter these reads. These routes are not flag-gated, so turning flags off would not hide such a conversation.

To reproduce, start the stack and API as above with any flag state. Insert a row into `public.conversations` with `owner_space_id` set to A's space id. As A, call `GET /api/v1/conversations` and `GET /api/v1/search?q=<its title>`. Both return it, and `GET /api/v1/conversations/{id}/messages` answers 200. Recorded in S4 in `results/planted-business-conversation.txt`. The probe row was inserted by SQL and deleted right after.

No other defect was found.

## Observations for decision

- **O1. S3 hides Personal documents.** Every `/financial-documents` route, including `GET /{id}/source`, depends on `require_document_surface`, which requires `ARGUS_DOCUMENT_EXTRACTION_ENABLED` (`src/argus/api/documents.py:97`). In S3 a person cannot open or download a Personal document original, although the file is kept. The document still appears in `GET /financial-connections` as a `statement` connection, and disconnect still deletes it. If the rollback lever should keep reads and downloads, that needs a code change.
- **O2. S4 has no per-document delete.** With ingestion off, `/financial-connections/{id}/disconnect` answers 404. Account deletion still removes the file.
- **O3. No WhatsApp unlink while Business is off.** `DELETE /whatsapp/link` answers 404 in S1 to S4. Intake also refuses deliveries in those states, so nothing is captured.
- **O4. Late capture on re-enable.** See the WhatsApp section above.
- **O5. Finished deletion runs are anonymous.** A finished run row sets `user_id` and `subject_hash` to null. An operator cannot look up a finished run by person.

## Network and cleanup

- **No provider was called from the API.** The stub extractor logged six calls, all during seeding with every flag on (`results/stub-calls.txt`). `api.log` has no proxy or connection error and no OpenRouter or Meta host. No Meta, OpenRouter or hosted Supabase call was made, and nothing was pushed or `db push`ed. `supabase start` pulled no image.
- **The web dev server may have reached Google Fonts.** The web's `app/layout.tsx` uses `next/font/google`, and the run did not block that fetch. Requests from the browser to hosts other than the local API were not recorded.
- **Two seeds failed partway.** The first seed attempts failed, once on the conversation response shape and once on a category id. The two partial users were removed through the local admin API, with their three Storage objects, before the real seed.
- **Cleanup.** The API and web were stopped. `supabase stop --no-backup` removed the `argus-biz-flagsoff` containers and volumes. Ports 57790 to 57799, 8641 and 3641 were free afterwards. No other stack was touched. `next dev` wrote to the worktree's ignored `web/.next`.

## Rerun

The harness is in `harness/`. Put `stack.env` (output of `supabase status -o env`) and `wa.env` (local `WA_APP_SECRET`, `WA_VERIFY_TOKEN` and `WA_SENDER_KEY` values) next to the scripts. Then run these steps in order.

1. Run `api.sh start ON`, then `seed.py A full` and `seed.py B bystander`.
2. Run `probe.py ON`, then `flagsback.py snapshot pre-S1`.
3. For each state X: run `api.sh start ON`, then `seed.py DX full`. Restart with `api.sh start X` and run `probe.py X`.
4. After S1, run `api.sh start ON`, then `flagsback.py compare pre-S1` and `flagsback.py replay S1`.
5. Run `web.sh` with the API in S1, then `node webcheck.mjs`.

The scripts write `world.json` with the test users' local passwords. That file stays in the scratch folder and is not committed.
