# Cuadrar el mes

Reference for the Business month close. Sofia can build the screen from this document alone.

The month is a calendar month. Money is integer minor units. A display string is only the same integer rendered with the currency's digits. Nothing in this contract is a float.

## What a caller can do

`GET /api/v1/business/month-close?month=YYYY-MM`

Read the month for the Business in scope. Scope is the caller's own Business, or the client named by `X-Business-Grant`, the same rule as the other Business routes.

`PATCH /api/v1/business/month-close/documents/{activity_id}`

Set that document's settlement. The caller needs the prepare capability. A repeat of the same status, date, and payment method changes nothing and appends no history row.

`GET /api/v1/business/open-items`

Read every invoice and receipt that is still `pendiente`, from any month. Scope and grants are the same as the month read. The caller needs the read capability, so the owner and an accountant can both call it.

## Authorization and errors

A missing, revoked, or expired grant is `403` `business_grant_not_live`. A live grant without the capability is `403` `business_permission_denied`. An activity that is not in this Business is `404` `business_record_not_found`. The body does not say whether the activity exists in another Business.

| HTTP | code | When |
| --- | --- | --- |
| 422 | `month_invalid` | `month` is not a real `YYYY-MM` |
| 422 | `validation_error` | The month read got a query parameter other than one `month`, or the open items read got any query parameter |
| 422 | `business_status_invalid` | Status is not allowed for that document |
| 422 | `business_payment_method_invalid` | Method is outside the allowed set |
| 422 | `business_settlement_incomplete` | A settled document lacks a date or method, or a pending document sends either |
| 422 | `activity_kind_unsupported` | The activity is not income or an expense |
| 404 | `business_record_not_found` | The activity is not in this Business |
| 403 | `business_permission_denied` | The grant cannot prepare, or cannot read |
| 403 | `business_grant_not_live` | The grant header does not name a live grant |
| 409 | `business_document_settlement_conflict` | Two first settlements of the same document collided again after one fresh retry |
| 503 | `business_month_close_unavailable` | The authorized snapshot could not be read or written. Open items use the same code. |

The error body is the usual problem document. `code` is the field above.

## GET response

```json
{
  "month": "2026-10",
  "from": "2026-10-01",
  "to": "2026-10-31",
  "closed": false,
  "reasons": [
    {"code": "missing_rnc", "activity_id": "…", "document_kind": "receipt"},
    {"code": "missing_ncf", "activity_id": "…", "document_kind": "receipt"}
  ],
  "currencies": [
    {
      "currency": "DOP",
      "income_before_itbis_minor": 15000,
      "income_before_itbis": "150.00",
      "expense_before_itbis_minor": 3000,
      "expense_before_itbis": "30.00",
      "net_result_minor": 12000,
      "net_result": "120.00",
      "itbis_charged_minor": 2700,
      "itbis_charged": "27.00",
      "itbis_paid_minor": 540,
      "itbis_paid": "5.40",
      "itbis_owed_minor": 2160,
      "itbis_owed": "21.60",
      "cuentas_por_cobrar_minor": 5900,
      "cuentas_por_cobrar": "59.00",
      "cuentas_por_pagar_minor": 1000,
      "cuentas_por_pagar": "10.00",
      "by_status": {
        "invoices": {
          "pendiente": {"count": 1, "before_itbis_minor": 5000},
          "cobrado": {"count": 1, "before_itbis_minor": 10000}
        },
        "receipts": {
          "pendiente": {"count": 1, "before_itbis_minor": 1000},
          "pagado": {"count": 1, "before_itbis_minor": 2000}
        }
      }
    }
  ],
  "missing_rnc": [],
  "missing_ncf": [],
  "cuentas_por_cobrar": [],
  "cuentas_por_pagar": []
}
```

The sample minors are illustrative. Each currency the month actually contains is one block. Currencies are never added together.

| Field | Meaning |
| --- | --- |
| `closed` | True when every business document in the month has an RNC and a fiscal number that normalizes, or is sin comprobante. A blank number and a number that is not a B-series or E-series value both use `missing_ncf`. |
| `reasons` | Why `closed` is false. `missing_rnc` or `missing_ncf`, with the activity. |
| `income_before_itbis_minor` | Sales lines that would go on the 607, plus sin comprobante sales. The line is the 607 Monto Facturado when the draft declares it, and the activity total minus ITBIS when it does not. A credit note subtracts. An e-CF sale is not a 607 line. |
| `expense_before_itbis_minor` | Purchase lines that would go on the 606, plus sin comprobante purchases, total minus ITBIS. |
| `net_result_minor` | Income before ITBIS minus expenses before ITBIS. Negative when expenses are larger. |
| `itbis_charged_minor` | ITBIS on the 607 lines. A credit note subtracts. A sin comprobante sale adds none. |
| `itbis_paid_minor` | ITBIS on the 606 lines. A sin comprobante purchase adds none. |
| `itbis_owed_minor` | Charged minus paid. Negative when the business paid more ITBIS than it charged. |
| `by_status` | Count and before-ITBIS total of every business document in the month, including one that is missing an RNC or a fiscal number. Invoice totals use the same signed Monto Facturado as income, so a credit note subtracts. Receipt totals are the activity total minus ITBIS. Those incomplete documents are not part of the net. |
| `cuentas_por_cobrar` | Invoices still `pendiente`. The list amount is the document total, the amount still to collect. |
| `cuentas_por_pagar` | Receipts still `pendiente`. The list amount is the document total, the amount still to pay. |

