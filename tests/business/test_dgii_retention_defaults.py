"""Approved purchases use the same retention amounts in every 606 output."""

import io
from dataclasses import replace
from datetime import date
from decimal import Decimal
from xml.etree import ElementTree
from zipfile import ZipFile

import pytest
from argus.domain.business.reporting_file import RecordsExport, build_file

from tests.business.test_records_file import NS, report, row, source, xlsx
from tests.dgii.test_packet import packet, practice_records


@pytest.mark.parametrize("output", ("excel", "txt", "review"))
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
        if output == "txt":
            lines = built.files["dgii/DGII_F_606_199990013_202609.TXT"].decode().splitlines()
            assert len(lines) == 2
            values = lines[1].split("|")
            assert [values[column] for column in (11, 17)] == [expected] * 2
        else:
            with ZipFile(io.BytesIO(built.files["dgii/606-607.xlsx"])) as book:
                strings = [
                    "".join(node.itertext())
                    for node in ElementTree.fromstring(
                        book.read("xl/sharedStrings.xml")
                    ).findall("m:si", NS)
                ]
                sheet = ElementTree.fromstring(book.read("xl/worksheets/sheet2.xml"))
            cells = {
                cell.attrib["r"]: strings[int(cell.find("m:v", NS).text)]
                for cell in sheet.findall("m:sheetData/m:row/m:c", NS)
            }
            assert [cells.get(address, "") for address in ("L2", "R2")] == [expected] * 2
    assert declaration.model_dump() == original
