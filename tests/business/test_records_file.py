"""The Registros file: what the table shows, or the 606/607 lines, in one file."""

from __future__ import annotations

import csv
import io
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID
from xml.etree import ElementTree
from zipfile import ZipFile

import pytest
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.facts import Unknown
from argus.domain.business.dgii_export import fiscal_manifest, line_verdicts
from argus.domain.business.reporting import ReportIdentity
from argus.domain.business.reporting_file import (
    HEADERS,
    RecordsExport,
    build_file,
    summarize_export,
)
from argus.domain.business.reporting_projection import with_export_verdicts
from argus.domain.business.reporting_query import (
    ReportRecord,
    ReportRequestV2,
    run_query,
)
from argus.domain.business.reporting_store import ExportSource
from faker import Faker
from pydantic import ValidationError

from scripts import generate_records_file_words
from tests.dgii.test_packet import practice_records

NOW = datetime(2026, 10, 18, 15, tzinfo=timezone.utc)
SEPTEMBER = {"kind": "custom", "from_date": "2026-09-01", "to_date": "2026-09-30"}
FILER = "199990013"
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


@pytest.fixture
def fake() -> Faker:
    faker = Faker("es")
    faker.seed_instance(1823)
    return faker


def report(**filters) -> ReportRequestV2:
    return ReportRequestV2(
        filters={"period": SEPTEMBER, "record_families": ["purchase"], **filters}
    )


def table(request: ReportRequestV2, columns=("counterparty",), **choice) -> RecordsExport:
    return RecordsExport(report=request, mode="table", columns=columns, **choice)


def row(fake: Faker, **changes) -> ReportRecord:
    identifier = fake.uuid4()
    values = dict(
        row_id=f"activity:{identifier}",
        linked_activity_ids=(identifier,),
        revision=1,
        report_date=date(2026, 9, fake.random_int(1, 28)),
        date_basis="document_issue",
        family="purchase",
        currency="DOP",
        gross_amount=f"{fake.random_int(100, 99999)}.{fake.random_int(0, 99):02}",
        money_kind="expense",
        counterparty=fake.company(),
        counterparty_key=fake.numerify("1########"),
    )
    return ReportRecord(**(values | changes))


def source(*records: ReportRecord, approved=None) -> ExportSource:
    return ExportSource(tuple(records), approved or {}, NOW)


def books() -> ExportSource:
    """The practice month plus a pesos purchase missing its NCF and two in
    dollars and euros, projected the way the store projects them."""

    practice = practice_records()
    purchase = practice[0]

    def copy(number: int, ncf, **changes):
        facts = purchase.facts.model_copy(
            update={"fiscal": purchase.facts.fiscal.model_copy(update={"ncf": ncf})}
        )
        return replace(
            purchase, activity_id=str(UUID(int=number)), facts=facts, **changes
        )

    def ncf(value: str):
        return purchase.facts.fiscal.ncf.model_copy(update={"value": value})

    records = (
        *practice,
        copy(170, Unknown()),
        copy(171, ncf("B0100000171"), currency="USD"),
        copy(172, ncf("B0100000172"), currency="EUR"),
    )
    verdicts = line_verdicts(records, rnc=FILER, captured_on=NOW.date())
    rows = tuple(
        ReportRecord(
            row_id=f"activity:{record.activity_id}",
            linked_activity_ids=(record.activity_id,),
            revision=1,
            report_date=record.occurred_on,
            date_basis="document_issue",
            family="sale" if record.kind == "income" else "purchase",
            stage="ready_for_export",
            currency=record.currency,
            gross_amount=record.amount,
            money_kind=record.kind,
            counterparty=f"Proveedor {index}",
        )
        for index, record in enumerate(records)
    )
    return ExportSource(
        with_export_verdicts(rows, verdicts, frozenset()),
        {record.activity_id: record for record in records},
        NOW,
    )


def xlsx(content: bytes) -> list[list[tuple[str, object, str | None]]]:
    """Each cell as (kind, value, number format): `s` for text, `n` for a number."""

    with ZipFile(io.BytesIO(content)) as book:
        strings = [
            "".join(node.itertext())
            for node in ElementTree.fromstring(book.read("xl/sharedStrings.xml")).findall(
                "m:si", NS
            )
        ]
        styles = ElementTree.fromstring(book.read("xl/styles.xml"))
        formats = {
            node.attrib["numFmtId"]: node.attrib["formatCode"]
            for node in styles.findall("m:numFmts/m:numFmt", NS)
        }
        xfs = styles.findall("m:cellXfs/m:xf", NS)
        sheet = ElementTree.fromstring(book.read("xl/worksheets/sheet1.xml"))
        assert book.namelist().count("xl/worksheets/sheet2.xml") == 0
    assert not sheet.findall(".//m:f", NS)
    assert sheet.find("m:sheetViews/m:sheetView/m:pane", NS).attrib["ySplit"] == "1"
    result = []
    for line in sheet.findall("m:sheetData/m:row", NS):
        cells = []
        for cell in line.findall("m:c", NS):
            style = xfs[int(cell.attrib.get("s", 0))]
            code = formats.get(style.attrib.get("numFmtId"))
            quoted = style.attrib.get("quotePrefix") == "1"
            value = cell.find("m:v", NS).text
            if cell.attrib.get("t") == "s":
                cells.append(("quoted" if quoted else "s", strings[int(value)], code))
            else:
                cells.append(("n", Decimal(value), code))
        result.append(cells)
    return result


