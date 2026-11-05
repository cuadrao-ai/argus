# Business B1 rerun at the combined head: search, hand completion and isolation

Label: **local services, stub extractor, replayed WhatsApp fixtures; not provider or hosted proof.**

Head: `380e38570c7364f671dd36622133f020a665df48` on `claude/business-attention`. It merges the isolation work, Business search (`2fb6053d9`, `99d30b649`) and the receipt next-step fixes (`3ab05433f`, `2e53e9580`, `bafef2506`). No source file was changed for this run.

## Setup

- API: uvicorn from this worktree on http://127.0.0.1:8661, with Supabase persistence on the disposable local stack `argus-biz-spaces` (DB 57782). The stack was reset with this worktree's 119 migrations before the runs.
- Web: `next dev` from this worktree on http://localhost:3661.
- Auth: real local Supabase Auth. Owners were created with the local admin API: one pair for scenarios 1 to 3 and one pair for the scenario 4 regression.
- Flags: the Business, ingestion, document, document-job and WhatsApp-intake flags were on only in these two local processes. WhatsApp outbound was off.
- Network: the API process had `HTTP(S)_PROXY` and `ALL_PROXY` pointed at a dead local port, with `NO_PROXY=127.0.0.1,localhost`. No OpenRouter key and no vision model were set.
- Extractor: a scripted stub replaced the document extractor. `reads.json` maps each synthetic receipt's sha256 to a list of outcomes. Call n plays outcome n, counted in a call log that survives restarts. An outcome is a fixed read, a failure code (the provider failure is marked retryable, as the real extractor marks it), or a hold that keeps the call in flight. Every call is logged; see `b1-stub-calls.txt`.
- WhatsApp: deliveries were signed replays of `tests/fixtures/whatsapp`. Media came from local files, and Meta was never contacted.
- Ids are aliased (`<A>`, `<web receipt>`, and so on). Row evidence comes from direct SQL on the local stack (`counts.py`, plus `events.py` for the import events and stored batch of each receipt) and from API reads.

## Results

| # | Check | Result | Evidence |
| --- | --- | --- | --- |
| 1 | "Ferretería" after a full reload of /biz: one Expenses row, opening it shows Saved expense for the web receipt, Download sha256 equals the upload | PASS | 1 expense row, 0 receipt rows; API `expenses` = [web expense]; sha256 `b3b675045581` both |
| 1 | "Colmado" after a full reload: one row, opens the WhatsApp receipt, Download sha256 equals the delivered media | PASS | API `expenses` = [WhatsApp expense]; sha256 `0cde8fde9397` both |
| 1 | The Personal expenses with the same merchants (1,200.00 and 310.00) appear in neither the omnisearch nor `GET /business/search` | PASS | personal amount absent from the result rows; personal ids absent from the API body |
| 1 | Owner B's search finds nothing of A's | PASS | 10 queries, all 200 with 0 expenses and 0 receipts; no A id in B's `q=a`; B's omnisearch shows "No results found" |
| 2a | No purchase: the message | **FAIL** | `attention` = `several_purchases` ("couldn't match this receipt to one purchase"); expected `no_purchase_found`. See Defects |
| 2a | No purchase: no retry and no Prepare button, fields open, filled by hand, one expense, read kept as evidence, same-key burst and stale replay | PASS | `preparable` false, `enterable` true; accepted +1; 1 PATCH and 1 confirm from the double-click; evidence unchanged |
| 2a2 | A purchase row with no receipt details (API upload): `no_purchase_found` message, entry by hand, one expense | PASS | 1 read event goes from open to dismissed; owner entry accepted with the expense |
| 2b | Several purchases: message, no retry, hand entry, one expense | PASS | 2 read events go from open to dismissed; 1 owner entry accepted |
| 2c | Ambiguous purchase: message, no retry, hand entry, one expense | PASS | the read made no import event; evidence (receipt details) kept |
| 2d | Provider failure: needs_attention with no batch | PASS | `ai_unavailable`; `read_batch_stored` false; 0 events |
| 2d | No retry without the click; "Try again with AI" sends `X-Extraction-Consent: true` and makes exactly 1 new stub call | PASS | 0 calls in 15 s with list and overview reads; prepare without consent is 422 with no call; the click made 1 request and 1 call |
| 2d | Hand entry after the second failure: one expense; no read exists to show | PASS (corrected) | the harness check printed FAIL. The batch stored after entry is the owner's entry (`metadata.entered_by = "owner"`), not an AI read; evidence stays null |
| 2e | Kill -9 mid-preparation, restart, sweep: `needs_attention` `outcome_unknown` with 1 stub call | PASS | settled 304 s after the restart; log line "Document preparation outcome unknown; waiting for the owner" |
| 2e | No retry without the click; the click sends consent and makes exactly 1 new stub call | PASS | call 2 only after the click |
| 2e | After the retry read several purchases: message, hand entry, one expense, evidence visible, 2 reads dismissed | PASS | accepted +1; evidence before and after equal |
| 2 | API restart, then each case's confirm replayed with its Idempotency-Key | PASS | all 6 return 200 with the same expense; counts and per-receipt events identical before and after |
| 3 | A's Personal account and B's Business account in `PATCH /review` on a saved, a review-ready and a several-purchases receipt | PASS | 6 of 6 return 404 `financial_account_not_found`; detail and rows unchanged; the control with A's Business account returns 200 |
| 4 | Isolation regression, steps 1 to 7 | PASS | 26 of 26; see `regression-isolation-log.md` |
| 4 | Step 8, flag off | PASS | Business routes 404 `business_unavailable` with the API flag unset, `/business/search` included; /biz shows the not-found page with the web flag unset |

