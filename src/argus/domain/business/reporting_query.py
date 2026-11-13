"""The fixed Registros query contract and reduction over one authorized snapshot."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import asdict, replace
from datetime import date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from argus.domain.business.contracts.facts import InheritedValue, personal_mark_admits
from argus.domain.business.country import DEFAULT_COUNTRY
from argus.domain.business.reporting import (
    FiscalAmount,
    ReportIdentity,
    ReportRow,
    summarize,
    summarize_fiscal,
)
from argus.domain.business.reporting_columns import SPECS, TableColumn, offered_columns
from argus.domain.business.reporting_preferences import (
    Contract,
    DocumentKind,
    Family,
    FiscalData,
    Period,
    Presentation,
    ReportFilters,
    ReportRequest,
    ReportRequestV2,
    Stage,
)
from argus.domain.business.reporting_preferences import (
    ReportRecipe as ReportRecipe,
)
from argus.domain.recording.currency import (
    format_minor_units,
    parse_minor_units,
)
from argus.domain.recording.errors import RecordingInputError

CALENDAR = "America/Santo_Domingo"


class ResolvedPeriod(Contract):
    from_date: date | None
    to_date: date | None
    calendar: Literal["America/Santo_Domingo"] = CALENDAR


class ReportAttachment(Contract):
    source_id: str
    receipt_id: str | None
    filename: str | None
    media_type: str | None
    source_available: bool | None
    download_available: bool = False


class DgiiChoice(Contract):
    """One 606 answer: its code and the name the DGII list gives it."""

    code: str
    label: str


class Purchase606(Contract):
    """The two 606 answers a purchase carries. A null answer is still missing."""

    expense_type: DgiiChoice | None
    payment_form: DgiiChoice | None


class ReportRecord(Contract):
    can_edit_note: bool = False
    can_append_supporting: bool = False
    annotation_unavailable_reason: str | None = "business_annotation_unsupported"
    attachment_sources: tuple[ReportAttachment, ...] = ()
    row_id: str
    draft_id: str | None = None
    linked_activity_ids: tuple[str, ...] = ()
    revision: int
    report_date: date | None
    date_basis: Literal["document_issue", "activity_effective"]
    family: Family | None = None
    stage: Stage | None = None
    #: Current 606/607 verdict, independent of downloaded export history.
    fiscal_data: FiscalData | None = None
    export_missing: str | None = None
    export_missing_several: bool = False
    export_line: bool = False
    technical_state: str | None = None
    workflow_blockers: tuple[str, ...] = ()
    currency: str | None = None
    gross_amount: str | None = None
    net_amount: str | None = None
    net_amount_source: Literal["read", "calculated", "edited"] | None = None
    amounts_difference: str | None = None
    inheritance: dict[str, InheritedValue] = {}
    itbis_amount: str | None = None
    goods_amount: str | None = None
    services_amount: str | None = None
    recorded_amount: str | None = None
    recorded_currency: str | None = None
    proposed_amount: str | None = None
    money_kind: str = "unknown"
    money_effect: Literal["known", "unknown", "unsupported"] = "known"
    adjustment_effect: Literal["known", "unknown", "unsupported"] | None = None
    counterparty: str | None = None
    counterparty_key: str | None = None
    category_key: str = "uncategorized"
    funding_key: str | None = None
    funding_label: str | None = None
    funding_kind: str | None = None
    has_document: bool = False
    personal: bool = False
    include_606: bool | None = None
    #: None for a record the 606 never lists: a sale, a Personal record the
    #: accountant did not admit, or a purchase the owner said has no comprobante.
    dgii_606: Purchase606 | None = None
    document_kind: DocumentKind = "unknown"
    fiscal_classification: str = "unknown"
    fiscal_number: str | None = None
    note: str | None = None
    attachment_filenames: tuple[str, ...] = ()
    document_identifiers: tuple[str, ...] = ()
    settlement_status: str | None = None
    dependency_fingerprint: str = ""


class Total(Contract):
    currency: str | None
    kind: str
    basis: Literal[
        "recorded_activity_amount",
        "proposed_activity_amount",
        "document_gross_amount",
        "document_credit_adjustment",
        "document_family_amount",
        "document_net_amount",
        "document_net_credit_adjustment",
        "document_net_family_amount",
    ]
    matching_count: int
    known_amount_minor: int
    unknown_count: int
    unsupported_count: int
    complete: bool
    amount_minor: int | None
    known_amount: str | None
    amount: str | None


class FiscalReportTotal(Contract):
    currency: str | None
    kind: str
    basis: Literal["itbis", "goods", "services"]
    applicable_count: int
    populated_count: int
    known_amount_minor: int
    unknown_count: int
    unsupported_count: int
    complete: bool
    amount_minor: int | None
    known_amount: str | None
    amount: str | None


class FilterOption(Contract):
    key: str
    labels: tuple[str, ...]


class FundingOption(Contract):
    key: str
    label: str | None
    kind: str | None


class ReportOverview(Contract):
    """Fiscal count uses all table filters before pagination.
    Other counts cover the period's recorded rows."""

    needs_review: int = 0
    ready_for_export: int = 0
    needs_fiscal_data: int = 0
    exported: int = 0
    export_lines: int = 0


