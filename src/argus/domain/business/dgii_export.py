from __future__ import annotations

import calendar
import io
import json
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

import xlsxwriter

from argus.domain.business.contracts.dgii import (
    PurchaseDeclaration,
    amount_or_zero,
    money_text,
)
from argus.domain.business.contracts.facts import (
    is_sin_comprobante,
    personal_mark_admits,
)
from argus.domain.business.dgii_columns import COLUMNS, OPTIONAL_AMOUNTS
from argus.domain.business.dgii_line import (
    confirmed_declaration,
    hard_rejects,
    line_review,
)
from argus.domain.business.dgii_validation import (
    FiscalRecord,
    declarable,
    fact_value,
    is_credit,
    ncf_type,
    record_issues,
)
from argus.domain.business.fiscal_identity import (
    document_identity,
    normalized_ncf,
    normalized_taxpayer_id,
)
from argus.domain.business.rnc_registry import RncRegistry, UnknownRncRegistry


@dataclass(frozen=True)
class FiscalPacket:
    manifest: dict
    files: dict[str, bytes]


def _row(record: FiscalRecord) -> tuple[str, ...]:
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
        if isinstance(value, date):
            value = value.strftime("%Y%m%d")
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


def _txt(form: str, rnc: str, period: str, rows: list[tuple[str, ...]]) -> bytes:
    fields = [(form, rnc, period, str(len(rows))), *rows]
    if any(
        any(character in field for character in "|\r\n\x00")
        for row in fields
        for field in row
    ):
        raise ValueError("fiscal_unsafe_field")
    return "\r\n".join("|".join(row) for row in fields).encode("ascii")


