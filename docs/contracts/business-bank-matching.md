# Business bank matching

Default off. The routes exist only when the Business pilot is on and `CUADRAO_BUSINESS_BANK_MATCHING_ENABLED` is true. Otherwise every route answers 404 `business_unavailable`.

One Business space has one bank account. A person imports one statement, confirms or declines each suggestion, and every movement ends igualada or still listed in Por igualar. Nothing confirms itself.

A suggestion pairs a line with a recorded document of the Business: a receipt is a recorded expense activity, a venta a recorded income activity. `target_id` is the activity id. These are the documents month close reads. Offers are stored when a statement is imported and when the movements are read, so a document approved after the statement still reaches its line.

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
      "state": "falta_comprobante"
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

`sense` is `charge`, `deposit`, or `zero`. `state` is `igualada`, `sugerencia`, `falta_comprobante`, or `no_lleva_comprobante`, by the rule in the movements read below. The line state is not stored and is not the document mark `sin_comprobante`. `target_kind` is `receipt` or `venta`. `status` is `pending`, `confirmed`, or `declined`. `actionable` is true only while the suggestion is pending and the line has no confirmed suggestion.

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

### GET /movements

Transacciones. Every line of the period, newest first, with its state. The caller needs `read`. Scope and grants are the month-close rule: the caller's own Business, or the client named by `X-Business-Grant`. It needs the durable Business store.

Query: `period_start` and `period_end` as dates, inclusive. Optional `segment` of `por_igualar`, `igualadas`, or `todas` (default). Optional `sense` of `charge` or `deposit`. Optional `limit` from 1 to 200, default 50. Optional `cursor` from the previous page's `next_cursor`.

```json
{
  "period_start": "2026-10-01",
  "period_end": "2026-10-31",
  "segment": "por_igualar",
  "sense": null,
  "accounts": [
    {
      "account_id": "uuid",
      "name": "Cuenta Popular",
      "type": "checking",
      "bank_account_id": "uuid",
      "currency": "DOP",
      "covered_through": "2026-10-20"
    }
  ],
  "totals": [
    {
      "currency": "DOP",
      "entradas_minor": 500000,
      "entradas": "5000.00",
      "salidas_minor": 360000,
      "salidas": "3600.00",
      "por_igualar_minor": 950000,
      "por_igualar": "9500.00",
      "counts": {
        "movimientos": 4,
        "igualadas": 0,
        "no_lleva_comprobante": 1,
        "sugerencias": 2,
        "falta_comprobante": 1,
        "sin_movimiento": 1,
        "por_igualar": 4
      }
    }
  ],
  "items": [
    {
      "kind": "movement",
      "id": "uuid",
      "occurred_on": "2026-10-17",
      "description": "COMPRA  FERRETERIA LA ESQUINA",
      "counterparty": "COMPRA FERRETERIA LA ESQUINA",
      "sense": "charge",
      "currency": "DOP",
      "amount_minor": -345000,
      "amount": "-3450.00",
      "state": "sugerencia",
      "reason": null,
      "category_id": null,
      "account": {"account_id": "uuid", "name": "Cuenta Popular", "type": "checking"},
      "method": "transferencia",
      "document": null,
      "suggestions": [
        {
          "id": "uuid",
          "confidence": "0.850",
          "reasons": [
            {"code": "monto_exacto", "days": null},
            {"code": "fecha_cercana", "days": -1},
            {"code": "nombre_parecido", "days": null}
          ],
          "document": {
            "activity_id": "uuid",
            "kind": "receipt",
            "counterparty": "Ferreteria La Esquina",
            "occurred_on": "2026-10-16",
            "currency": "DOP",
            "total_minor": 345000,
            "total": "3450.00",
            "itbis_minor": null,
            "itbis": null,
            "rnc": null,
            "ncf": null,
            "ecf": null,
            "status": "pendiente",
            "settled_on": null,
            "payment_method": null,
            "category_id": null
          }
        }
      ]
    }
  ],
  "next_cursor": null
}
```

| Field | Meaning |
| --- | --- |
| `state` | `igualada`: the line has a confirmed pair. `no_lleva_comprobante`: the line needs no comprobante; `reason` says why. `sugerencia`: the line has at least one pending pair whose document no other line holds. `falta_comprobante`: none of these. A document row is `sin_movimiento`. |
| `reason` | Set only with `no_lleva_comprobante`. `monto_cero` is a zero-amount line. |
| `kind` | `movement` is a bank line. `document` is a settled document recorded on a bank account that the statement does not show (`sin_movimiento`). Its `description` is null, its amount is signed by kind (a receipt is negative), and its `method` is the settlement's method. |
| `counterparty` | The matched document's counterparty when igualada. Otherwise the bank text with runs of spaces joined. |
| `category_id` | The matched document's category, or null. |
| `account` | The financial account the line came from. `name` is its nickname or null. The last four digits are not stored. |
| `method` | From the account type: `checking` and `savings` are `transferencia`, `credit_card` is `tarjeta`, `cash` is `efectivo`, anything else is `otro`. |
| `document` | The matched document, or the `sin_movimiento` document. Null otherwise. |
| `suggestions` | Only on a `sugerencia` line. Best `confidence` first. Each `reasons` entry is a data code the web words: `monto_exacto`, `misma_fecha`, `fecha_cercana` with `days` (document date minus movement date), and `nombre_parecido`. |
| `covered_through` | The newest movement date imported for that account. A date after it is unknown, not missing. |
| `totals` | One block per currency for the whole period, whatever the segment, sense, or page. Currencies are never added together. `salidas` is a positive amount. `por_igualar` adds the size of every `sugerencia`, `falta_comprobante`, and `sin_movimiento` row. `counts.por_igualar` counts those rows. |

`segment=por_igualar` lists `sugerencia` rows first (best offer first), then `falta_comprobante`, then `sin_movimiento`, each newest first. `igualadas` lists `igualada` and `no_lleva_comprobante`. `todas` lists every line and no document row. `sense` filters lines by sense and documents by kind.

A document is `sin_movimiento` when it is recorded on the bank-bound account, it is settled (`pagado` or `cobrado`), its date is in the period, no line is matched to it, and its settlement date plus the 5-day match window is on or before `covered_through`.

The read stores the offers the rules allow that were never stored. A declined pair is never offered again. Storing an offer confirms nothing.

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
| invalid_cursor | 422 |
| business_grant_not_live | 403 |
| business_record_not_found | 404 |
| business_bank_unavailable | 503 |
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