class ExcludedPersonal(Contract):
    """Matching rows the Personal mark keeps out of every total, counted by
    the family the cards group on (a sale is income, a purchase expense)."""

    income: int = 0
    expense: int = 0


class ReportColumn(Contract):
    """One column the table offers, with the rules the web draws it by."""

    key: TableColumn
    #: Locale path of its name; the web reads the words in the reader's language.
    label_key: str
    #: Always shown.
    required: bool
    #: Fixed first.
    pinned: bool
    shown: bool


def report_columns(
    presentation: Presentation, families: tuple[Family, ...], country: str
) -> tuple[ReportColumn, ...]:
    """The columns these families offer in this country, in the layout's order."""

    offered = offered_columns(families, country)
    return tuple(
        ReportColumn(
            key=key,
            label_key=SPECS[key].label,
            required=SPECS[key].required,
            pinned=SPECS[key].pinned,
            shown=key not in presentation.hidden,
        )
        for key in presentation.order
        if key in offered
    )


class ReportAnswer(Contract):
    #: The request's layout after the upgrade; the web keeps this one.
    presentation: Presentation
    columns: tuple[ReportColumn, ...]
    items: tuple[ReportRecord, ...]
    overview: ReportOverview = ReportOverview()
    effective_sort: str = "date_desc"
    sort_unavailable_reason: str | None = None
    matching_count: int
    page: int
    page_size: int
    page_count: int
    totals: tuple[Total, ...]
    fiscal_totals: tuple[FiscalReportTotal, ...] = ()
    fingerprint: str
    captured_at: datetime
    resolved_period: ResolvedPeriod
    excluded_unknown_dates: int
    excluded_personal: ExcludedPersonal = ExcludedPersonal()
    counterparties: tuple[FilterOption, ...]
    categories: tuple[str, ...]
    #: The tipos de gasto the records carry, by code. `missing` is always a
    #: valid filter value and never listed here.
    expense_types: tuple[DgiiChoice, ...] = ()
    funding_sources: tuple[FundingOption, ...]
    coverage_notes: tuple[str, ...] = (
        "records_only_evidence_separate",
        "legal_cancellation_coverage_unavailable",
        "source_document_subtype_may_be_unknown",
        "counterparty_identity_requires_explicit_tax_id",
    )


def _whole_month(day: date) -> tuple[date, date]:
    start = day.replace(day=1)
    next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return start, next_month - timedelta(days=1)


def resolve_period(
    period: Period,
    records: tuple[ReportRecord, ...] | list[ReportRecord],
    observed_at: datetime,
) -> ResolvedPeriod:
    today = observed_at.astimezone(ZoneInfo(CALENDAR)).date()
    start, end = period.from_date, period.to_date
    if period.kind == "this_month":
        start, end = _whole_month(today)
    elif period.kind == "last_month":
        start, end = _whole_month(today.replace(day=1) - timedelta(days=1))
    elif period.kind == "latest_month":
        passed = (
            row.report_date
            for row in records
            if row.report_date is not None and row.report_date <= today
        )
        start, end = _whole_month(max(passed, default=today))
    elif period.kind == "this_year":
        start, end = date(today.year, 1, 1), date(today.year, 12, 31)
    return ResolvedPeriod(from_date=start, to_date=end)