def _workbook(manifest: dict, rows: dict[str, list[tuple[str, ...]]]) -> bytes:
    output = io.BytesIO()
    with xlsxwriter.Workbook(
        output,
        {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False},
    ) as book:
        book.set_properties({"created": datetime(1980, 1, 1, tzinfo=timezone.utc)})
        summary = book.add_worksheet("Resumen ITBIS")
        summary.write_row(0, 0, ("Campo", "Valor"))
        for index, (name, value) in enumerate(manifest.items(), 1):
            summary.write_string(index, 0, name)
            summary.write_string(
                index,
                1,
                json.dumps(value, ensure_ascii=False)
                if isinstance(value, (dict, list))
                else str(value),
            )
        summary.set_column(0, 0, 34)
        summary.set_column(1, 1, 75)
        for form, columns in COLUMNS.items():
            sheet = book.add_worksheet(form)
            for column, (_, label) in enumerate(columns):
                sheet.write_string(0, column, label)
            for index, row in enumerate(rows[form], 1):
                for column, value in enumerate(row):
                    sheet.write_string(index, column, value)
            if not rows[form]:
                sheet.write_string(1, 0, manifest["forms"][form]["label"])
            sheet.freeze_panes(1, 0)
            sheet.set_column(0, 22, 22)
        bridge = book.add_worksheet("Conciliación")
        columns = (
            "activity_id",
            "draft_id",
            "activity_revision",
            "approved_revision",
            "kind",
            "gross",
            "disposition",
            "reason",
            "source_ids",
        )
        bridge.write_row(0, 0, columns)
        for index, record in enumerate(manifest["reconciliation"], 1):
            for column, name in enumerate(columns):
                value = record.get(name, "")
                bridge.write_string(
                    index,
                    column,
                    json.dumps(value) if isinstance(value, list) else str(value),
                )
        bridge.set_column(0, len(columns) - 1, 28)
    return output.getvalue()


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

    The packet writes its files from these. Month close reads each form's
    status from the same summary, so both say the same thing about a month.
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
    period = start.strftime("%Y%m")
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

    def identity(record):
        return document_identity(
            record.kind,
            fact_value(record, "rnc"),
            fact_value(record, "ecf") or fact_value(record, "ncf"),
        )

    occurrences = Counter(
        identity(record)
        for record in selected
        if fact_value(record, "ecf") or fact_value(record, "ncf")
    )

    def collect(subject: FiscalRecord) -> list[dict]:
        found = record_issues(subject, originals, filer_identity=rnc, period_end=end)
        return found + hard_rejects(subject, registry)

    for record in selected:
        gross = Decimal(record.amount)
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
        if not personal_mark_admits(
            record.personal, record.include_606, sale=record.kind == "income"
        ):
            item.update(disposition="excluded", reason="personal")
            continue
        if isinstance(record.declaration, PurchaseDeclaration):
            check, line_warnings = line_review(record, registry)
            checks.append(check)
            item["rnc_check_status"] = check["status"]
            warnings.extend(line_warnings)

        if not declarable(record.currency):
            if is_sin_comprobante(record.facts):
                item.update(disposition="excluded", reason="no_fiscal_number")
                continue
            item["reason"] = "fiscal_conversion_required"
            issues.extend(collect(record))
            continue
        if record.kind == "expense":
            totals["purchase_invoice_gross"] += gross
        elif record.kind == "refund":
            totals["purchase_credit_gross"] += gross
        elif record.kind == "income":
            totals["sales_gross"] += gross
        else:
            item.update(disposition="excluded", reason="non_fiscal_money_movement")
            continue
        ncf = fact_value(record, "ecf") or fact_value(record, "ncf")
        if not ncf:
            if is_sin_comprobante(record.facts):
                item.update(disposition="excluded", reason="no_fiscal_number")
            else:
                item["reason"] = "fiscal_fact_required"
                issues.append(
                    {
                        "code": "fiscal_fact_required",
                        "activity_id": record.activity_id,
                        "field": "ncf",
                    }
                )
            continue
        if isinstance(record.declaration, PurchaseDeclaration) and ncf_type(ncf) == "02":
            item.update(
                disposition="excluded", reason="b02_purchase_not_reportable_in_606"
            )
            continue
        errors = collect(record)
        if occurrences[identity(record)] > 1:
            errors.append(
                {
                    "code": "fiscal_duplicate_document",
                    "activity_id": record.activity_id,
                    "field": "ncf",
                }
            )
        if errors:
            issues.extend(errors)
            item["reason"] = errors[0]["code"]
            continue
        declaration = record.declaration
        values = _row(record)
        mapped = dict(
            zip((column[0] for column in COLUMNS[declaration.form]), values, strict=False)
        )
        base, tax = Decimal(mapped["billed_amount"]), Decimal(mapped["itbis"])
        sign = Decimal(-1) if is_credit(record) else Decimal(1)
        if declaration.form == "606":
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
        rows[declaration.form].append(values)
        item.update(
            disposition=declaration.form,
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
    elif not closed_month and rnc is not None:
        issues.append(
            {
                "code": "fiscal_closed_calendar_month_required",
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
                record.activity_id == issue["activity_id"]
                and (record.declaration is None or record.declaration.form == form)
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
        }
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
        "physical_format": {
            "encoding": "ASCII",
            "newline": "CRLF",
            "bom": False,
            "code_padding": {
                "606_category_payment_isr": "two_digits",
                "607_income_type": "single_digit",
                "identity_type": "single_digit",
            },
            "official_tool_verified": False,
        },
    }
    return manifest, rows


def build_fiscal_packet(
    records: tuple[FiscalRecord, ...],
    *,
    rnc: str | None,
    business_name: str,
    start: date,
    end: date,
    captured_on: date,
    registry: RncRegistry | None = None,
) -> FiscalPacket:
    manifest, rows = fiscal_manifest(
        records,
        rnc=rnc,
        business_name=business_name,
        start=start,
        end=end,
        captured_on=captured_on,
        registry=registry,
    )
    period = manifest["period"]
    files = {
        f"dgii/DGII_F_{form}_{rnc}_{period}.TXT": _txt(form, rnc, period, rows[form])
        for form, shape in manifest["forms"].items()
        if shape["status"] == "prepared_candidate"
    }
    files["dgii/summary.json"] = json.dumps(
        manifest, ensure_ascii=False, indent=2
    ).encode("utf-8")
    files["dgii/606-607.xlsx"] = _workbook(manifest, rows)
    return FiscalPacket(manifest, files)
