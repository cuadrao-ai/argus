# Business capture-to-expense (B1) and Personal isolation: local end-to-end evidence log

Label: **local services, stub extractor, replayed WhatsApp fixtures; not provider or hosted proof.**

Run: 2026-10-08T06:12:04.823Z. Code: branch claude/business-spaces at ce116998e83d0d4e0aae8d7b2e1e7e9e7906d4da. API http://127.0.0.1:8621 (uvicorn from this worktree, Supabase persistence on the disposable local stack argus-biz-spaces, DB 57782, reset before the run, 119 migrations). Web http://localhost:3621 (next dev from this worktree). Real local Supabase Auth; owners A and B created with the local admin API. Flags were on only in the API and web process env. The API process had HTTP(S)_PROXY pointed at a dead local port with NO_PROXY=127.0.0.1,localhost, so any outbound provider call would fail. The stub extractor returns a fixed read per synthetic receipt digest and logs each call; WhatsApp deliveries are signed replays of the repo fixtures in tests/fixtures/whatsapp, with media served from local files; outbound replies off.

Ids are shown by alias: <A>, <B>, and names such as <web receipt>. Counts come from `counts.py` (direct SQL on the local stack). Business rows are those with `owner_space_id` set; Personal rows have it null.

Files: `business-isolation-journey.mp4` is owner A's browser for the whole session (Playwright video, converted with ffmpeg in a local container with no network). It covers steps 1, 2, 3, 4b and 5, then the end of 4c. About 286 s of a still frame, the browser idle on /biz while steps 6 and 7 ran by API and the dead worker's 5-minute lease ran out, were cut at 0:40; the clip is 45 s. `counts-before.json` and `counts-after.json` are the per-owner counts before step 1 and after step 7 (step 8 changes no rows). `isolation-reads.json` holds the step 6 leak scan. `search-ferreteria.png`, `flag-off-api.png` and `flag-off-web.png` are screenshots.

Step 4c ran last in time: the journey polled the interrupted preparation after steps 5 to 7, so its section appears after step 7.


## Result

| Step | Result | Backing rows |
| --- | --- | --- |
| 1. Web upload, review and correct | PASS | Business `import_events_accepted` 0 to 1; stored merchant "Ferretería La Esquina", 3400.00; evidence 3450.00 |
| 2. Without AI | PASS | accepted 1 to 2; evidence null; 0 extractor calls |
| 3. WhatsApp | PASS | accepted 2 to 3; 1 captured message after a replay; source sha256 equals the delivered media |
| 4. Duplicates and restart | PASS | accepted stays 3 through same-key confirms, the kill -9 and the restart; the interrupted job settled to `needs_attention` with 1 extractor call |
| 5. Reload and find | PASS, search GAP | 3 expenses listed after reload; 3 downloads match by sha256; no Business search exists |
| 6. Personal and Business separate | PASS except one route | no cross-scope ids in 12 Personal and 6 Business reads; two documents for one file; FAIL: the review route answers 422, not 404, for a Personal account id |
| 7. Denied access | PASS | 23 probes by owner B all 404; 7 signed-out probes all 401 |
| 8. Flag off | PASS | 18 Business probes 404 `business_unavailable`; /biz renders the not-found page |

Findings:

- FAIL, low. `PATCH /api/v1/business/receipts/{id}/review` with `fields.account_id` set to the owner's Personal account answers 422 `financial_account_not_found`, not 404. A random account id gets the same 422, so it does not reveal that the Personal account exists. The check is `src/argus/domain/ingestion/reconcile/service.py:137-145` (owned accounts are listed in the Business scope), and `src/argus/api/routers/business.py:115-118` maps every `ReconcileError` outside `_CONFLICTS` to 422. `POST /api/v1/business/expenses` with the same id answers 404. `docs/API_CONTRACT.md` does not name the review route's account error.
- GAP. Business has no search. No `/api/v1/business` route takes a query, and `GET /business/expenses` ignores `q`. The Search button in the /biz shell calls the conversation search `GET /api/v1/search` and finds nothing for "Ferretería" or "Colmado". Not built.
- Observation. `/biz` with the web flag off renders the Next.js not-found page with HTTP 200 under `next dev`. `web/app/biz/page.tsx:16` calls `notFound()`, and a path with no route answers 404 on the same server. A production build was not checked.
- Observation. The Inbox list is fetched on page load and after the owner's own actions, and is not polled. A WhatsApp receipt that arrives while /biz is open does not appear in the Inbox until the page loads again.
- Observation. After the sweep, the interrupted receipt shows the generic "Something went wrong with this receipt. It is still saved." for `document_preparation_outcome_unknown`. It offers manual entry only, with no Prepare with AI retry (`web/components/business-app/ReceiptReviewPanel.tsx:256-274` shows the prepare button only for `saved`).
- Observation. With the API flag off and the web flag on, /biz shows the Business shell with its load error and live Upload receipt and Record expense actions. The two flags must move together.
- Observation. Every /biz load sends `POST /api/v1/business/space`, which answers 200 after the first time.