def _text(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", value).casefold()
        if not unicodedata.combining(char)
    ).strip()


def _expense_type_key(row: ReportRecord) -> str | None:
    if row.dgii_606 is None:
        return None
    return row.dgii_606.expense_type.code if row.dgii_606.expense_type else "missing"


def _matches_period(row: ReportRecord, period: ResolvedPeriod) -> bool:
    return period.from_date is None or (
        row.report_date is not None
        and period.from_date <= row.report_date <= period.to_date
    )


def _matches(row: ReportRecord, filters: ReportFilters, period: ResolvedPeriod) -> bool:
    if filters.fiscal_data is not None and row.fiscal_data != filters.fiscal_data:
        return False
    if not _matches_period(row, period):
        return False
    if filters.q and not any(
        _text(filters.q) in _text(value or "")
        for value in (
            row.counterparty,
            row.note,
            row.counterparty_key,
            row.fiscal_number,
            *row.document_identifiers,
            *row.attachment_filenames,
        )
    ):
        return False
    for values, value in (
        (filters.record_families, row.family),
        (filters.review_stages, row.stage),
        (filters.currencies, row.currency),
        (filters.counterparties, row.counterparty_key),
        (filters.categories, row.category_key),
        (filters.expense_types, _expense_type_key(row)),
        (filters.funding_sources, row.funding_key),
        (filters.document_kinds, row.document_kind),
        (filters.fiscal_classifications, row.fiscal_classification),
    ):
        if values and value not in values:
            return False
    if filters.has_document is not None and row.has_document != filters.has_document:
        return False
    for bound, lower in ((filters.amount_min, True), (filters.amount_max, False)):
        if bound is not None:
            if row.gross_amount is None or row.currency is None:
                return False
            amount, limit = (
                parse_minor_units(row.gross_amount, row.currency),
                parse_minor_units(bound, row.currency),
            )
            if (lower and amount < limit) or (not lower and amount > limit):
                return False
    return True


def _admitted(row: ReportRecord) -> bool:
    return personal_mark_admits(row.personal, row.include_606, sale=row.family == "sale")


def _totals(
    rows: tuple[ReportRecord, ...], identity: ReportIdentity, observed_at: datetime
) -> tuple[Total, ...]:
    rows = tuple(filter(_admitted, rows))
    result = []
    for basis, field in (
        ("recorded_activity_amount", "recorded_amount"),
        ("proposed_activity_amount", "proposed_amount"),
        ("document_gross_amount", "gross_amount"),
        ("document_credit_adjustment", "gross_amount"),
    ):
        components = []
        for row in rows:
            if (
                basis == "recorded_activity_amount"
                and not row.linked_activity_ids
                or basis == "proposed_activity_amount"
                and row.linked_activity_ids
                or basis == "document_gross_amount"
                and (
                    row.document_kind == "credit_note"
                    or row.date_basis != "document_issue"
                )
                or basis == "document_credit_adjustment"
                and row.document_kind != "credit_note"
            ):
                continue
            amount = getattr(row, field)
            currency = (
                (row.recorded_currency or row.currency)
                if basis == "recorded_activity_amount"
                else row.currency
            )
            effect = (
                row.adjustment_effect or "unknown"
                if basis == "document_credit_adjustment"
                else row.money_effect
            )
            kind = (
                row.money_kind
                if basis in ("recorded_activity_amount", "proposed_activity_amount")
                else {"sale": "income", "purchase": "expense"}.get(row.family, "unknown")
            )
            if amount is None or currency is None or kind == "unknown":
                effect = "unknown"
            components.append(
                ReportRow(
                    row.row_id,
                    row.revision,
                    row.report_date or date.min,
                    kind,
                    currency or "unknown",
                    parse_minor_units(amount, currency)
                    if amount is not None and currency is not None
                    else None,
                    effect,
                )
            )
        reduced = summarize(
            identity, components, page_number=1, page_size=25, observed_at=observed_at
        )
        for total in reduced.totals:
            fields = asdict(total) | {
                "currency": None if total.currency == "unknown" else total.currency,
                "basis": basis,
                "complete": total.complete,
                "amount_minor": total.amount_minor,
            }
            if basis == "document_credit_adjustment":
                fields["known_amount_minor"] = -total.known_amount_minor
                fields["amount_minor"] = (
                    -total.amount_minor if total.amount_minor is not None else None
                )
            fields["known_amount"] = (
                format_minor_units(fields["known_amount_minor"], total.currency)
                if fields["currency"]
                else None
            )
            fields["amount"] = (
                format_minor_units(fields["amount_minor"], total.currency)
                if fields["currency"] and fields["amount_minor"] is not None
                else None
            )
            result.append(Total(**fields))
    result.extend(_net_totals(rows))
    result.extend(_document_totals(result, rows))
    return tuple(result)


