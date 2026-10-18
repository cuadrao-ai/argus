import io
from dataclasses import replace
from datetime import date
from decimal import Decimal
from xml.etree import ElementTree
from zipfile import ZipFile

import pytest
from argus.domain.business.dgii_columns import COLUMNS, PAYMENT_BUCKETS
from argus.domain.business.fiscal_profile import FiscalProfileChange
from pydantic import ValidationError
from test_packet import packet, practice_records


def changed(record, *, ncf=None, amount=None, tax=None, **declaration):
    fiscal = record.facts.fiscal
    if ncf is not None:
        field = "ecf" if ncf.startswith("E") else "ncf"
        fiscal = fiscal.model_copy(
            update={field: fiscal.ncf.model_copy(update={"value": ncf})}
        )
    if tax is not None:
        fiscal = fiscal.model_copy(
            update={"itbis": fiscal.itbis.model_copy(update={"value": tax})}
        )
    facts = record.facts.model_copy(update={"fiscal": fiscal})
    if amount is not None:
        facts = facts.model_copy(
            update={"amount": facts.amount.model_copy(update={"value": amount})}
        )
    return replace(
        record,
        amount=amount or record.amount,
        facts=facts,
        declaration=record.declaration.model_copy(update=declaration),
    )


@pytest.mark.parametrize("filer", ["199990013", "00100000001"])
def test_filer_identity_preserves_rnc_or_cedula_in_header_and_filename(filer):
    assert FiscalProfileChange(rnc=filer, previous_rnc=None).rnc == filer
    result = packet(rnc=filer)
    for form, count in [("606", 3), ("607", 1)]:
        name = f"dgii/DGII_F_{form}_{filer}_202609.TXT"
        assert (
            result.files[name].decode().splitlines()[0]
            == f"{form}|{filer}|202609|{count}"
        )
        assert result.manifest["forms"][form]["status"] == "prepared_candidate"


@pytest.mark.parametrize(
    "filer", ["000000000", "00000000000", "1234567890", "123456789012"]
)
def test_invalid_filer_shape_is_rejected(filer):
    with pytest.raises(ValidationError):
        FiscalProfileChange(rnc=filer, previous_rnc=None)


@pytest.mark.parametrize(
    "code", ["03", "11", "13", "14", "15", "17", "33", "41", "43", "44", "45", "47"]
)
def test_additional_purchase_document_types_are_exportable(code):
    number = ("E" + code + "0000000001") if int(code) > 30 else ("B" + code + "00000001")
    declaration = {"modified_ncf": "B0100000099"} if code in {"03", "33"} else {}
    filer = "199990021" if code in {"13", "17", "43", "47"} else "199990013"
    result = packet(
        (changed(practice_records()[0], ncf=number, **declaration),), rnc=filer
    )
    assert result.manifest["issues"] == []
    assert number in result.files[f"dgii/DGII_F_606_{filer}_202609.TXT"].decode()


@pytest.mark.parametrize("code", ["14", "15", "16"])
def test_additional_sales_document_types_are_exportable(code):
    result = packet((changed(practice_records()[4], ncf=f"B{code}00000001"),))
    assert result.manifest["issues"] == []
    assert (
        f"B{code}00000001"
        in result.files["dgii/DGII_F_607_199990013_202609.TXT"].decode()
    )


def test_sales_credit_note_has_modified_reference_and_signed_tax_bridge():
    original = practice_records()[4]
    note = changed(
        original,
        ncf="B0400000099",
        amount="118.00",
        tax="18.00",
        billed_amount="100.00",
        modified_ncf="B0100000001",
        **{name: None for name in PAYMENT_BUCKETS},
    )
    note = replace(
        note,
        activity_id="sale-credit",
        draft_id="sale-credit-draft",
        occurred_on=date(2026, 9, 20),
        facts=note.facts.model_copy(
            update={
                "occurred_on": note.facts.occurred_on.model_copy(
                    update={"value": date(2026, 9, 20)}
                )
            }
        ),
    )
    result = packet((original, note))
    assert result.manifest["issues"] == []
    rows = result.files["dgii/DGII_F_607_199990013_202609.TXT"].decode().splitlines()
    row = next(row.split("|") for row in rows[1:] if "B0400000099" in row)
    assert row[3] == "B0100000001" and row[7:9] == ["100.00", "18.00"]
    assert row[16:] == [""] * 7
    assert result.manifest["totals_dop"]["itbis_facturado"] == "342.00"
    assert result.manifest["totals_dop"]["607_detail_gross"] == "2242.00"
    missing = packet((original, changed(note, modified_ncf=None)))
    assert missing.manifest["forms"]["607"]["status"] == "needs_review"


