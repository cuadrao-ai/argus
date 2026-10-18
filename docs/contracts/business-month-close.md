# Cuadrar el mes

Reference for the Business month close. Sofia can build the screen from this document alone.

The month is a calendar month. Money is integer minor units. A display string is only the same integer rendered with the currency's digits. Nothing in this contract is a float.

## What a caller can do

`GET /api/v1/business/month-close?month=YYYY-MM`

Read the month for the Business in scope. Scope is the caller's own Business, or the client named by `X-Business-Grant`, the same rule as the other Business routes.

`PATCH /api/v1/business/month-close/documents/{activity_id}`

Set that document's settlement. The caller needs the prepare capability. A repeat of the same status, date, and payment method changes nothing and appends no history row.

## Authorization and errors

A missing, revoked, or expired grant is `403` `business_grant_not_live`. A live grant without the capability is `403` `business_permission_denied`. An activity that is not in this Business is `404` `business_record_not_found`. The body does not say whether the activity exists in another Business.

| HTTP | code | When |
| --- | --- | --- |
| 422 | `month_invalid` | `month` is not a real `YYYY-MM` |
| 422 | `business_status_invalid` | Status is not allowed for that document |
| 422 | `business_payment_method_invalid` | Method is outside the allowed set |
| 422 | `business_settlement_incomplete` | A settled document lacks a date or method, or a pending document sends either |
| 422 | `activity_kind_unsupported` | The activity is not income or an expense |
| 404 | `business_record_not_found` | The activity is not in this Business |
| 403 | `business_permission_denied` | The grant cannot prepare, or cannot read |
| 403 | `business_grant_not_live` | The grant header does not name a live grant |
| 409 | `business_document_settlement_conflict` | Two first settlements of the same document collided again after one fresh retry |
| 503 | `business_month_close_unavailable` | The authorized snapshot could not be read or written |

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
| `closed` | True when every business document in the month has an RNC and a fiscal number (NCF or e-CF). |
| `reasons` | Why `closed` is false. `missing_rnc` or `missing_ncf`, with the activity. |
| `income_before_itbis_minor` | Sales lines that would go on the 607. The line is the 607 Monto Facturado when the draft declares it, and the activity total minus ITBIS when it does not. A credit note subtracts. An e-CF sale is not a 607 line. |
| `expense_before_itbis_minor` | Purchase lines that would go on the 606, total minus ITBIS. |
| `net_result_minor` | Income before ITBIS minus expenses before ITBIS. Negative when expenses are larger. |
| `itbis_charged_minor` | ITBIS on the 607 lines. A credit note subtracts. |
| `itbis_paid_minor` | ITBIS on the 606 lines. |
| `itbis_owed_minor` | Charged minus paid. Negative when the business paid more ITBIS than it charged. |
| `by_status` | Count and before-ITBIS total of every business document in the month, including one that is missing an RNC or a fiscal number. Those incomplete documents are not part of the net. |
| `cuentas_por_cobrar` | Invoices still `pendiente`. The list amount is the document total, the amount still to collect. |
| `cuentas_por_pagar` | Receipts still `pendiente`. The list amount is the document total, the amount still to pay. |

A list item is `activity_id`, `document_kind` (`invoice` or `receipt`), `currency`, `occurred_on`, `total_minor`, `before_itbis_minor`, `itbis_minor` (null when the document does not state ITBIS), and `status`.

An invoice is a recorded income activity. A receipt is a recorded expense activity. The printed total on that activity already includes ITBIS when ITBIS is known. Before-ITBIS is that total minus the stored ITBIS. Unknown ITBIS is treated as zero for the subtraction and does not by itself open the month. That assumption is an open question.

Personal expenses stay out of the month unless the accountant has answered yes to including them. Sales marked personal stay out. Transfers and other activity kinds stay out.

Pending documents are the receivables and payables. They do not flip `closed` to false. The month still closes when every document in it has an RNC and a fiscal number. Paying one later does not move its amount into another month.

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

The latest draft for an activity supplies RNC, NCF, e-CF, ITBIS, the 607 billed amount when the draft declares one, the personal mark, and the inclusion answer. The settlement row supplies status. Totals are then summed in `summarize` from those parts and the activity's minor-unit total. `EXPLAIN` for both reads needs a disposable database with the migrations applied. This change did not have one, so no plan is attached. Staging and production were not migrated from here.