## 0. Start

Owners A and B exist in local Supabase Auth. Neither has a space.

DB rows (owner A):

```json
{
 "personal": {
  "accounts": 0,
  "documents_live": 0,
  "document_drafts": 0,
  "import_events_open": 0,
  "import_events_accepted": 0
 },
 "business": {
  "accounts": 0,
  "documents_live": 0,
  "document_drafts": 0,
  "import_events_open": 0,
  "import_events_accepted": 0
 },
 "activities_by_receipt_scope": {},
 "spaces": 0,
 "storage_objects": 0,
 "whatsapp_messages_captured": 0,
 "whatsapp_links_active": 0
}
```


## Setup. Sign in, space, Business account

Owner A signed in through the login form and landed on /biz. The first visit started A's space: GET /business/space -> 200 name "My business". Business account "Cuenta operativa" (checking, DOP) -> 201.

HTTP:

- `browser: POST /api/v1/business/space -> 201`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `A: GET /business/space -> 200`
- `A: POST /business/accounts -> 201`
- `browser: POST /api/v1/business/space -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`

DB rows (owner A):

```json
{
 "personal": {
  "accounts": 0,
  "documents_live": 0,
  "document_drafts": 0,
  "import_events_open": 0,
  "import_events_accepted": 0
 },
 "business": {
  "accounts": 1,
  "documents_live": 0,
  "document_drafts": 0,
  "import_events_open": 0,
  "import_events_accepted": 0
 },
 "activities_by_receipt_scope": {},
 "spaces": 1,
 "storage_objects": 0,
 "whatsapp_messages_captured": 0,
 "whatsapp_links_active": 0
}
```


## 1. Web upload, review and correct

Owner A uploaded ferreteria-oct.png (31764 bytes, sha256 5feb3f2ad0e0) from Create > Upload receipt with the AI box checked. The stub read it: status review_ready, merchant "FERRETERIA LA ESQUINA SRL", total 3450. From the Inbox A corrected the merchant to "Ferretería La Esquina" and the total from 3,450.00 to 3,400.00, chose the account, and double-clicked Confirm expense. The UI sent 1 confirm request(s). Stored: status confirmed, merchant "Ferretería La Esquina", amount 3400.00 DOP; evidence still "FERRETERIA LA ESQUINA SRL" 3450.00. Stub calls for this receipt: 1.

HTTP:

- `browser: POST /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts/{id} -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `browser: GET /api/v1/business/receipts/{id} -> 200`
- `browser: GET /api/v1/business/receipts/{id}/source -> 200`
- `A: GET /business/receipts/<web receipt> -> 200`
- `browser: GET /api/v1/business/receipts/{id}/source -> 200`
- `browser: GET /api/v1/business/receipts/{id} -> 200`
- `browser: GET /api/v1/business/receipts/{id} -> 200`
- `browser: GET /api/v1/business/receipts/{id}/source -> 200`
- `browser: GET /api/v1/business/receipts/{id}/source -> 200`
- `browser: PATCH /api/v1/business/receipts/{id}/review -> 200`
- `browser: POST /api/v1/business/receipts/{id}/confirm -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `A: GET /business/receipts/<web receipt> -> 200`

DB rows (owner A):

```json
{
 "personal": {
  "accounts": 0,
  "documents_live": 0,
  "document_drafts": 0,
  "import_events_open": 0,
  "import_events_accepted": 0
 },
 "business": {
  "accounts": 1,
  "documents_live": 1,
  "document_drafts": 1,
  "import_events_open": 0,
  "import_events_accepted": 1
 },
 "activities_by_receipt_scope": {
  "canonical": 1
 },
 "spaces": 1,
 "storage_objects": 1,
 "whatsapp_messages_captured": 0,
 "whatsapp_links_active": 0
}
```

- PASS: stub prepared the upload once
- PASS: exactly one expense with the corrected values (accepted 0 -> 1)
- PASS: double-click sent one confirm (confirm requests 1)
- PASS: evidence unchanged by the correction

## 2. Without AI

Uploaded farmacia.png with the AI box left unchecked (checked: false). Saved status saved. Confirm disabled before entry: true; enabled after merchant, date, currency, total, category and account were typed: true. Stored: status confirmed, merchant "Farmacia Carol", amount 498.00, category health, evidence null. Prepare with AI afterwards -> 409 document_entered_by_owner. Stub calls during this step: 0.

HTTP:

- `browser: POST /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/receipts/{id} -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `browser: GET /api/v1/business/receipts/{id} -> 200`
- `browser: GET /api/v1/business/receipts/{id}/source -> 200`
- `browser: GET /api/v1/business/receipts/{id}/source -> 200`
- `A: GET /business/receipts/<no-AI receipt> -> 200`
- `browser: PATCH /api/v1/business/receipts/{id}/review -> 200`
- `browser: POST /api/v1/business/receipts/{id}/confirm -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `A: GET /business/receipts/<no-AI receipt> -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `A: POST /business/receipts/<no-AI receipt>/prepare -> 409`

DB rows (owner A):

```json
{
 "personal": {
  "accounts": 0,
  "documents_live": 0,
  "document_drafts": 0,
  "import_events_open": 0,
  "import_events_accepted": 0
 },
 "business": {
  "accounts": 1,
  "documents_live": 2,
  "document_drafts": 2,
  "import_events_open": 0,
  "import_events_accepted": 2
 },
 "activities_by_receipt_scope": {
  "canonical": 2
 },
 "spaces": 1,
 "storage_objects": 2,
 "whatsapp_messages_captured": 0,
 "whatsapp_links_active": 0
}
```

- PASS: hand-entered receipt confirmed as exactly one expense, no extractor call
- PASS: prepare after hand entry refused

## 3. WhatsApp

Link code issued (201); signed link message from A's synthetic number -> 200; link {"linked":true,"last4":"4484"}. Signed image delivery (media id 700000000000901 served from a local file) -> 200. With /biz already open, the Inbox nav showed 0 WhatsApp row(s) until the page was loaded again (the Inbox list is fetched on load and after the owner's own actions, not polled). After a load it showed the receipt in A's Business Inbox with the WhatsApp mark: channel whatsapp, status saved; stub calls at capture 0. A chose Prepare with AI: merchant "COLMADO DON PEDRO", total 706.10. A corrected the merchant to "Colmado Don Pedro", set the category and account, and double-clicked Confirm expense (UI confirm requests: 1). Before confirming, the same signed image event was replayed -> 200; Business documents 3, captured messages 1. Stored: status confirmed, merchant "Colmado Don Pedro", amount 706.10. Source sha256 f313e5de8fa9, delivered media sha256 f313e5de8fa9.

HTTP:

- `A: POST /whatsapp/link-codes -> 201`
- `webhook: POST /webhooks/whatsapp -> 200`
- `A: GET /whatsapp/link -> 200`
- `webhook: POST /webhooks/whatsapp -> 200`
- `browser: POST /api/v1/business/space -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `A: GET /business/receipts -> 200`
- `A: GET /business/receipts/<WhatsApp receipt> -> 200`
- `browser: GET /api/v1/business/receipts/{id} -> 200`
- `browser: GET /api/v1/business/receipts/{id} -> 200`
- `browser: GET /api/v1/business/receipts/{id}/source -> 200`
- `browser: GET /api/v1/business/receipts/{id}/source -> 200`
- `browser: POST /api/v1/business/receipts/{id}/prepare -> 200`
- `browser: GET /api/v1/business/receipts/{id} -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `A: GET /business/receipts/<WhatsApp receipt> -> 200`
- `browser: POST /api/v1/business/space -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/receipts/{id} -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `browser: GET /api/v1/business/receipts/{id} -> 200`
- `browser: GET /api/v1/business/receipts/{id}/source -> 200`
- `browser: GET /api/v1/business/receipts/{id}/source -> 200`
- `webhook: POST /webhooks/whatsapp -> 200`
- `browser: PATCH /api/v1/business/receipts/{id}/review -> 200`
- `browser: POST /api/v1/business/receipts/{id}/confirm -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `A: GET /business/receipts/<WhatsApp receipt> -> 200`
- `A: GET /business/receipts/<WhatsApp receipt>/source -> 200`

DB rows (owner A):

```json
{
 "personal": {
  "accounts": 0,
  "documents_live": 0,
  "document_drafts": 0,
  "import_events_open": 0,
  "import_events_accepted": 0
 },
 "business": {
  "accounts": 1,
  "documents_live": 3,
  "document_drafts": 3,
  "import_events_open": 0,
  "import_events_accepted": 3
 },
 "activities_by_receipt_scope": {
  "canonical": 3
 },
 "spaces": 1,
 "storage_objects": 3,
 "whatsapp_messages_captured": 1,
 "whatsapp_links_active": 1
}
```

- PASS: WhatsApp receipt lands in A's Business Inbox without AI
- PASS: reviewed, corrected and confirmed as exactly one expense
- PASS: source bytes match the delivered media by sha256
- PASS: replayed delivery made no second receipt

## 4a. Duplicate confirms

Two concurrent API confirms of the WhatsApp receipt with one Idempotency-Key -> [200,200], expense ids ["<WhatsApp expense>","<WhatsApp expense>"]. A late confirm of the web receipt with a new key -> 200, expense <web expense>. The UI double-clicks in steps 1 and 3 sent 1 and 1 confirm request(s).

HTTP:

- `A: POST /business/receipts/<WhatsApp receipt>/confirm -> 200`
- `A: POST /business/receipts/<WhatsApp receipt>/confirm -> 200`
- `A: POST /business/receipts/<web receipt>/confirm -> 200`

DB rows (owner A):

```json
{
 "personal": {
  "accounts": 0,
  "documents_live": 0,
  "document_drafts": 0,
  "import_events_open": 0,
  "import_events_accepted": 0
 },
 "business": {
  "accounts": 1,
  "documents_live": 3,
  "document_drafts": 3,
  "import_events_open": 0,
  "import_events_accepted": 3
 },
 "activities_by_receipt_scope": {
  "canonical": 3
 },
 "spaces": 1,
 "storage_objects": 3,
 "whatsapp_messages_captured": 1,
 "whatsapp_links_active": 1
}
```

- PASS: double-click and same-key replay each leave one expense

## 4b. Kill the API mid-session and restart

Uploaded libreria.png through the API with AI consent -> 200 status queued. The stub logged the call (in flight: true) and holds it for 120 s. Before the kill: receipt status preparing. killed -9 <pid> while owner A's browser stayed open; a request during the outage -> connection refused. Restarted: api up pid <pid>. After restart the receipt is preparing. The same-key confirm of the WhatsApp receipt replayed after the restart -> 200, same expense true. The browser reloaded /biz on the new process.

HTTP:

- `A: POST /business/receipts -> 200`
- `A: GET /business/receipts/<in-flight receipt> -> 200`
- `A: GET /business/receipts/<in-flight receipt> -> 200`
- `A: POST /business/receipts/<WhatsApp receipt>/confirm -> 200`
- `browser: POST /api/v1/business/space -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts/{id} -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `browser: GET /api/v1/business/receipts/{id} -> 200`
- `browser: GET /api/v1/business/receipts/{id}/source -> 200`
- `browser: GET /api/v1/business/receipts/{id}/source -> 200`

