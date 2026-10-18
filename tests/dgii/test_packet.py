import io
import json
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID
from xml.etree import ElementTree
from zipfile import ZipFile

import pytest
from argus.domain.business.contracts.dgii import FiscalReview
from argus.domain.business.contracts.facts import (
    BusinessFacts,
    FiscalFacts,
    Known,
    Unknown,
)
from argus.domain.business.dgii_export import build_fiscal_packet
from argus.domain.business.dgii_validation import FiscalRecord
from pydantic import ValidationError


def practice_records():
    root = Path(__file__).parent / "fixtures"
    inputs = json.loads((root / "practice-inputs.json").read_text())["records"]
    oracle = {
        item["id"]: item
        for item in json.loads((root / "practice-oracle.json").read_text())["records"]
    }
    result = []
    for index, item in enumerate(inputs, 1):
        data = oracle[item["record_id"]]
        value = FiscalReview.model_validate(item["input"])
        if item["record_id"] == "P04":
            value = value.model_copy(
                update={
                    "declaration": value.declaration.model_copy(
                        update={"purchase_activity_id": UUID(int=1)}
                    )
                }
            )

        def known(value, source_index=index):
            return (
                Known(
                    value=value,
                    origin="member_set",
                    source_ids=(UUID(int=source_index + 100),),
                )
                if value is not None
                else Unknown()
            )

        kind = (
            "refund"
            if item["record_id"] == "P04"
            else "expense"
            if value.declaration.form == "606"
            else "income"
        )
        facts = BusinessFacts(
            kind=known(kind),
            amount=known(data["gross"]),
            currency=known("DOP"),
            occurred_on=known(date.fromisoformat(data["date"])),
            fiscal=FiscalFacts(
                rnc=known(value.fiscal.rnc),
                ncf=known(value.fiscal.ncf),
                itbis=known(value.fiscal.itbis),
            ),
        )
        result.append(
            FiscalRecord(
                str(UUID(int=index)),
                1,
                str(UUID(int=index + 10)),
                2,
                date.fromisoformat(data["date"]),
                data["gross"],
                "DOP",
                kind,
                facts,
                value.declaration,
                (str(UUID(int=index + 100)),),
            )
        )
    return tuple(result)


def packet(records=None, **changes):
    return build_fiscal_packet(
        practice_records() if records is None else records,
        **{
            "rnc": "199990013",
            "business_name": "PRÁCTICA José",
            "start": date(2026, 9, 1),
            "end": date(2026, 9, 30),
            "captured_on": date(2026, 10, 18),
            **changes,
        },
    )


def test_practice_annex_rows_and_economic_reconciliation():
    result = packet()
    assert result.manifest["issues"] == []
    assert result.manifest["forms"]["606"]["record_count"] == 3
    assert result.manifest["forms"]["607"]["record_count"] == 1
    purchase = result.files["dgii/DGII_F_606_199990013_202609.TXT"].decode("ascii").splitlines()
    assert purchase[0] == "606|199990013|202609|3"
    assert all(len(row.split("|")) == 23 for row in purchase[1:])
    note = purchase[-1].split("|")
    assert (note[3], note[4], note[9], note[10], note[14], note[22]) == (
        "B0400000001",
        "B0100000001",
        "100.00",
        "18.00",
        "18.00",
        "06",
    )
    assert Decimal(note[9]) > 0
    totals = result.manifest["totals_dop"]
    assert {
        name: totals[name]
        for name in (
            "purchase_invoice_gross",
            "purchase_credit_gross",
            "purchase_net_gross",
            "606_unsigned_base",
            "606_unsigned_itbis",
            "606_net_base",
            "itbis_por_adelantar",
            "itbis_facturado",
            "sales_gross",
        )
    } == {
        "purchase_invoice_gross": "2006.00",
        "purchase_credit_gross": "118.00",
        "purchase_net_gross": "1888.00",
        "606_unsigned_base": "1600.00",
        "606_unsigned_itbis": "288.00",
        "606_net_base": "1400.00",
        "itbis_por_adelantar": "252.00",
        "itbis_facturado": "450.00",
        "sales_gross": "2950.00",
    }
    assert result.manifest["consumption_summary"] == {
        "count": 1,
        "base": "500.00",
        "itbis": "90.00",
        "gross": "590.00",
    }
    assert result.manifest["official_validation"] == "NOT RUN"
    assert result.manifest["submitted"] is False


def test_missing_rnc_produces_no_aplica_without_empty_txt():
    result = packet(rnc=None, start=date(2026, 10, 1), end=date(2026, 10, 17))
    assert all(form["label"] == "No aplica" for form in result.manifest["forms"].values())
    assert not any(name.lower().endswith(".txt") for name in result.files)
    assert result.manifest["period_status"] == "DRY RUN"
    with ZipFile(io.BytesIO(result.files["dgii/606-607.xlsx"])) as book:
        assert b"No aplica" in book.read("xl/sharedStrings.xml")


@pytest.mark.parametrize("field", ["itbis_cost", "goods_amount", "itbis_proportionality"])
def test_unknown_required_tax_fact_never_becomes_zero_or_valid_file(field):
    records = practice_records()
    first = records[0]
    first = replace(first, declaration=first.declaration.model_copy(update={field: None}))
    result = packet((first, *records[1:]))
    assert result.manifest["forms"]["606"]["status"] == "needs_review"
    assert "dgii/DGII_F_606_199990013_202609.TXT" not in result.files
    assert any(issue["field"] == field for issue in result.manifest["issues"])


