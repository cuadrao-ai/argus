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
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote
from zoneinfo import ZoneInfo

import xlsxwriter
from pydantic import model_validator
from typing_extensions import assert_never

from argus.domain.business.authority import ActionContext, ActionError, BusinessAuthority
from argus.domain.business.contracts.dgii import printed_date
from argus.domain.business.dgii_codes import TOOL_LABELS
from argus.domain.business.dgii_columns import COLUMNS
from argus.domain.business.dgii_export import line_values
from argus.domain.business.dgii_line import REQUIRED_ZERO_606, line_review
from argus.domain.business.dgii_validation import (
    DECLARABLE_CURRENCY,
    FiscalRecord,
    declarable,
    fact_value,
)
from argus.domain.business.export import spreadsheet_cell
from argus.domain.business.fiscal_identity import identity_digits
from argus.domain.business.month_close import unreviewed_in_month
from argus.domain.business.reporting_columns import (
    CURRENCY_LABEL,
    RETIRED_COLUMNS,
    SPECS,
    FileColumn,
)
from argus.domain.business.reporting_preferences import (
    Contract,
    Family,
    Presentation,
    ReportFilters,
    ReportInput,
    ReportRequest,
    ReportRequestV2,
)
from argus.domain.business.reporting_query import (
    CALENDAR,
    ReportRecord,
    matching_records,
    report_columns,
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
    #: Table mode: the preview's columns to include. Required ones are always in.
    columns: tuple[FileColumn, ...] = ()
    currencies: Literal["all", "current"] = "all"
    format: Literal["xlsx", "csv"] = "xlsx"

    @model_validator(mode="before")
    @classmethod
    def drop_retired_table_columns(cls, value: Any) -> Any:
        if isinstance(value, dict) and value.get("mode") == "table":
            columns = value.get("columns")
            if isinstance(columns, (list, tuple)):
                return {
                    **value,
                    "columns": [key for key in columns if key not in RETIRED_COLUMNS],
                }
        return value

    @model_validator(mode="after")
    def mode_choices(self) -> RecordsExport:
        if self.mode == "table":
            if not self.columns or len(set(self.columns)) != len(self.columns):
                raise ValueError("table export columns must be nonempty and unique")
        elif self.columns or self.currencies != "all":
            raise ValueError("the DGII format defines its own columns and currency")
        return self


class ExportColumn(Contract):
    key: FileColumn
    #: Locale path of its name; the web reads the words in the reader's language.
    label_key: str
    #: Always in the file.
    required: bool
    shown: bool


class ExportFileNames(Contract):
    """The name the export gives this choice's file in each format."""

    xlsx: str
    csv: str


class CurrencySelection(Contract):
    record_count: int
    currencies: tuple[str, ...]
    #: The file's columns for this choice, in file order.
    columns: tuple[ExportColumn, ...]
    filenames: ExportFileNames


class TableExport(Contract):
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
    form: Literal["606"]
    #: The one currency the form states; Revisar shows its pending records.
    currency: str = DECLARABLE_CURRENCY
    record_count: int
    #: Every record the 606 holds back, for either reason below.
    pending_count: int
    #: Pesos records the 606 holds for missing fiscal data.
    pending_fiscal_count: int
    #: Foreign-currency records the 606 holds until they have a rate.
    pending_rate_count: int
    pending_rate_currencies: tuple[str, ...]
    rnc_warning_count: int
    rnc_supplier_count: int
    rnc_suppliers: tuple[RncSupplier, ...]
    filenames: ExportFileNames


class ExportPreview(Contract):
    table: TableExport
    dgii: DgiiExport | None
    #: Documents the Bandeja still holds in the export's period, either tab.
    bandeja_count: int


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


def _file_columns(
    request: ReportRequest | ReportRequestV2, country: str, all_: bool
) -> tuple[ExportColumn, ...]:
    """The table's offered columns in its order, with Moneda after the gross
    amount when the file holds every currency. The registry says which column
    the file always holds and which it offers checked while the table hides it;
    that one goes last."""

    columns: list[ExportColumn] = []
    last: list[ExportColumn] = []
    for column in report_columns(_presentation(request), (_family(request),), country):
        rule = SPECS[column.key].file
        (last if rule == "default" and not column.shown else columns).append(
            ExportColumn(
                key=column.key,
                label_key=column.label_key,
                required=rule == "always",
                shown=column.shown or rule != "as_shown",
            )
        )
        if column.key == "gross_amount" and all_:
            columns.append(
                ExportColumn(
                    key="currency", label_key=CURRENCY_LABEL, required=True, shown=True
                )
            )
    return (*columns, *last)


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


def _dgii_records(source: ExportSource, selection: _DgiiSelection) -> list[FiscalRecord]:
    return sorted(
        (source.approved[row.linked_activity_ids[0]] for row in selection.lines),
        key=lambda record: (record.occurred_on, record.activity_id),
    )


def _currencies(rows: Sequence[ReportRecord]) -> tuple[str, ...]:
    return tuple(sorted({row.currency for row in rows if row.currency}))


def _table_dates(rows: Sequence[ReportRecord]) -> list[date]:
    return [row.report_date for row in rows if row.report_date is not None]


def _filename(
    source: ExportSource,
    request: ReportRequest | ReportRequestV2,
    mode: Literal["table", "dgii"],
    dates: Sequence[date],
    extension: Literal["xlsx", "csv"],
    business_name: str | None,
    locale: FileLocale,
) -> str:
    """The one name a file of this selection gets, offered before it is built."""
    period = resolve_period(request.filters.period, source.records, source.observed_at)
    return records_filename(
        business_name=business_name,
        families=request.filters.record_families,
        start=period.from_date or min(dates, default=None),
        end=period.to_date or max(dates, default=None),
        mode=mode,
        extension=extension,
        observed_at=source.observed_at,
        locale=locale,
    )


def summarize_export(
    source: ExportSource,
    request: ReportRequest | ReportRequestV2,
    *,
    business_name: str | None = None,
    locale: FileLocale = "es-419",
    bandeja: Iterable[tuple[date, str | None]] = (),
) -> ExportPreview:
    """``bandeja`` is the close day and currency of each draft the Bandeja
    still lists, as ``unreviewed_days`` answers them."""

    def filenames(
        mode: Literal["table", "dgii"], dates: Sequence[date]
    ) -> ExportFileNames:
        return ExportFileNames(
            xlsx=_filename(source, request, mode, dates, "xlsx", business_name, locale),
            csv=_filename(source, request, mode, dates, "csv", business_name, locale),
        )

    def selection(
        selected: ReportRequest | ReportRequestV2, all_: bool
    ) -> CurrencySelection:
        rows = matching_records(source.records, selected, source.observed_at)
        return CurrencySelection(
            record_count=len(rows),
            currencies=_currencies(rows),
            columns=_file_columns(request, source.country, all_),
            filenames=filenames("table", _table_dates(rows)),
        )

    every = _with_currencies(request, "all")
    dgii = _dgii_selection(source, request) if _family(request) == "purchase" else None
    period = resolve_period(request.filters.period, source.records, source.observed_at)
    waiting = unreviewed_in_month(
        ((day, "") for day, _ in bandeja),
        period.from_date or date.min,
        period.to_date or date.max,
    )
    return ExportPreview(
        bandeja_count=sum(waiting.values()),
        table=TableExport(
            current=selection(request, False),
            all=None if every is None else selection(every, True),
        ),
        dgii=DgiiExport(
            form="606",
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
            filenames=filenames(
                "dgii", [record.occurred_on for record in _dgii_records(source, dgii)]
            ),
        )
        if dgii is not None
        else None,
    )


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
        return row.title
    if key == "counterparty_id":
        return row.counterparty_key
    if key == "fiscal_number":
        return row.fiscal_number
    if key == "date":
        return row.report_date
    if key == "net_amount":
        return _amount(row.net_amount) if row.currency else None
    if key == "gross_amount":
        return _amount(row.gross_amount) if row.currency else None
    if key == "currency":
        return row.currency
    if key == "itbis_amount":
        return _amount(row.itbis_amount) if row.currency else None
    if key == "stage":
        state = "ready" if row.ready else "not_ready"
        return _WORDS[locale][f"business.transactions.layout.workflow.{state}"]
    if key == "note":
        return row.note
    if key == "attachment":
        return _WORDS[locale]["common.yes" if row.has_document else "common.no"]
    if key in ("expense_type", "payment_form"):
        return _dgii_word(row, key, locale)
    assert_never(key)


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
            return printed_date(value)
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
        return Decimal(0) if name in REQUIRED_ZERO_606 else None
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
        if family == "sale":
            raise ActionError("invalid_input", "business_export_dgii_sales_unavailable")
        columns = COLUMNS["606"]
        headers = _PURCHASE_HEADERS
        records = _dgii_records(source, _dgii_selection(source, request))
        rows = [
            [
                cell
                for (name, _), value in zip(columns, line_values(record), strict=True)
                for cell in (
                    (value[:6] or None, value[6:] or None)
                    if name in _SPLIT_DATES
                    else (_dgii_cell(name, value),)
                )
            ]
            for record in records
        ]
        dates = [record.occurred_on for record in records]
        sheet = "606"
    else:
        selected = _with_currencies(request, choice.currencies)
        if selected is None:
            raise ActionError("invalid_input", "business_export_currency_required")
        columns = _file_columns(request, source.country, choice.currencies == "all")
        if not set(choice.columns) <= {column.key for column in columns}:
            raise ActionError("invalid_input", "business_export_column_unavailable")
        chosen = [
            column
            for column in columns
            if column.required or column.key in choice.columns
        ]
        keys = [column.key for column in chosen]
        words = _WORDS[locale]
        headers = [
            words[column.label_key].replace("{{currency}}", "").strip()
            for column in chosen
        ]
        matching = matching_records(source.records, selected, source.observed_at)
        rows = [[_table_cell(row, key, locale) for key in keys] for row in matching]
        dates = _table_dates(matching)
        sheet = words[
            "business.transactions.layout.overview."
            + ("sales" if family == "sale" else "purchases")
        ]
    filename = _filename(
        source, request, choice.mode, dates, choice.format, business_name, locale
    )
    if choice.format == "csv":
        return RecordsFile(filename, CSV, _csv(headers, rows), len(rows))
    return RecordsFile(filename, XLSX, _xlsx(sheet, headers, rows), len(rows))


def preview_export(
    authority: BusinessAuthority,
    context: ActionContext,
    request: ReportRequest | ReportRequestV2,
    *,
    business_name: str | None = None,
    locale: FileLocale = "es-419",
    bandeja: Callable[[], Iterable[tuple[date, str | None]]] = tuple,
) -> ExportPreview:
    """``bandeja`` is read only once the grant has proven it exports."""

    source = read_export_source(authority, context)
    return summarize_export(
        source,
        request,
        business_name=business_name,
        locale=locale,
        bandeja=bandeja(),
    )


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
