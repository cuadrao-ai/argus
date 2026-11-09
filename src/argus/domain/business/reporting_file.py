"""Registros export: one Excel or CSV file of the table, or of the 606/607 lines.

The counts the export modal shows and the rows the file holds come from the
same selection over the same projection the table and the cards read.
"""

from __future__ import annotations

import csv
import io
import json
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Literal

import xlsxwriter
from babel.dates import format_date
from pydantic import model_validator

from argus.domain.business.authority import ActionContext, ActionError, BusinessAuthority
from argus.domain.business.dgii_columns import COLUMNS
from argus.domain.business.dgii_export import line_values
from argus.domain.business.dgii_validation import declarable
from argus.domain.business.export import spreadsheet_cell
from argus.domain.business.reporting_preferences import (
    PURCHASE_ONLY_COLUMNS,
    Contract,
    Presentation,
    ReportFilters,
    ReportInput,
    ReportRequest,
    ReportRequestV2,
    TableColumn,
)
from argus.domain.business.reporting_query import (
    ReportRecord,
    matching_records,
    resolve_period,
)
from argus.domain.business.reporting_store import (
    ExportSource,
    read_export_source,
    require_export,
)

_WORDS = json.loads(
    Path(__file__).with_name("records_file_words.generated.json").read_text("utf-8")
)
FileColumn = TableColumn | Literal["currency"]
_HEADER_PATHS: dict[FileColumn, str] = {
    "counterparty": "business.transactions.columns.contraparte",
    "fiscal_number": "business.transactions.columns.ncf",
    "date": "business.transactions.columns.fecha",
    "gross_amount": "business.transactions.columns.monto",
    "currency": "business.transactions.columns.moneda",
    "itbis_amount": "business.transactions.columns.itbis",
    "stage": "business.transactions.layout.column_state",
    "note": "business.transactions.columns.notas",
    "attachment": "business.transactions.layout.column_attachment",
    "expense_type": "business.dossier.placeholder.expense_type",
    "payment_form": "business.dossier.placeholder.payment_form",
    "funding": "business.transactions.columns.cuenta",
}
#: The table header with no currency, as Registros renders it.
HEADERS: dict[FileColumn, str] = {
    key: _WORDS[path].replace("{{currency}}", "").strip()
    for key, path in _HEADER_PATHS.items()
}
_STAGE_PATHS = {
    "needs_review": "business.transactions.layout.workflow.review",
    "ready_for_export": "business.transactions.layout.workflow.ready",
    "exported": "business.transactions.layout.workflow.exported",
}
_MISSING = _WORDS["business.transactions.layout.workflow.missing"]
_DGII_TEXT = frozenset(
    {
        "rnc",
        "id_type",
        "category",
        "ncf",
        "modified_ncf",
        "income_type",
        "income_withholding_type",
        "payment_method",
    }
)
_DGII_DATES = frozenset({"occurred_on", "paid_on", "withheld_on"})
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CSV = "text/csv; charset=utf-8"


class ExportPreviewRequest(Contract):
    report: ReportInput


class RecordsExport(Contract):
    report: ReportInput
    mode: Literal["table", "dgii"]
    #: Table mode: the table columns to include. Counterparty is always in.
    columns: tuple[TableColumn, ...] = ()
    currencies: Literal["all", "current"] = "all"
    format: Literal["xlsx", "csv"] = "xlsx"

    @model_validator(mode="after")
    def mode_choices(self) -> RecordsExport:
        if self.mode == "table":
            if not self.columns or len(set(self.columns)) != len(self.columns):
                raise ValueError("table export columns must be nonempty and unique")
        elif self.columns or self.currencies != "all":
            raise ValueError("the DGII format defines its own columns and currency")
        return self


class ExportColumn(Contract):
    key: TableColumn
    shown: bool


class CurrencySelection(Contract):
    record_count: int
    currencies: tuple[str, ...]


class TableExport(Contract):
    columns: tuple[ExportColumn, ...]
    current: CurrencySelection
    #: None while an amount range ties the selection to the screen's currency.
    all: CurrencySelection | None


class DgiiExport(Contract):
    form: Literal["606", "607"]
    record_count: int
    #: Pesos records the 606/607 holds for missing fiscal data, the card's count.
    pending_fiscal_count: int
    #: Foreign-currency records the 606/607 holds until they have a rate.
    pending_rate_count: int
    pending_rate_currencies: tuple[str, ...]


class ExportPreview(Contract):
    table: TableExport
    dgii: DgiiExport


@dataclass(frozen=True)
class RecordsFile:
    filename: str
    media_type: str
    content: bytes


Cell = str | Decimal | date | None


def _family(request: ReportRequest | ReportRequestV2) -> Literal["sale", "purchase"]:
    families = request.filters.record_families
    if len(families) != 1:
        raise ActionError("invalid_input", "business_export_family_required")
    return families[0]


def _presentation(request: ReportRequest | ReportRequestV2) -> Presentation:
    return (
        request.presentation if isinstance(request, ReportRequestV2) else Presentation()
    )