DB rows (owner A):

```json
{
 "personal": {
  "accounts": 0,
  "documents_live": 0,
  "document_drafts": 0,
  "import_events_open": 0,
  "import_events_accepted": 0
 },
 "business": {
  "accounts": 1,
  "documents_live": 4,
  "document_drafts": 4,
  "import_events_open": 0,
  "import_events_accepted": 3
 },
 "activities_by_receipt_scope": {
  "canonical": 3
 },
 "spaces": 1,
 "storage_objects": 4,
 "whatsapp_messages_captured": 1,
 "whatsapp_links_active": 1
}
```

- PASS: expense count unchanged across the kill and restart (accepted before kill 3, after restart 3)

## 5. Reload and find

After a full browser reload, Expenses lists 3 expenses: [{"merchant":"Colmado Don Pedro","amount":"706.10","receipt":"<WhatsApp receipt>"},{"merchant":"Ferretería La Esquina","amount":"3400.00","receipt":"<web receipt>"},{"merchant":"Farmacia Carol","amount":"498.00","receipt":"<no-AI receipt>"}]. Receipts: view=all [{"id":"<in-flight receipt>","status":"preparing"},{"id":"<WhatsApp receipt>","status":"confirmed"},{"id":"<no-AI receipt>","status":"confirmed"},{"id":"<web receipt>","status":"confirmed"}]; view=inbox [{"id":"<in-flight receipt>","status":"preparing"}]. Each expense row's Receipt link opened Saved expense, and Download returned the original: sha256 match {"web":true,"no-AI":true,"WhatsApp":true}. Search: /biz shows 0 searchbox, 1 search button(s) and 0 search link(s). A separate probe after the run, with the flag on again and the same data, opened that Search button on /biz as owner A and typed "Ferretería", then "Colmado": the dialog answered "No results found" both times and offered only "Ask Argus" (screenshot search-ferreteria.png). The browser requests were GET /api/v1/search, the conversation search. OpenAPI search paths: ["/api/v1/search","/api/v1/financial-search","/api/v1/households/{household_id}/search"]; none is under /business. GET /business/expenses with q=Ferreter -> 200, 3 items (q is not a parameter; the full period list comes back).

HTTP:

- `browser: POST /api/v1/business/space -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts/{id} -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `browser: GET /api/v1/business/receipts/{id} -> 200`
- `browser: GET /api/v1/business/expenses -> 200`
- `browser: GET /api/v1/business/expenses -> 200`
- `A: GET /business/expenses -> 200`
- `A: GET /business/receipts -> 200`
- `A: GET /business/receipts -> 200`
- `browser: POST /api/v1/business/space -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts/{id} -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `browser: GET /api/v1/business/receipts/{id} -> 200`
- `browser: GET /api/v1/business/receipts/{id}/source -> 200`
- `browser: GET /api/v1/business/receipts/{id}/source -> 200`
- `browser: POST /api/v1/business/space -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts/{id} -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `browser: GET /api/v1/business/receipts/{id} -> 200`
- `browser: GET /api/v1/business/receipts/{id}/source -> 200`
- `browser: GET /api/v1/business/receipts/{id}/source -> 200`
- `browser: POST /api/v1/business/space -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts/{id} -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `browser: GET /api/v1/business/receipts/{id} -> 200`
- `browser: GET /api/v1/business/receipts/{id}/source -> 200`
- `browser: GET /api/v1/business/receipts/{id}/source -> 200`
- `browser: POST /api/v1/business/space -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `A: GET /business/expenses -> 200`

- PASS: each expense shows in Expenses after a reload, its receipt in All
- PASS: each original downloads with a matching sha256
- GAP: find a Business expense by merchant (no Business search in the UI or the API; not built)

## 6a. Personal data for owner A

Personal account "Cuenta personal" -> 201. Personal document upload of the same bytes as the Business web receipt (sha256 5feb3f2ad0e0, no AI) -> 200 status saved, replayed false. Personal expense "Supermercado Nacional" 1,200.00 DOP via /financial-activities (preview 200) -> 201.

HTTP:

- `A: POST /financial-accounts -> 201`
- `A: POST /financial-documents -> 200`
- `A: POST /financial-activities/preview -> 200`
- `A: POST /financial-activities -> 201`

DB rows (owner A):

```json
{
 "personal": {
  "accounts": 1,
  "documents_live": 1,
  "document_drafts": 1,
  "import_events_open": 0,
  "import_events_accepted": 0
 },
 "business": {
  "accounts": 1,
  "documents_live": 4,
  "document_drafts": 4,
  "import_events_open": 0,
  "import_events_accepted": 3
 },
 "activities_by_receipt_scope": {
  "canonical": 4
 },
 "spaces": 1,
 "storage_objects": 5,
 "whatsapp_messages_captured": 1,
 "whatsapp_links_active": 1
}
```


## 6b. Personal and Business stay separate

Personal reads as A (status and any Business id, merchant or account name found in the body):

```json
{
 "/financial-accounts": {
  "status": 200,
  "business_hits": []
 },
 "/financial-documents": {
  "status": 200,
  "business_hits": []
 },
 "/financial-imports?state=open": {
  "status": 200,
  "business_hits": []
 },
 "/financial-imports?state=accepted": {
  "status": 200,
  "business_hits": []
 },
 "/financial-activities/purchases": {
  "status": 200,
  "business_hits": []
 },
 "/financial-home": {
  "status": 200,
  "business_hits": []
 },
 "/financial-search?q=Ferreter": {
  "status": 200,
  "business_hits": []
 },
 "/financial-search?q=Colmado": {
  "status": 200,
  "business_hits": []
 },
 "/financial-search?q=Farmacia": {
  "status": 200,
  "business_hits": []
 },
 "/financial-search?q=Libreria": {
  "status": 200,
  "business_hits": []
 },
 "/financial-search?q=": {
  "status": 200,
  "business_hits": []
 },
 "/search?q=Ferreter": {
  "status": 200,
  "business_hits": []
 }
}
```

Personal still sees its own rows: {"documents":true,"purchases":true,"home":true,"search":true}. Personal home DOP gross purchases (minor units): 120000.

Business reads as A (any Personal id, merchant or account name found):

```json
{
 "/business/receipts?view=all": {
  "status": 200,
  "personal_hits": []
 },
 "/business/receipts?view=inbox": {
  "status": 200,
  "personal_hits": []
 },
 "/business/expenses?from=2026-10-01&to=2026-10-31": {
  "status": 200,
  "personal_hits": []
 },
 "/business/workspace": {
  "status": 200,
  "personal_hits": []
 },
 "/business/overview?from=2026-10-01&to=2026-10-31": {
  "status": 200,
  "personal_hits": []
 },
 "/business/updates": {
  "status": 200,
  "personal_hits": []
 }
}
```

Business overview totals: [{"currency":"DOP","amount":"4604.10","count":3}].

Same file in both scopes: Business web receipt <web receipt> and Personal document <A personal document> are different ids: true; Personal documents 1, Business documents 4.

Cross-scope ids:

```json
{
 "POST /business/expenses with A's Personal account": "404 financial_account_not_found",
 "GET /business/receipts/{Personal document}": "404 receipt_not_found",
 "GET /business/receipts/{Personal document}/source": "404 receipt_not_found",
 "GET /financial-accounts/{Business account}": "404 financial_account_not_found",
 "POST /financial-activities/preview with the Business account": "404 financial_account_not_found",
 "GET /financial-documents/{web receipt}": "404 financial_document_not_found",
 "GET /financial-documents/{web receipt}/source": "404 financial_document_not_found",
 "GET /financial-activities/{web expense}": "404 financial_account_not_found",
 "POST /business/expenses with a random account id": "404 financial_account_not_found",
 "PATCH /business/receipts/{no-AI receipt}/review account_id = random id": "422 financial_account_not_found",
 "PATCH /business/receipts/{no-AI receipt}/review account_id = Personal account": "422 financial_account_not_found"
}
```

HTTP:

- `A: GET /financial-accounts -> 200`
- `A: GET /financial-documents -> 200`
- `A: GET /financial-imports -> 200`
- `A: GET /financial-imports -> 200`
- `A: GET /financial-activities/purchases -> 200`
- `A: GET /financial-home -> 200`
- `A: GET /financial-search -> 200`
- `A: GET /financial-search -> 200`
- `A: GET /financial-search -> 200`
- `A: GET /financial-search -> 200`
- `A: GET /financial-search -> 200`
- `A: GET /search -> 200`
- `A: GET /business/receipts -> 200`
- `A: GET /business/receipts -> 200`
- `A: GET /business/expenses -> 200`
- `A: GET /business/workspace -> 200`
- `A: GET /business/overview -> 200`
- `A: GET /business/updates -> 200`
- `A: GET /financial-search -> 200`
- `A: POST /business/expenses -> 404`
- `A: GET /business/receipts/<A personal document> -> 404`
- `A: GET /business/receipts/<A personal document>/source -> 404`
- `A: GET /financial-accounts/<A business account> -> 404`
- `A: POST /financial-activities/preview -> 404`
- `A: GET /financial-documents/<web receipt> -> 404`
- `A: GET /financial-documents/<web receipt>/source -> 404`
- `A: GET /financial-activities/<web expense> -> 404`
- `A: POST /business/expenses -> 404`
- `A: PATCH /business/receipts/<no-AI receipt>/review -> 422`
- `A: PATCH /business/receipts/<no-AI receipt>/review -> 422`

DB rows (owner A):

```json
{
 "personal": {
  "accounts": 1,
  "documents_live": 1,
  "document_drafts": 1,
  "import_events_open": 0,
  "import_events_accepted": 0
 },
 "business": {
  "accounts": 1,
  "documents_live": 4,
  "document_drafts": 4,
  "import_events_open": 0,
  "import_events_accepted": 3
 },
 "activities_by_receipt_scope": {
  "canonical": 4
 },
 "spaces": 1,
 "storage_objects": 5,
 "whatsapp_messages_captured": 1,
 "whatsapp_links_active": 1
}
```

- PASS: Personal lists, home and search never show Business receipts or expenses
- PASS: Personal reads still show A's Personal rows
- PASS: Business lists never show Personal ones (overview [{"currency":"DOP","amount":"4604.10","count":3}])
- PASS: same file in Personal and Business gives two documents
- PASS: Personal account id on POST /business/expenses returns 404 (404 financial_account_not_found; random id 404 financial_account_not_found)
- FAIL: Personal account id on PATCH /business/receipts/{id}/review returns 404 (422 financial_account_not_found; random id 422 financial_account_not_found)
- PASS: Business ids on Personal routes, and Personal document on Business routes, return 404 ({"POST /business/expenses with A's Personal account":"404 financial_account_not_found","GET /business/receipts/{Personal document}":"404 receipt_not_found","GET /business/receipts/{Personal document}/source":"404 receipt_not_found","GET /financial-accounts/{Business account}":"404 financial_account_not_found","POST /financial-activities/preview with the Business account":"404 financial_account_not_found","GET /financial-documents/{web receipt}":"404 financial_document_not_found","GET /financial-documents/{web receipt}/source":"404 financial_document_not_found","GET /financial-activities/{web expense}":"404 financial_account_not_found","POST /business/expenses with a random account id":"404 financial_account_not_found","PATCH /business/receipts/{no-AI receipt}/review account_id = random id":"422 financial_account_not_found","PATCH /business/receipts/{no-AI receipt}/review account_id = Personal account":"422 financial_account_not_found"})

## 7. Denied access

Owner B started their own space (201) and account (201). B's probes on A's ids:

```json
{
 "GET receipt (web receipt)": 404,
 "GET source (web receipt)": 404,
 "PATCH review (web receipt)": 404,
 "POST confirm (web receipt)": 404,
 "POST prepare (web receipt)": 404,
 "GET receipt (WhatsApp receipt)": 404,
 "GET source (WhatsApp receipt)": 404,
 "PATCH review (WhatsApp receipt)": 404,
 "POST confirm (WhatsApp receipt)": 404,
 "POST prepare (WhatsApp receipt)": 404,
 "GET receipt (in-flight receipt)": 404,
 "GET source (in-flight receipt)": 404,
 "PATCH review (in-flight receipt)": 404,
 "POST confirm (in-flight receipt)": 404,
 "POST prepare (in-flight receipt)": 404,
 "GET /financial-activities/{web expense}": 404,
 "GET /financial-activities/{web expense}/history": 404,
 "GET /financial-activities/{no-AI expense}": 404,
 "GET /financial-activities/{no-AI expense}/history": 404,
 "GET /financial-activities/{WhatsApp expense}": 404,
 "GET /financial-activities/{WhatsApp expense}/history": 404,
 "POST /business/expenses with A's Business account": 404,
 "GET /financial-documents/{A personal document}": 404
}
```

B's own lists: {"receipts":0,"expenses":0,"workspace_accounts":0}. Signed-out requests:

```json
{
 "GET /business/space": 401,
 "GET /business/workspace": 401,
 "GET /business/receipts": 401,
 "GET /business/receipts/<web receipt>": 401,
 "GET /business/receipts/<web receipt>/source": 401,
 "GET /business/expenses": 401,
 "POST /business/receipts/<web receipt>/confirm": 401
}
```

HTTP:

- `B: POST /business/space -> 201`
- `B: POST /business/accounts -> 201`
- `B: GET /business/receipts/<web receipt> -> 404`
- `B: GET /business/receipts/<web receipt>/source -> 404`
- `B: PATCH /business/receipts/<web receipt>/review -> 404`
- `B: POST /business/receipts/<web receipt>/confirm -> 404`
- `B: POST /business/receipts/<web receipt>/prepare -> 404`
- `B: GET /business/receipts/<WhatsApp receipt> -> 404`
- `B: GET /business/receipts/<WhatsApp receipt>/source -> 404`
- `B: PATCH /business/receipts/<WhatsApp receipt>/review -> 404`
- `B: POST /business/receipts/<WhatsApp receipt>/confirm -> 404`
- `B: POST /business/receipts/<WhatsApp receipt>/prepare -> 404`
- `B: GET /business/receipts/<in-flight receipt> -> 404`
- `B: GET /business/receipts/<in-flight receipt>/source -> 404`
- `B: PATCH /business/receipts/<in-flight receipt>/review -> 404`
- `B: POST /business/receipts/<in-flight receipt>/confirm -> 404`
- `B: POST /business/receipts/<in-flight receipt>/prepare -> 404`
- `B: GET /financial-activities/<web expense> -> 404`
- `B: GET /financial-activities/<web expense>/history -> 404`
- `B: GET /financial-activities/<no-AI expense> -> 404`
- `B: GET /financial-activities/<no-AI expense>/history -> 404`
- `B: GET /financial-activities/<WhatsApp expense> -> 404`
- `B: GET /financial-activities/<WhatsApp expense>/history -> 404`
- `B: POST /business/expenses -> 404`
- `B: GET /financial-documents/<A personal document> -> 404`
- `B: GET /business/receipts -> 200`
- `B: GET /business/expenses -> 200`
- `B: GET /business/workspace -> 200`
- `signed out: GET /business/space -> 401`
- `signed out: GET /business/workspace -> 401`
- `signed out: GET /business/receipts -> 401`
- `signed out: GET /business/receipts/<web receipt> -> 401`
- `signed out: GET /business/receipts/<web receipt>/source -> 401`
- `signed out: GET /business/expenses -> 401`
- `signed out: POST /business/receipts/<web receipt>/confirm -> 401`

DB rows (owner A):

```json
{
 "personal": {
  "accounts": 1,
  "documents_live": 1,
  "document_drafts": 1,
  "import_events_open": 0,
  "import_events_accepted": 0
 },
 "business": {
  "accounts": 1,
  "documents_live": 4,
  "document_drafts": 4,
  "import_events_open": 0,
  "import_events_accepted": 3
 },
 "activities_by_receipt_scope": {
  "canonical": 4
 },
 "spaces": 1,
 "storage_objects": 5,
 "whatsapp_messages_captured": 1,
 "whatsapp_links_active": 1
}
```

- PASS: owner B gets 404 for A's receipts, sources and expense ids ({"GET receipt (web receipt)":404,"GET source (web receipt)":404,"PATCH review (web receipt)":404,"POST confirm (web receipt)":404,"POST prepare (web receipt)":404,"GET receipt (WhatsApp receipt)":404,"GET source (WhatsApp receipt)":404,"PATCH review (WhatsApp receipt)":404,"POST confirm (WhatsApp receipt)":404,"POST prepare (WhatsApp receipt)":404,"GET receipt (in-flight receipt)":404,"GET source (in-flight receipt)":404,"PATCH review (in-flight receipt)":404,"POST confirm (in-flight receipt)":404,"POST prepare (in-flight receipt)":404,"GET /financial-activities/{web expense}":404,"GET /financial-activities/{web expense}/history":404,"GET /financial-activities/{no-AI expense}":404,"GET /financial-activities/{no-AI expense}/history":404,"GET /financial-activities/{WhatsApp expense}":404,"GET /financial-activities/{WhatsApp expense}/history":404,"POST /business/expenses with A's Business account":404,"GET /financial-documents/{A personal document}":404})
- PASS: owner B's lists hold none of A's records
- PASS: signed-out requests get 401 ({"GET /business/space":401,"GET /business/workspace":401,"GET /business/receipts":401,"GET /business/receipts/<web receipt>":401,"GET /business/receipts/<web receipt>/source":401,"GET /business/expenses":401,"POST /business/receipts/<web receipt>/confirm":401})

## 4c. The interrupted preparation after the restart

Polled the in-flight receipt for 290 s after the earlier steps (the connection lease from the dead worker lasts 5 minutes; the restarted API sweeps every 5 s). Status: needs_attention, error document_preparation_outcome_unknown. API log lines from the sweep: ["argus.domain.ingestion.documents.jobs:_reconcile:150 - Document preparation outcome unknown; waiting for the owner"]. Stub extractor calls for this receipt across both processes: 1 (pid). The review screen shows: ["Needs attention"].

HTTP:

- `browser: POST /api/v1/business/space -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts/{id} -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `browser: GET /api/v1/business/receipts/{id} -> 200`
- `browser: GET /api/v1/business/receipts/{id}/source -> 200`
- `browser: GET /api/v1/business/receipts/{id}/source -> 200`

