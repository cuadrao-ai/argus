from __future__ import annotations

import calendar
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from argus.domain.business import dgii_606_rules
from argus.domain.business.contracts.dgii import (
    MONEY_PATTERN,
    PurchaseDeclaration,
    amount_or_zero,
    date_cell,
    money_text,
    period_text,
)
from argus.domain.business.contracts.facts import (
    is_sin_comprobante,
    personal_mark_admits,
)
from argus.domain.business.dgii_columns import COLUMNS, OPTIONAL_AMOUNTS
from argus.domain.business.dgii_line import (
    REQUIRED_ZERO_606,
    confirmed_declaration,
    hard_rejects,
    line_review,
    missing_items,
)
from argus.domain.business.dgii_validation import (
    DECLARABLE_CURRENCY,
    FiscalRecord,
    declarable,
    fact_value,
    is_credit,
    ncf_type,
    record_issues,
)
from argus.domain.business.document_type import direction
from argus.domain.business.fiscal_identity import (
    document_identity,
    normalized_ncf,
    normalized_taxpayer_id,
)
from argus.domain.business.rnc_registry import RncRegistry, UnknownRncRegistry

FOREIGN_CURRENCY_NOTE = "Moneda extranjera: pendiente de tasa"


def fiscal_form(record: FiscalRecord) -> str | None:
    """The one form the record is on, from its document type: the 606 for a
    purchase, the 607 for a sale, none for money with no document."""

    found = direction(record.document_type)
    return found.form if found else None


def line_values(record: FiscalRecord) -> tuple[str, ...]:
    """One 606 or 607 line in annex order, each value as DGII's format writes it."""

    declaration = confirmed_declaration(record)
    values = declaration.model_dump()
    values.update(
        rnc=normalized_taxpayer_id(fact_value(record, "rnc"))
        if declaration.id_type != "3"
        else fact_value(record, "rnc"),
        ncf=normalized_ncf(fact_value(record, "ecf") or fact_value(record, "ncf")),
        itbis=money_text(Decimal(fact_value(record, "itbis"))),
        occurred_on=record.occurred_on,
    )
    if isinstance(declaration, PurchaseDeclaration):
        values["billed_amount"] = money_text(
            amount_or_zero(declaration.services_amount)
            + amount_or_zero(declaration.goods_amount)
        )
        values["itbis_advance"] = money_text(
            Decimal(values["itbis"]) - amount_or_zero(declaration.itbis_cost)
        )
    result = []
    for name, _ in COLUMNS[declaration.form]:
        value = None if name in {"itbis_perceived", "income_perceived"} else values[name]
        if value is None and declaration.form == "606" and name in REQUIRED_ZERO_606:
            value = "0.00"
        if isinstance(value, date):
            value = date_cell(value)
        elif value is not None and name not in {
            "rnc",
            "ncf",
            "modified_ncf",
            "id_type",
            "category",
            "income_type",
            "income_withholding_type",
            "payment_method",
        }:
            amount = Decimal(value)
            value = "" if name in OPTIONAL_AMOUNTS and amount == 0 else money_text(amount)
        result.append("" if value is None else str(value))
    return tuple(result)


def rule_issues(record: FiscalRecord, *, today: date) -> list[dict]:
    """What the 606 rule table holds the record for, read from the line the
    file would write. A record with no line to write is held by its missing
    value, not by a rule."""

    tax = fact_value(record, "itbis")
    if (
        not isinstance(confirmed_declaration(record), PurchaseDeclaration)
        or tax is None
        or re.fullmatch(MONEY_PATTERN, tax) is None
    ):
        return []
    line = dict(
        zip((name for name, _ in COLUMNS["606"]), line_values(record), strict=True)
    )
    context = dgii_606_rules.Context(
        today=today, period=period_text(record.occurred_on)
    )
    return [
        {
            "code": rule.id,
            "activity_id": record.activity_id,
            "field": rule.field,
            "message_key": rule.message_key,
        }
        for rule in dgii_606_rules.broken(line, context)
        if rule.severity == "block"
    ]