def _available(request: ReportRequest | ReportRequestV2) -> tuple[TableColumn, ...]:
    sale = _family(request) == "sale"
    return tuple(
        key
        for key in _presentation(request).order
        if not (sale and key in PURCHASE_ONLY_COLUMNS)
    )


def _with_currencies(
    request: ReportRequest | ReportRequestV2, choice: Literal["all", "current"]
) -> ReportRequest | ReportRequestV2 | None:
    if choice == "current":
        return request
    if request.filters.amount_min is not None or request.filters.amount_max is not None:
        return None
    return request.model_copy(
        update={"filters": request.filters.model_copy(update={"currencies": ()})}
    )


def _dgii_request(
    request: ReportRequest | ReportRequestV2,
) -> ReportRequest | ReportRequestV2:
    """Only the tab and the period: no forgotten filter makes a partial filing."""

    filters = ReportFilters(
        period=request.filters.period, record_families=request.filters.record_families
    )
    return request.model_copy(update={"filters": filters})


@dataclass(frozen=True)
class _DgiiSelection:
    lines: tuple[ReportRecord, ...]
    pending_fiscal: tuple[ReportRecord, ...]
    pending_rate: tuple[ReportRecord, ...]


def _dgii_selection(
    source: ExportSource, request: ReportRequest | ReportRequestV2
) -> _DgiiSelection:
    rows = matching_records(source.records, _dgii_request(request), source.observed_at)
    return _DgiiSelection(
        lines=tuple(row for row in rows if row.fiscal_data == "complete"),
        pending_fiscal=tuple(
            row
            for row in rows
            if row.fiscal_data == "missing" and row.currency and declarable(row.currency)
        ),
        pending_rate=tuple(
            row
            for row in rows
            if row.fiscal_data is not None
            and row.currency
            and not declarable(row.currency)
        ),
    )


def _selection(rows: Sequence[ReportRecord]) -> CurrencySelection:
    return CurrencySelection(record_count=len(rows), currencies=_currencies(rows))


def _currencies(rows: Sequence[ReportRecord]) -> tuple[str, ...]:
    return tuple(sorted({row.currency for row in rows if row.currency}))


def summarize_export(
    source: ExportSource, request: ReportRequest | ReportRequestV2
) -> ExportPreview:
    def selection(selected: ReportRequest | ReportRequestV2) -> CurrencySelection:
        return _selection(matching_records(source.records, selected, source.observed_at))

    hidden = set(_presentation(request).hidden)
    every = _with_currencies(request, "all")
    dgii = _dgii_selection(source, request)
    return ExportPreview(
        table=TableExport(
            columns=tuple(
                ExportColumn(key=key, shown=key not in hidden)
                for key in _available(request)
            ),
            current=selection(request),
            all=None if every is None else selection(every),
        ),
        dgii=DgiiExport(
            form="607" if _family(request) == "sale" else "606",
            record_count=len(dgii.lines),
            pending_fiscal_count=len(dgii.pending_fiscal),
            pending_rate_count=len(dgii.pending_rate),
            pending_rate_currencies=_currencies(dgii.pending_rate),
        ),
    )


def _stage_word(row: ReportRecord) -> str | None:
    if row.stage == "needs_fiscal_data":
        if row.export_missing_several:
            return _MISSING["several"]
        if row.export_missing in _MISSING and row.export_missing != "several":
            return _MISSING[row.export_missing]
        return _MISSING["detail_missing"]
    return _WORDS[_STAGE_PATHS[row.stage]] if row.stage else None


def _dgii_word(row: ReportRecord, field: Literal["expense_type", "payment_form"]) -> str:
    if row.dgii_606 is None:
        return _WORDS["business.export.form_no_aplica"]
    choice = getattr(row.dgii_606, field)
    return choice.label if choice else _WORDS["business.dossier.standing.missing"]


def _amount(text: str | None) -> Decimal | None:
    return Decimal(text) if text is not None else None


def _table_cell(row: ReportRecord, key: FileColumn) -> Cell:
    if key == "counterparty":
        return row.counterparty
    if key == "fiscal_number":
        return row.fiscal_number
    if key == "date":
        return row.report_date
    if key == "gross_amount":
        return _amount(row.gross_amount) if row.currency else None
    if key == "currency":
        return row.currency
    if key == "itbis_amount":
        return _amount(row.itbis_amount) if row.currency else None
    if key == "stage":
        return _stage_word(row)
    if key == "note":
        return row.note
    if key == "attachment":
        return _WORDS["common.yes" if row.has_document else "common.no"]
    if key in ("expense_type", "payment_form"):
        return _dgii_word(row, key)
    return row.funding_label


def _file_columns(
    request: ReportRequest | ReportRequestV2, chosen: tuple[TableColumn, ...], all_: bool
) -> tuple[FileColumn, ...]:
    available = _available(request)
    if not set(chosen) <= set(available):
        raise ActionError("invalid_input", "business_export_column_unavailable")
    order: list[FileColumn] = []
    for key in available:
        if key == "counterparty" or key in chosen:
            order.append(key)
        if key == "gross_amount" and all_:
            order.append("currency")
    return tuple(order)