def _net_totals(rows: tuple[ReportRecord, ...]) -> list[Total]:
    result = []
    for credit in (False, True):
        components = []
        for row in rows:
            if (row.document_kind == "credit_note") != credit or (
                not credit and row.date_basis != "document_issue"
            ):
                continue
            kind = {"sale": "income", "purchase": "expense"}.get(row.family, "unknown")
            effect = (row.adjustment_effect or "unknown") if credit else row.money_effect
            if row.net_amount is None or row.currency is None or kind == "unknown":
                effect = "unknown"
            amount_minor = None
            if row.net_amount is not None and row.currency is not None:
                try:
                    amount_minor = _fiscal_minor_units(row.net_amount, row.currency)
                except RecordingInputError:
                    effect = "unsupported"
            components.append(
                FiscalAmount(
                    currency=row.currency,
                    kind=kind,
                    basis="net_amount",
                    amount_minor=amount_minor,
                    populated=row.net_amount is not None,
                    effect=effect,
                    sign=-1 if credit else 1,
                )
            )
        for total in summarize_fiscal(components):
            result.append(
                Total(
                    currency=total.currency,
                    kind=total.kind,
                    basis="document_net_credit_adjustment"
                    if credit
                    else "document_net_amount",
                    matching_count=total.applicable_count,
                    known_amount_minor=total.known_amount_minor,
                    unknown_count=total.unknown_count,
                    unsupported_count=total.unsupported_count,
                    complete=total.complete,
                    amount_minor=total.amount_minor,
                    known_amount=format_minor_units(
                        total.known_amount_minor, total.currency
                    )
                    if total.currency
                    else None,
                    amount=format_minor_units(total.amount_minor, total.currency)
                    if total.currency and total.amount_minor is not None
                    else None,
                )
            )
    return result


def _fiscal_minor_units(amount: str, currency: str) -> int:
    """Discard only redundant fractional zeroes, then use the exact money parser."""
    whole, dot, fraction = amount.strip().partition(".")
    if dot and fraction:
        fraction = fraction.rstrip("0")
        amount = whole + ("." + fraction if fraction else "")
    return parse_minor_units(amount, currency)


def _fiscal_totals(rows: tuple[ReportRecord, ...]) -> tuple[FiscalReportTotal, ...]:
    components = []
    for row in filter(_admitted, rows):
        kind = {"sale": "income", "purchase": "expense"}.get(row.family, "unknown")
        credit = row.document_kind == "credit_note"
        for basis, amount in (
            ("itbis", row.itbis_amount),
            ("goods", row.goods_amount),
            ("services", row.services_amount),
        ):
            if basis != "itbis" and row.dgii_606 is None:
                continue
            effect = (row.adjustment_effect or "unknown") if credit else row.money_effect
            if amount is None or row.currency is None or kind == "unknown":
                effect = "unknown"
            amount_minor = None
            if amount is not None and row.currency is not None:
                try:
                    amount_minor = _fiscal_minor_units(amount, row.currency)
                except RecordingInputError:
                    effect = "unsupported"
            components.append(
                FiscalAmount(
                    currency=row.currency,
                    kind=kind,
                    basis=basis,
                    amount_minor=amount_minor,
                    populated=amount is not None,
                    effect=effect,
                    sign=-1 if credit else 1,
                )
            )
    return tuple(
        FiscalReportTotal(
            **asdict(total),
            complete=total.complete,
            amount_minor=total.amount_minor,
            known_amount=format_minor_units(total.known_amount_minor, total.currency)
            if total.currency
            else None,
            amount=format_minor_units(total.amount_minor, total.currency)
            if total.currency and total.amount_minor is not None
            else None,
        )
        for total in summarize_fiscal(components)
    )