DB rows (owner A):

```json
{
 "personal": {
  "accounts": 1,
  "documents_live": 1,
  "document_drafts": 1,
  "import_events_open": 0,
  "import_events_accepted": 0
 },
 "business": {
  "accounts": 1,
  "documents_live": 4,
  "document_drafts": 4,
  "import_events_open": 0,
  "import_events_accepted": 3
 },
 "activities_by_receipt_scope": {
  "canonical": 4
 },
 "spaces": 1,
 "storage_objects": 5,
 "whatsapp_messages_captured": 1,
 "whatsapp_links_active": 1
}
```

- PASS: interrupted preparation swept with no second extractor call (status needs_attention, stub calls 1)

## Counts after steps 1 to 7

```json
{
 "A": {
  "personal": {
   "accounts": 1,
   "documents_live": 1,
   "document_drafts": 1,
   "import_events_open": 0,
   "import_events_accepted": 0
  },
  "business": {
   "accounts": 1,
   "documents_live": 4,
   "document_drafts": 4,
   "import_events_open": 0,
   "import_events_accepted": 3
  },
  "activities_by_receipt_scope": {
   "canonical": 4
  },
  "spaces": 1,
  "storage_objects": 5,
  "whatsapp_messages_captured": 1,
  "whatsapp_links_active": 1
 },
 "B": {
  "personal": {
   "accounts": 0,
   "documents_live": 0,
   "document_drafts": 0,
   "import_events_open": 0,
   "import_events_accepted": 0
  },
  "business": {
   "accounts": 1,
   "documents_live": 0,
   "document_drafts": 0,
   "import_events_open": 0,
   "import_events_accepted": 0
  },
  "activities_by_receipt_scope": {},
  "spaces": 1,
  "storage_objects": 0,
  "whatsapp_messages_captured": 0,
  "whatsapp_links_active": 0
 }
}
```

