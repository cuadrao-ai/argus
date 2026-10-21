Run 2026-10-08T07:18:35.808Z at 380e38570c7364f671dd36622133f020a665df48.


### Setup

Owner A signed in through the login form on /biz; the first visit started A's space (GET /business/space -> 200). Business account "Cuenta operativa" (checking, DOP) -> 201. Personal account "Cuenta personal" (checking, DOP) -> 201.

HTTP:

- `browser: POST /api/v1/business/space -> 201`
- `A: GET /business/space -> 200`
- `A: POST /business/accounts -> 201`
- `A: POST /financial-accounts -> 201`
- `browser: POST /api/v1/business/space -> 200`


### 2(e) part 1. Kill the API mid-preparation

Owner A uploaded gasolinera.png from Create > Upload receipt with the AI box checked. The stub logged the call (in flight: true) and holds it for 900 s. Status before the kill: preparing. killed -9 <pid>; a request during the outage -> connection refused. api up pid <pid>. After the restart the receipt is preparing. Scenarios 1 and 2(a) to 2(d) ran while the dead worker's 5-minute lease ran out.

HTTP:

- `browser: POST /api/v1/business/receipts -> 200`


### 1a. Two Business receipts confirmed, two Personal expenses with the same merchants

Web: ferreteria-oct.png uploaded with AI, stub read "FERRETERIA LA ESQUINA SRL" 3,450.00, corrected to "Ferretería La Esquina", double-clicked Confirm (UI: {"review_patches":1,"confirm_posts":1}). Stored confirmed Ferretería La Esquina 3450.00. WhatsApp: link code 201, signed link message -> 200, signed image delivery (media 700000000000911 from a local file) -> 200; Prepare with AI, stub read "COLMADO DON PEDRO" 706.10, corrected to "Colmado Don Pedro", double-clicked Confirm (UI: {"review_patches":1,"confirm_posts":1}). Stored confirmed Colmado Don Pedro 706.10. Personal expenses through /financial-activities on "Cuenta personal": "Ferretería La Esquina" 1,200.00 and "Colmado Don Pedro" 310.00.

HTTP:

- `browser: POST /api/v1/business/receipts -> 200`
- `browser: POST /api/v1/business/space -> 200`
- `browser: PATCH /api/v1/business/receipts/{id}/review -> 200`
- `browser: POST /api/v1/business/receipts/{id}/confirm -> 200`
- `A: POST /whatsapp/link-codes -> 201`
- `webhook: POST /webhooks/whatsapp -> 200`
- `webhook: POST /webhooks/whatsapp -> 200`
- `browser: POST /api/v1/business/space -> 200`
- `browser: POST /api/v1/business/receipts/{id}/prepare -> 200`
- `browser: POST /api/v1/business/space -> 200`
- `browser: PATCH /api/v1/business/receipts/{id}/review -> 200`
- `browser: POST /api/v1/business/receipts/{id}/confirm -> 200`
- `A: POST /financial-activities/preview -> 200`
- `A: POST /financial-activities -> 201`
- `A: POST /financial-activities/preview -> 200`
- `A: POST /financial-activities -> 201`

Rows:

```json
{
 "personal": {
  "accounts": 1,
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
  "import_events_accepted": 2
 },
 "activities_by_receipt_scope": {
  "canonical": 4
 },
 "spaces": 1,
 "storage_objects": 3,
 "whatsapp_messages_captured": 1,
 "whatsapp_links_active": 1
}
```


### 1b. Search after a full reload

For each merchant the journey loaded /biz again (a full navigation), opened Search, typed the merchant, clicked the one Expenses row, landed on Saved expense for that receipt and clicked Download.

```json
{
 "ferreteria": {
  "query": "Ferretería",
  "ui_expense_rows": 1,
  "ui_receipt_rows": 0,
  "ui_shows_business_merchant": true,
  "ui_shows_personal_amount": false,
  "opened_receipt_is_expected": true,
  "download_sha256_matches": true,
  "download_sha256": "b3b675045581",
  "api_status": 200,
  "api_expense_ids": [
   "<web expense>"
  ],
  "api_receipt_ids": [],
  "api_personal_hit": false
 },
 "colmado": {
  "query": "Colmado",
  "ui_expense_rows": 1,
  "ui_receipt_rows": 0,
  "ui_shows_business_merchant": true,
  "ui_shows_personal_amount": false,
  "opened_receipt_is_expected": true,
  "download_sha256_matches": true,
  "download_sha256": "0cde8fde9397",
  "api_status": 200,
  "api_expense_ids": [
   "<WhatsApp expense>"
  ],
  "api_receipt_ids": [],
  "api_personal_hit": false
 }
}
```

Personal GET /financial-search?q=Ferreter as A -> 200; Business ids in it: [].

HTTP:

- `browser: POST /api/v1/business/space -> 200`
- `A: GET /business/search -> 200`
- `browser: POST /api/v1/business/space -> 200`
- `A: GET /business/search -> 200`
- `A: GET /financial-search -> 200`

- PASS: search "Ferretería" after reload finds the Business expense only; opening it shows its receipt; the original downloads with a matching sha256 ({"query":"Ferretería","ui_expense_rows":1,"ui_receipt_rows":0,"ui_shows_business_merchant":true,"ui_shows_personal_amount":false,"opened_receipt_is_expected":true,"download_sha256_matches":true,"download_sha256":"b3b675045581","api_status":200,"api_expense_ids":["<web expense>"],"api_receipt_ids":[],"api_personal_hit":false})
- PASS: search "Colmado" after reload finds the Business expense only; opening it shows its receipt; the original downloads with a matching sha256 ({"query":"Colmado","ui_expense_rows":1,"ui_receipt_rows":0,"ui_shows_business_merchant":true,"ui_shows_personal_amount":false,"opened_receipt_is_expected":true,"download_sha256_matches":true,"download_sha256":"0cde8fde9397","api_status":200,"api_expense_ids":["<WhatsApp expense>"],"api_receipt_ids":[],"api_personal_hit":false})
- PASS: the Personal expense with the same merchant is in neither the omnisearch rows nor GET /business/search

### 2(a). The stub returns no purchase

