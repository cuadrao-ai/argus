"""606 spreadsheet formatting and RNC warnings in exported records."""

import csv
import hashlib
import io
from dataclasses import replace
from datetime import date

import pytest
from argus.domain.business.authority import ActionError
from argus.domain.business.reporting_file import (
    RecordsExport,
    build_file,
    summarize_export,
)
from argus.domain.business.reporting_query import ReportRequestV2
from argus.domain.business.reporting_store import ExportSource
from faker import Faker

from tests.business.test_records_file import (
    SEPTEMBER,
    books,
    report,
    row,
    source,
    xlsx,
)
from tests.dgii.test_packet import practice_records


@pytest.mark.parametrize("format", ("xlsx", "csv"))
def test_606_spreadsheet_splits_dates_as_text_and_unpaid_dates_are_blank(faker, format):
    purchase = practice_records()[0]
    rows, approved = [], {}
    for index, paid_on in enumerate((date(2026, 9, 4), None), 1):
        projected = row(faker, fiscal_data="complete")
        rows.append(projected)
        approved[projected.linked_activity_ids[0]] = replace(
            purchase,
            activity_id=projected.linked_activity_ids[0],
            occurred_on=date(2026, 9, index + 3),
            declaration=purchase.declaration.model_copy(update={"paid_on": paid_on}),
        )
    built = build_file(
        source(*rows, approved=approved),
        RecordsExport(report=report(), mode="dgii", format=format),
    )
    if format == "xlsx":
        header, *lines = xlsx(built.content)
        headers = [value for _, value, _ in header]
        assert lines[0][5:9] == [("s", "202609", None), ("s", "04", None)] * 2
        assert lines[1][7:9] == [("blank", None, None)] * 2
    else:
        headers, *lines = csv.reader(io.StringIO(built.content.decode("utf-8-sig")))
        assert lines[0][5:9] == ["202609", "04"] * 2
        assert lines[1][7:9] == ["", ""]
    assert headers == [
        "RNC o Cédula",
        "Tipo Id",
        "Tipo Bienes y Servicios Comprados",
        "NCF",
        "NCF ó Documento Modificado",
        "Fecha Comprobante (AAAAMM)",
        "Fecha Comprobante (DD)",
        "Fecha Pago (AAAAMM)",
        "Fecha Pago (DD)",
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
    ]


def warning_books(faker: Faker) -> ExportSource:
    from argus.domain.business.rnc_registry import RncRecord, RncRegistrySnapshot

    month = books()
    purchase = practice_records()[0]
    rows, approved = [], {}
    identities = (
        "1-01-00157-7",
        "101001577",
        "101010632",
        "101000015",
        "101001577",
        "101001577",
    )
    for index, identity in enumerate(identities):
        projected = row(
            faker,
            counterparty=f"Proveedor {index}",
            fiscal_data="missing" if index == 4 else None if index == 5 else "complete",
        )
        rows.append(projected)
        fiscal = purchase.facts.fiscal.model_copy(
            update={
                "rnc": purchase.facts.fiscal.rnc.model_copy(update={"value": identity})
            }
        )
        approved[projected.linked_activity_ids[0]] = replace(
            purchase,
            activity_id=projected.linked_activity_ids[0],
            facts=purchase.facts.model_copy(update={"fiscal": fiscal}),
        )
    registry = RncRegistrySnapshot(
        {
            "101001577": RncRecord(
                "101001577", "Suplidor registrado", None, "SUSPENDIDO", None, "no_activo"
            ),
            "101010632": None,
            "101000015": RncRecord(
                "101000015", "Activo", None, "ACTIVO", None, "verificado"
            ),
        }
    )
    selected = ExportSource(tuple(rows), approved, month.observed_at, registry)
    return selected


def test_rnc_notice_counts_exported_rows_and_groups_normalized_supplier_identity(faker):
    selected = warning_books(faker)
    preview = summarize_export(selected, report()).dgii
    assert (
        preview.record_count,
        preview.rnc_warning_count,
        preview.rnc_supplier_count,
    ) == (4, 3, 2)
    assert [supplier.model_dump() for supplier in preview.rnc_suppliers] == [
        {
            "name": "Suplidor registrado",
            "rnc": "101001577",
            "estado": "SUSPENDIDO",
            "status": "rnc_inactive",
            "record_count": 2,
        },
        {
            "name": "Proveedor 2",
            "rnc": "101010632",
            "estado": "sin verificar",
            "status": "rnc_unverified",
            "record_count": 1,
        },
    ]
    assert (
        build_file(selected, RecordsExport(report=report(), mode="dgii")).row_count == 4
    )
    active = replace(selected, records=(selected.records[3],))
    assert summarize_export(active, report()).dgii.rnc_warning_count == 0
    assert summarize_export(active, report()).dgii.rnc_suppliers == ()


@pytest.mark.parametrize("format", ("csv", "xlsx"))
def test_sales_dgii_file_is_unavailable(format):
    request = report(record_families=["sale"])
    with pytest.raises(ActionError) as refused:
        build_file(books(), RecordsExport(report=request, mode="dgii", format=format))
    assert refused.value.result.code == "business_export_dgii_sales_unavailable"


def test_rnc_snapshot_copies_entries_and_preserves_misses():
    from argus.domain.business.rnc_registry import RncRegistrySnapshot

    entries = {"101001577": None}
    snapshot = RncRegistrySnapshot(entries)
    entries.clear()
    assert dict(snapshot.entries) == {"101001577": None}
    with pytest.raises(TypeError):
        snapshot.entries["101001577"] = None


@pytest.mark.parametrize(
    ("form", "name", "code"),
    [
        *(("606", "income_withholding_type", f"{n:02}") for n in range(1, 10)),
        *(("606", "id_type", str(n)) for n in range(1, 3)),
    ],
)
def test_dgii_file_writes_the_withholding_income_and_id_codes_without_names(
    form, name, code
):
    from argus.domain.business.dgii_columns import COLUMNS

    month = books()
    approved = {
        key: replace(
            record, declaration=record.declaration.model_copy(update={name: code})
        )
        if record.declaration.form == form
        else record
        for key, record in month.approved.items()
    }
    request = report(record_families=["purchase"])
    built = build_file(
        replace(month, approved=approved),
        RecordsExport(report=request, mode="dgii", format="csv"),
    )
    headers, *lines = csv.reader(io.StringIO(built.content.decode("utf-8-sig")))
    column = headers.index(dict(COLUMNS[form])[name])
    assert lines
    assert {line[column] for line in lines} == {code}


#: The 606 files of the practice month, hashed at 5877fc650 before the name
#: column took Emisor and Cliente. A screen word must never reach these files.
DGII_FILES = {
    ("purchase", "csv"): (
        3,
        "06fd86335dbbcbdbd5da242f64e2e0f0c85b2f0f30323ac66a3d86694f4b7b67",
    ),
    ("purchase", "xlsx"): (
        3,
        "522622fd10960d89dd9570c92dd89e3596816572a58e56ed7bd05e80db76f9b0",
    ),
}


@pytest.mark.parametrize("locale", ("es-419", "en"))
@pytest.mark.parametrize(("family", "format"), sorted(DGII_FILES))
def test_the_dgii_files_are_byte_identical_to_before_the_rename(family, format, locale):
    request = ReportRequestV2(filters={"period": SEPTEMBER, "record_families": [family]})
    built = build_file(
        books(), RecordsExport(report=request, mode="dgii", format=format), locale=locale
    )
    digest = hashlib.sha256(built.content).hexdigest()
    assert (built.row_count, digest) == DGII_FILES[family, format]