def test_the_file_words_are_the_locale_words():
    assert (
        generate_records_file_words.TARGET.read_text(encoding="utf-8")
        == generate_records_file_words.build()
    )


def test_lo_que_ves_follows_every_filter_and_the_chosen_columns(fake):
    wanted = row(fake, counterparty="Ferretería Ozama", note="cemento")
    other_currency = row(fake, counterparty="Ferretería Ozama", currency="USD")
    rows = (
        wanted,
        other_currency,
        row(fake, counterparty="Colmado Duarte"),
        row(fake, counterparty="Ferretería Ozama", family="sale"),
        row(fake, counterparty="Ferretería Ozama", report_date=date(2026, 10, 2)),
    )
    request = report(q="ozama", currencies=["DOP"])
    built = build_file(
        source(*rows),
        table(request, ("note", "date", "gross_amount"), currencies="current"),
    )
    cells = xlsx(built.content)
    assert [value for _, value, _ in cells[0]] == [
        "Contraparte",
        "Fecha",
        "Monto",
        "Notas",
    ]
    assert [[value for _, value, _ in line] for line in cells[1:]] == [
        [
            "Ferretería Ozama",
            Decimal((wanted.report_date - date(1899, 12, 30)).days),
            Decimal(wanted.gross_amount),
            "cemento",
        ]
    ]
    every = build_file(
        source(*rows), table(request, ("gross_amount",), currencies="all", format="csv")
    )
    lines = list(csv.reader(io.StringIO(every.content.decode("utf-8-sig"))))
    assert lines[0] == ["Contraparte", "Monto", "Moneda"]
    assert sorted(line[2] for line in lines[1:]) == ["DOP", "USD"]


def test_with_all_currencies_moneda_is_in_even_when_not_asked(fake):
    built = build_file(
        source(row(fake), row(fake, currency="EUR")),
        table(report(currencies=["DOP"]), ("note",), currencies="all", format="csv"),
    )
    header = next(csv.reader(io.StringIO(built.content.decode("utf-8-sig"))))
    assert header == ["Contraparte", "Moneda", "Notas"]
    only = build_file(
        source(row(fake), row(fake, currency="EUR")),
        table(report(currencies=["DOP"]), ("note",), currencies="current", format="csv"),
    )
    assert next(csv.reader(io.StringIO(only.content.decode("utf-8-sig")))) == [
        "Contraparte",
        "Notas",
    ]


def test_columns_follow_the_table_order_and_offer_only_the_tab_columns(fake):
    presentation = {
        "order": [
            "counterparty",
            "note",
            "date",
            "gross_amount",
            "fiscal_number",
            "itbis_amount",
            "stage",
            "attachment",
            "expense_type",
            "payment_form",
            "funding",
        ],
        "hidden": [
            "fiscal_number",
            "itbis_amount",
            "expense_type",
            "payment_form",
            "funding",
        ],
    }
    request = ReportRequestV2(
        filters={"period": SEPTEMBER, "record_families": ["sale"], "currencies": ["DOP"]},
        presentation=presentation,
    )
    preview = summarize_export(source(row(fake, family="sale")), request)
    assert [(column.key, column.shown) for column in preview.table.columns] == [
        ("counterparty", True),
        ("note", True),
        ("date", True),
        ("gross_amount", True),
        ("fiscal_number", False),
        ("itbis_amount", False),
        ("stage", True),
        ("attachment", True),
        ("funding", False),
    ]
    built = build_file(
        source(row(fake, family="sale")),
        table(request, ("gross_amount", "note"), currencies="current", format="csv"),
    )
    assert next(csv.reader(io.StringIO(built.content.decode("utf-8-sig")))) == [
        "Contraparte",
        "Notas",
        "Monto",
    ]
    with pytest.raises(ActionError) as refused:
        build_file(source(), table(request, ("expense_type",), currencies="current"))
    assert refused.value.result.code == "business_export_column_unavailable"