def _document_totals(
    components: list[Total], rows: tuple[ReportRecord, ...]
) -> list[Total]:
    groups: dict[tuple[str | None, str, str], list[Total]] = {}
    for component in components:
        if component.basis in (
            "document_gross_amount",
            "document_credit_adjustment",
            "document_net_amount",
            "document_net_credit_adjustment",
        ):
            basis = (
                "document_net_family_amount"
                if "net" in component.basis
                else "document_family_amount"
            )
            groups.setdefault((component.currency, component.kind, basis), []).append(
                component
            )
    totals = []
    for (currency, kind, basis), members in groups.items():
        known = sum(member.known_amount_minor for member in members)
        unknown = sum(member.unknown_count for member in members)
        unsupported = sum(member.unsupported_count for member in members)
        complete = unknown == unsupported == 0
        totals.append(
            Total(
                currency=currency,
                kind=kind,
                basis=basis,
                matching_count=sum(member.matching_count for member in members),
                known_amount_minor=known,
                unknown_count=unknown,
                unsupported_count=unsupported,
                complete=complete,
                amount_minor=known if complete else None,
                known_amount=format_minor_units(known, currency) if currency else None,
                amount=format_minor_units(known, currency)
                if currency and complete
                else None,
            )
        )
    return totals


def matching_records(
    records: tuple[ReportRecord, ...] | list[ReportRecord],
    request: ReportRequest | ReportRequestV2,
    observed_at: datetime,
) -> tuple[ReportRecord, ...]:
    period = resolve_period(request.filters.period, records, observed_at)
    rows = [row for row in records if _matches(row, request.filters, period)]
    sort, _ = effective_sort(rows, request.sort)
    field, direction = sort.split("_")

    def value(row: ReportRecord) -> object:
        if field == "name":
            return _text(row.counterparty) if row.counterparty else None
        if field == "amount":
            return (
                parse_minor_units(row.gross_amount, row.currency)
                if row.gross_amount is not None and row.currency
                else None
            )
        return row.report_date

    known = [row for row in rows if value(row) is not None]
    missing = [row for row in rows if value(row) is None]
    known.sort(key=lambda row: row.row_id)
    known.sort(key=value, reverse=direction == "desc")
    return tuple(known + sorted(missing, key=lambda row: row.row_id))


def effective_sort(
    rows: list[ReportRecord] | tuple[ReportRecord, ...], requested: str
) -> tuple[str, str | None]:
    currencies = {row.currency for row in rows}
    if requested.startswith("amount_") and (len(currencies) != 1 or None in currencies):
        return "date_desc", "amount_sort_requires_single_known_currency"
    return requested, None