@pytest.mark.parametrize("index,columns", [(0, (15, 18)), (4, (10, 12))])
@pytest.mark.parametrize("value", [None, "0.00"])
def test_disabled_perception_fields_remain_empty(index, columns, value):
    record = changed(
        practice_records()[index], itbis_perceived=value, income_perceived=value
    )
    result = packet((record,))
    form = record.declaration.form
    row = (
        result.files[f"dgii/DGII_F_{form}_199990013_202609.TXT"]
        .decode()
        .splitlines()[1]
        .split("|")
    )
    assert [row[column] for column in columns] == ["", ""]


@pytest.mark.parametrize("index", [0, 4])
def test_nonzero_perception_is_not_silently_discarded(index):
    result = packet((changed(practice_records()[index], itbis_perceived="1.00"),))
    assert any(
        x["code"] == "fiscal_perception_regime_unsupported"
        for x in result.manifest["issues"]
    )


def test_purchase_total_must_be_positive():
    record = changed(
        practice_records()[0], amount="0", tax="0", services_amount="0", goods_amount="0"
    )
    result = packet((record,))
    assert any(
        x["code"] == "fiscal_billed_amount_must_be_positive"
        for x in result.manifest["issues"]
    )


def test_sales_billed_amount_cannot_be_less_than_itbis():
    record = changed(
        practice_records()[4], amount="190", tax="180", billed_amount="10", cash="190"
    )
    result = packet((record,))
    assert any(
        x["code"] == "fiscal_itbis_exceeds_billed_amount"
        for x in result.manifest["issues"]
    )


@pytest.mark.parametrize(
    "paid_on,valid", [(date(2026, 9, 30), True), (date(2026, 10, 1), False)]
)
def test_purchase_payment_date_does_not_pass_export_period_end(paid_on, valid):
    result = packet((changed(practice_records()[0], paid_on=paid_on),))
    assert (result.manifest["forms"]["606"]["status"] == "prepared_candidate") is valid
    assert (
        any(
            x["code"] == "fiscal_payment_date_after_period"
            for x in result.manifest["issues"]
        )
        is not valid
    )


def test_workbook_uses_exact_official_column_titles():
    result = packet()
    expected = {
        "606": [
            "RNC o Cédula",
            "Tipo Id",
            "Tipo Bienes y Servicios Comprados",
            "NCF",
            "NCF ó Documento Modificado",
            "Fecha Comprobante",
            "Fecha Pago",
            "Monto Facturado en Servicios",
            "Monto Facturado en Bienes",
            "Total Monto Facturado",
            "ITBIS Facturado",
            "ITBIS Retenido",
            "ITBIS sujeto a Proporcionalidad (Art. 349)",
            "ITBIS llevado al Costo",
            "ITBIS por Adelantar",
            "ITBIS percibido en compras",
            "Tipo de Retención en ISR",
            "Monto Retención Renta",
            "ISR Percibido en compras",
            "Impuesto Selectivo al Consumo",
            "Otros Impuesto/Tasas",
            "Monto Propina Legal",
            "Forma de Pago",
        ],
        "607": [
            "RNC/Cédula o Pasaporte",
            "Tipo Identificación",
            "Número Comprobante Fiscal",
            "Número Comprobante Fiscal Modificado",
            "Tipo de Ingreso",
            "Fecha Comprobante",
            "Fecha de Retención",
            "Monto Facturado",
            "ITBIS Facturado",
            "ITBIS Retenido por Terceros",
            "ITBIS Percibido",
            "Retención Renta por Terceros",
            "ISR Percibido",
            "Impuesto Selectivo al Consumo",
            "Otros Impuestos/Tasas",
            "Monto Propina Legal",
            "Efectivo",
            "Cheque/ Transferencia/ Depósito",
            "Tarjeta Débito/Crédito",
            "Venta a Crédito",
            "Bonos o Certificados de Regalo",
            "Permuta",
            "Otras Formas de Ventas",
        ],
    }
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with ZipFile(io.BytesIO(result.files["dgii/606-607.xlsx"])) as book:
        strings = [
            "".join(x.itertext())
            for x in ElementTree.fromstring(book.read("xl/sharedStrings.xml")).findall(
                "m:si", ns
            )
        ]
        for number, form in [(2, "606"), (3, "607")]:
            row = ElementTree.fromstring(
                book.read(f"xl/worksheets/sheet{number}.xml")
            ).findall("m:sheetData/m:row", ns)[0]
            assert [strings[int(cell.find("m:v", ns).text)] for cell in row] == expected[
                form
            ]
            assert [label for _, label in COLUMNS[form]] == expected[form]