def test_values_are_words_amounts_are_numbers_and_dates_are_dates(fake):
    from argus.domain.business.reporting_query import DgiiChoice, Purchase606

    record = row(
        fake,
        stage="needs_fiscal_data",
        export_missing="ncf_missing",
        itbis_amount="18.00",
        has_document=True,
        funding_label="Banco Popular",
        dgii_606=Purchase606(
            expense_type=DgiiChoice(
                code="02", label="Gastos por trabajos, suministros y servicios"
            ),
            payment_form=None,
        ),
    )
    columns = (
        "date",
        "gross_amount",
        "itbis_amount",
        "stage",
        "attachment",
        "expense_type",
        "payment_form",
        "funding",
    )
    cells = xlsx(
        build_file(
            source(record),
            table(report(currencies=["DOP"]), columns, currencies="current"),
        ).content
    )
    assert [value for _, value, _ in cells[0]] == [
        HEADERS[key] for key in ("counterparty", *columns)
    ]
    kinds = [(kind, code) for kind, _, code in cells[1]]
    assert kinds[1:4] == [("n", "dd/mm/yyyy"), ("n", "#,##0.00"), ("n", "#,##0.00")]
    assert [value for _, value, _ in cells[1][4:]] == [
        "Falta el NCF",
        "Sí",
        "Gastos por trabajos, suministros y servicios",
        "Falta",
        "Banco Popular",
    ]
    csv_line = list(
        csv.reader(
            io.StringIO(
                build_file(
                    source(record),
                    table(
                        report(currencies=["DOP"]),
                        columns,
                        currencies="current",
                        format="csv",
                    ),
                ).content.decode("utf-8-sig")
            )
        )
    )[1]
    assert csv_line[1:4] == [
        record.report_date.strftime("%d/%m/%Y"),
        record.gross_amount,
        "18.00",
    ]


def test_formula_like_cells_are_escaped_in_both_formats(fake):
    record = row(
        fake, counterparty='=HYPERLINK("x")', note="+1 llamada", fiscal_number="@B01"
    )
    request = report(currencies=["DOP"])
    cells = xlsx(
        build_file(
            source(record),
            table(request, ("note", "fiscal_number"), currencies="current"),
        ).content
    )
    assert [cell[:2] for cell in cells[1]] == [
        ("quoted", '=HYPERLINK("x")'),
        ("quoted", "@B01"),
        ("quoted", "+1 llamada"),
    ]
    lines = list(
        csv.reader(
            io.StringIO(
                build_file(
                    source(record),
                    table(request, ("note",), currencies="current", format="csv"),
                ).content.decode("utf-8-sig")
            )
        )
    )
    assert lines[1] == ['\'=HYPERLINK("x")', "'+1 llamada"]


def test_csv_has_a_bom_and_keeps_accents(fake):
    built = build_file(
        source(row(fake, counterparty="Panadería Ñoño")),
        table(report(currencies=["DOP"]), currencies="current", format="csv"),
    )
    assert built.content.startswith(b"\xef\xbb\xbf")
    assert built.content.decode("utf-8-sig").splitlines() == [
        "Contraparte",
        "Panadería Ñoño",
    ]
    assert built.media_type == "text/csv; charset=utf-8"


@pytest.mark.parametrize(
    ("period", "family", "mode", "fmt", "name"),
    [
        (
            {"kind": "custom", "from_date": "2026-11-01", "to_date": "2026-11-30"},
            "purchase",
            "table",
            "xlsx",
            "Compras_noviembre-2026.xlsx",
        ),
        (
            {"kind": "custom", "from_date": "2026-11-01", "to_date": "2026-11-30"},
            "sale",
            "table",
            "csv",
            "Ventas_noviembre-2026.csv",
        ),
        (
            {"kind": "custom", "from_date": "2026-11-01", "to_date": "2026-11-30"},
            "purchase",
            "dgii",
            "xlsx",
            "606_noviembre-2026.xlsx",
        ),
        (
            {"kind": "custom", "from_date": "2026-01-01", "to_date": "2026-12-31"},
            "sale",
            "dgii",
            "csv",
            "607_2026.csv",
        ),
        (
            {"kind": "custom", "from_date": "2026-11-03", "to_date": "2026-11-09"},
            "purchase",
            "table",
            "xlsx",
            "Compras_2026-11-03_2026-11-09.xlsx",
        ),
        ({"kind": "all"}, "purchase", "table", "xlsx", "Compras.xlsx"),
    ],
)
def test_file_names_are_readable_and_plain(period, family, mode, fmt, name):
    request = ReportRequestV2(
        filters={"period": period, "record_families": [family], "currencies": ["DOP"]}
    )
    choice = (
        RecordsExport(report=request, mode="dgii", format=fmt)
        if mode == "dgii"
        else table(request, currencies="current", format=fmt)
    )
    assert build_file(source(), choice).filename == name