def _collect_issues(
    record: FiscalRecord,
    originals: dict[str, FiscalRecord],
    *,
    rnc: str | None,
    end: date,
    captured_on: date,
    registry: RncRegistry,
) -> list[dict]:
    return (
        record_issues(record, originals, filer_identity=rnc, period_end=end)
        + hard_rejects(record, registry)
        + rule_issues(record, today=captured_on)
    )


def _missing_ncf_issue(record: FiscalRecord) -> dict:
    return {
        "code": "fiscal_fact_required",
        "activity_id": record.activity_id,
        "field": "ncf",
    }


def _duplicate_issues(records: Sequence[FiscalRecord]) -> dict[str, dict]:
    """Repeated comprobantes in the selected month, using the export's scope."""

    identified = [
        (
            record,
            document_identity(
                record.kind,
                fact_value(record, "rnc"),
                fact_value(record, "ecf") or fact_value(record, "ncf"),
            ),
        )
        for record in records
        if fact_value(record, "ecf") or fact_value(record, "ncf")
    ]
    occurrences = Counter(identity for _, identity in identified)
    return {
        record.activity_id: {
            "code": "fiscal_duplicate_document",
            "activity_id": record.activity_id,
            "field": "ncf",
        }
        for record, identity in identified
        if occurrences[identity] > 1
    }