```json
{
 "id": "<2a receipt>",
 "api": {
  "status": "needs_attention",
  "error_code": "no_financial_observations",
  "attention": "several_purchases",
  "preparable": false,
  "enterable": true,
  "version": 0,
  "evidence": {
   "merchant": "PAPELERIA CENTRAL",
   "occurred_on": "2026-10-07",
   "total": "845.00",
   "currency": "DOP",
   "tax": "128.90",
   "tip": null,
   "service": null,
   "lines": [
    {
     "description": "Resma carta x2",
     "amount": "716.10"
    }
   ]
  }
 },
 "screen": {
  "attention_text": "Cuadrao couldn't match this receipt to one purchase. Enter the details yourself to save one expense.",
  "retry_button": 0,
  "retry_consent_line": 0,
  "prepare_button": 0,
  "merchant_editable": true,
  "evidence_shown": 1,
  "confirm_button": 1
 },
 "rows_before": {
  "events": [],
  "read_batch_stored": true,
  "draft_status": "needs_attention",
  "draft_error_code": "no_financial_observations"
 },
 "ui_confirm": {
  "review_patches": 1,
  "confirm_posts": 1
 },
 "confirmed": {
  "status": "confirmed",
  "merchant": "Papelería Central",
  "amount": "845.00",
  "evidence_after": {
   "merchant": "PAPELERIA CENTRAL",
   "occurred_on": "2026-10-07",
   "total": "845.00",
   "currency": "DOP",
   "tax": "128.90",
   "tip": null,
   "service": null,
   "lines": [
    {
     "description": "Resma carta x2",
     "amount": "716.10"
    }
   ]
  },
  "expense": "<2a expense>"
 },
 "saved_screen_evidence": 1,
 "rows_after": {
  "events": [
   {
    "state": "accepted",
    "origin": "owner_entry",
    "expense": true,
    "live_observations": 1
   }
  ],
  "read_batch_stored": true,
  "draft_status": "needs_attention",
  "draft_error_code": "no_financial_observations"
 },
 "dismissal": {
  "reads_before": [],
  "reads_after": [],
  "owner_entries": [
   "accepted+expense"
  ],
  "ok": true
 },
 "replays": {
  "burst": [
   [
    200,
    "<2a expense>"
   ],
   [
    200,
    "<2a expense>"
   ]
  ],
  "stale_entry_replay": [
   409,
   "stale_version"
  ]
 },
 "accepted": [
  2,
  3
 ]
}
```

HTTP:

- `browser: POST /api/v1/business/receipts -> 200`
- `browser: POST /api/v1/business/space -> 200`
- `browser: PATCH /api/v1/business/receipts/{id}/review -> 200`
- `browser: POST /api/v1/business/receipts/{id}/confirm -> 200`
- `A: POST /business/receipts/<2a receipt>/confirm -> 200`
- `A: POST /business/receipts/<2a receipt>/confirm -> 200`
- `A: PATCH /business/receipts/<2a receipt>/review -> 409`

- FAIL: message "Cuadrao read this receipt but didn't find a purchase to save. Enter the details yourself." with no retry, fields open for entry ({"api":{"status":"needs_attention","error_code":"no_financial_observations","attention":"several_purchases","preparable":false,"enterable":true,"version":0,"evidence":{"merchant":"PAPELERIA CENTRAL","occurred_on":"2026-10-07","total":"845.00","currency":"DOP","tax":"128.90","tip":null,"service":null,"lines":[{"description":"Resma carta x2","amount":"716.10"}]}},"screen":{"attention_text":"Cuadrao couldn't match this receipt to one purchase. Enter the details yourself to save one expense.","retry_button":0,"retry_consent_line":0,"prepare_button":0,"merchant_editable":true,"evidence_shown":1,"confirm_button":1}})
- PASS: filled in by hand and confirmed: exactly one expense; double-click sent one review and one confirm ({"confirmed":{"status":"confirmed","merchant":"Papelería Central","amount":"845.00","evidence_after":{"merchant":"PAPELERIA CENTRAL","occurred_on":"2026-10-07","total":"845.00","currency":"DOP","tax":"128.90","tip":null,"service":null,"lines":[{"description":"Resma carta x2","amount":"716.10"}]},"expense":"<2a expense>"},"accepted":[2,3],"ui":{"review_patches":1,"confirm_posts":1}})
- PASS: the AI reading stays stored and visible as evidence after the hand entry ({"evidence_before":{"merchant":"PAPELERIA CENTRAL","occurred_on":"2026-10-07","total":"845.00","currency":"DOP","tax":"128.90","tip":null,"service":null,"lines":[{"description":"Resma carta x2","amount":"716.10"}]},"evidence_after":{"merchant":"PAPELERIA CENTRAL","occurred_on":"2026-10-07","total":"845.00","currency":"DOP","tax":"128.90","tip":null,"service":null,"lines":[{"description":"Resma carta x2","amount":"716.10"}]},"shown":1,"read_batch_stored":true})
- PASS: the read's purchase events are dismissed and kept, not deleted; the owner's entry is the one accepted expense ({"reads_before":[],"reads_after":[],"owner_entries":["accepted+expense"],"ok":true})
- PASS: same-key confirm burst returns the one expense; replaying the version-0 entry is refused ({"burst":[[200,"<2a expense>"],[200,"<2a expense>"]],"stale_entry_replay":[409,"stale_version"]})

### 2(a2). The stub returns a purchase row with no receipt details (not a receipt purchase), by API upload

```json
{
 "id": "<2a2 receipt>",
 "api": {
  "status": "needs_attention",
  "error_code": "no_purchase_found",
  "attention": "no_purchase_found",
  "preparable": false,
  "enterable": true,
  "version": 0,
  "evidence": null
 },
 "screen": {
  "attention_text": "Cuadrao read this receipt but didn't find a purchase to save. Enter the details yourself.",
  "retry_button": 0,
  "retry_consent_line": 0,
  "prepare_button": 0,
  "merchant_editable": true,
  "evidence_shown": 0,
  "confirm_button": 1
 },
 "rows_before": {
  "events": [
   {
    "state": "open",
    "origin": "read",
    "expense": false,
    "live_observations": 1
   }
  ],
  "read_batch_stored": true,
  "draft_status": "review_ready",
  "draft_error_code": null
 },
 "ui_confirm": {
  "review_patches": 1,
  "confirm_posts": 1
 },
 "confirmed": {
  "status": "confirmed",
  "merchant": "Claro Internet",
  "amount": "1890.00",
  "evidence_after": null,
  "expense": "<2a2 expense>"
 },
 "saved_screen_evidence": 0,
 "rows_after": {
  "events": [
   {
    "state": "accepted",
    "origin": "owner_entry",
    "expense": true,
    "live_observations": 1
   },
   {
    "state": "dismissed",
    "origin": "read",
    "expense": false,
    "live_observations": 1
   }
  ],
  "read_batch_stored": true,
  "draft_status": "review_ready",
  "draft_error_code": null
 },
 "dismissal": {
  "reads_before": [
   "open"
  ],
  "reads_after": [
   "dismissed"
  ],
  "owner_entries": [
   "accepted+expense"
  ],
  "ok": true
 },
 "replays": {
  "burst": [
   [
    200,
    "<2a2 expense>"
   ],
   [
    200,
    "<2a2 expense>"
   ]
  ],
  "stale_entry_replay": [
   409,
   "stale_version"
  ]
 },
 "accepted": [
  3,
  4
 ]
}
```

