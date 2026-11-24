"""Which purchases the 606 file holds for a seeded period. The export logic
is settled: this passes unchanged at every later change."""

from __future__ import annotations

import csv
import io
from dataclasses import replace
from datetime import date

import pytest
from argus.domain.business.reporting_file import (
    RecordsExport,
    build_file,
    summarize_export,
)
from argus.domain.business.reporting_store import ExportSource

from tests.business.test_records_file import NOW, report, row, xlsx
from tests.dgii.test_packet import practice_records

#: NCF, receipt date, family, currency, fiscal data. The file holds the first two.
SEEDED = (
    ("B0100000902", date(2026, 9, 21), "purchase", "DOP", "complete"),
    ("B0100000901", date(2026, 9, 4), "purchase", "DOP", "complete"),
    ("B0100000903", date(2026, 9, 9), "purchase", "DOP", "missing"),
    ("B0100000904", date(2026, 9, 11), "purchase", "DOP", None),
    ("B0100000905", date(2026, 9, 15), "purchase", "USD", "missing"),
    ("B0100000906", date(2026, 8, 31), "purchase", "DOP", "complete"),
    ("B0100000907", date(2026, 10, 1), "purchase", "DOP", "complete"),
    ("B0100000908", date(2026, 9, 18), "sale", "DOP", "complete"),
)
HELD = ["B0100000901", "B0100000902"]


def seeded_september(faker) -> ExportSource:
    purchase = practice_records()[0]
    rows, approved = [], {}
    for ncf, day, family, currency, fiscal_data in SEEDED:
        projected = row(
            faker,
            report_date=day,
            family=family,
            currency=currency,
            fiscal_data=fiscal_data,
        )
        rows.append(projected)
        fiscal = purchase.facts.fiscal.model_copy(
            update={"ncf": purchase.facts.fiscal.ncf.model_copy(update={"value": ncf})}
        )
        approved[projected.linked_activity_ids[0]] = replace(
            purchase,
            activity_id=projected.linked_activity_ids[0],
            occurred_on=day,
            currency=currency,
            facts=purchase.facts.model_copy(update={"fiscal": fiscal}),
        )
    return ExportSource(tuple(rows), approved, NOW)


def _ncfs(content: bytes, fmt: str) -> list[str]:
    if fmt == "xlsx":
        return [line[3][1] for line in xlsx(content)[1:]]
    return [line[3] for line in csv.reader(io.StringIO(content.decode("utf-8-sig")))][1:]


@pytest.mark.parametrize("fmt", ("xlsx", "csv"))
@pytest.mark.parametrize(
    "filters", ({}, {"q": "nothing matches this", "currencies": ["USD"], "ready": False})
)
def test_the_606_file_holds_the_periods_complete_purchases_in_date_order(
    faker, fmt, filters
):
    books = seeded_september(faker)
    request = report(**filters)
    built = build_file(books, RecordsExport(report=request, mode="dgii", format=fmt))
    assert _ncfs(built.content, fmt) == HELD
    assert built.row_count == len(HELD)
    preview = summarize_export(books, request).dgii
    assert (preview.form, preview.record_count) == ("606", len(HELD))
    assert (preview.pending_fiscal_count, preview.pending_rate_count) == (1, 1)