def fiscal_manifest(
    records: tuple[FiscalRecord, ...],
    *,
    rnc: str | None,
    business_name: str,
    start: date,
    end: date,
    captured_on: date,
    registry: RncRegistry | None = None,
) -> tuple[dict, dict[str, list[tuple[str, ...]]]]:
    """The DGII summary and the 606 and 607 rows for ``[start, end]``.

    Month close, Registros and the handover records sheet read each form's
    status and each record's place from this one summary, so all say the same
    thing about a month.
    """

    registry = registry or UnknownRncRegistry()
    rows: dict[str, list[tuple[str, ...]]] = {"606": [], "607": []}
    issues = []
    warnings = []
    checks = []
    bridge = []
    originals = {record.activity_id: record for record in records}
    selected = [record for record in records if start <= record.occurred_on <= end]
    same_month = (start.year, start.month) == (end.year, end.month)
    closed_month = (
        same_month
        and start.day == 1
        and end.day == calendar.monthrange(end.year, end.month)[1]
        and end < captured_on
    )
    period = period_text(start)
    totals = {
        name: Decimal(0)
        for name in (
            "purchase_invoice_gross",
            "purchase_credit_gross",
            "purchase_net_gross",
            "sales_gross",
            "606_unsigned_base",
            "606_unsigned_itbis",
            "606_net_base",
            "itbis_por_adelantar",
            "itbis_facturado",
            "607_detail_itbis",
            "607_detail_gross",
            "consumption_base",
            "consumption_itbis",
            "consumption_gross",
        )
    }
    consumption_count = 0
    pending_rate = Counter()

    duplicates = _duplicate_issues(selected)

    def collect(subject: FiscalRecord) -> list[dict]:
        return _collect_issues(
            subject,
            originals,
            rnc=rnc,
            end=end,
            captured_on=captured_on,
            registry=registry,
        )

    for record in selected:
        gross = Decimal(record.amount)
        form = fiscal_form(record)
        item = {
            "activity_id": record.activity_id,
            "draft_id": record.draft_id,
            "activity_revision": record.activity_revision,
            "approved_revision": record.approved_revision,
            "kind": record.kind,
            "gross": record.amount,
            "currency": record.currency,
            "source_ids": list(record.source_ids),
            "disposition": "needs_review",
            "reason": None,
        }
        bridge.append(item)
        if form is None:
            item.update(disposition="excluded", reason="non_fiscal_money_movement")
            continue
        if not personal_mark_admits(
            record.personal, record.include_606, sale=form == "607"
        ):
            item.update(disposition="excluded", reason="personal")
            continue
        if isinstance(confirmed_declaration(record), PurchaseDeclaration):
            check, line_warnings = line_review(record, registry)
            checks.append(check)
            item["rnc_check_status"] = check["status"]
            warnings.extend(line_warnings)

        if not declarable(record.currency):
            if is_sin_comprobante(record.facts):
                item.update(disposition="excluded", reason="no_fiscal_number")
                continue
            item["reason"] = "fiscal_conversion_required"
            item["note"] = FOREIGN_CURRENCY_NOTE
            pending_rate[form] += 1
            issues.extend(collect(record))
            continue
        if form == "607":
            totals["sales_gross"] += gross
        elif record.kind == "refund":
            totals["purchase_credit_gross"] += gross
        else:
            totals["purchase_invoice_gross"] += gross
        ncf = fact_value(record, "ecf") or fact_value(record, "ncf")
        if not ncf:
            if is_sin_comprobante(record.facts):
                item.update(disposition="excluded", reason="no_fiscal_number")
            else:
                item["reason"] = "fiscal_fact_required"
                issues.append(_missing_ncf_issue(record))
            continue
        if form == "606" and ncf_type(ncf) == "02":
            item.update(
                disposition="excluded", reason="b02_purchase_not_reportable_in_606"
            )
            continue
        errors = collect(record)
        if record.activity_id in duplicates:
            errors.append(duplicates[record.activity_id])
        if errors:
            issues.extend(errors)
            item["reason"] = errors[0]["code"]
            continue
        values = line_values(record)
        mapped = dict(zip((column[0] for column in COLUMNS[form]), values, strict=False))
        base, tax = Decimal(mapped["billed_amount"]), Decimal(mapped["itbis"])
        sign = Decimal(-1) if is_credit(record) else Decimal(1)
        if form == "606":
            totals["606_unsigned_base"] += base
            totals["606_unsigned_itbis"] += tax
            totals["606_net_base"] += sign * base
            totals["itbis_por_adelantar"] += sign * Decimal(mapped["itbis_advance"])
        else:
            totals["itbis_facturado"] += sign * tax
            if ncf_type(ncf) == "02":
                consumption_count += 1
                totals["consumption_base"] += base
                totals["consumption_itbis"] += tax
                totals["consumption_gross"] += gross
                if gross < 250000:
                    item.update(
                        disposition="consumption_summary", reason="b02_below_250000"
                    )
                    continue
            totals["607_detail_itbis"] += sign * tax
            totals["607_detail_gross"] += sign * gross
        rows[form].append(values)
        item.update(
            disposition=form,
            reason="credit_note_positive_magnitude" if is_credit(record) else "included",
        )
    totals["purchase_net_gross"] = (
        totals["purchase_invoice_gross"] - totals["purchase_credit_gross"]
    )
    if not same_month:
        issues.append(
            {
                "code": "fiscal_single_month_required",
                "field": "period",
                "activity_id": None,
            }
        )
    forms = {}
    for form in COLUMNS:
        relevant = [
            issue
            for issue in issues
            if issue["activity_id"] is None
            or any(
                record.activity_id == issue["activity_id"] and fiscal_form(record) == form
                for record in selected
            )
        ]
        status = (
            "no_aplica"
            if rnc is None
            else "needs_review"
            if relevant
            else "summary_only"
            if form == "607" and consumption_count and not rows[form]
            else "no_operations"
            if not rows[form]
            else "prepared_candidate"
        )
        forms[form] = {
            "status": status,
            "label": "No aplica" if status == "no_aplica" else status,
            "record_count": len(rows[form]),
            "issues": relevant,
            "official_validation": "NOT RUN",
            "foreign_currency_pending_rate_count": 0
            if status == "no_aplica"
            else pending_rate[form],
        }
        if forms[form]["foreign_currency_pending_rate_count"]:
            forms[form]["foreign_currency_note"] = FOREIGN_CURRENCY_NOTE
    manifest = {
        "schema_version": 1,
        "business_name": business_name,
        "reporter_rnc": rnc,
        "period": period,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "period_status": "closed_month_candidate" if closed_month else "DRY RUN",
        "submitted": False,
        "official_validation": "NOT RUN",
        "forms": forms,
        "totals_dop": {name: money_text(value) for name, value in totals.items()},
        "consumption_summary": {
            "count": consumption_count,
            "base": money_text(totals["consumption_base"]),
            "itbis": money_text(totals["consumption_itbis"]),
            "gross": money_text(totals["consumption_gross"]),
        },
        "reconciliation": bridge,
        "reconciliation_complete": not issues,
        "totals_complete": not issues,
        "issues": issues,
        "warnings": warnings,
        "rnc_checks": checks,
    }
    return manifest, rows


