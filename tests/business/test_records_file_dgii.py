"""606 spreadsheet formatting and RNC warnings in exported records."""

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
from faker import Faker

from tests.business.test_records_file import books, report, row, source, xlsx
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
def test_607_spreadsheet_columns_and_dates_stay_unchanged(format):
    from argus.domain.business.dgii_columns import COLUMNS
    from argus.domain.business.dgii_export import line_values

    month = books()
    request = report(record_families=["sale"])
    built = build_file(month, RecordsExport(report=request, mode="dgii", format=format))
    if format == "xlsx":
        header, *rows = xlsx(built.content)
        headers = [value for _, value, _ in header]
        dates = [line[5] for line in rows]
        assert all(kind == "s" and len(value) == 8 for kind, value, _ in dates)
    else:
        headers, *rows = csv.reader(io.StringIO(built.content.decode("utf-8-sig")))
        dates = [line[5] for line in rows]
        assert dates == sorted(
            line_values(month.approved[row.linked_activity_ids[0]])[5]
            for row in month.records
            if row.family == "sale" and row.fiscal_data == "complete"
        )
    assert headers == [label for _, label in COLUMNS["607"]]
    preview = summarize_export(month, request).dgii
    assert preview.rnc_warning_count == preview.rnc_supplier_count == 0
    assert preview.rnc_suppliers == ()


def test_rnc_snapshot_copies_entries_and_preserves_misses():
    from argus.domain.business.rnc_registry import RncRegistrySnapshot

    entries = {"101001577": None}
    snapshot = RncRegistrySnapshot(entries)
    entries.clear()
    assert dict(snapshot.entries) == {"101001577": None}
    with pytest.raises(TypeError):
        snapshot.entries["101001577"] = None
