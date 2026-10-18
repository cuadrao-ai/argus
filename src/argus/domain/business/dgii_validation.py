from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from argus.domain.business.contracts.dgii import (
    DgiiDeclaration,
    PurchaseDeclaration,
    SalesDeclaration,
)
from argus.domain.business.contracts.facts import BusinessFacts, Known
from argus.domain.business.dgii_columns import PAYMENT_BUCKETS
from argus.domain.business.fiscal_identity import normalized_ncf, normalized_taxpayer_id


@dataclass(frozen=True)
class FiscalRecord:
    activity_id: str
    activity_revision: int
    draft_id: str
    approved_revision: int
    occurred_on: date
    amount: str
    currency: str
    kind: str
    facts: BusinessFacts
    declaration: DgiiDeclaration | None
    source_ids: tuple[str, ...]


def ncf_type(value: str) -> str | None:
    normalized = normalized_ncf(value)
    return normalized[1:3] if normalized else None


def fact_value(record: FiscalRecord, name: str) -> str | None:
    fact = getattr(record.facts.fiscal, name, None)
    return fact.value if isinstance(fact, Known) else None


def is_credit(record: FiscalRecord) -> bool:
    return ncf_type(fact_value(record, "ecf") or fact_value(record, "ncf") or "") in {
        "04",
        "34",
    }