@pytest.mark.parametrize(
    "number", ["B3300000001", "E030000000001", "B4100000001", "E110000000001"]
)
def test_document_series_and_type_cannot_be_mixed(number):
    result = packet((changed(practice_records()[0], ncf=number),))
    assert any(x["code"] == "fiscal_ncf_unsupported" for x in result.manifest["issues"])


def test_flagged_electronic_document_behavior_is_preserved():
    purchase = packet((changed(practice_records()[0], ncf="E310000000001"),))
    assert purchase.manifest["forms"]["606"]["status"] == "prepared_candidate"
    sale = packet((changed(practice_records()[4], ncf="E310000000001"),))
    assert any(x["code"] == "fiscal_607_ecf_excluded" for x in sale.manifest["issues"])


@pytest.mark.parametrize("amount,detail", [("249999.99", False), ("250000.00", True)])
def test_flagged_consumption_cutoff_still_uses_gross_amount(amount, detail):
    record = changed(
        practice_records()[-1],
        amount=amount,
        tax="18",
        billed_amount=str(Decimal(amount) - Decimal("18")),
        **{name: amount if name == "cash" else "0" for name in PAYMENT_BUCKETS},
    )
    fiscal = record.facts.fiscal.model_copy(
        update={"rnc": practice_records()[4].facts.fiscal.rnc}
    )
    record = replace(
        record,
        facts=record.facts.model_copy(update={"fiscal": fiscal}),
        declaration=record.declaration.model_copy(update={"id_type": "1"}),
    )
    result = packet((record,))
    assert result.manifest["issues"] == []
    assert result.manifest["forms"]["607"]["record_count"] == int(detail)
    assert result.manifest["consumption_summary"]["gross"] == amount


def test_flagged_purchase_credit_payment_and_thirty_day_rules_remain():
    original, *_, note, sale, consumer = practice_records()
    result = packet((original, changed(note, payment_method="05")))
    assert any(
        x["code"] == "fiscal_credit_payment_code_required"
        for x in result.manifest["issues"]
    )
    old_date = date(2026, 8, 1)
    original = replace(
        original,
        occurred_on=old_date,
        facts=original.facts.model_copy(
            update={
                "occurred_on": original.facts.occurred_on.model_copy(
                    update={"value": old_date}
                )
            }
        ),
    )
    result = packet((original, note))
    assert any(
        x["code"] == "fiscal_credit_tax_treatment_required"
        for x in result.manifest["issues"]
    )