def run_query(
    identity: ReportIdentity,
    records: tuple[ReportRecord, ...] | list[ReportRecord],
    request: ReportRequest | ReportRequestV2,
    observed_at: datetime,
    *,
    country: str = DEFAULT_COUNTRY,
) -> ReportAnswer:
    ids = [row.row_id for row in records]
    effects = [effect for row in records for effect in row.linked_activity_ids]
    if len(ids) != len(set(ids)) or len(effects) != len(set(effects)):
        raise ValueError("duplicate canonical report record or activity")
    period = resolve_period(request.filters.period, records, observed_at)
    rows = matching_records(records, request, observed_at)
    semantic = request.model_dump(
        mode="json", exclude={"page", "page_size", "presentation"}
    )
    # Multiselect order and repeated keys do not change the semantic query.
    for key, value in semantic["filters"].items():
        if isinstance(value, list):
            semantic["filters"][key] = sorted(set(value))
    semantic["filters"]["q"] = _text(request.filters.q)
    excluded_unknown_dates = (
        sum(
            row.report_date is None
            and _matches(
                row, request.filters, ResolvedPeriod(from_date=None, to_date=None)
            )
            for row in records
        )
        if period.from_date is not None
        else 0
    )
    funding_options = {
        row.funding_key: FundingOption(
            key=row.funding_key, label=row.funding_label, kind=row.funding_kind
        )
        for row in records
        if row.funding_key
    }
    expense_types = {
        row.dgii_606.expense_type.code: row.dgii_606.expense_type
        for row in records
        if row.dgii_606 and row.dgii_606.expense_type
    }
    family_records = [
        row
        for row in records
        if not request.filters.record_families
        or row.family in request.filters.record_families
    ]
    parties: dict[str, str] = {}
    for row in sorted(
        family_records,
        key=lambda row: (
            -(row.report_date.toordinal() if row.report_date else 0),
            row.row_id,
        ),
    ):
        if row.counterparty_key and row.counterparty:
            parties.setdefault(row.counterparty_key, row.counterparty)
    for row in family_records:
        if row.counterparty_key:
            parties.setdefault(row.counterparty_key, row.counterparty_key)
    options = {
        "counterparties": sorted(parties.items()),
        "categories": sorted({row.category_key for row in records}),
        "expense_types": [
            expense_types[code].model_dump(mode="json") for code in sorted(expense_types)
        ],
        "funding_sources": [
            funding_options[key].model_dump(mode="json")
            for key in sorted(funding_options)
        ],
    }
    payload = {
        "excluded_unknown_dates": excluded_unknown_dates,
        "options": options,
        "contract": "registros_v1",
        "scope": asdict(replace(identity, query_fingerprint="")),
        "query": semantic,
        "resolved_period": period.model_dump(mode="json"),
        "rows": [row.model_dump(mode="json") for row in rows],
    }
    fingerprint = hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()
    offset = (request.page - 1) * request.page_size
    overview_rows = [row for row in records if _matches_period(row, period)]
    overview = ReportOverview(
        needs_fiscal_data=sum(row.fiscal_data == "missing" for row in rows),
        **{
            stage: sum(row.stage == stage for row in overview_rows)
            for stage in (
                "needs_review",
                "ready_for_export",
                "exported",
            )
        },
        export_lines=sum(row.export_line for row in overview_rows),
    )
    chosen_sort, reason = effective_sort(rows, request.sort)
    left_out = [row for row in rows if not _admitted(row)]
    presentation = (
        request.presentation if isinstance(request, ReportRequestV2) else Presentation()
    )
    return ReportAnswer(
        presentation=presentation,
        columns=report_columns(presentation, request.filters.record_families, country),
        excluded_personal=ExcludedPersonal(
            income=sum(row.family == "sale" for row in left_out),
            expense=sum(row.family == "purchase" for row in left_out),
        ),
        overview=overview,
        effective_sort=chosen_sort,
        sort_unavailable_reason=reason,
        items=rows[offset : offset + request.page_size],
        matching_count=len(rows),
        page=request.page,
        page_size=request.page_size,
        page_count=(len(rows) + request.page_size - 1) // request.page_size,
        totals=_totals(rows, identity, observed_at),
        fiscal_totals=_fiscal_totals(rows),
        fingerprint=fingerprint,
        captured_at=observed_at,
        resolved_period=period,
        excluded_unknown_dates=excluded_unknown_dates,
        counterparties=tuple(
            FilterOption(key=key, labels=(label,))
            for key, label in sorted(parties.items())
        ),
        categories=tuple(sorted({row.category_key for row in records})),
        expense_types=tuple(expense_types[code] for code in sorted(expense_types)),
        funding_sources=tuple(funding_options[key] for key in sorted(funding_options)),
    )