HTTP:

- `A: POST /business/receipts -> 200`
- `browser: POST /api/v1/business/space -> 200`
- `browser: PATCH /api/v1/business/receipts/{id}/review -> 200`
- `browser: POST /api/v1/business/receipts/{id}/confirm -> 200`
- `A: POST /business/receipts/<2a2 receipt>/confirm -> 200`
- `A: POST /business/receipts/<2a2 receipt>/confirm -> 200`
- `A: PATCH /business/receipts/<2a2 receipt>/review -> 409`

- PASS: message "Cuadrao read this receipt but didn't find a purchase to save. Enter the details yourself." with no retry, fields open for entry ({"api":{"status":"needs_attention","error_code":"no_purchase_found","attention":"no_purchase_found","preparable":false,"enterable":true,"version":0,"evidence":null},"screen":{"attention_text":"Cuadrao read this receipt but didn't find a purchase to save. Enter the details yourself.","retry_button":0,"retry_consent_line":0,"prepare_button":0,"merchant_editable":true,"evidence_shown":0,"confirm_button":1}})
- PASS: filled in by hand and confirmed: exactly one expense; double-click sent one review and one confirm ({"confirmed":{"status":"confirmed","merchant":"Claro Internet","amount":"1890.00","evidence_after":null,"expense":"<2a2 expense>"},"accepted":[3,4],"ui":{"review_patches":1,"confirm_posts":1}})
- PASS: the read stays stored; it had no receipt details, so evidence is null before and after ({"evidence_before":null,"evidence_after":null,"shown":0,"read_batch_stored":true})
- PASS: the read's purchase events are dismissed and kept, not deleted; the owner's entry is the one accepted expense ({"reads_before":["open"],"reads_after":["dismissed"],"owner_entries":["accepted+expense"],"ok":true})
- PASS: same-key confirm burst returns the one expense; replaying the version-0 entry is refused ({"burst":[[200,"<2a2 expense>"],[200,"<2a2 expense>"]],"stale_entry_replay":[409,"stale_version"]})

### 2(b). The stub returns several purchases

```json
{
 "id": "<2b receipt>",
 "api": {
  "status": "needs_attention",
  "error_code": "several_purchases_found",
  "attention": "several_purchases",
  "preparable": false,
  "enterable": true,
  "version": 0,
  "evidence": {
   "merchant": "SUPERMERCADO BRAVO",
   "occurred_on": "2026-10-07",
   "total": "2100.00",
   "currency": "DOP",
   "tax": "320.34",
   "tip": null,
   "service": null,
   "lines": [
    {
     "description": "Compra semanal",
     "amount": "1779.66"
    }
   ]
  }
 },
 "screen": {
  "attention_text": "Cuadrao couldn't match this receipt to one purchase. Enter the details yourself to save one expense.",
  "retry_button": 0,
  "retry_consent_line": 0,
  "prepare_button": 0,
  "merchant_editable": true,
  "evidence_shown": 1,
  "confirm_button": 1
 },
 "rows_before": {
  "events": [
   {
    "state": "open",
    "origin": "read",
    "expense": false,
    "live_observations": 1
   },
   {
    "state": "open",
    "origin": "read",
    "expense": false,
    "live_observations": 1
   }
  ],
  "read_batch_stored": true,
  "draft_status": "review_ready",
  "draft_error_code": null
 },
 "ui_confirm": {
  "review_patches": 1,
  "confirm_posts": 1
 },
 "confirmed": {
  "status": "confirmed",
  "merchant": "Supermercado Bravo",
  "amount": "2100.00",
  "evidence_after": {
   "merchant": "SUPERMERCADO BRAVO",
   "occurred_on": "2026-10-07",
   "total": "2100.00",
   "currency": "DOP",
   "tax": "320.34",
   "tip": null,
   "service": null,
   "lines": [
    {
     "description": "Compra semanal",
     "amount": "1779.66"
    }
   ]
  },
  "expense": "<2b expense>"
 },
 "saved_screen_evidence": 1,
 "rows_after": {
  "events": [
   {
    "state": "accepted",
    "origin": "owner_entry",
    "expense": true,
    "live_observations": 1
   },
   {
    "state": "dismissed",
    "origin": "read",
    "expense": false,
    "live_observations": 1
   },
   {
    "state": "dismissed",
    "origin": "read",
    "expense": false,
    "live_observations": 1
   }
  ],
  "read_batch_stored": true,
  "draft_status": "review_ready",
  "draft_error_code": null
 },
 "dismissal": {
  "reads_before": [
   "open",
   "open"
  ],
  "reads_after": [
   "dismissed",
   "dismissed"
  ],
  "owner_entries": [
   "accepted+expense"
  ],
  "ok": true
 },
 "replays": {
  "burst": [
   [
    200,
    "<2b expense>"
   ],
   [
    200,
    "<2b expense>"
   ]
  ],
  "stale_entry_replay": [
   409,
   "stale_version"
  ]
 },
 "accepted": [
  4,
  5
 ]
}
```

HTTP:

- `browser: POST /api/v1/business/receipts -> 200`
- `browser: POST /api/v1/business/space -> 200`
- `browser: PATCH /api/v1/business/receipts/{id}/review -> 200`
- `browser: POST /api/v1/business/receipts/{id}/confirm -> 200`
- `A: POST /business/receipts/<2b receipt>/confirm -> 200`
- `A: POST /business/receipts/<2b receipt>/confirm -> 200`
- `A: PATCH /business/receipts/<2b receipt>/review -> 409`

