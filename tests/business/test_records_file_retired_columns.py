"""Compatibility for saved Registros table exports."""

import csv
import io
import json

import pytest
from argus.domain.business.reporting_file import RecordsExport, build_file
from pydantic import ValidationError

from tests.business.test_records_file import report, row, source


def test_saved_table_export_ignores_retired_columns_and_keeps_the_state(faker):
    record = row(faker, ready=False, funding_label="Cuenta de operaciones")
    saved = {
        "report": report(currencies=["DOP"]).model_dump(mode="json"),
        "mode": "table",
        "columns": ["date", "missing", "stage", "funding"],
        "currencies": "current",
        "format": "csv",
    }
    built = build_file(
        source(record), RecordsExport.model_validate_json(json.dumps(saved))
    )
    header, values = csv.reader(io.StringIO(built.content.decode("utf-8-sig")))
    assert header == ["Emisor", "Fecha", "Estado"]
    assert values == [
        record.counterparty,
        record.report_date.strftime("%d/%m/%Y"),
        "Faltan datos",
    ]


@pytest.mark.parametrize(
    "mode,columns",
    [
        ("table", ("missing", "funding")),
        ("table", ("stage", "missing", "stage")),
        ("table", ("date", "funding", "unknown")),
        ("dgii", ("missing", "funding")),
    ],
)
def test_retired_export_columns_do_not_relax_validation(mode, columns):
    with pytest.raises(ValidationError):
        RecordsExport(report=report(), mode=mode, columns=columns)
