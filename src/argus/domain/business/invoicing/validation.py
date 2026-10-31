from __future__ import annotations

import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from argus.domain.business.contracts.invoicing import (
    CustomerInput,
    InvoiceAmounts,
    InvoiceDraft,
    InvoiceItem,
)

CENT = Decimal("0.01")


def decimal_input(value: str) -> Decimal | None:
    text = value.strip().replace(",", ".")
    if not re.fullmatch(r"\d{1,7}(?:\.\d{1,2})?", text):
        return None
    return Decimal(text)


def money(value: Decimal) -> str:
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def email_valid(value: str) -> bool:
    return bool(re.fullmatch(r"[^\s@,;]+@[^\s@,;]+\.[^\s@,;]+", value.strip()))


def customer_errors(data: CustomerInput, *, fiscal: bool = False) -> dict[str, str]:
    errors = {}
    if not data.name.strip():
        errors["name"] = "required"
    if data.email and not email_valid(data.email):
        errors["email"] = "email"
    if data.tax_id and (
        not re.fullmatch(r"(?:\d{9}|\d{11})", data.tax_id)
        or not any(c != "0" for c in data.tax_id)
    ):
        errors["tax_id"] = "tax_id"
    if fiscal and not data.tax_id:
        errors["tax_id"] = "required"
    return errors


def line_amounts(item: InvoiceItem) -> InvoiceAmounts | None:
    quantity, price, tax, discount = (
        decimal_input(value)
        for value in (item.quantity, item.price, item.tax, item.discount or "0")
    )
    if (
        quantity is None
        or price is None
        or tax is None
        or discount is None
        or quantity <= 0
        or quantity > 1000
        or tax > 100
    ):
        return None
    subtotal = Decimal(money(quantity * price))
    if discount > subtotal:
        return None
    tax_amount = Decimal(money((subtotal - discount) * tax / 100))
    return InvoiceAmounts(
        subtotal=money(subtotal),
        discount=money(discount),
        tax=money(tax_amount),
        total=money(subtotal - discount + tax_amount),
    )


def amounts(data: InvoiceDraft) -> InvoiceAmounts | None:
    if data.tax_inclusion != "excluded":
        return None
    lines = [line_amounts(item) for item in data.items]
    if not lines or any(line is None for line in lines):
        return None
    return InvoiceAmounts(
        **{
            field: money(
                sum((Decimal(getattr(line, field)) for line in lines), Decimal(0))
            )
            for field in ("subtotal", "discount", "tax", "total")
        }
    )


def draft_errors(data: InvoiceDraft) -> dict[str, str]:
    errors = {
        "customer_input." + k: v
        for k, v in customer_errors(
            data.customer_input, fiscal=data.document_type == "E31"
        ).items()
    }
    dates = {}
    for key in ("issued_on", "due_on"):
        try:
            dates[key] = date.fromisoformat(getattr(data, key))
        except ValueError:
            errors[key] = "date"
    if len(dates) == 2 and dates["due_on"] < dates["issued_on"]:
        errors["due_on"] = "due_date"
    if not data.items:
        errors["items"] = "required"
    for item in data.items:
        prefix = "items." + item.id + "."
        if not item.description.strip():
            errors[prefix + "description"] = "required"
        if line_amounts(item) is None:
            for field in ("quantity", "price", "tax", "discount"):
                value = decimal_input(
                    getattr(item, field) or ("0" if field == "discount" else "")
                )
                if value is None:
                    errors[prefix + field] = "decimal"
            if prefix + "quantity" not in errors:
                q = decimal_input(item.quantity)
                if q <= 0 or q > 1000:
                    errors[prefix + "quantity"] = "quantity"
            rate = decimal_input(item.tax)
            if rate is not None and rate > 100:
                errors[prefix + "tax"] = "tax"
            if not any(k.startswith(prefix) for k in errors):
                errors[prefix + "discount"] = "amount"
        if item.classification is None:
            errors[prefix + "classification"] = "required"
        if item.tax_treatment is None:
            errors[prefix + "tax_treatment"] = "required"
    for field in ("payment_type", "income_type", "tax_inclusion"):
        if getattr(data, field) is None:
            errors[field] = "required"
    if data.delivery.to and not email_valid(data.delivery.to):
        errors["delivery.to"] = "email"
    if any(not email_valid(value) for value in data.delivery.cc):
        errors["delivery.cc"] = "email"
    total = amounts(data)
    if total is not None and Decimal(total.total) <= 0:
        errors["items"] = "total"
    return errors


def fiscal_blockers(data: InvoiceDraft) -> list[str]:
    """Reasons a saved draft cannot be issued yet, shown before issue."""

    return ["foreign_currency_pending_rate"] if data.currency != "DOP" else []
