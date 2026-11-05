# Business bank matching

Default off. The routes exist only when the Business pilot is on and `CUADRAO_BUSINESS_BANK_MATCHING_ENABLED` is true. Otherwise every route answers 404 `business_unavailable`.

One Business space has one bank account. A person imports one statement, confirms or declines each suggestion, and every movement ends igualada or still listed in Por igualar. Nothing confirms itself.

A suggestion pairs a line with a recorded document of the Business: a receipt is a recorded expense activity, a venta a recorded income activity. `target_id` is the activity id. These are the documents month close reads. Offers are stored when a statement is imported and when the movements are read, so a document approved after the statement still reaches its line.

`unmatched_charge_count(space_id: UUID, period_start: date, period_end: date) -> int`

Defined in `src/argus/domain/business/bank/service.py`. The period is inclusive. The count is charges whose amount is below zero and whose state is `falta_comprobante` or `sugerencia`: no live match and no "no lleva comprobante" reason. Deposits are not included. The function raises `business_bank_matching_off` when the process service is unset.

## Endpoints

All routes are under `/api/v1/business/bank`. They require a signed-in Business person. `prepare` can import and decide (confirm, decline, match, unmatch, mark). `read` can list. Every decision needs the durable Business store and answers 404 `business_unavailable` without it. Responses send `Cache-Control: no-store`.

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

`sense` is `charge`, `deposit`, or `zero`. `state` is `igualada`, `sugerencia`, `falta_comprobante`, or `no_lleva_comprobante`, by the rule in the movements read below. The line state is not stored and is not the document mark `sin_comprobante`. `target_kind` is `receipt` or `venta`. `status` is `pending`, `confirmed`, or `declined`. `confirmed` is not stored: a suggestion is confirmed while its line holds a live match to its target. `actionable` is true only while the suggestion is pending, its line has no live outcome, and no other line holds its document.

### GET /suggestions

Optional query `status` of `pending`, `confirmed`, or `declined`. Returns the suggestion array above.

### POST /suggestions/{suggestion_id}/confirm

### POST /suggestions/{suggestion_id}/decline

Header `Idempotency-Key`. Returns one suggestion. The same key and the same decision returns the same row.

Confirm is igualar. In one transaction it records a live match of the line and the document and sets the document's settlement: `pagado` for a receipt, `cobrado` for a venta, `settled_on` the movement's date, and `payment_method` from the account type (the method rule in the movements read). The settlement it replaced is stored on the match. Confirming a declined pair is 409 `pair_declined`. A line that already has a live outcome is 409 `line_already_confirmed` or `line_marked_no_receipt`. A document another line holds is 409 `document_already_matched`. A pair that no longer passes the offer rules is 409 `target_not_approved`.

Declining a pair that is confirmed is 409 `suggestion_not_pending`. Undo it with unmatch first.

### POST /movements/{line_id}/match

Igualar with a document the person chose. Body `{"activity_id": "uuid"}`. Header `Idempotency-Key`. The document must be a recorded receipt or venta of this Business (404 `business_record_not_found` otherwise) of the line's sense (a charge takes a receipt, a deposit a venta), in the line's currency, for exactly the line's amount (422 `document_not_matchable` otherwise). The date window and the name do not apply. It writes the settlement as confirm does. Returns the line as one movements item.

### POST /movements/{line_id}/unmatch

Desigualar. Header `Idempotency-Key`. Ends the live match and writes back the settlement stored on it: the same status, date, and method the document had before igualar. A document that had no settlement row before keeps a `pendiente` row, which every read shows as before. Both writes add a settlement revision. A line with no live match is 409 `line_not_matched`; the same key again returns the line. The pair's suggestion is pending again, so the line shows `sugerencia`. Returns the line as one movements item.

### PUT /movements/{line_id}/disposition

No lleva comprobante. Body `{"reason": "cargo_banco" | "entre_cuentas" | "compra_informal" | "personal"}`. Header `Idempotency-Key`. A new reason ends the old one. The same reason again changes nothing. A matched line is 409 `line_already_confirmed`. `compra_informal` here is a line reason; it does not create a document or the document mark `sin_comprobante`. Returns the line as one movements item.

### DELETE /movements/{line_id}/disposition

Header `Idempotency-Key`. Ends the reason. A line with no reason is 409 `line_not_marked`; the same key again returns the line.

### GET /movements/{line_id}/history

Every outcome the line has had, oldest first, ended ones included.

```json
[
  {
    "id": "uuid",
    "kind": "match",
    "target_kind": "receipt",
    "activity_id": "uuid",
    "reason": null,
    "created_at": "2026-10-21T12:00:00Z",
    "ended_at": "2026-10-21T12:01:00Z"
  }
]
```

`kind` is `match` or `no_receipt`. `reason` is set only on `no_receipt`.

### One owner for cobrado and pagado

