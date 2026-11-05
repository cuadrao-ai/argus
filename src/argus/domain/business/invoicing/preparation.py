from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.contracts.invoicing import Invoice, InvoiceDraft
from argus.domain.business.fiscal_sandbox.contracts import Case, digest
from argus.domain.business.fiscal_sandbox.service import Service

from .store import InvoiceError, Store
from .validation import (
    amounts,
    decimal_input,
    draft_errors,
    fiscal_blockers,
    line_amounts,
    money,
)


def number(value: str | Decimal) -> int | float:
    exact = Decimal(value)
    wire = float(exact)
    if Decimal(str(wire)) != exact:
        raise InvoiceError("invalid_input", "invoice_amount_precision")
    return int(exact) if exact == exact.to_integral_value() else wire


def payload(
    data: InvoiceDraft, allocation: Case, issuer: dict[str, Any]
) -> dict[str, Any]:
    errors = draft_errors(data)
    for blocker in fiscal_blockers(data):
        errors["currency"] = blocker
    if issuer["country"] != "DO":
        errors["issuer.country"] = "jurisdiction"
    sender = allocation.payload["sender"]
    if issuer["business_rnc"] != allocation.issuer:
        errors["issuer.tax_id"] = "issuer_mismatch"
    if (
        issuer["name"] != sender["companyName"]
        or issuer["business_provided_details"].get("address") != sender["address"]
    ):
        errors["issuer.identity"] = "issuer_mismatch"
    if (
        not 1 <= len(sender["companyName"]) <= 150
        or not 1 <= len(sender["address"]) <= 100
    ):
        errors["issuer.identity"] = "provider_length"
    if data.tax_inclusion != "excluded":
        errors["tax_inclusion"] = "excluded_required"
    if data.payment_type == "free":
        errors["payment_type"] = "unsupported_payment_type"
    if len(data.terms) > 15:
        errors["terms"] = "provider_max_15"
    pdf_note = "\n\n".join(value for value in (data.notes, data.instructions) if value)
    if len(pdf_note) > 250:
        errors["notes"] = "provider_combined_max_250"
        errors["instructions"] = "provider_combined_max_250"
    if len(data.customer_input.name) > 150:
        errors["customer_input.name"] = "provider_max_150"
    if len(data.customer_input.address) > 100:
        errors["customer_input.address"] = "provider_max_100"
    total = amounts(data)
    if total and Decimal(total.total) >= 250000 and not data.customer_input.tax_id:
        errors["customer_input.tax_id"] = "required"
    for item in data.items:
        prefix = "items." + item.id + "."
        if len(item.description) > 80:
            errors[prefix + "description"] = "provider_max_80"
        rate = decimal_input(item.tax)
        if rate not in (Decimal(0), Decimal(16), Decimal(18)):
            errors[prefix + "tax"] = "unsupported_tax_rate"
        if item.tax_treatment == "exempt" and rate != 0:
            errors[prefix + "tax_treatment"] = "exempt_requires_zero"
    if errors:
        raise InvoiceError("invalid_input", "invoice_not_ready", field_errors=errors)
    id_doc = {
        "encf": allocation.number,
        "incomeType": data.income_type,
        "paymentType": {"cash": 1, "credit": 2}[data.payment_type],
        "taxAmountIndicator": 0,
    }
    if data.payment_type == "credit":
        id_doc["paymentDeadline"] = data.due_on
    if data.terms:
        id_doc["paymentTerm"] = data.terms
    if data.document_type == "E31":
        raw = allocation.payload["idDoc"].get("sequenceDueDate", "")
        try:
            try:
                expiry = date.fromisoformat(raw)
            except ValueError:
                expiry = datetime.strptime(raw, "%d-%m-%Y").date()
            if expiry < date.fromisoformat(data.issued_on):
                raise ValueError()
        except ValueError:
            raise InvoiceError(
                "invalid_input",
                "invoice_not_ready",
                field_errors={"document_type": "sequence_expiry"},
            ) from None
        id_doc["sequenceDueDate"] = expiry.isoformat()
    lines = []
    bases, taxes = {}, {}
    for index, item in enumerate(data.items, 1):
        line = line_amounts(item)
        rate = decimal_input(item.tax)
        indicator = 4 if item.tax_treatment == "exempt" else {18: 1, 16: 2, 0: 3}[rate]
        base = Decimal(line.subtotal) - Decimal(line.discount)
        bases[indicator] = bases.get(indicator, Decimal(0)) + base
        taxes[indicator] = taxes.get(indicator, Decimal(0)) + Decimal(line.tax)
        detail = {
            "lineNumber": index,
            "itemName": item.description,
            "goodServiceIndicator": 1 if item.classification == "goods" else 2,
            "billingIndicator": indicator,
            "quantityItem": number(decimal_input(item.quantity)),
            "unitPriceItem": number(decimal_input(item.price)),
            "itemAmount": number(base),
        }
        if Decimal(line.discount):
            detail["discountAmount"] = number(line.discount)
            detail["subDiscounts"] = [
                {"subDiscountRate": "$", "subDiscountAmount": number(line.discount)}
            ]
        lines.append(detail)
    totals = {"totalAmount": number(total.total)}
    taxable = sum((value for key, value in bases.items() if key != 4), Decimal(0))
    if any(key != 4 for key in bases):
        totals.update(totalTaxedAmount=number(taxable), itbisTotal=number(total.tax))
    for indicator, base in bases.items():
        if indicator == 4:
            totals["exemptAmount"] = number(base)
            continue
        rate = {1: 18, 2: 16, 3: 0}[indicator]
        if Decimal(money(base * rate / 100)) != taxes[indicator]:
            raise InvoiceError(
                "invalid_input",
                "invoice_not_ready",
                field_errors={"items": "fiscal_rounding_mismatch"},
            )
        totals[f"i{indicator}AmountTaxed"] = number(base)
        totals[f"itbisS{indicator}"] = rate
        totals[f"itbis{indicator}Total"] = number(taxes[indicator])
    buyer = {"companyName": data.customer_input.name}
    if data.customer_input.tax_id:
        buyer["rnc"] = data.customer_input.tax_id
    if data.customer_input.address:
        buyer["address"] = data.customer_input.address
    return {
        "config": {"pdf": {"type": "generic", "note": pdf_note}},
        "idDoc": id_doc,
        "sender": {
            "rnc": allocation.issuer,
            "companyName": sender["companyName"],
            "address": sender["address"],
            "stampDate": data.issued_on,
        },
        "buyer": buyer,
        "itemDetails": lines,
        "totals": totals,
    }


