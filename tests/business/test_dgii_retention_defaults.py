"""Approved purchases use the same retention amounts in every 606 output."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from argus.domain.business.reporting_file import RecordsExport, build_file

from tests.business.test_records_file import report, row, source, xlsx
from tests.dgii.test_packet import packet, practice_records


@pytest.mark.parametrize("output", ("excel", "summary"))
@pytest.mark.parametrize(
    "retention,expected",
    [(None, "0.00"), ("0.00", "0.00"), ("18.40", "18.40")],
    ids=("empty", "zero", "nonzero"),
)
def test_approved_purchase_retention_amounts_agree(faker, output, retention, expected):
    purchase = practice_records()[0]
    declaration = purchase.declaration.model_copy(
        update={
            "itbis_withheld": retention,
            "income_withheld": retention,
            "paid_on": date(2026, 9, 4) if retention == "18.40" else None,
        }
    )
    purchase = replace(purchase, declaration=declaration)
    original = declaration.model_dump()
    assert purchase.approved_revision > 0

    if output == "excel":
        projected = row(
            faker,
            linked_activity_ids=(purchase.activity_id,),
            fiscal_data="complete",
        )
        built = build_file(
            source(projected, approved={purchase.activity_id: purchase}),
            RecordsExport(report=report(), mode="dgii"),
        )
        assert built.row_count == 1
        _, cells = xlsx(built.content)
        assert [cells[column][:2] for column in (13, 19)] == [
            ("n", Decimal(expected)),
        ] * 2
    else:
        built = packet((purchase,))
        assert built.manifest["issues"] == []
        assert built.manifest["forms"]["606"]["status"] == "prepared_candidate"
        [values] = built.rows["606"]
        assert [values[column] for column in (11, 17)] == [expected] * 2
    assert declaration.model_dump() == original