def test_dgii_follows_only_tab_and_period_and_holds_only_complete_pesos_lines():
    month = books()
    request = report(q="nothing matches this", currencies=["USD"], has_document=True)
    preview = summarize_export(month, request)
    peso_card = run_query(
        ReportIdentity("b", "a", "o", "g", ""),
        month.records,
        report(currencies=["DOP"]),
        NOW,
    ).overview.needs_fiscal_data
    foreign_cards = sum(
        run_query(
            ReportIdentity("b", "a", "o", "g", ""),
            month.records,
            report(currencies=[code]),
            NOW,
        ).overview.needs_fiscal_data
        for code in ("USD", "EUR")
    )
    assert preview.dgii.form == "606"
    assert preview.dgii.pending_fiscal_count == peso_card
    assert preview.dgii.pending_rate_count == foreign_cards == 2
    assert preview.dgii.pending_rate_currencies == ("EUR", "USD")
    manifest, lines = fiscal_manifest(
        tuple(month.approved.values()),
        rnc=FILER,
        business_name="",
        start=date(2026, 9, 1),
        end=date(2026, 9, 30),
        captured_on=NOW.date(),
    )
    assert preview.dgii.record_count == len(lines["606"]) == 3
    built = build_file(month, RecordsExport(report=request, mode="dgii", format="csv"))
    written = list(csv.reader(io.StringIO(built.content.decode("utf-8-sig"))))
    assert written[0][:3] == [
        "RNC o Cédula",
        "Tipo Id",
        "Tipo Bienes y Servicios Comprados",
    ]
    assert sorted(map(tuple, written[1:])) == sorted(lines["606"])
    sales = summarize_export(
        month,
        report().model_copy(
            update={
                "filters": report().filters.model_copy(
                    update={"record_families": ("sale",)}
                )
            }
        ),
    )
    assert (sales.dgii.form, sales.dgii.record_count) == ("607", len(lines["607"]))


def test_dgii_excel_amounts_are_numbers_and_codes_stay_text():
    month = books()
    cells = xlsx(build_file(month, RecordsExport(report=report(), mode="dgii")).content)
    header = [value for _, value, _ in cells[0]]
    line = dict(zip(header, cells[1], strict=False))
    assert line["Tipo Bienes y Servicios Comprados"][0] == "s"
    assert len(line["Tipo Bienes y Servicios Comprados"][1]) == 2
    assert line["Fecha Comprobante"][0] == "s"
    assert line["Total Monto Facturado"][:1] == ("n",)
    assert line["Total Monto Facturado"][2] == "#,##0.00"


def test_zero_records_is_a_file_with_only_headers(fake):
    built = build_file(
        source(), table(report(currencies=["DOP"]), currencies="current", format="csv")
    )
    assert built.content.decode("utf-8-sig").splitlines() == ["Contraparte"]


def test_an_amount_range_ties_the_export_to_the_screen_currency(fake):
    request = report(currencies=["DOP"], amount_min="1.00")
    preview = summarize_export(source(row(fake)), request)
    assert preview.table.all is None
    assert preview.table.current.record_count == 1
    with pytest.raises(ActionError) as refused:
        build_file(source(row(fake)), table(request, currencies="all"))
    assert refused.value.result.code == "business_export_currency_required"


def test_the_preview_counts_what_the_table_file_would_hold(fake):
    rows = (row(fake), row(fake), row(fake, currency="USD"), row(fake, currency="EUR"))
    preview = summarize_export(source(*rows), report(currencies=["DOP"]))
    assert preview.table.current.record_count == 2
    assert preview.table.current.currencies == ("DOP",)
    assert (preview.table.all.record_count, preview.table.all.currencies) == (
        4,
        ("DOP", "EUR", "USD"),
    )


@pytest.mark.parametrize(
    "choice",
    [
        {"mode": "dgii", "columns": ["note"]},
        {"mode": "dgii", "currencies": "current"},
        {"mode": "table", "columns": []},
        {"mode": "table", "columns": ["note", "note"]},
    ],
)
def test_choices_that_do_not_fit_the_mode_are_refused(choice):
    with pytest.raises(ValidationError):
        RecordsExport(report=report(), **choice)


def test_dgii_needs_one_tab():
    request = ReportRequestV2(filters={"period": SEPTEMBER})
    with pytest.raises(ActionError) as refused:
        summarize_export(source(), request)
    assert refused.value.result.code == "business_export_family_required"
