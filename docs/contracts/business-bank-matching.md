# Business bank matching

Default off. The routes exist only when the Business pilot is on and `CUADRAO_BUSINESS_BANK_MATCHING_ENABLED` is true. Otherwise every route answers 404 `business_unavailable`.

One Business space has one bank account. A person imports one statement, confirms or declines each suggestion, and every charge ends confirmed or on the sin comprobante list. Nothing confirms itself.

`unmatched_charge_count(space_id: UUID, period_start: date, period_end: date) -> int`

Defined in `src/argus/domain/business/bank/service.py`. The period is inclusive. The count is charges whose amount is below zero and that have no confirmed receipt. Deposits are not included. The function raises `business_bank_matching_off` when the process service is unset.

## Endpoints

All routes are under `/api/v1/business/bank`. They require a signed-in Business person. `prepare` can import, confirm, and decline. `read` can list. Responses send `Cache-Control: no-store`.

### POST /imports

Multipart file field `statement`. Form field `account_id`. Optional `reader_id` of `pilot_bank`, `banco_popular`, `bhd`, `mercury`, `sandbox_csv`, or `mapped_csv`. Mapped CSV also sends `date_column`, `description_column`, and either `amount_column` plus `sign_column` or `debit_column` plus `credit_column`. Optional `currency_column`. Header `Idempotency-Key`.

201 when the upload is new. 200 when the same key and the same bytes are sent again.

```json
{
  "id": "uuid",
  "reader_id": "banco_popular",
  "inserted_count": 1,
  "unchanged_count": 0,
  "created": true,
  "imported_at": "2026-10-17T12:00:00Z",
  "lines": [
    {
      "id": "uuid",
      "occurred_on": "2026-10-01",
      "description": "text",
      "amount": "-1500.0000",
      "currency": "DOP",
      "sense": "charge",
      "state": "sin_comprobante"
    }
  ],
  "suggestions": [
    {
      "id": "uuid",
      "line_id": "uuid",
      "target_id": "text",
      "target_kind": "receipt",
      "status": "pending",
      "amount_score": "1.000",
      "date_score": "1.000",
      "merchant_score": "1.000",
      "confidence": "1.000",
      "actionable": true
    }
  ]
}
```

`sense` is `charge`, `deposit`, or `zero`. `state` is `matched`, `sin_comprobante`, or `unmatched`. `target_kind` is `receipt` or `venta`. `status` is `pending`, `confirmed`, or `declined`. `actionable` is true only while the suggestion is pending and the line has no confirmed suggestion.

### GET /suggestions

Optional query `status` of `pending`, `confirmed`, or `declined`. Returns the suggestion array above.

### POST /suggestions/{suggestion_id}/confirm

### POST /suggestions/{suggestion_id}/decline

Header `Idempotency-Key`. Returns one suggestion. The same key and the same decision returns the same row.

### GET /unmatched

Query `period_start` and `period_end` as dates. `period_end` before `period_start` is 422 `invalid_period`.

```json
{
  "count": 1,
  "period_start": "2026-10-01",
  "period_end": "2026-10-17",
  "lines": []
}
```

`count` matches `unmatched_charge_count` for that space and period.

## Errors

| Code | Status |
| --- | --- |
| business_unavailable | 404 |
| business_bank_matching_off | 404 |
| business_permission_denied | 403 |
| idempotency_key_required | 400 |
| validation_error | 422 |
| account_not_in_space | 404 |
| suggestion_not_found | 404 |
| layout_not_ready | 422 |
| unsupported_layout | 422 |
| invalid_mapping | 422 |
| invalid_statement | 422 |
| invalid_period | 422 |
| one_account | 409 |
| suggestion_not_pending | 409 |
| pair_declined | 409 |
| line_already_confirmed | 409 |
| target_not_approved | 409 |
| idempotency_conflict | 409 |
| statement_too_large | 413 |

## UI string keys

`business.bank.nav`

`business.bank.empty.no_account`

`business.bank.empty.no_lines`

`business.bank.error.layout_not_ready`

`business.bank.error.line_already_confirmed`

`business.bank.error.one_account`

`business.bank.error.pair_declined`

`business.bank.error.unsupported_layout`

`business.bank.import.account`

`business.bank.import.choose_file`

`business.bank.import.column_amount`

`business.bank.import.column_credit`

`business.bank.import.column_date`

`business.bank.import.column_debit`

`business.bank.import.column_description`

`business.bank.import.column_sign`

`business.bank.import.converged`

`business.bank.import.inserted`

`business.bank.import.mapped_csv`

`business.bank.import.reader`

`business.bank.import.submit`

`business.bank.import.title`

`business.bank.line.charge`

`business.bank.line.deposit`

`business.bank.line.zero`

`business.bank.suggestion.confidence`

`business.bank.suggestion.confirm`

`business.bank.suggestion.confirmed`

`business.bank.suggestion.decline`

`business.bank.suggestion.declined`

`business.bank.suggestion.pending`

`business.bank.suggestion.receipt`

`business.bank.suggestion.venta`

`business.bank.unmatched.count`

`business.bank.unmatched.empty`

`business.bank.unmatched.title`

The suggestion card shows the bank line and the document in one row. Confirm uses `business.bank.suggestion.confirm`. Decline uses `business.bank.suggestion.decline`. A receipt shows `business.bank.suggestion.receipt` with an icon. A venta shows `business.bank.suggestion.venta` with an icon.
