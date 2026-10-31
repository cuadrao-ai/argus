"""Foreign-currency lines wait for a rate, and the user reads it in words."""

from __future__ import annotations

import io
from dataclasses import replace
from datetime import date
from xml.etree import ElementTree
from zipfile import ZipFile

from argus.api.business_month_close_schemas import MonthClose
from argus.domain.business.dgii_export import build_fiscal_packet, fiscal_manifest
from argus.domain.business.month_close import PAYMENT_METHODS, summarize
from argus.domain.business.month_close_store import foreign_currency, month_close

from tests.business.test_month_close import DAY
from tests.dgii.test_packet import practice_records

NOTE = "Moneda extranjera: pendiente de tasa"
SEPTEMBER = dict(
    rnc="131000001",
    business_name="Práctica",
    start=date(2026, 9, 1),
    end=date(2026, 9, 30),
    captured_on=DAY,
)


def _dollars(*indexes):
    records = practice_records()
    return tuple(
        replace(record, currency="USD") if index in indexes else record
        for index, record in enumerate(records)
    )


def _conciliacion(packet):
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with ZipFile(io.BytesIO(packet.files["dgii/606-607.xlsx"])) as book:
        strings = [
            "".join(item.itertext())
            for item in ElementTree.fromstring(book.read("xl/sharedStrings.xml")).findall(
                "m:si", ns
            )
        ]
        sheet = ElementTree.fromstring(book.read("xl/worksheets/sheet4.xml"))
    return [
        [strings[int(cell.find("m:v", ns).text)] for cell in row]
        for row in sheet.findall("m:sheetData/m:row", ns)
    ]


def test_peso_only_month_has_no_pending_rate_and_no_note():
    manifest, _rows = fiscal_manifest(practice_records(), **SEPTEMBER)
    for form in ("606", "607"):
        assert manifest["forms"][form]["foreign_currency_pending_rate_count"] == 0
        assert "foreign_currency_note" not in manifest["forms"][form]
    assert foreign_currency(manifest["forms"]) == {
        "606": {"pending_rate_count": 0, "reason": None},
        "607": {"pending_rate_count": 0, "reason": None},
    }


def test_each_form_counts_its_own_dollar_lines():
    one = fiscal_manifest(_dollars(4), **SEPTEMBER)[0]["forms"]
    assert one["607"]["foreign_currency_pending_rate_count"] == 1
    assert one["607"]["foreign_currency_note"] == NOTE
    assert one["606"]["foreign_currency_pending_rate_count"] == 0
    several = fiscal_manifest(_dollars(0, 1, 2), **SEPTEMBER)[0]["forms"]
    assert several["606"]["foreign_currency_pending_rate_count"] == 3
    assert several["607"]["foreign_currency_pending_rate_count"] == 0
    assert foreign_currency(several)["606"] == {"pending_rate_count": 3, "reason": NOTE}


def test_counting_leaves_lines_totals_and_status_alone():
    records = _dollars(1)
    manifest, rows = fiscal_manifest(records, **SEPTEMBER)
    baseline, baseline_rows = fiscal_manifest(
        tuple(r for i, r in enumerate(records) if i != 1), **SEPTEMBER
    )
    assert rows == baseline_rows
    assert manifest["totals_dop"] == baseline["totals_dop"]
    assert manifest["forms"]["606"]["status"] == "needs_review"
    [bridge] = [b for b in manifest["reconciliation"] if b["currency"] == "USD"]
    assert bridge["reason"] == "fiscal_conversion_required"
    assert bridge["note"] == NOTE


def test_workbook_reads_the_note_and_never_the_raw_code():
    rows = _conciliacion(build_fiscal_packet(_dollars(0, 4), **SEPTEMBER))
    reason = rows[0].index("reason")
    reasons = [row[reason] for row in rows[1:]]
    assert reasons.count(NOTE) == 2
    assert "fiscal_conversion_required" not in reasons


def test_older_summary_without_the_count_reads_as_zero():
    assert foreign_currency({"606": {"status": "needs_review"}}) == {
        "606": {"pending_rate_count": 0, "reason": None},
        "607": {"pending_rate_count": 0, "reason": None},
    }
    wire = {
        "month": "2026-09",
        "today": DAY,
        "payment_methods": list(PAYMENT_METHODS),
        "dgii_forms": {"606": "no_operations", "607": "no_operations"},
        **summarize([], date(2026, 9, 1), date(2026, 9, 30)),
    }
    parsed = MonthClose.model_validate(wire).model_dump(by_alias=True)
    assert parsed["dgii_foreign_currency"]["606"] == {
        "pending_rate_count": 0,
        "reason": None,
    }


def test_month_close_carries_the_count_beside_the_unchanged_status():
    manifest, _rows = fiscal_manifest(_dollars(0, 1), **SEPTEMBER)
    statuses = {form: shape["status"] for form, shape in manifest["forms"].items()}
    body = month_close("2026-09", DAY, (), statuses, foreign_currency(manifest["forms"]))
    wire = MonthClose.model_validate(body).model_dump(by_alias=True, mode="json")
    assert wire["dgii_forms"]["606"] == "needs_review"
    assert wire["dgii_foreign_currency"] == {
        "606": {"pending_rate_count": 2, "reason": NOTE},
        "607": {"pending_rate_count": 0, "reason": None},
    }


def test_undeclared_dollar_lines_count_once_on_their_own_form():
    records = practice_records()
    expense = next(r for r in records if r.kind == "expense")
    income = next(r for r in records if r.kind == "income")
    undeclared = tuple(
        replace(r, currency="USD", declaration=None) for r in (expense, income)
    )
    manifest, _rows = fiscal_manifest(undeclared, **SEPTEMBER)
    statuses = {form: shape["status"] for form, shape in manifest["forms"].items()}
    body = month_close("2026-09", DAY, (), statuses, foreign_currency(manifest["forms"]))
    wire = MonthClose.model_validate(body).model_dump(by_alias=True, mode="json")
    assert wire["dgii_foreign_currency"] == {
        "606": {"pending_rate_count": 1, "reason": NOTE},
        "607": {"pending_rate_count": 1, "reason": NOTE},
    }
