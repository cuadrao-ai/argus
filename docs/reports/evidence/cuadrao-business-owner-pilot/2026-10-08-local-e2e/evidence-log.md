# Business owner pilot: local end-to-end evidence log

Label: **local services, stub extractor, replayed WhatsApp fixtures; not provider or hosted proof.**

Run: 2026-10-08T01:53:25.115Z. API http://127.0.0.1:8621 (uvicorn, Supabase persistence on the local lane stack), web http://localhost:3621 (next dev). Real local Supabase Auth. Code: branch claude/business-pilot-flow at 92599473a. Owner ids are shown as A and B.

Files: `business-owner-pilot-journey.mp4` is the Playwright recording of owner A's browser (41 s, 1280x800, converted from the WebM with ffmpeg). The receipts are synthetic images marked SAMPLE DATA. The stub extractor returns a fixed read per receipt digest, so no model and no provider was called. WhatsApp deliveries are signed replays of the repo fixtures, with media served from local files. No message went to Meta, and outbound replies were off.

## 0. Start

Owner A and owner B exist in local Supabase Auth (admin API on the local stack).

DB rows (owner A):

```json
{
 "receipts_live": 0,
 "document_drafts": 0,
 "storage_objects": 0,
 "import_events_open": 0,
 "import_events_accepted": 0,
 "expenses_recorded": 0,
 "whatsapp_messages_captured": 0,
 "whatsapp_links_active": 0,
 "_buckets": [
  "financial-document-sources"
 ]
}
```

## a. Create a Business account

API as owner A: nickname "Cuenta operativa", checking, DOP. id returned.

HTTP:

- `api: POST /business/accounts -> 201`

- PASS: account created
## Sign in

Owner A signed in through the login form and returned to /biz.

HTTP:

- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`

## b. Upload with AI consent

Uploaded ferreteria-oct.png (31079 bytes) with the consent box checked. The stub prepared it: status review_ready, merchant "FERRETERIA LA ESQUINA SRL", amount 3450 DOP, missing ["account_id"].

HTTP:

- `browser: POST /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts/{id} -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `browser: GET /api/v1/business/receipts/{id} -> 200`
- `browser: GET /api/v1/business/receipts/{id}/source -> 200`
- `browser: GET /api/v1/business/receipts/{id}/source -> 200`
- `api: GET /business/receipts/f605c3c3-0f94-4236-9c9b-34c2bf7cbbfa -> 200`

DB rows (owner A):

```json
{
 "receipts_live": 1,
 "document_drafts": 1,
 "storage_objects": 1,
 "import_events_open": 1,
 "import_events_accepted": 0,
 "expenses_recorded": 0,
 "whatsapp_messages_captured": 0,
 "whatsapp_links_active": 0,
 "_buckets": [
  "financial-document-sources"
 ]
}
```

- PASS: web receipt prepared by the stub
## c. Inbox, then review

Opened the receipt from the Inbox. Corrected the merchant to "Ferretería La Esquina" and the total from 3,450.00 to 3,400.00, and chose the account.

HTTP:

- `browser: GET /api/v1/business/receipts/{id} -> 200`
- `browser: GET /api/v1/business/receipts/{id} -> 200`
- `browser: GET /api/v1/business/receipts/{id}/source -> 200`
- `browser: GET /api/v1/business/receipts/{id}/source -> 200`

## d. Confirm

Confirm saved one expense. Receipt status confirmed, merchant "Ferretería La Esquina", amount 3400.00; evidence total still 3450.00.

HTTP:

- `browser: PATCH /api/v1/business/receipts/{id}/review -> 200`
- `browser: POST /api/v1/business/receipts/{id}/confirm -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `api: GET /business/receipts/f605c3c3-0f94-4236-9c9b-34c2bf7cbbfa -> 200`

DB rows (owner A):

```json
{
 "receipts_live": 1,
 "document_drafts": 1,
 "storage_objects": 1,
 "import_events_open": 0,
 "import_events_accepted": 1,
 "expenses_recorded": 1,
 "whatsapp_messages_captured": 0,
 "whatsapp_links_active": 0,
 "_buckets": [
  "financial-document-sources"
 ]
}
```

- PASS: one expense from the web receipt
- PASS: evidence unchanged by the correction
## e. Reload

After a reload the expense is in Expenses and the Overview total. API overview totals: [{"currency":"DOP","amount":"3400.00","count":1}]; expenses: 1.

HTTP:

- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `browser: GET /api/v1/business/receipts/{id} -> 200`
- `browser: GET /api/v1/business/receipts/{id} -> 200`
- `browser: GET /api/v1/business/receipts/{id}/source -> 200`
- `browser: GET /api/v1/business/expenses -> 200`
- `browser: GET /api/v1/business/receipts/{id}/source -> 200`
- `browser: GET /api/v1/business/expenses -> 200`
- `api: GET /business/overview -> 200`
- `api: GET /business/expenses -> 200`

- PASS: overview total after reload
## f. Download the original

Downloaded from the review screen: sha256 7ef599f777273bb2…, uploaded sha256 7ef599f777273bb2…. API source: 200, 31079 bytes.

HTTP:

- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `browser: GET /api/v1/business/receipts/{id} -> 200`
- `browser: GET /api/v1/business/receipts/{id} -> 200`
- `browser: GET /api/v1/business/receipts/{id}/source -> 200`
- `browser: GET /api/v1/business/receipts/{id}/source -> 200`
- `api: GET /business/receipts/f605c3c3-0f94-4236-9c9b-34c2bf7cbbfa/source -> 200`

- PASS: downloaded bytes match the upload
## g. WhatsApp delivery

Link code issued (201); signed link message from A's synthetic number -> 200; link {"linked":true,"last4":"1234"}. Signed image message, media served by the local stub -> 200. Inbox shows it with the WhatsApp mark: channel whatsapp, status saved. Stub extractor calls during capture: 0.

HTTP:

- `api: POST /whatsapp/link-codes -> 201`
- `webhook: POST /webhooks/whatsapp -> 200`
- `api: GET /whatsapp/link -> 200`
- `webhook: POST /webhooks/whatsapp -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `api: GET /business/receipts -> 200`

DB rows (owner A):

```json
{
 "receipts_live": 2,
 "document_drafts": 2,
 "storage_objects": 2,
 "import_events_open": 0,
 "import_events_accepted": 1,
 "expenses_recorded": 1,
 "whatsapp_messages_captured": 1,
 "whatsapp_links_active": 1,
 "_buckets": [
  "financial-document-sources"
 ]
}
```

- PASS: WhatsApp receipt saved without AI
## g2. Review link after sign-in

Signed out, opened the review link /biz?receipt=<id> (the shape review_url builds from ARGUS_APP_ORIGIN). Login carried return_to=/biz?receipt=<id>; after sign-in the page is /biz?receipt=<that id> on Review receipt.

HTTP:

- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `browser: GET /api/v1/business/receipts/{id} -> 200`
- `browser: GET /api/v1/business/receipts/{id} -> 200`
- `browser: GET /api/v1/business/receipts/{id}/source -> 200`
- `browser: GET /api/v1/business/receipts/{id}/source -> 200`

- PASS: review link opens the receipt after sign-in
## h. Prepare and review

Prepare with AI (consent header) -> stub read it: status review_ready, merchant "COLMADO DON PEDRO", amount 706.1. Chose the account.

HTTP:

- `browser: POST /api/v1/business/receipts/{id}/prepare -> 200`
- `browser: GET /api/v1/business/receipts/{id} -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `browser: GET /api/v1/business/receipts/{id} -> 200`
- `browser: GET /api/v1/business/receipts/{id} -> 200`
- `browser: GET /api/v1/business/receipts/{id}/source -> 200`
- `browser: GET /api/v1/business/receipts/{id}/source -> 200`
- `api: GET /business/receipts/8236f33d-db3e-4573-abde-87287e34dd8b -> 200`

- PASS: WhatsApp receipt prepared after consent
## i. Replay and double-click

Replayed the same signed image event -> 200; receipts 2, captured messages 1. Double-clicked Confirm expense: the UI sent 1 confirm request(s). Then two concurrent API confirms with one key and a late confirm of the web receipt with a new key -> [200,200,200]; same expenses true.

HTTP:

- `webhook: POST /webhooks/whatsapp -> 200`
- `browser: PATCH /api/v1/business/receipts/{id}/review -> 200`
- `browser: POST /api/v1/business/receipts/{id}/confirm -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `api: GET /business/receipts/8236f33d-db3e-4573-abde-87287e34dd8b -> 200`
- `api: POST /business/receipts/f605c3c3-0f94-4236-9c9b-34c2bf7cbbfa/confirm -> 200`
- `api: POST /business/receipts/8236f33d-db3e-4573-abde-87287e34dd8b/confirm -> 200`
- `api: POST /business/receipts/8236f33d-db3e-4573-abde-87287e34dd8b/confirm -> 200`

DB rows (owner A):