def test_duplicate_document_does_not_silently_claim_valid_second_expense():
    records = practice_records()
    duplicate = replace(records[0], activity_id=str(UUID(int=50)))
    result = packet((*records, duplicate))
    assert any(
        issue["code"] == "fiscal_duplicate_document"
        for issue in result.manifest["issues"]
    )
    assert "dgii/DGII_F_606_199990013_202609.TXT" not in result.files


def test_itbis_advance_is_billed_minus_cost_not_withholding():
    record = practice_records()[0]
    declaration = record.declaration.model_copy(
        update={"itbis_cost": "20.00", "itbis_withheld": "10.00"}
    )
    result = packet((replace(record, declaration=declaration),))
    row = result.files["dgii/DGII_F_606_199990013_202609.TXT"].decode().splitlines()[1].split("|")
    assert row[14] == "160.00"


def test_credit_note_requires_actual_refund_original_and_tax_date():
    records = practice_records()
    credit = records[3]
    for update, code in [
        ({"actual_refund": False}, "fiscal_credit_settlement_required"),
        ({"modified_ncf": "B0100000099"}, "fiscal_credit_reference_conflict"),
    ]:
        result = packet(
            (
                *records[:3],
                replace(credit, declaration=credit.declaration.model_copy(update=update)),
                *records[4:],
            )
        )
        assert any(issue["code"] == code for issue in result.manifest["issues"])


@pytest.mark.parametrize("value", ["1.001", "1e2", "1,00", "-1", 1.1, "1|0", "1\n0"])
def test_money_and_identifiers_reject_unsafe_or_inexact_inputs(value):
    inputs = json.loads(
        (Path(__file__).parent / "fixtures/practice-inputs.json").read_text()
    )["records"][0]["input"]
    inputs["fiscal"]["itbis"] = value
    with pytest.raises(ValidationError):
        FiscalReview.model_validate(inputs)


def test_xlsx_identifiers_are_text_without_formula_or_hyperlink():
    result = packet(business_name='=HYPERLINK("bad")')
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with ZipFile(io.BytesIO(result.files["dgii/606-607.xlsx"])) as book:
        strings = [
            "".join(item.itertext())
            for item in ElementTree.fromstring(book.read("xl/sharedStrings.xml")).findall(
                "m:si", ns
            )
        ]
        for name in book.namelist():
            if name.startswith("xl/worksheets/sheet"):
                sheet = ElementTree.fromstring(book.read(name))
                assert sheet.findall(".//m:f", ns) == []
                assert sheet.findall(".//m:hyperlink", ns) == []
        sheet = ElementTree.fromstring(book.read("xl/worksheets/sheet2.xml"))
        first = sheet.findall("m:sheetData/m:row", ns)[1]
        cells = [strings[int(cell.find("m:v", ns).text)] for cell in first]
        assert cells[0] == "199990021"
        assert cells[2] == "09"


def test_year_boundary_requires_one_month_and_current_month_stays_dry_run():
    assert (
        packet(start=date(2026, 12, 1), end=date(2027, 1, 1)).manifest["forms"]["606"][
            "status"
        ]
        == "needs_review"
    )
    assert packet(captured_on=date(2026, 9, 30)).manifest["period_status"] == "DRY RUN"


def test_partial_month_keeps_review_evidence_but_never_emits_monthly_txt():
    result = packet(end=date(2026, 9, 17))
    assert result.manifest["period_status"] == "DRY RUN"
    assert not any(name.lower().endswith(".txt") for name in result.files)
    assert result.manifest["reconciliation"]


def test_small_consumption_sale_is_summary_only_instead_of_no_operations():
    result = packet((practice_records()[-1],))
    assert result.manifest["forms"]["607"]["status"] == "summary_only"
    assert result.manifest["consumption_summary"]["count"] == 1
    assert "dgii/DGII_F_607_199990013_202609.TXT" not in result.files
    empty = packet(())
    assert empty.manifest["forms"]["607"]["status"] == "no_operations"


def test_formatted_legacy_ids_share_identity_without_changing_source_facts():
    records = practice_records()
    first = records[0]
    fiscal = first.facts.fiscal.model_copy(
        update={
            "rnc": first.facts.fiscal.rnc.model_copy(update={"value": "199-99002-1"}),
            "ncf": first.facts.fiscal.ncf.model_copy(update={"value": "b0100000001"}),
        }
    )
    legacy = replace(first, facts=first.facts.model_copy(update={"fiscal": fiscal}))
    result = packet((legacy,))
    assert result.manifest["issues"] == []
    assert "199990021|1|09|B0100000001" in result.files["dgii/DGII_F_606_199990013_202609.TXT"].decode()
    assert legacy.facts.fiscal.rnc.value == "199-99002-1"
    duplicate = replace(first, activity_id=str(UUID(int=77)))
    blocked = packet((legacy, duplicate))
    assert (
        len(
            [
                issue
                for issue in blocked.manifest["issues"]
                if issue["code"] == "fiscal_duplicate_document"
            ]
        )
        == 2
    )


def test_legacy_tax_precision_is_reported_without_rounding():
    first = practice_records()[0]
    fiscal = first.facts.fiscal.model_copy(
        update={"itbis": first.facts.fiscal.itbis.model_copy(update={"value": "180.001"})}
    )
    result = packet(
        (replace(first, facts=first.facts.model_copy(update={"fiscal": fiscal})),)
    )
    assert "dgii/DGII_F_606_199990013_202609.TXT" not in result.files
    assert any(
        issue["code"] == "fiscal_amount_precision_or_limit"
        for issue in result.manifest["issues"]
    )
