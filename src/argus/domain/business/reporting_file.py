"""Registros export: one Excel or CSV file of the table, or of the 606/607 lines.

The counts the export modal shows and the rows the file holds come from the
same selection over the same projection the table and the cards read.
"""

from __future__ import annotations

import csv
import io
import json
import unicodedata
from calendar import monthrange
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Literal
from urllib.parse import quote
from zoneinfo import ZoneInfo

import xlsxwriter
from pydantic import model_validator

from argus.domain.business.authority import ActionContext, ActionError, BusinessAuthority
from argus.domain.business.dgii_codes import TOOL_LABELS
from argus.domain.business.dgii_columns import COLUMNS
from argus.domain.business.dgii_export import line_values
from argus.domain.business.dgii_line import line_review
from argus.domain.business.dgii_validation import (
    DECLARABLE_CURRENCY,
    declarable,
    fact_value,
)
from argus.domain.business.export import spreadsheet_cell
from argus.domain.business.fiscal_identity import identity_digits
from argus.domain.business.reporting_preferences import (
    PURCHASE_ONLY_COLUMNS,
    Contract,
    Family,
    Presentation,
    ReportFilters,
    ReportInput,
    ReportRequest,
    ReportRequestV2,
    TableColumn,
)
from argus.domain.business.reporting_query import (
    CALENDAR,
    ReportRecord,
    matching_records,
    resolve_period,
)
from argus.domain.business.reporting_store import (
    ExportSource,
    read_export_source,
    require_export,
)
from argus.domain.business.space_name import default_space_name, given_name

_WORDS = json.loads(
    Path(__file__).with_name("records_file_words.generated.json").read_text("utf-8")
)
FileLocale = Literal["en", "es-419"]
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
_STAGE_PATHS = {
    "needs_review": "business.transactions.layout.workflow.review",
    "ready_for_export": "business.transactions.layout.workflow.ready",
    "exported": "business.transactions.layout.workflow.exported",
}
_DGII_TEXT = frozenset(
    {
        "rnc",
        "id_type",
        "ncf",
        "modified_ncf",
        "income_type",
        "income_withholding_type",
    }
)
_REQUIRED_ZERO = frozenset({"itbis_withheld", "income_withheld"})
_DGII_DATES = frozenset({"occurred_on", "paid_on", "withheld_on"})
_SPLIT_DATES = frozenset({"occurred_on", "paid_on"})
_PURCHASE_HEADERS = tuple(
    f"{label} ({part})" if name in _SPLIT_DATES else label
    for name, label in COLUMNS["606"]
    for part in (("AAAAMM", "DD") if name in _SPLIT_DATES else (None,))
)
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


class RncSupplier(Contract):
    name: str
    rnc: str
    estado: str
    status: Literal["rnc_inactive", "rnc_unverified"]
    record_count: int


class DgiiExport(Contract):
    form: Literal["606", "607"]
    #: The one currency the form states; Revisar shows its pending records.
    currency: str = DECLARABLE_CURRENCY
    record_count: int
    #: Every record the 606/607 holds back, for either reason below.
    pending_count: int
    #: Pesos records the 606/607 holds for missing fiscal data, the card's count.
    pending_fiscal_count: int
    #: Foreign-currency records the 606/607 holds until they have a rate.
    pending_rate_count: int
    pending_rate_currencies: tuple[str, ...]
    rnc_warning_count: int
    rnc_supplier_count: int
    rnc_suppliers: tuple[RncSupplier, ...]


class ExportPreview(Contract):
    table: TableExport
    dgii: DgiiExport


@dataclass(frozen=True)
class RecordsFile:
    filename: str
    media_type: str
    content: bytes
    row_count: int = 0


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
    rnc_suppliers: tuple[RncSupplier, ...]