- PASS: message "Cuadrao couldn't match this receipt to one purchase. Enter the details yourself to save one expense." with no retry, fields open for entry ({"api":{"status":"needs_attention","error_code":"several_purchases_found","attention":"several_purchases","preparable":false,"enterable":true,"version":0,"evidence":{"merchant":"SUPERMERCADO BRAVO","occurred_on":"2026-10-07","total":"2100.00","currency":"DOP","tax":"320.34","tip":null,"service":null,"lines":[{"description":"Compra semanal","amount":"1779.66"}]}},"screen":{"attention_text":"Cuadrao couldn't match this receipt to one purchase. Enter the details yourself to save one expense.","retry_button":0,"retry_consent_line":0,"prepare_button":0,"merchant_editable":true,"evidence_shown":1,"confirm_button":1}})
- PASS: filled in by hand and confirmed: exactly one expense; double-click sent one review and one confirm ({"confirmed":{"status":"confirmed","merchant":"Supermercado Bravo","amount":"2100.00","evidence_after":{"merchant":"SUPERMERCADO BRAVO","occurred_on":"2026-10-07","total":"2100.00","currency":"DOP","tax":"320.34","tip":null,"service":null,"lines":[{"description":"Compra semanal","amount":"1779.66"}]},"expense":"<2b expense>"},"accepted":[4,5],"ui":{"review_patches":1,"confirm_posts":1}})
- PASS: the AI reading stays stored and visible as evidence after the hand entry ({"evidence_before":{"merchant":"SUPERMERCADO BRAVO","occurred_on":"2026-10-07","total":"2100.00","currency":"DOP","tax":"320.34","tip":null,"service":null,"lines":[{"description":"Compra semanal","amount":"1779.66"}]},"evidence_after":{"merchant":"SUPERMERCADO BRAVO","occurred_on":"2026-10-07","total":"2100.00","currency":"DOP","tax":"320.34","tip":null,"service":null,"lines":[{"description":"Compra semanal","amount":"1779.66"}]},"shown":1,"read_batch_stored":true})
- PASS: the read's purchase events are dismissed and kept, not deleted; the owner's entry is the one accepted expense ({"reads_before":["open","open"],"reads_after":["dismissed","dismissed"],"owner_entries":["accepted+expense"],"ok":true})
- PASS: same-key confirm burst returns the one expense; replaying the version-0 entry is refused ({"burst":[[200,"<2b expense>"],[200,"<2b expense>"]],"stale_entry_replay":[409,"stale_version"]})

### 2(c). The stub returns an ambiguous purchase

```json
{
 "id": "<2c receipt>",
 "api": {
  "status": "needs_attention",
  "error_code": "receipt_purchase_ambiguous",
  "attention": "several_purchases",
  "preparable": false,
  "enterable": true,
  "version": 0,
  "evidence": {
   "merchant": "PANADERIA DONA ANA",
   "occurred_on": "2026-10-07",
   "total": "1250.00",
   "currency": "DOP",
   "tax": "190.68",
   "tip": null,
   "service": null,
   "lines": [
    {
     "description": "Pan sobao x10",
     "amount": "1059.32"
    }
   ]
  }
 },
 "screen": {
  "attention_text": "Cuadrao couldn't match this receipt to one purchase. Enter the details yourself to save one expense.",
  "retry_button": 0,
  "retry_consent_line": 0,
  "prepare_button": 0,
  "merchant_editable": true,
  "evidence_shown": 1,
  "confirm_button": 1
 },
 "rows_before": {
  "events": [],
  "read_batch_stored": true,
  "draft_status": "needs_attention",
  "draft_error_code": "receipt_purchase_ambiguous"
 },
 "ui_confirm": {
  "review_patches": 1,
  "confirm_posts": 1
 },
 "confirmed": {
  "status": "confirmed",
  "merchant": "Panadería Doña Ana",
  "amount": "1250.00",
  "evidence_after": {
   "merchant": "PANADERIA DONA ANA",
   "occurred_on": "2026-10-07",
   "total": "1250.00",
   "currency": "DOP",
   "tax": "190.68",
   "tip": null,
   "service": null,
   "lines": [
    {
     "description": "Pan sobao x10",
     "amount": "1059.32"
    }
   ]
  },
  "expense": "<2c expense>"
 },
 "saved_screen_evidence": 1,
 "rows_after": {
  "events": [
   {
    "state": "accepted",
    "origin": "owner_entry",
    "expense": true,
    "live_observations": 1
   }
  ],
  "read_batch_stored": true,
  "draft_status": "needs_attention",
  "draft_error_code": "receipt_purchase_ambiguous"
 },
 "dismissal": {
  "reads_before": [],
  "reads_after": [],
  "owner_entries": [
   "accepted+expense"
  ],
  "ok": true
 },
 "replays": {
  "burst": [
   [
    200,
    "<2c expense>"
   ],
   [
    200,
    "<2c expense>"
   ]
  ],
  "stale_entry_replay": [
   409,
   "stale_version"
  ]
 },
 "accepted": [
  5,
  6
 ]
}
```

HTTP:

- `browser: POST /api/v1/business/receipts -> 200`
- `browser: POST /api/v1/business/space -> 200`
- `browser: PATCH /api/v1/business/receipts/{id}/review -> 200`
- `browser: POST /api/v1/business/receipts/{id}/confirm -> 200`
- `A: POST /business/receipts/<2c receipt>/confirm -> 200`
- `A: POST /business/receipts/<2c receipt>/confirm -> 200`
- `A: PATCH /business/receipts/<2c receipt>/review -> 409`