```json
{
 "receipts_live": 2,
 "document_drafts": 2,
 "storage_objects": 2,
 "import_events_open": 0,
 "import_events_accepted": 2,
 "expenses_recorded": 2,
 "whatsapp_messages_captured": 1,
 "whatsapp_links_active": 1,
 "_buckets": [
  "financial-document-sources"
 ]
}
```

- PASS: replay made no second receipt
- PASS: double confirm made one expense each
## j. Owner B

As owner B, A's two receipts on detail, source, review and confirm: [404,404,404,404,404,404,404,404]. B's expenses: 0; B's receipts: 0.

HTTP:

- `api: GET /business/receipts/f605c3c3-0f94-4236-9c9b-34c2bf7cbbfa -> 404`
- `api: GET /business/receipts/f605c3c3-0f94-4236-9c9b-34c2bf7cbbfa/source -> 404`
- `api: PATCH /business/receipts/f605c3c3-0f94-4236-9c9b-34c2bf7cbbfa/review -> 404`
- `api: POST /business/receipts/f605c3c3-0f94-4236-9c9b-34c2bf7cbbfa/confirm -> 404`
- `api: GET /business/receipts/8236f33d-db3e-4573-abde-87287e34dd8b -> 404`
- `api: GET /business/receipts/8236f33d-db3e-4573-abde-87287e34dd8b/source -> 404`
- `api: PATCH /business/receipts/8236f33d-db3e-4573-abde-87287e34dd8b/review -> 404`
- `api: POST /business/receipts/8236f33d-db3e-4573-abde-87287e34dd8b/confirm -> 404`
- `api: GET /business/expenses -> 200`
- `api: GET /business/receipts -> 200`

- PASS: owner B gets 404 for A's receipts and sources
- PASS: owner B sees no expenses or receipts
## k. WhatsApp receipt declined AI, completed by hand

Signed delivery -> 200; opened from the Inbox without preparing. Confirm disabled before entry: true; enabled after filling merchant, date, amount, currency, category and account: true. Saved: status confirmed, evidence null, expense {"merchant":"Panadería La Espiga","amount":"542.80","currency":"DOP","category_id":"groceries","linked_to_this_receipt":true}. Source sha256 matches the delivered media: true. Prepare with AI afterwards -> 409 document_entered_by_owner; another confirm with a new key -> 200, same expense true. Stub extractor calls during this step: 0.

HTTP:

- `webhook: POST /webhooks/whatsapp -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `browser: GET /api/v1/business/receipts/{id} -> 200`
- `browser: GET /api/v1/business/receipts/{id} -> 200`
- `browser: GET /api/v1/business/receipts/{id}/source -> 200`
- `browser: GET /api/v1/business/receipts/{id}/source -> 200`
- `browser: PATCH /api/v1/business/receipts/{id}/review -> 200`
- `browser: POST /api/v1/business/receipts/{id}/confirm -> 200`
- `browser: GET /api/v1/business/workspace -> 200`
- `browser: GET /api/v1/business/receipts -> 200`
- `browser: GET /api/v1/business/overview -> 200`
- `api: GET /business/receipts/aeffcf8b-86c5-4e7d-943e-f946cfe5bf9a -> 200`
- `api: GET /business/expenses -> 200`
- `api: GET /business/receipts/aeffcf8b-86c5-4e7d-943e-f946cfe5bf9a/source -> 200`
- `api: POST /business/receipts/aeffcf8b-86c5-4e7d-943e-f946cfe5bf9a/prepare -> 409`
- `api: POST /business/receipts/aeffcf8b-86c5-4e7d-943e-f946cfe5bf9a/confirm -> 200`

DB rows (owner A):

```json
{
 "receipts_live": 3,
 "document_drafts": 3,
 "storage_objects": 3,
 "import_events_open": 0,
 "import_events_accepted": 3,
 "expenses_recorded": 3,
 "whatsapp_messages_captured": 2,
 "whatsapp_links_active": 1,
 "_buckets": [
  "financial-document-sources"
 ]
}
```

- PASS: hand-entered receipt saved once without AI
- PASS: hand-entered expense linked to its source
- PASS: prepare after hand entry refused

## Final

DB rows (owner A):

```json
{
 "receipts_live": 3,
 "document_drafts": 3,
 "storage_objects": 3,
 "import_events_open": 0,
 "import_events_accepted": 3,
 "expenses_recorded": 3,
 "whatsapp_messages_captured": 2,
 "whatsapp_links_active": 1,
 "_buckets": [
  "financial-document-sources"
 ]
}
```

Stub extractor calls this run: 2.

16/16 checks passed.