def _dgii_selection(
    source: ExportSource, request: ReportRequest | ReportRequestV2
) -> _DgiiSelection:
    rows = matching_records(source.records, _dgii_request(request), source.observed_at)
    lines = tuple(row for row in rows if row.fiscal_data == "complete")
    suppliers: dict[str, RncSupplier] = {}
    if _family(request) == "purchase":
        for row in lines:
            record = source.approved[row.linked_activity_ids[0]]
            check, warnings = line_review(record, source.rnc_registry)
            warning = next(
                (
                    item
                    for item in warnings
                    if item["code"] in {"rnc_inactive", "rnc_unverified"}
                ),
                None,
            )
            if warning is None:
                continue
            rnc = identity_digits(fact_value(record, "rnc"))
            assert rnc is not None
            previous = suppliers.get(rnc)
            suppliers[rnc] = RncSupplier(
                name=check["name"] or row.counterparty or rnc,
                rnc=rnc,
                estado=check["estado"] or "sin verificar",
                status=warning["code"],
                record_count=previous.record_count + 1 if previous else 1,
            )
    return _DgiiSelection(
        lines=lines,
        rnc_suppliers=tuple(suppliers[key] for key in sorted(suppliers)),
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
            pending_count=len(dgii.pending_fiscal) + len(dgii.pending_rate),
            pending_fiscal_count=len(dgii.pending_fiscal),
            pending_rate_count=len(dgii.pending_rate),
            pending_rate_currencies=_currencies(dgii.pending_rate),
            rnc_warning_count=sum(
                supplier.record_count for supplier in dgii.rnc_suppliers
            ),
            rnc_supplier_count=len(dgii.rnc_suppliers),
            rnc_suppliers=dgii.rnc_suppliers,
        ),
    )


def _stage_word(row: ReportRecord, locale: FileLocale) -> str | None:
    words = _WORDS[locale]
    if row.stage == "needs_fiscal_data":
        missing = words["business.transactions.layout.workflow.missing"]
        if row.export_missing_several:
            return missing["several"]
        if row.export_missing in missing and row.export_missing != "several":
            return missing[row.export_missing]
        return missing["detail_missing"]
    return words[_STAGE_PATHS[row.stage]] if row.stage else None


def _dgii_word(
    row: ReportRecord, field: Literal["expense_type", "payment_form"], locale: FileLocale
) -> str:
    words = _WORDS[locale]
    if row.dgii_606 is None:
        return words["business.export.form_no_aplica"]
    choice = getattr(row.dgii_606, field)
    if choice is None:
        return words["business.dossier.standing.missing"]
    option = "category" if field == "expense_type" else "payment_method"
    name = words[f"business.dgii.option.{option}"].get(choice.code)
    return f"{choice.code} - {name.upper()}" if name else choice.code


def _amount(text: str | None) -> Decimal | None:
    return Decimal(text) if text is not None else None


def _table_cell(row: ReportRecord, key: FileColumn, locale: FileLocale) -> Cell:
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
        return _stage_word(row, locale)
    if key == "note":
        return row.note
    if key == "attachment":
        return _WORDS[locale]["common.yes" if row.has_document else "common.no"]
    if key in ("expense_type", "payment_form"):
        return _dgii_word(row, key, locale)
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


def _period_name(start: date | None, end: date | None, separator: str) -> str:
    if start is None or end is None:
        return ""
    first, last = start.isoformat(), end.isoformat()
    if start.day == 1 and end.day == monthrange(end.year, end.month)[1]:
        first, last = first[:7], last[:7]
        if first == last:
            return first
    return f"{first} {separator} {last}"


def _safe_filename_part(value: str) -> str:
    clean = "".join(
        char
        for char in value
        if char not in '/\\:*?"<>|'
        and unicodedata.category(char) not in {"Cc", "Cf", "Cs"}
    )
    return " ".join(clean.split())


def records_filename(
    *,
    business_name: str | None,
    families: Sequence[Family],
    start: date | None,
    end: date | None,
    mode: Literal["table", "dgii"],
    extension: Literal["xlsx", "csv"],
    observed_at: datetime,
    locale: FileLocale,
) -> str:
    words = _WORDS[locale]["business.export.filename"]
    family = {
        frozenset({"purchase"}): "purchases",
        frozenset({"sale"}): "sales",
    }.get(frozenset(families), "mixed")
    period = _period_name(start, end, words["to"])
    selection = " ".join(part for part in (words[family], period) if part)
    name = _safe_filename_part(given_name(business_name) or "") or default_space_name(
        locale
    )
    purpose = words["dgii" if mode == "dgii" else "records"]
    timestamp = observed_at.astimezone(ZoneInfo(CALENDAR)).strftime("%Y-%m-%d %H%M")
    return f"{name} - {selection} - {purpose} - {timestamp}.{extension}"