A list item is `activity_id`, `document_kind` (`invoice` or `receipt`), `currency`, `occurred_on`, `total_minor`, `total`, `before_itbis_minor`, `before_itbis`, `itbis_minor`, `itbis`, `counterparty`, `rnc`, `ncf`, `ecf`, `status`, and `sin_comprobante`. Each `_minor` field has a display string with the same name and no suffix, in the line's own currency. `itbis_minor` and `itbis` are null when the document does not state ITBIS. `counterparty`, `rnc`, `ncf`, and `ecf` come from the latest draft and are null when the draft does not know them. `sin_comprobante` is true when the document is sin comprobante, and false otherwise. The same item shape is used in every list in this contract.

An invoice is a recorded income activity. A receipt is a recorded expense activity. The printed total on that activity already includes ITBIS when ITBIS is known. Before-ITBIS is that total minus the stored ITBIS. Unknown ITBIS is treated as zero for the subtraction and does not by itself open the month. That assumption is an open question.

## Sin comprobante

A document is sin comprobante when a person states in review that it has no comprobante fiscal and the draft carries no NCF or e-CF. The statement is the draft fact `receipt_state` with the value `no_receipt` or `informal_receipt`. The owner sets it in chat or a prepare-holder sets it in review. It is editable while the draft is open, it is kept in the draft history, and it is locked when the draft is approved. A missing NCF alone never makes a document sin comprobante. A draft that carries an NCF or an e-CF has a comprobante, whatever `receipt_state` says.

A sin comprobante document counts in `income_before_itbis` or `expense_before_itbis` and in `by_status`. It adds no ITBIS charged or paid. It is not a 606 or 607 line, and the DGII export lists it as excluded with the reason `no_fiscal_number`. It never adds a `missing_rnc` or `missing_ncf` reason, so it never keeps the month open. A personal sin comprobante purchase stays out of the month like any personal purchase.

A document that has a comprobante, or whose `receipt_state` is unknown, and has no RNC or fiscal number still keeps the month open.

Receipt summaries and details, expenses and their detail, and the draft dossier carry the same mark as `sin_comprobante`. Lists leave it out when it is false. The dossier always has it.

## Venta

A Venta is an invoice the business has already issued. In the Bandeja the person uploads or captures it the same way as a receipt and names the document type at that moment. The type is `venta`. A purchase stays `recibo`. The same bytes keep the type from the first save. A later upload of those bytes that names the other type is `409` `document_type_conflict`. An absent type header means `recibo`. Any other value is `422` `document_type_invalid`.

The read is the same read a receipt gets. The reader prompt stays as it is. The capture type gives the printed fields their meaning on a Venta:

| Printed field | Meaning on a Venta |
| --- | --- |
| RNC | The client's RNC or cédula |
| NCF or e-CF | The fiscal number the business already issued |
| ITBIS | ITBIS charged |

A Venta is prepared as an income activity, which this contract calls an invoice. It counts in income before ITBIS, in ITBIS charged, and in the 607 selection. While its status is `pendiente` it appears in Por cobrar. `cobrado` removes it from that list and leaves the amount in the month it was issued. A missing client RNC or a missing fiscal number keeps the month open.

Recording a Venta uses the income approval, into a business account. The Bandeja shows the type. Approval of a Venta sends `record_income`.

Creating an invoice, issuing an NCF, and running a numbering sequence are outside this contract.

The RNC field holds one number. It does not record whether that number is an RNC, a cédula, or a passport. A passport with no nonzero digit cannot be stored there. That identification type is an open question for a future 607 file. The printed name stays the counterparty the read found.

Personal expenses stay out of the month unless the accountant has answered yes to including them. Sales marked personal stay out. Transfers and other activity kinds stay out.

Pending documents are the receivables and payables. They do not flip `closed` to false. The month still closes when every document in it has an RNC and a fiscal number. Paying one later does not move its amount into another month.

## Open items

The month lists show only what was issued in that month. Inicio shows what is still owed, so a September invoice that is still `pendiente` stays in Por cobrar when the person views October.

```json
{
  "cuentas_por_cobrar": {
    "count": 1,
    "totals": [{"currency": "DOP", "total_minor": 5900, "total": "59.00"}],
    "items": [
      {
        "activity_id": "…",
        "document_kind": "invoice",
        "currency": "DOP",
        "occurred_on": "2026-09-12",
        "total_minor": 5900,
        "total": "59.00",
        "before_itbis_minor": 5000,
        "before_itbis": "50.00",
        "itbis_minor": 900,
        "itbis": "9.00",
        "counterparty": "Cliente de práctica",
        "rnc": "131000001",
        "ncf": "B0100000001",
        "ecf": null,
        "status": "pendiente"
      }
    ]
  },
  "cuentas_por_pagar": {"count": 0, "totals": [], "items": []}
}
```