- PASS: message "Cuadrao couldn't match this receipt to one purchase. Enter the details yourself to save one expense." with no retry, fields open for entry ({"api":{"status":"needs_attention","error_code":"receipt_purchase_ambiguous","attention":"several_purchases","preparable":false,"enterable":true,"version":0,"evidence":{"merchant":"PANADERIA DONA ANA","occurred_on":"2026-10-07","total":"1250.00","currency":"DOP","tax":"190.68","tip":null,"service":null,"lines":[{"description":"Pan sobao x10","amount":"1059.32"}]}},"screen":{"attention_text":"Cuadrao couldn't match this receipt to one purchase. Enter the details yourself to save one expense.","retry_button":0,"retry_consent_line":0,"prepare_button":0,"merchant_editable":true,"evidence_shown":1,"confirm_button":1}})
- PASS: filled in by hand and confirmed: exactly one expense; double-click sent one review and one confirm ({"confirmed":{"status":"confirmed","merchant":"Panadería Doña Ana","amount":"1250.00","evidence_after":{"merchant":"PANADERIA DONA ANA","occurred_on":"2026-10-07","total":"1250.00","currency":"DOP","tax":"190.68","tip":null,"service":null,"lines":[{"description":"Pan sobao x10","amount":"1059.32"}]},"expense":"<2c expense>"},"accepted":[5,6],"ui":{"review_patches":1,"confirm_posts":1}})
- PASS: the AI reading stays stored and visible as evidence after the hand entry ({"evidence_before":{"merchant":"PANADERIA DONA ANA","occurred_on":"2026-10-07","total":"1250.00","currency":"DOP","tax":"190.68","tip":null,"service":null,"lines":[{"description":"Pan sobao x10","amount":"1059.32"}]},"evidence_after":{"merchant":"PANADERIA DONA ANA","occurred_on":"2026-10-07","total":"1250.00","currency":"DOP","tax":"190.68","tip":null,"service":null,"lines":[{"description":"Pan sobao x10","amount":"1059.32"}]},"shown":1,"read_batch_stored":true})
- PASS: the read's purchase events are dismissed and kept, not deleted; the owner's entry is the one accepted expense ({"reads_before":[],"reads_after":[],"owner_entries":["accepted+expense"],"ok":true})
- PASS: same-key confirm burst returns the one expense; replaying the version-0 entry is refused ({"burst":[[200,"<2c expense>"],[200,"<2c expense>"]],"stale_entry_replay":[409,"stale_version"]})

### 2(d). Provider failure, no batch

```json
{
 "id": "<2d receipt>",
 "api": {
  "status": "needs_attention",
  "error_code": "extraction_provider_failed",
  "attention": "ai_unavailable",
  "preparable": true,
  "enterable": true,
  "version": 0,
  "evidence": null
 },
 "screen": {
  "attention_text": "AI preparation isn't available right now. Your receipt is saved. Try again later or enter the details yourself.",
  "retry_button": 1,
  "retry_consent_line": 1,
  "prepare_button": 0,
  "merchant_editable": true,
  "evidence_shown": 0,
  "confirm_button": 1
 },
 "rows_before": {
  "events": [],
  "read_batch_stored": false,
  "draft_status": "needs_attention",
  "draft_error_code": "extraction_provider_failed"
 },
 "no_click": {
  "stub_calls_after_15s_and_list_reads": 0,
  "prepare_without_consent": [
   422,
   "document_extraction_consent_required"
  ],
  "stub_calls_after_refusal": 0
 },
 "retry": {
  "prepare_requests": [
   {
    "consent_header": "true"
   }
  ],
  "new_stub_calls": 1,
  "after": {
   "status": "needs_attention",
   "attention": "ai_unavailable",
   "preparable": true,
   "enterable": true,
   "evidence": false
  }
 },
 "retry_evidence": null,
 "screen_after_retry": {
  "attention_text": "AI preparation isn't available right now. Your receipt is saved. Try again later or enter the details yourself.",
  "retry_button": 1,
  "retry_consent_line": 1,
  "prepare_button": 0,
  "merchant_editable": true,
  "evidence_shown": 0,
  "confirm_button": 1
 },
 "rows_after_retry": {
  "events": [],
  "read_batch_stored": false,
  "draft_status": "needs_attention",
  "draft_error_code": "extraction_provider_failed"
 },
 "ui_confirm": {
  "review_patches": 1,
  "confirm_posts": 1
 },
 "confirmed": {
  "status": "confirmed",
  "merchant": "Taller Mecánico Ramírez",
  "amount": "3800.00",
  "evidence_after": null,
  "expense": "<2d expense>"
 },
 "saved_screen_evidence": 0,
 "rows_after": {
  "events": [
   {
    "state": "accepted",
    "origin": "owner_entry",
    "expense": true,
    "live_observations": 1
   }
  ],
  "read_batch_stored": true,
  "draft_status": "review_ready",
  "draft_error_code": null
 },
 "dismissal": {
  "reads_before": [],
  "reads_after": [],
  "owner_entries": [
   "accepted+expense"
  ],
  "ok": true
 },
 "replays": {
  "burst": [
   [
    200,
    "<2d expense>"
   ],
   [
    200,
    "<2d expense>"
   ]
  ],
  "stale_entry_replay": [
   409,
   "stale_version"
  ]
 },
 "accepted": [
  6,
  7
 ]
}
```

HTTP:

- `browser: POST /api/v1/business/receipts -> 200`
- `browser: POST /api/v1/business/space -> 200`
- `A: GET /business/receipts -> 200`
- `A: GET /business/overview -> 200`
- `A: POST /business/receipts/<2d receipt>/prepare -> 422`
- `browser: POST /api/v1/business/receipts/{id}/prepare -> 200`
- `browser: POST /api/v1/business/space -> 200`
- `browser: PATCH /api/v1/business/receipts/{id}/review -> 200`
- `browser: POST /api/v1/business/receipts/{id}/confirm -> 200`
- `A: POST /business/receipts/<2d receipt>/confirm -> 200`
- `A: POST /business/receipts/<2d receipt>/confirm -> 200`
- `A: PATCH /business/receipts/<2d receipt>/review -> 409`