def record_issues(record: FiscalRecord, originals: dict[str, FiscalRecord]) -> list[dict]:
    issues = []

    def issue(code: str, field: str) -> None:
        issues.append({"code": code, "activity_id": record.activity_id, "field": field})

    declaration = record.declaration
    if declaration is None:
        issue("fiscal_declaration_missing", "declaration")
        return issues
    if record.currency != "DOP":
        issue("fiscal_conversion_required", "currency")
    if record.approved_revision < 1 or not record.source_ids:
        issue("fiscal_approval_evidence_missing", "approved_revision")
    ncf = normalized_ncf(fact_value(record, "ecf") or fact_value(record, "ncf"))
    kind = ncf_type(ncf or "")
    if kind is None:
        issue("fiscal_ncf_unsupported", "ncf")
    elif kind not in (
        {"01", "04", "31", "34"}
        if isinstance(declaration, PurchaseDeclaration)
        else {"01", "02"}
    ):
        issue("fiscal_ncf_unsupported", "ncf")
    if (
        not isinstance(record.facts.occurred_on, Known)
        or record.facts.occurred_on.value != record.occurred_on
    ):
        issue("fiscal_activity_revision_changed", "occurred_on")
    if not isinstance(record.facts.amount, Known) or Decimal(
        record.facts.amount.value
    ) != Decimal(record.amount):
        issue("fiscal_activity_revision_changed", "amount")
    tax = fact_value(record, "itbis")
    if tax is None:
        issue("fiscal_fact_required", "itbis")
    elif re.fullmatch(r"(?:0|[1-9]\d{0,8})(?:\.\d{1,2})?", tax) is None:
        issue("fiscal_amount_precision_or_limit", "itbis")
    optional = {
        "modified_ncf",
        "paid_on",
        "withheld_on",
        "income_withholding_type",
        "purchase_activity_id",
        "actual_refund",
    }
    consumption = (
        isinstance(declaration, SalesDeclaration)
        and kind == "02"
        and Decimal(record.amount) < 250000
    )
    for name in type(declaration).model_fields:
        if name in optional or name == "form" or consumption and name == "id_type":
            continue
        if getattr(declaration, name) is None:
            issue("fiscal_fact_required", name)
    identity = (
        normalized_taxpayer_id(fact_value(record, "rnc"))
        if declaration.id_type != "3"
        else fact_value(record, "rnc")
    )
    if not consumption:
        expected = {"1": 9, "2": 11}.get(declaration.id_type)
        if (
            identity is None
            or expected
            and not re.fullmatch(rf"\d{{{expected}}}", identity)
            or identity
            and not any(c in "123456789" for c in identity)
        ):
            issue("fiscal_identity_required", "rnc")
        elif (
            declaration.id_type == "3"
            and re.fullmatch(r"[A-Z0-9]{1,11}", identity) is None
        ):
            issue("fiscal_identity_required", "rnc")
    values = declaration.model_dump()
    for name, value in values.items():
        if isinstance(value, str) and any(c in value for c in "|\r\n\x00"):
            issue("fiscal_unsafe_field", name)
    if isinstance(declaration, PurchaseDeclaration):
        if declaration.id_type == "3":
            issue("fiscal_identity_type_unsupported", "id_type")
        if record.kind != ("refund" if is_credit(record) else "expense"):
            issue("fiscal_direction_conflict", "kind")
        if (
            declaration.itbis_cost is not None
            and tax is not None
            and Decimal(declaration.itbis_cost) > Decimal(tax)
        ):
            issue("fiscal_itbis_cost_exceeds_tax", "itbis_cost")
        if declaration.paid_on is None and (
            declaration.income_withholding_type
            or any(
                Decimal(values[name] or "0") > 0
                for name in ("itbis_withheld", "income_withheld")
            )
        ):
            issue("fiscal_payment_date_required", "paid_on")
        if is_credit(record):
            original = originals.get(str(declaration.purchase_activity_id))
            if (
                not declaration.actual_refund
                or original is None
                or original.kind != "expense"
            ):
                issue("fiscal_credit_settlement_required", "purchase_activity_id")
            elif (
                normalized_ncf(declaration.modified_ncf)
                != normalized_ncf(
                    fact_value(original, "ecf") or fact_value(original, "ncf")
                )
                or normalized_taxpayer_id(fact_value(original, "rnc")) != identity
            ):
                issue("fiscal_credit_reference_conflict", "modified_ncf")
            elif not 0 <= (record.occurred_on - original.occurred_on).days <= 30:
                issue("fiscal_credit_tax_treatment_required", "occurred_on")
            elif (record.occurred_on.year, record.occurred_on.month) != (
                original.occurred_on.year,
                original.occurred_on.month,
            ):
                issue("fiscal_credit_original_reporting_required", "modified_ncf")
            elif ncf_type(
                fact_value(original, "ecf") or fact_value(original, "ncf") or ""
            ) not in {"01", "31"}:
                issue("fiscal_credit_original_unsupported", "modified_ncf")
            if declaration.payment_method != "06":
                issue("fiscal_credit_payment_code_required", "payment_method")
        elif (
            declaration.modified_ncf is not None
            or declaration.actual_refund
            or declaration.purchase_activity_id
        ):
            issue("fiscal_credit_reference_not_applicable", "modified_ncf")
    else:
        if ncf and ncf.startswith("E"):
            issue("fiscal_607_ecf_excluded", "ncf")
        if record.kind != "income" or is_credit(record):
            issue("fiscal_direction_unsupported", "kind")
        if declaration.withheld_on is None and any(
            Decimal(values[name] or "0") > 0
            for name in (
                "itbis_withheld_by_third_parties",
                "income_withheld_by_third_parties",
            )
        ):
            issue("fiscal_withholding_date_required", "withheld_on")
        if all(values[name] is not None for name in PAYMENT_BUCKETS) and sum(
            Decimal(values[name]) for name in PAYMENT_BUCKETS
        ) != Decimal(record.amount):
            issue("fiscal_payment_total_conflict", "cash")
    if not issues:
        base = (
            Decimal(declaration.services_amount) + Decimal(declaration.goods_amount)
            if isinstance(declaration, PurchaseDeclaration)
            else Decimal(declaration.billed_amount)
        )
        gross = (
            base
            + Decimal(tax)
            + sum(
                Decimal(values[name])
                for name in ("selective_tax", "other_taxes", "legal_tip")
            )
        )
        if gross != Decimal(record.amount):
            issue("fiscal_invoice_total_conflict", "amount")
        if base >= Decimal("1000000000"):
            issue("fiscal_amount_precision_or_limit", "billed_amount")
    return issues