| Field | Meaning |
| --- | --- |
| `cuentas_por_cobrar` | Every invoice still `pendiente`. The same documents the month read lists in its `cuentas_por_cobrar`, from every month together. |
| `cuentas_por_pagar` | Every receipt still `pendiente`, chosen the same way. |
| `count` | How many pending documents the list has, including the ones past the cap. |
| `totals` | The sum of `total_minor` for every pending document in the list, one entry per currency. Currencies are never added together or converted. A currency with no pending document has no entry. |
| `items` | The oldest 100 pending documents, by `occurred_on` and then `activity_id`. The item shape is the month-close list item. |

Marking a document `cobrado` or `pagado` with the PATCH above removes it from this read. Setting it back to `pendiente` returns it. The month summary and the close checklist stay month-scoped.

A document has no due date today, so the order uses the date the document was issued. A due date is an open question.

## PATCH

```json
{"status": "cobrado", "settled_on": "2026-10-18", "payment_method": "transferencia"}
```

Invoice statuses are `pendiente` and `cobrado`. Receipt statuses are `pendiente` and `pagado`. Methods are `efectivo`, `transferencia`, `tarjeta`, `credito`, and `otro`.

`pendiente` must omit `settled_on` and `payment_method`. Either settled status requires both.

```json
{
  "activity_id": "…",
  "document_kind": "invoice",
  "status": "cobrado",
  "settled_on": "2026-10-18",
  "payment_method": "transferencia",
  "changed": false
}
```

`changed` is false when this request matches the stored settlement. The history row count stays the same.

## Data-model checklist

**Needs.** The summary has to answer the net result before ITBIS, the ITBIS still owed, counts and before-ITBIS totals by status, which documents lack an RNC or a fiscal number, the open receivables and payables, and whether the month is closed.

**Grain.** One settlement row is one recorded activity in one Business. The activity is the same row the export already reads. The month summary is not a stored row. It is computed when the caller asks.

**History.** `business_document_settlement_revisions` is append-only. Each change stores the actor, the time, and the previous status, date, and method. A repeat of the same request does not append. Updates and deletes of a revision are rejected.

**Table shape.** `business_document_settlements` holds space, owner, activity, document kind, status, settlement date, payment method, and updated time. It does not hold amounts, ITBIS, RNC, NCF, or the actor. The revision holds the actor and the previous status, date, and method.

**Parts, not ratios.** Amount, ITBIS, and the activity date stay on the recorded activity and its draft. The summary subtracts those parts. The ratio and the month totals are not stored.

**Constraints.** Status is checked against the document kind. A pending row has no date and no method. A settled row has both. The method is a checked set. The activity must belong to the owner. The space must belong to that owner. Revisions cannot be updated or deleted.

**Retention.** These rows follow the business record. The working assumption is ten years, and counsel has not signed that period. This migration adds no purge.

**Immutable raw input.** Applying a settlement does not write the activity amount, the ITBIS, the RNC, or the NCF.

**Idempotency.** The stored status, date, and method are compared with the request. Equality is a no-op.

**Venta.** The Bandeja type lives on the capture draft and is copied onto the business resolution when that draft is prepared. Both are existing JSON documents. This change adds no column, no table, and no migration. A later revision keeps the type. A Venta's kind is income. Changing that kind is refused. The month-close query below is unchanged: a recorded Venta is an income activity in that read.

**Query.** Activities come from the same scoped read the export uses (`current_activities` on the Business scope). Draft facts are this read.

```sql
select e.activity_id::text as activity_id,
       e.updated_at,
       e.resolution
from public.financial_import_events e
where e.user_id = $owner
  and e.owner_space_id = $space
  and e.activity_id is not null
  and e.resolution ? 'business'
order by e.updated_at desc, e.id desc
```

Status is a separate read of the settlement table, including a recorded activity that has no draft.

```sql
select activity_id::text as activity_id,
       status,
       settled_on,
       payment_method
from public.business_document_settlements
where space_id = $space
  and owner_id = $owner
```

The latest draft for an activity supplies RNC, NCF, e-CF, ITBIS, the 607 billed amount when the draft declares one, the personal mark, the inclusion answer, and the receipt state. That draft is the current `resolution` on the import event. The 607 reads a different row: the approved revision at or before the approval receipt version, and it requires that receipt. The two agree until a personal mark or a 606 inclusion answer is written after approval, or until an accepted draft has no approval receipt. Month close keeps reading the current draft. This note records the gap and does not change the read. The settlement row supplies status. Totals are then summed in `summarize` from those parts and the activity's minor-unit total. `EXPLAIN` for both reads needs a disposable database with the migrations applied. This change did not have one, so no plan is attached. Staging and production were not migrated from here.