- PASS: message "AI preparation isn't available right now. Your receipt is saved. Try again later or enter the details yourself." with Try again with AI and its consent line, fields open for entry ({"api":{"status":"needs_attention","error_code":"extraction_provider_failed","attention":"ai_unavailable","preparable":true,"enterable":true,"version":0,"evidence":null},"screen":{"attention_text":"AI preparation isn't available right now. Your receipt is saved. Try again later or enter the details yourself.","retry_button":1,"retry_consent_line":1,"prepare_button":0,"merchant_editable":true,"evidence_shown":0,"confirm_button":1}})
- PASS: no retry without the click; Try again with AI sends the consent header and makes exactly one new stub call ({"no_click":{"stub_calls_after_15s_and_list_reads":0,"prepare_without_consent":[422,"document_extraction_consent_required"],"stub_calls_after_refusal":0},"retry":{"prepare_requests":[{"consent_header":"true"}],"new_stub_calls":1,"after":{"status":"needs_attention","attention":"ai_unavailable","preparable":true,"enterable":true,"evidence":false}}})
- PASS: after the retry: message "AI preparation isn't available right now. Your receipt is saved. Try again later or enter the details yourself.", still enterable ({"after":{"status":"needs_attention","attention":"ai_unavailable","preparable":true,"enterable":true,"evidence":false},"screen":{"attention_text":"AI preparation isn't available right now. Your receipt is saved. Try again later or enter the details yourself.","retry_button":1,"retry_consent_line":1,"prepare_button":0,"merchant_editable":true,"evidence_shown":0,"confirm_button":1}})
- PASS: filled in by hand and confirmed: exactly one expense; double-click sent one review and one confirm ({"confirmed":{"status":"confirmed","merchant":"Taller Mecánico Ramírez","amount":"3800.00","evidence_after":null,"expense":"<2d expense>"},"accepted":[6,7],"ui":{"review_patches":1,"confirm_posts":1}})
- FAIL: no reading exists (provider failed); no batch stored and evidence stays null ({"evidence_before":null,"evidence_after":null,"shown":0,"read_batch_stored":true})
- PASS: the read's purchase events are dismissed and kept, not deleted; the owner's entry is the one accepted expense ({"reads_before":[],"reads_after":[],"owner_entries":["accepted+expense"],"ok":true})
- PASS: same-key confirm burst returns the one expense; replaying the version-0 entry is refused ({"burst":[[200,"<2d expense>"],[200,"<2d expense>"]],"stale_entry_replay":[409,"stale_version"]})
- PASS: provider failure ends needs_attention with no batch stored ({"api":{"status":"needs_attention","error_code":"extraction_provider_failed","attention":"ai_unavailable","preparable":true,"enterable":true,"version":0,"evidence":null},"rows":{"events":[],"read_batch_stored":false,"draft_status":"needs_attention","draft_error_code":"extraction_provider_failed"}})

### 2(e). Unknown outcome after the API was killed mid-preparation

```json
{
 "id": "<2e receipt>",
 "api": {
  "status": "needs_attention",
  "error_code": "document_preparation_outcome_unknown",
  "attention": "outcome_unknown",
  "preparable": true,
  "enterable": true,
  "version": 0,
  "evidence": null
 },
 "screen": {
  "attention_text": "We don't know if the AI finished reading this receipt, and nothing was saved from it. Try again or enter the details yourself.",
  "retry_button": 1,
  "retry_consent_line": 1,
  "prepare_button": 0,
  "merchant_editable": true,
  "evidence_shown": 0,
  "confirm_button": 1
 },
 "rows_before": {
  "events": [],
  "read_batch_stored": false,
  "draft_status": "needs_attention",
  "draft_error_code": "document_preparation_outcome_unknown"
 },
 "no_click": {
  "stub_calls_after_15s_and_list_reads": 0,
  "prepare_without_consent": [
   422,
   "document_extraction_consent_required"
  ],
  "stub_calls_after_refusal": 0
 },
 "retry": {
  "prepare_requests": [
   {
    "consent_header": "true"
   }
  ],
  "new_stub_calls": 1,
  "after": {
   "status": "needs_attention",
   "attention": "several_purchases",
   "preparable": false,
   "enterable": true,
   "evidence": true
  }
 },
 "retry_evidence": {
  "merchant": "GASOLINERA LA AUTOPISTA",
  "occurred_on": "2026-10-07",
  "total": "2000.00",
  "currency": "DOP",
  "tax": "305.08",
  "tip": null,
  "service": null,
  "lines": [
   {
    "description": "Gasolina premium",
    "amount": "1694.92"
   }
  ]
 },
 "screen_after_retry": {
  "attention_text": "Cuadrao couldn't match this receipt to one purchase. Enter the details yourself to save one expense.",
  "retry_button": 0,
  "retry_consent_line": 0,
  "prepare_button": 0,
  "merchant_editable": true,
  "evidence_shown": 1,
  "confirm_button": 1
 },
 "rows_after_retry": {
  "events": [
   {
    "state": "open",
    "origin": "read",
    "expense": false,
    "live_observations": 1
   },
   {
    "state": "open",
    "origin": "read",
    "expense": false,
    "live_observations": 1
   }
  ],
  "read_batch_stored": true,
  "draft_status": "review_ready",
  "draft_error_code": null
 },
 "ui_confirm": {
  "review_patches": 1,
  "confirm_posts": 1
 },
 "confirmed": {
  "status": "confirmed",
  "merchant": "Gasolinera La Autopista",
  "amount": "2000.00",
  "evidence_after": {
   "merchant": "GASOLINERA LA AUTOPISTA",
   "occurred_on": "2026-10-07",
   "total": "2000.00",
   "currency": "DOP",
   "tax": "305.08",
   "tip": null,
   "service": null,
   "lines": [
    {
     "description": "Gasolina premium",
     "amount": "1694.92"
    }
   ]
  },
  "expense": "<2e expense>"
 },
 "saved_screen_evidence": 1,
 "rows_after": {
  "events": [
   {
    "state": "accepted",
    "origin": "owner_entry",
    "expense": true,
    "live_observations": 1
   },
   {
    "state": "dismissed",
    "origin": "read",
    "expense": false,
    "live_observations": 1
   },
   {
    "state": "dismissed",
    "origin": "read",
    "expense": false,
    "live_observations": 1
   }
  ],
  "read_batch_stored": true,
  "draft_status": "review_ready",
  "draft_error_code": null
 },
 "dismissal": {
  "reads_before": [
   "open",
   "open"
  ],
  "reads_after": [
   "dismissed",
   "dismissed"
  ],
  "owner_entries": [
   "accepted+expense"
  ],
  "ok": true
 },
 "replays": {
  "burst": [
   [
    200,
    "<2e expense>"
   ],
   [
    200,
    "<2e expense>"
   ]
  ],
  "stale_entry_replay": [
   409,
   "stale_version"
  ]
 },
 "accepted": [
  7,
  8
 ]
}
```

HTTP:

- `browser: POST /api/v1/business/space -> 200`
- `browser: POST /api/v1/business/space -> 200`
- `A: GET /business/receipts -> 200`
- `A: GET /business/overview -> 200`
- `A: POST /business/receipts/<2e receipt>/prepare -> 422`
- `browser: POST /api/v1/business/receipts/{id}/prepare -> 200`
- `browser: POST /api/v1/business/space -> 200`
- `browser: PATCH /api/v1/business/receipts/{id}/review -> 200`
- `browser: POST /api/v1/business/receipts/{id}/confirm -> 200`
- `A: POST /business/receipts/<2e receipt>/confirm -> 200`
- `A: POST /business/receipts/<2e receipt>/confirm -> 200`
- `A: PATCH /business/receipts/<2e receipt>/review -> 409`

- PASS: message "We don't know if the AI finished reading this receipt, and nothing was saved from it. Try again or enter the details yourself." with Try again with AI and its consent line, fields open for entry ({"api":{"status":"needs_attention","error_code":"document_preparation_outcome_unknown","attention":"outcome_unknown","preparable":true,"enterable":true,"version":0,"evidence":null},"screen":{"attention_text":"We don't know if the AI finished reading this receipt, and nothing was saved from it. Try again or enter the details yourself.","retry_button":1,"retry_consent_line":1,"prepare_button":0,"merchant_editable":true,"evidence_shown":0,"confirm_button":1}})
- PASS: no retry without the click; Try again with AI sends the consent header and makes exactly one new stub call ({"no_click":{"stub_calls_after_15s_and_list_reads":0,"prepare_without_consent":[422,"document_extraction_consent_required"],"stub_calls_after_refusal":0},"retry":{"prepare_requests":[{"consent_header":"true"}],"new_stub_calls":1,"after":{"status":"needs_attention","attention":"several_purchases","preparable":false,"enterable":true,"evidence":true}}})
- PASS: after the retry: message "Cuadrao couldn't match this receipt to one purchase. Enter the details yourself to save one expense.", still enterable ({"after":{"status":"needs_attention","attention":"several_purchases","preparable":false,"enterable":true,"evidence":true},"screen":{"attention_text":"Cuadrao couldn't match this receipt to one purchase. Enter the details yourself to save one expense.","retry_button":0,"retry_consent_line":0,"prepare_button":0,"merchant_editable":true,"evidence_shown":1,"confirm_button":1}})
- PASS: filled in by hand and confirmed: exactly one expense; double-click sent one review and one confirm ({"confirmed":{"status":"confirmed","merchant":"Gasolinera La Autopista","amount":"2000.00","evidence_after":{"merchant":"GASOLINERA LA AUTOPISTA","occurred_on":"2026-10-07","total":"2000.00","currency":"DOP","tax":"305.08","tip":null,"service":null,"lines":[{"description":"Gasolina premium","amount":"1694.92"}]},"expense":"<2e expense>"},"accepted":[7,8],"ui":{"review_patches":1,"confirm_posts":1}})
- PASS: the AI reading stays stored and visible as evidence after the hand entry ({"evidence_before":{"merchant":"GASOLINERA LA AUTOPISTA","occurred_on":"2026-10-07","total":"2000.00","currency":"DOP","tax":"305.08","tip":null,"service":null,"lines":[{"description":"Gasolina premium","amount":"1694.92"}]},"evidence_after":{"merchant":"GASOLINERA LA AUTOPISTA","occurred_on":"2026-10-07","total":"2000.00","currency":"DOP","tax":"305.08","tip":null,"service":null,"lines":[{"description":"Gasolina premium","amount":"1694.92"}]},"shown":1,"read_batch_stored":true})
- PASS: the read's purchase events are dismissed and kept, not deleted; the owner's entry is the one accepted expense ({"reads_before":["open","open"],"reads_after":["dismissed","dismissed"],"owner_entries":["accepted+expense"],"ok":true})
- PASS: same-key confirm burst returns the one expense; replaying the version-0 entry is refused ({"burst":[[200,"<2e expense>"],[200,"<2e expense>"]],"stale_entry_replay":[409,"stale_version"]})

2(e) settle: 304 s after the restart the receipt was needs_attention (document_preparation_outcome_unknown). Sweep log: ["argus.domain.ingestion.documents.jobs:_reconcile:150 - Document preparation outcome unknown; waiting for the owner","argus.domain.ingestion.documents.jobs:_reconcile:150 - Document preparation outcome unknown; waiting for the owner"]. Stub calls for this receipt: 2: ["pid <2e receipt> fc21d52c1acc call=1 read","pid <2e receipt> fc21d52c1acc call=2 read"].

- PASS: the sweep settled the killed preparation to needs_attention outcome_unknown with one stub call ({"status":"needs_attention","attention":"outcome_unknown","error_code":"document_preparation_outcome_unknown"})

### 2. API restart, then the same keys again

stopped; api up pid <pid>. Each scenario 2 receipt's confirm replayed with its earlier Idempotency-Key -> {"a":[200,true],"a2":[200,true],"b":[200,true],"c":[200,true],"d":[200,true],"e":[200,true]} ([status, same expense]). Business expenses listed for October: 8.

HTTP:

- `A: POST /business/receipts/<2a receipt>/confirm -> 200`
- `A: POST /business/receipts/<2a2 receipt>/confirm -> 200`
- `A: POST /business/receipts/<2b receipt>/confirm -> 200`
- `A: POST /business/receipts/<2c receipt>/confirm -> 200`
- `A: POST /business/receipts/<2d receipt>/confirm -> 200`
- `A: POST /business/receipts/<2e receipt>/confirm -> 200`
- `browser: POST /api/v1/business/space -> 200`
- `A: GET /business/expenses -> 200`

Rows:

```json
{
 "before_restart": {
  "accounts": 1,
  "documents_live": 8,
  "document_drafts": 8,
  "import_events_open": 0,
  "import_events_accepted": 8
 },
 "after_restart_and_replay": {
  "accounts": 1,
  "documents_live": 8,
  "document_drafts": 8,
  "import_events_open": 0,
  "import_events_accepted": 8
 }
}
```

- PASS: an API restart and a same-key replay of every scenario 2 confirm leave one expense each ({"replays":{"a":[200,true],"a2":[200,true],"b":[200,true],"c":[200,true],"d":[200,true],"e":[200,true]},"accepted":[8,8]})

### 3. A Personal or another owner's account id in review

