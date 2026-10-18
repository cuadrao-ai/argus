# Business Venta contract

This reference defines an issued sale and its API, domain, and storage rules.

## Sale record

`public.business_sales` stores one issued invoice for one open Bandeja draft.
The record belongs to a Business space. It is not a money activity or an
expense.

The stored monetary parts are `invoice_total` and `itbis_charged`.
`invoice_total` includes ITBIS and records what the customer owes.
Both values use DOP with two decimal places. `invoice_total` is positive.
`itbis_charged` is between zero and `invoice_total`.

The customer has either a nine-digit RNC or an eleven-digit cedula. An
identifier of all zeros is rejected. The NCF is `B` plus ten digits or `E`
plus twelve digits. `issued_on` is the comprobante date. The owner sets
`collection_status` to `cobrado` or `por_cobrar`.

The table enforces one sale per draft and one NCF per Business. The owner and
people with a live Business grant can read rows through row-level security.
Only the server role can insert or update a sale. No role has a delete grant.

The retention registry describes this rule. Retain the sale for ten years from
`issued_on`. This slice installs no purge.

## Domain API

The month-close caller uses these functions:

```python
def sales_for_period(
    rows: Sequence[Sale], *, start: date, end: date
) -> SalesPeriod: ...

def load_sales_period(
    tx, *, space_id: UUID, start: date, end: date
) -> SalesPeriod: ...
```

Both functions use an inclusive period. `SalesPeriod` derives these values:

- `income` is the sum of `invoice_total - itbis_charged`.
- `itbis_charged` is the sum of charged ITBIS.
- `itbis_cobrado` includes only sales with `collection_status = cobrado`.
- `por_cobrar` is the gross `invoice_total` for sales with
  `collection_status = por_cobrar`.

The stored parts remain the source values. The database does not store these
period totals.

## Feature flag

`CUADRAO_BUSINESS_VENTA_ENABLED` controls all Venta routes and defaults to
`false`. `ARGUS_BUSINESS_VENTA_ENABLED` is the fallback setting name. If the
flag is off, each route returns 404 `business_venta_unavailable`. The Business
pilot gate still applies. A disabled pilot returns 404 `business_unavailable`
before this flag is considered.

## HTTP API

All routes require the Business surface, an authenticated owner, and the
default-off Venta flag.

### Mark an issued sale

`POST /api/v1/business/ventas` requires `Idempotency-Key` and this body:

```json
{
  "draft_id": "00000000-0000-0000-0000-000000000001",
  "invoice_total": "1180.00",
  "itbis_charged": "180.00",
  "customer": {
    "id_type": "rnc",
    "id_number": "101010101"
  },
  "ncf": "B0101010101",
  "issued_on": "2026-10-15",
  "collection_status": "por_cobrar"
}
```

The route returns the sale with 201 after creation. An exact replay returns the
same sale with 200. The request body is the only source for the sale fields.
Marking a sale does not change the draft facts, kind, or state.

### Change collection status

`PATCH /api/v1/business/ventas/{venta_id}/collection` requires
`Idempotency-Key`. The body contains `collection_status`. The write changes
only `collection_status` and `updated_at`.

### Load a sales period

`GET /api/v1/business/ventas?from=YYYY-MM-DD&to=YYYY-MM-DD` returns the
inclusive period. If `to` is absent, the server uses the current Business day
in Santo Domingo. The response contains `sales`, `income`, `itbis_charged`,
`itbis_cobrado`, `por_cobrar`, and `rows`.

All monetary values are decimal strings.

## Idempotency

Both writes store a human `business_action_receipts` row. The commands are
`mark_venta` and `set_venta_collection`. The actor is a member. `turn_key` and
`action_index` are null.

The same key and canonical body replay the stored sale. The same key with a
different body returns 409 `business_action_conflict`. A new key cannot create
a second sale for the draft or reuse an NCF in the same Business.

## 607 projection

Each sale in the period produces one 607 row. `invoiced_amount` is
`invoice_total - itbis_charged`. `itbis_invoiced` is `itbis_charged`.
`buyer_id_type` is `1` for an RNC and `2` for a cedula.

These response fields are null. This slice does not know them, and it does
not send zero in their place.

| Response field | 607 column |
| --- | --- |
| `modified_ncf` | Número de Comprobante Fiscal Modificado |
| `income_type` | Tipo de Ingreso |
| `withheld_on` | Fecha de Retención |
| `itbis_withheld` | ITBIS Retenido por Terceros |
| `itbis_perceived` | ITBIS Percibido |
| `rent_withheld` | Retención Renta por Terceros |
| `isr_perceived` | ISR Percibido |
| `selective_tax` | Impuesto Selectivo al Consumo |
| `other_tax` | Otros Impuestos/Tasas |
| `legal_tip` | Monto Propina Legal |
| `cash` | Efectivo |
| `transfer` | Cheque/Transferencia/Depósito |
| `card` | Tarjeta Débito/Crédito |
| `credit_sale` | Venta a Crédito |
| `gift` | Bonos o Certificados de Regalo |
| `barter` | Permuta |
| `other_payment` | Otras Formas de Ventas |

`buyer_id`, `buyer_id_type`, `ncf`, `issued_on`, `invoiced_amount`, and
`itbis_invoiced` are the columns this slice fills. `issued_on` is the
comprobante date.

## Errors

- 400 `idempotency_key_required` means a write omitted the header.
- 403 `business_permission_denied` means the caller is not the owner.
- 404 `business_record_not_found` means the draft is unavailable in the
  Business.
- 404 `business_venta_not_found` means the sale is unavailable in the
  Business.
- 409 `business_action_conflict` means an idempotency key has different input.
- 409 `business_venta_draft_already_recorded` means another key already marked
  the draft.
- 409 `business_venta_ncf_conflict` means the Business already uses the NCF.
- 422 `business_venta_draft_closed` means the draft is not open.
- 422 `business_venta_recorded` means expense or income approval targeted a
  draft that already has a sale.
- 422 `period_reversed` means `from` is after `to`.
- 422 `validation_error` means the body or query does not match the contract.

## Proving queries

```sql
select coalesce(sum(invoice_total - itbis_charged), 0)
  from public.business_sales
 where space_id = $1 and issued_on between $2 and $3;

select coalesce(sum(itbis_charged), 0)
  from public.business_sales
 where space_id = $1 and issued_on between $2 and $3
   and collection_status = 'cobrado';

select coalesce(sum(invoice_total), 0)
  from public.business_sales
 where space_id = $1 and issued_on between $2 and $3
   and collection_status = 'por_cobrar';
```