While a document has a live match, its settlement is the one the match wrote. `PATCH /business/month-close/documents/{activity_id}` with anything else is 409 `business_document_matched`, so Inicio and Transacciones cannot disagree. The same values are a no-op. The database enforces it with a trigger on `business_document_settlements`. Unmatch ends the match before it restores the settlement.

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

Transacciones. Every line of the period, newest first, with its state. The caller needs `read`. Scope and grants are the month-close rule: the caller's own Business, or the client named by `X-Business-Grant`. It needs the durable Business store; the in-memory app keeps none and answers the empty period in this same shape (no accounts, totals or items, every count zero, `next_cursor` null) once the caller's Business exists, while every decision route there stays 404 `business_unavailable`.

Query: `period_start` and `period_end` as dates, inclusive. Optional `segment` of `por_igualar`, `igualadas`, or `todas` (default). Optional `sense` of `charge` or `deposit`. Optional `currency`, an ISO 4217 code in upper case (anything else is 422): the table follows that currency. Optional `limit` from 1 to 200, default 50. Optional `cursor` from the previous page's `next_cursor`.

```json
{
  "period_start": "2026-10-01",
  "period_end": "2026-10-31",
  "segment": "por_igualar",
  "sense": null,
  "currency": "DOP",
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
  "counts": {
    "movimientos": 5,
    "igualadas": 0,
    "no_lleva_comprobante": 1,
    "sugerencias": 2,
    "falta_comprobante": 2,
    "sin_movimiento": 1,
    "por_igualar": 5
  },
  "other_currencies": [{"currency": "USD", "count": 1}],
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
| `state` | `igualada`: the line has a live match. `no_lleva_comprobante`: the line needs no comprobante; `reason` says why. `sugerencia`: the line has at least one pending pair whose document no other line holds. `falta_comprobante`: none of these. A document row is `sin_movimiento`. |
| `reason` | Set only with `no_lleva_comprobante`. A person's reason (`cargo_banco`, `entre_cuentas`, `compra_informal`, `personal`), or `monto_cero` for a zero-amount line with no reason. |
| `kind` | `movement` is a bank line. `document` is a settled document recorded on a bank account that the statement does not show (`sin_movimiento`). Its `description` is null, its amount is signed by kind (a receipt is negative), and its `method` is the settlement's method. |
| `counterparty` | The matched document's counterparty when igualada. Otherwise the bank text with runs of spaces joined. |
| `category_id` | The matched document's category, or null. |
| `account` | The financial account the line came from. `name` is its nickname or null. The last four digits are not stored. |
| `method` | From the account type: `checking` and `savings` are `transferencia`, `credit_card` is `tarjeta`, `cash` is `efectivo`, anything else is `otro`. |
| `document` | The matched document, or the `sin_movimiento` document. Null otherwise. |
| `suggestions` | Only on a `sugerencia` line. Best `confidence` first. Each `reasons` entry is a data code the web words: `monto_exacto`, `misma_fecha`, `fecha_cercana` with `days` (document date minus movement date), and `nombre_parecido`. |
| `covered_through` | The newest movement date imported for that account. A date after it is unknown, not missing. |
| `totals` | One block per currency for the whole period, whatever the segment, sense, or page. Currencies are never added together. `salidas` is a positive amount. `por_igualar` adds the size of every `sugerencia`, `falta_comprobante`, and `sin_movimiento` row. `counts.por_igualar` counts those rows. With `currency`, only that currency's block, and an empty list when the period has no row in it. |
| `counts` | The period's counts across every currency, the same keys as a block's `counts` added over every block, whatever the segment, sense, currency, or page. Counts are not money. The web renders these and adds nothing. |
| `currency` | The chosen currency, or null. |
| `other_currencies` | With `currency`, how many rows of the chosen segment and sense are in each other currency, sorted by code, so the table can say what it leaves out. Empty without `currency`. |

`segment=por_igualar` lists `sugerencia` rows first (best offer first), then `falta_comprobante`, then `sin_movimiento`, each newest first. `igualadas` lists `igualada` and `no_lleva_comprobante`. `todas` lists every line and no document row. `sense` filters lines by sense and documents by kind. `currency` keeps only the rows in that currency; the page and `next_cursor` walk those rows.

A document is `sin_movimiento` when it is recorded on the bank-bound account, it is settled (`pagado` or `cobrado`), its date is in the period, no line is matched to it, and its settlement date plus the 5-day match window is on or before `covered_through`.

`GET /business/receipt-activity` and `GET /business/overview` carry `por_igualar_count`: the number of `sugerencia`, `falta_comprobante`, and `sin_movimiento` rows over every period, the same rule as `counts.por_igualar` here. It is null while this switch is off. Inicio and the sidebar render that one number.

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
| line_not_found | 404 |
| line_marked_no_receipt | 409 |
| line_not_matched | 409 |
| line_not_marked | 409 |
| document_already_matched | 409 |
| document_not_matchable | 422 |
| business_document_matched | 409 |
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