## Counts

Scenarios 1 to 3, owner A, Business rows. On the Personal side A went from 0 to 1 account (the account the cross-scope checks use) and two Personal expenses (the same-merchant controls), with no import events or documents:

| | accounts | documents | import events open | import events accepted |
| --- | --- | --- | --- | --- |
| Before | 0 | 0 | 0 | 0 |
| After | 1 | 11 | 3 | 8 |

The 8 accepted events are 2 from scenario 1 and 6 from scenario 2: one expense per receipt. The 3 open events belong to the scenario 3 receipts, which were left unconfirmed. Owner B ended with 1 space, 1 Business account and no documents or events. The stub made 12 calls: 11 receipts read once, plus one consented retry each for 2d and 2e. Full counts are in `b1-counts-before.json` and `b1-counts-after.json`. The regression's counts are in `regression-counts-*.json`, and its owner A ended with Business accepted 3 and documents 4, as at `ce116998e`.

## Defects

- **Low. A read with receipt details and no purchase row shows the several-purchases message.** Reproduce with stub outcome `{"observations": [], "receipt": {...total 845.00}}`. The receipt ends with `error_code` `no_financial_observations` and `attention` `several_purchases`, and the page says "Cuadrao couldn't match this receipt to one purchase." `docs/API_CONTRACT.md` names `no_purchase_found` for a read with no purchase. The cause is `src/argus/domain/ingestion/documents/extractor.py:87`. It sets `receipt_ambiguous` when `len(receipt_rows) != 1`, which includes zero rows. Then `src/argus/domain/ingestion/receipt_review.py:152-153` checks that issue before "no purchases", and `src/argus/domain/business/receipts.py:183-185` maps every blocker other than `no_purchase_found` to `several_purchases`. The flow still completes: hand entry, one expense, evidence kept. The unit test `test_a_document_with_no_receipt_purchase_sets_the_reading_aside` reaches `no_purchase_found` only because its stub drops the receipt details. Not fixed here.

## Observations

- Upload and prepare share a limit of 5 POSTs per minute per owner (`src/argus/api/documents.py:122`). The first attempt of this run hit 429 `document_rate_limited` on the sixth receipt in a minute and stopped. The prepare-without-consent probe also counts. The harness now waits for the window, and those waits are cut from the video. `b1-results.json` lists every window.
- A read with no receipt details (2a2) has `evidence` null before and after entry. The dismissed purchase row it found (CLARO INTERNET 1,890.00) is kept as history but is not shown to the owner. This matches the contract, which defines `evidence` as the receipt details.
- In 2a and 2c the read created no import event, so there was nothing to dismiss. The dismissal was exercised by 2a2 (1 event), 2b (2) and 2e (2). Each was kept with state `dismissed`, and the total event count rose only by the owner's entry.
- The review page does not poll. A receipt open while the sweep settles keeps showing "Preparing" until the page loads again.
- The only browser console error was `ERR_CONNECTION_REFUSED` during the kill -9 outage.

## Video

`business-b1-rerun-journey.mp4` (79 s, 1280x800) is owner A's Playwright video, converted with ffmpeg in a local container with no network. It shows scenario 1 (both confirms, the reload, both searches, opened receipts and downloads) and all of scenario 2, including 2(a) and 2(e). Idle segments were cut, found by the journey's own timing and confirmed by ffmpeg `freezedetect`:

- 31 to 61 s: the browser was idle while 2a2's API upload waited out the rate limit.
- 81 to 85 s and 102 to 132 s: rate-limit pacing.
- 88 to 102 s and 313 to 327 s: the 15 s no-click windows of 2d and 2e. No stub call happened in either.
- 139 to 307 s: the dead worker's 5-minute lease running out before the sweep settled 2e.
- 333 to 337 s: the restart for the replay check.
- 343 s to the end: scenario 3 and owner B's search ran by API and in a separate browser.

The uncut recording lasted 394 s.

## Files

- `b1-journey-log.md`: every scenario 1 to 3 step, with HTTP lines, per-receipt rows and check details.
- `b1-results.json`: the checks, the cut windows and the timeline marks.
- `b1-stub-calls.txt`: every stub call, by alias.
- `regression-isolation-log.md`: the scenario 4 run of the earlier harness at this head.
- `regression-isolation-reads.json`: the step 6 leak scan.
- `screenshots/`: the search results, each attention screen before entry, the 2d and 2e screens after the retry, and the step 8 flag-off screens.