```json
{
 "s3-saved with A's Personal account": {
  "status_before": "saved",
  "response": [
   404,
   "financial_account_not_found"
  ],
  "detail_unchanged": true,
  "rows_unchanged": true,
  "version": [
   0,
   0
  ]
 },
 "s3-saved with B's Business account": {
  "status_before": "saved",
  "response": [
   404,
   "financial_account_not_found"
  ],
  "detail_unchanged": true,
  "rows_unchanged": true,
  "version": [
   0,
   0
  ]
 },
 "s3-ready with A's Personal account": {
  "status_before": "review_ready",
  "response": [
   404,
   "financial_account_not_found"
  ],
  "detail_unchanged": true,
  "rows_unchanged": true,
  "version": [
   1,
   1
  ]
 },
 "s3-ready with B's Business account": {
  "status_before": "review_ready",
  "response": [
   404,
   "financial_account_not_found"
  ],
  "detail_unchanged": true,
  "rows_unchanged": true,
  "version": [
   1,
   1
  ]
 },
 "s3-several with A's Personal account": {
  "status_before": "needs_attention",
  "response": [
   404,
   "financial_account_not_found"
  ],
  "detail_unchanged": true,
  "rows_unchanged": true,
  "version": [
   0,
   0
  ]
 },
 "s3-several with B's Business account": {
  "status_before": "needs_attention",
  "response": [
   404,
   "financial_account_not_found"
  ],
  "detail_unchanged": true,
  "rows_unchanged": true,
  "version": [
   0,
   0
  ]
 }
}
```

Control: the same PATCH on the review-ready receipt with A's own Business account -> 200.

HTTP:

- `B: POST /business/space -> 201`
- `B: POST /business/accounts -> 201`
- `A: POST /business/receipts -> 200`
- `A: PATCH /business/receipts/<s3-saved receipt>/review -> 404`
- `A: PATCH /business/receipts/<s3-saved receipt>/review -> 404`
- `A: POST /business/receipts -> 200`
- `A: PATCH /business/receipts/<s3-ready receipt>/review -> 404`
- `A: PATCH /business/receipts/<s3-ready receipt>/review -> 404`
- `A: POST /business/receipts -> 200`
- `A: PATCH /business/receipts/<s3-several receipt>/review -> 404`
- `A: PATCH /business/receipts/<s3-several receipt>/review -> 404`
- `A: PATCH /business/receipts/<s3-ready receipt>/review -> 200`

- PASS: Personal and another owner's account ids in review return 404 financial_account_not_found; the receipt and its rows are unchanged ({"s3-saved with A's Personal account":{"status_before":"saved","response":[404,"financial_account_not_found"],"detail_unchanged":true,"rows_unchanged":true,"version":[0,0]},"s3-saved with B's Business account":{"status_before":"saved","response":[404,"financial_account_not_found"],"detail_unchanged":true,"rows_unchanged":true,"version":[0,0]},"s3-ready with A's Personal account":{"status_before":"review_ready","response":[404,"financial_account_not_found"],"detail_unchanged":true,"rows_unchanged":true,"version":[1,1]},"s3-ready with B's Business account":{"status_before":"review_ready","response":[404,"financial_account_not_found"],"detail_unchanged":true,"rows_unchanged":true,"version":[1,1]},"s3-several with A's Personal account":{"status_before":"needs_attention","response":[404,"financial_account_not_found"],"detail_unchanged":true,"rows_unchanged":true,"version":[0,0]},"s3-several with B's Business account":{"status_before":"needs_attention","response":[404,"financial_account_not_found"],"detail_unchanged":true,"rows_unchanged":true,"version":[0,0]}})

### 1c. Owner B's search

```json
{
 "3450": {
  "status": 200,
  "expenses": 0,
  "receipts": 0,
  "accounts": []
 },
 "Ferretería": {
  "status": 200,
  "expenses": 0,
  "receipts": 0,
  "accounts": []
 },
 "Ferreter": {
  "status": 200,
  "expenses": 0,
  "receipts": 0,
  "accounts": []
 },
 "Colmado": {
  "status": 200,
  "expenses": 0,
  "receipts": 0,
  "accounts": []
 },
 "706.10": {
  "status": 200,
  "expenses": 0,
  "receipts": 0,
  "accounts": []
 },
 "ferreteria-oct": {
  "status": 200,
  "expenses": 0,
  "receipts": 0,
  "accounts": []
 },
 "Cuenta operativa": {
  "status": 200,
  "expenses": 0,
  "receipts": 0,
  "accounts": []
 },
 "Papelería": {
  "status": 200,
  "expenses": 0,
  "receipts": 0,
  "accounts": []
 },
 "Gasolinera": {
  "status": 200,
  "expenses": 0,
  "receipts": 0,
  "accounts": []
 },
 "a": {
  "status": 200,
  "expenses": 0,
  "receipts": 0,
  "accounts": []
 }
}
```

A's ids (receipts, expenses, accounts, space) found in B's q=a response: []. B's browser: /biz Search "Ferretería" shows Business results: 0, "No results found": 1.

HTTP:

- `B: GET /business/search -> 200`
- `B: GET /business/search -> 200`
- `B: GET /business/search -> 200`
- `B: GET /business/search -> 200`
- `B: GET /business/search -> 200`
- `B: GET /business/search -> 200`
- `B: GET /business/search -> 200`
- `B: GET /business/search -> 200`
- `B: GET /business/search -> 200`
- `B: GET /business/search -> 200`
- `B: GET /business/search -> 200`

- PASS: owner B's search finds nothing of A's (API and omnisearch) ({"bSearch":{"3450":{"status":200,"expenses":0,"receipts":0,"accounts":[]},"Ferretería":{"status":200,"expenses":0,"receipts":0,"accounts":[]},"Ferreter":{"status":200,"expenses":0,"receipts":0,"accounts":[]},"Colmado":{"status":200,"expenses":0,"receipts":0,"accounts":[]},"706.10":{"status":200,"expenses":0,"receipts":0,"accounts":[]},"ferreteria-oct":{"status":200,"expenses":0,"receipts":0,"accounts":[]},"Cuenta operativa":{"status":200,"expenses":0,"receipts":0,"accounts":[]},"Papelería":{"status":200,"expenses":0,"receipts":0,"accounts":[]},"Gasolinera":{"status":200,"expenses":0,"receipts":0,"accounts":[]},"a":{"status":200,"expenses":0,"receipts":0,"accounts":[]}},"bLeaks":[],"bUi":{"business_rows":0,"no_results":1}})

Stub extractor calls this run: 12. Browser console errors: 1.