@dataclass(frozen=True)
class LineAssessment:
    """The current line's source and issues, before their codes become words.
    None means a line on the form; a tuple means the form holds it."""

    record: FiscalRecord
    issues: tuple[dict, ...] | None
    # Export holds can stop later checks. Readiness still needs every fix;
    # legacy export fields continue to read only the manifest's issues.
    readiness_issues: tuple[dict, ...] | None = None

    @property
    def missing(self) -> tuple[str, ...] | None:
        return (
            None if self.issues is None else missing_items(self.record, list(self.issues))
        )


def line_assessments(
    records: tuple[FiscalRecord, ...],
    *,
    rnc: str | None,
    captured_on: date,
    registry: RncRegistry | None = None,
) -> dict[str, LineAssessment]:
    """Preserve each month's issues for Registros; rule-excluded rows are absent."""

    registry = registry or UnknownRncRegistry()
    by_id = {record.activity_id: record for record in records}
    verdicts: dict[str, LineAssessment] = {}
    months = {(record.occurred_on.year, record.occurred_on.month) for record in records}
    for year, month in months:
        end = date(year, month, calendar.monthrange(year, month)[1])
        manifest, _rows = fiscal_manifest(
            records,
            rnc=rnc,
            business_name="",
            start=date(year, month, 1),
            end=end,
            captured_on=captured_on,
            registry=registry,
        )
        duplicates = _duplicate_issues(
            tuple(
                record for record in records
                if (record.occurred_on.year, record.occurred_on.month) == (year, month)
            )
        )
        for identifier, assessment in manifest_assessments(manifest, by_id).items():
            record = assessment.record
            missing_ncf = not (
                fact_value(record, "ecf") or fact_value(record, "ncf")
            )
            if assessment.issues is not None and (
                missing_ncf or not declarable(record.currency)
            ):
                # Recheck the same amounts without the conversion hold masking
                # consistency checks. This validation-only copy converts no
                # money; the original record and export issues stay untouched.
                checked = _collect_issues(
                    replace(record, currency=DECLARABLE_CURRENCY),
                    by_id,
                    rnc=rnc,
                    end=end,
                    captured_on=captured_on,
                    registry=registry,
                )
                if identifier in duplicates:
                    checked.append(duplicates[identifier])
                complete = assessment.issues + tuple(
                    issue for issue in checked if issue not in assessment.issues
                )
                # An absent number needs entering, not repairing. Other fiscal
                # issues still come from the same validators as the export.
                if missing_ncf:
                    complete = (
                        _missing_ncf_issue(record),
                        *(issue for issue in complete if issue["field"] != "ncf"),
                    )
                assessment = replace(assessment, readiness_issues=complete)
            verdicts[identifier] = assessment
    return verdicts


def line_verdicts(
    records: tuple[FiscalRecord, ...],
    *,
    rnc: str | None,
    captured_on: date,
    registry: RncRegistry | None = None,
) -> dict[str, tuple[str, ...] | None]:
    """The existing export verdict: None for a line, otherwise missing words."""

    return {
        identifier: assessment.missing
        for identifier, assessment in line_assessments(
            records, rnc=rnc, captured_on=captured_on, registry=registry
        ).items()
    }


def manifest_assessments(
    manifest: dict, by_id: dict[str, FiscalRecord]
) -> dict[str, LineAssessment]:
    """The one reading of manifest issues shared by Registros and month close."""

    verdicts: dict[str, LineAssessment] = {}
    for item in manifest["reconciliation"]:
        identifier = item["activity_id"]
        if item["disposition"] in COLUMNS:
            verdicts[identifier] = LineAssessment(by_id[identifier], None)
        elif item["disposition"] == "needs_review":
            issues = [
                issue
                for issue in manifest["issues"]
                if issue["activity_id"] == identifier
            ]
            verdicts[identifier] = LineAssessment(by_id[identifier], tuple(issues))
    return verdicts


def manifest_verdicts(
    manifest: dict, by_id: dict[str, FiscalRecord]
) -> dict[str, tuple[str, ...] | None]:
    return {
        identifier: assessment.missing
        for identifier, assessment in manifest_assessments(manifest, by_id).items()
    }