def content_disposition(filename: str) -> str:
    ascii_name = (
        unicodedata.normalize("NFKD", filename).encode("ascii", "ignore").decode("ascii")
    )
    fallback = _safe_filename_part(ascii_name)
    encoded = quote(filename, safe="")
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{encoded}"


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
                if (
                    isinstance(value, Decimal)
                    and len(value.normalize().as_tuple().digits) > 15
                ):
                    # Excel keeps 15 significant digits; past them the exact text stays.
                    sheet.write_string(index, column, str(value))
                elif isinstance(value, Decimal):
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
        return Decimal(0) if name in _REQUIRED_ZERO else None
    if name in TOOL_LABELS:
        return TOOL_LABELS[name][value]
    if name in _DGII_TEXT or name in _DGII_DATES:
        return value
    return Decimal(value)


def build_file(
    source: ExportSource,
    choice: RecordsExport,
    *,
    business_name: str | None = None,
    locale: FileLocale = "es-419",
) -> RecordsFile:
    request = choice.report
    family = _family(request)
    if choice.mode == "dgii":
        form = "607" if family == "sale" else "606"
        columns = COLUMNS[form]
        headers = (
            _PURCHASE_HEADERS if form == "606" else tuple(label for _, label in columns)
        )
        records = sorted(
            (
                source.approved[row.linked_activity_ids[0]]
                for row in _dgii_selection(source, request).lines
            ),
            key=lambda record: (record.occurred_on, record.activity_id),
        )
        rows = [
            [
                cell
                for (name, _), value in zip(columns, line_values(record), strict=True)
                for cell in (
                    (value[:6] or None, value[6:] or None)
                    if form == "606" and name in _SPLIT_DATES
                    else (_dgii_cell(name, value),)
                )
            ]
            for record in records
        ]
        dates = [record.occurred_on for record in records]
        sheet = form
    else:
        selected = _with_currencies(request, choice.currencies)
        if selected is None:
            raise ActionError("invalid_input", "business_export_currency_required")
        keys = _file_columns(request, choice.columns, choice.currencies == "all")
        words = _WORDS[locale]
        headers = [
            words[_HEADER_PATHS[key]].replace("{{currency}}", "").strip() for key in keys
        ]
        matching = matching_records(source.records, selected, source.observed_at)
        rows = [[_table_cell(row, key, locale) for key in keys] for row in matching]
        dates = [row.report_date for row in matching if row.report_date is not None]
        sheet = words[
            "business.transactions.layout.overview."
            + ("sales" if family == "sale" else "purchases")
        ]
    period = resolve_period(request.filters.period, source.records, source.observed_at)
    filename = records_filename(
        business_name=business_name,
        families=request.filters.record_families,
        start=period.from_date or min(dates, default=None),
        end=period.to_date or max(dates, default=None),
        mode=choice.mode,
        extension=choice.format,
        observed_at=source.observed_at,
        locale=locale,
    )
    if choice.format == "csv":
        return RecordsFile(filename, CSV, _csv(headers, rows), len(rows))
    return RecordsFile(filename, XLSX, _xlsx(sheet, headers, rows), len(rows))


def preview_export(
    authority: BusinessAuthority,
    context: ActionContext,
    request: ReportRequest | ReportRequestV2,
) -> ExportPreview:
    return summarize_export(read_export_source(authority, context), request)


def export_file(
    authority: BusinessAuthority,
    context: ActionContext,
    choice: RecordsExport,
    *,
    business_name: str | None = None,
    locale: FileLocale = "es-419",
) -> RecordsFile:
    built = build_file(
        read_export_source(authority, context),
        choice,
        business_name=business_name,
        locale=locale,
    )
    require_export(authority, context)
    return built