def test_credit_note_for_small_consumption_sale_keeps_anonymous_identity():
    original = practice_records()[-1]
    note = changed(
        original,
        ncf="B0400000098",
        amount="118.00",
        tax="18.00",
        billed_amount="100.00",
        modified_ncf="B0200000001",
        **{name: None for name in PAYMENT_BUCKETS},
    )
    day = date(2026, 9, 20)
    note = replace(
        note,
        activity_id="consumption-credit",
        occurred_on=day,
        facts=note.facts.model_copy(
            update={
                "occurred_on": note.facts.occurred_on.model_copy(update={"value": day})
            }
        ),
    )
    result = packet((original, note))
    assert result.manifest["issues"] == []
    rows = result.files["dgii/DGII_F_607_199990013_202609.TXT"].decode().splitlines()
    assert len(rows) == 2 and rows[1].split("|")[:2] == ["", ""]
    assert result.manifest["totals_dop"]["itbis_facturado"] == "72.00"


def test_sales_credit_reference_cannot_change_known_buyer():
    original = practice_records()[4]
    buyer = original.facts.fiscal.rnc.model_copy(update={"value": "199990048"})
    note = changed(original, ncf="B0400000097", modified_ncf="B0100000001")
    note = replace(
        note,
        activity_id="changed-buyer-note",
        facts=note.facts.model_copy(
            update={"fiscal": note.facts.fiscal.model_copy(update={"rnc": buyer})}
        ),
    )
    result = packet((original, note))
    assert any(
        x["code"] == "fiscal_credit_reference_conflict" for x in result.manifest["issues"]
    )


def test_flagged_b02_purchase_stays_excluded_without_erasing_book_gross():
    result = packet((practice_records()[2],))
    assert result.manifest["forms"]["606"]["record_count"] == 0
    assert (
        result.manifest["reconciliation"][0]["reason"]
        == "b02_purchase_not_reportable_in_606"
    )
    assert result.manifest["totals_dop"]["purchase_invoice_gross"] == "236.00"
    assert result.manifest["totals_dop"]["itbis_por_adelantar"] == "0.00"


@pytest.mark.parametrize(
    "number", ["B1300000001", "B1700000001", "E430000000001", "E470000000001"]
)
@pytest.mark.parametrize("filer", ["199990013", "00100000001"])
@pytest.mark.parametrize("matching", [True, False])
def test_self_billed_purchase_identity_must_match_filer_without_rewriting_facts(
    number, filer, matching
):
    record = changed(
        practice_records()[0],
        ncf=number,
        id_type="2" if len(filer) == 11 and matching else "1",
    )
    supplier = filer if matching else "199990021"
    fiscal = record.facts.fiscal.model_copy(
        update={"rnc": record.facts.fiscal.rnc.model_copy(update={"value": supplier})}
    )
    record = replace(record, facts=record.facts.model_copy(update={"fiscal": fiscal}))
    result = packet((record,), rnc=filer)
    assert (result.manifest["forms"]["606"]["status"] == "prepared_candidate") is matching
    assert record.facts.fiscal.rnc.value == supplier
    assert (
        any(
            x["code"] == "fiscal_supplier_must_match_filer"
            for x in result.manifest["issues"]
        )
        is not matching
    )
    if matching:
        assert (
            result.files[f"dgii/DGII_F_606_{filer}_202609.TXT"]
            .decode()
            .splitlines()[1]
            .split("|")[0]
            == filer
        )
    else:
        assert not any(name.endswith(".TXT") for name in result.files)


@pytest.mark.parametrize("note", ["B0300000001", "E330000000001"])
@pytest.mark.parametrize(
    "reference,valid",
    [
        ("E030000000001", False),
        ("B3300000001", False),
        ("B0100000099", True),
        ("E310000000099", True),
    ],
)
def test_debit_note_modified_ncf_uses_the_same_valid_series_type_pairs(
    note, reference, valid
):
    record = changed(practice_records()[0], ncf=note, modified_ncf=reference)
    result = packet((record,))
    assert (result.manifest["forms"]["606"]["status"] == "prepared_candidate") is valid
    assert (
        any(
            x["code"] == "fiscal_ncf_unsupported" and x["field"] == "modified_ncf"
            for x in result.manifest["issues"]
        )
        is not valid
    )
    assert record.declaration.modified_ncf == reference