def prepare(
    store: Store,
    service: Service,
    actor: TrustedActor,
    grant: UUID | None,
    invoice_id: UUID,
    expected_version: int,
) -> Invoice:
    service._scope(actor)
    try:
        with store.transaction(actor, grant, write=True) as db:
            row = store.invoice_row(db, actor.space_id, invoice_id)
            store.check_version(
                row, expected_version, {"expected_version": expected_version}
            )
            if row["operation_id"]:
                return store.invoice_view(db, row)
            invoice = store.invoice_view(db, row)
            if amounts(invoice.data) != invoice.amounts:
                raise InvoiceError(
                    "stale_version",
                    "invoice_totals_version_changed",
                    current_version=row["version"],
                )
            if invoice.data.customer_id:
                customer = store.customer_row(
                    db, actor.space_id, invoice.data.customer_id
                )
                if customer["archived"]:
                    raise InvoiceError(
                        "invalid_input",
                        "invoice_not_ready",
                        field_errors={"customer_id": "archived"},
                    )
            allocations = [
                case
                for case in service.cases.values()
                if case.kind == invoice.data.document_type
            ]
            if len(allocations) != 1:
                raise InvoiceError(
                    "invalid_input",
                    "invoice_not_ready",
                    field_errors={"document_type": "allocation_unavailable"},
                )
            allocation = allocations[0]
            issuer = db.execute(
                "select name,country,business_rnc,business_provided_details from public.spaces where id=%s",
                (actor.space_id,),
            ).fetchone()
            prepared_payload = payload(invoice.data, allocation, issuer)
            case = Case.model_validate(
                {
                    **allocation.model_dump(mode="json"),
                    "invoice_id": invoice.id,
                    "invoice_revision_id": invoice.revision_id,
                    "manifest_digest": digest(allocation.model_dump(mode="json")),
                    "document_key": "invoice:" + str(invoice.id),
                    "fixture_revision": str(invoice.revision_id),
                    "fixture_digest": digest(invoice.data.model_dump(mode="json")),
                    "payload": prepared_payload,
                    "payload_digest": digest(prepared_payload),
                }
            )
            operation = service.store.prepare_on(db, actor, grant, case)
            row = db.execute(
                "update public.business_invoices set operation_id=%s,issue_snapshot=%s,updated_at=clock_timestamp() where id=%s returning *",
                (
                    operation.id,
                    Jsonb(
                        {
                            "issuer": issuer,
                            "customer": invoice.data.customer_input.model_dump(
                                mode="json"
                            ),
                            "revision_id": str(invoice.revision_id),
                            "case": case.model_dump(mode="json"),
                        }
                    ),
                    invoice.id,
                ),
            ).fetchone()
            return store.invoice_view(db, row)
    except UniqueViolation:
        raise ActionError("idempotency_conflict", "fiscal_identity_conflict") from None