Stub extractor calls this run: 3 (web receipt 1, WhatsApp receipt 1, in-flight receipt 1). Browser console errors: 0.


## 8. Flag off

8a. The API was stopped and started again with ARGUS_BUSINESS_PILOT_ENABLED removed from its env (launcher printed "business flag <unset>": true). The web still had its flag on.

```json
{
 "A: GET /business/space": "404 business_unavailable",
 "signed out: GET /business/space": "404 business_unavailable",
 "A: POST /business/space": "404 business_unavailable",
 "signed out: POST /business/space": "404 business_unavailable",
 "A: GET /business/workspace": "404 business_unavailable",
 "signed out: GET /business/workspace": "404 business_unavailable",
 "A: GET /business/receipts": "404 business_unavailable",
 "signed out: GET /business/receipts": "404 business_unavailable",
 "A: GET /business/receipts/<web receipt>": "404 business_unavailable",
 "signed out: GET /business/receipts/<web receipt>": "404 business_unavailable",
 "A: GET /business/receipts/<web receipt>/source": "404 business_unavailable",
 "signed out: GET /business/receipts/<web receipt>/source": "404 business_unavailable",
 "A: GET /business/expenses": "404 business_unavailable",
 "signed out: GET /business/expenses": "404 business_unavailable",
 "A: GET /business/overview": "404 business_unavailable",
 "signed out: GET /business/overview": "404 business_unavailable",
 "A: GET /business/updates": "404 business_unavailable",
 "signed out: GET /business/updates": "404 business_unavailable"
}
```

Personal GET /financial-accounts as A -> 200. Owner A signed in and opened /biz -> HTTP 200; Business nav visible: true; page text starts "argus New chat Search Overview Inbox Expenses Updates Recents Your business This month Last month Last 30 days We couldn't load your business records. Your saved receipts and expenses are safe. Try again. Upload receipt Record expense Write". Screenshot flag-off-api.png.

- PASS: every /api/v1/business route returns 404 with the flag unset, signed in or out
- PASS: Personal routes keep working

8b. The web was stopped and started again without NEXT_PUBLIC_BUSINESS_PILOT_ENABLED. Owner A signed in and opened /biz -> HTTP 200; Business nav visible: false; page text starts "404 This page could not be found.". A signed-out GET /biz -> HTTP 200, body is the Next.js not-found page: true. For comparison, a path with no route (/no-such-page) -> HTTP 404. Screenshot flag-off-web.png.

- PASS: /biz is not available with the flag unset (not-found page, no Business UI) (HTTP status signed in 200, signed out 200)