def _period_name(
    request: ReportRequest | ReportRequestV2, source: ExportSource
) -> str | None:
    period = resolve_period(request.filters.period, source.records, source.observed_at)
    start, end = period.from_date, period.to_date
    if start is None or end is None:
        return None
    if start.day == 1 and (end + timedelta(days=1)).day == 1:
        if (start.year, start.month) == (end.year, end.month):
            return f"{format_date(start, 'LLLL', locale='es')}-{start.year}"
        if (start.month, end.month, start.year) == (1, 12, end.year):
            return str(start.year)
    return f"{start.isoformat()}_{end.isoformat()}"


def _filename(stem: str, period: str | None, extension: str) -> str:
    name = "_".join(part for part in (stem, period) if part)
    ascii_name = "".join(
        char
        for char in unicodedata.normalize("NFKD", name)
        if not unicodedata.combining(char)
    )
    return f"{ascii_name.replace(' ', '-')}.{extension}"


def _csv(headers: Sequence[str], rows: Sequence[Sequence[Cell]]) -> bytes:
    def text(value: Cell) -> str:
        if value is None:
            return ""
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, date):
            return value.strftime("%d/%m/%Y")
        return spreadsheet_cell(value)

    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(headers)
    writer.writerows([text(value) for value in row] for row in rows)
    return buffer.getvalue().encode("utf-8-sig")


def _xlsx(
    sheet_name: str, headers: Sequence[str], rows: Sequence[Sequence[Cell]]
) -> bytes:
    output = io.BytesIO()
    with xlsxwriter.Workbook(
        output,
        {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False},
    ) as book:
        book.set_properties({"created": datetime(1980, 1, 1, tzinfo=timezone.utc)})
        bold = book.add_format({"bold": True})
        # Two decimals, or the currency's own precision when it has more.
        money = {
            places: book.add_format({"num_format": "#,##0." + "0" * places})
            for places in range(2, 5)
        }
        day = book.add_format({"num_format": "dd/mm/yyyy"})
        quoted = book.add_format({"quote_prefix": True})
        sheet = book.add_worksheet(sheet_name)
        sheet.write_row(0, 0, headers, bold)
        for index, row in enumerate(rows, 1):
            for column, value in enumerate(row):
                if value is None:
                    continue
                if isinstance(value, Decimal):
                    places = min(max(2, -value.as_tuple().exponent), 4)
                    sheet.write_number(index, column, float(value), money[places])
                elif isinstance(value, date):
                    sheet.write_datetime(
                        index, column, datetime(value.year, value.month, value.day), day
                    )
                elif spreadsheet_cell(value) != value:
                    sheet.write_string(index, column, value, quoted)
                else:
                    sheet.write_string(index, column, value)
        sheet.freeze_panes(1, 0)
        sheet.set_column(0, max(len(headers) - 1, 0), 20)
    return output.getvalue()


def _dgii_cell(name: str, value: str) -> Cell:
    if value == "":
        return None
    if name in _DGII_TEXT or name in _DGII_DATES:
        return value
    return Decimal(value)


def build_file(source: ExportSource, choice: RecordsExport) -> RecordsFile:
    request = choice.report
    family = _family(request)
    if choice.mode == "dgii":
        form = "607" if family == "sale" else "606"
        columns = COLUMNS[form]
        headers = [label for _, label in columns]
        rows = [
            [
                _dgii_cell(name, value)
                for (name, _), value in zip(
                    columns,
                    line_values(source.approved[row.linked_activity_ids[0]]),
                    strict=True,
                )
            ]
            for row in _dgii_selection(source, request).lines
        ]
        stem, sheet = form, form
    else:
        selected = _with_currencies(request, choice.currencies)
        if selected is None:
            raise ActionError("invalid_input", "business_export_currency_required")
        keys = _file_columns(request, choice.columns, choice.currencies == "all")
        headers = [HEADERS[key] for key in keys]
        rows = [
            [_table_cell(row, key) for key in keys]
            for row in matching_records(source.records, selected, source.observed_at)
        ]
        stem = sheet = _WORDS[
            "business.transactions.layout.overview."
            + ("sales" if family == "sale" else "purchases")
        ]
    period = _period_name(request, source)
    if choice.format == "csv":
        return RecordsFile(_filename(stem, period, "csv"), CSV, _csv(headers, rows))
    return RecordsFile(_filename(stem, period, "xlsx"), XLSX, _xlsx(sheet, headers, rows))


def preview_export(
    authority: BusinessAuthority,
    context: ActionContext,
    request: ReportRequest | ReportRequestV2,
) -> ExportPreview:
    return summarize_export(read_export_source(authority, context), request)


def export_file(
    authority: BusinessAuthority, context: ActionContext, choice: RecordsExport
) -> RecordsFile:
    built = build_file(read_export_source(authority, context), choice)
    require_export(authority, context)
    return built
