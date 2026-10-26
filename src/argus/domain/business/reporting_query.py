"""The fixed Registros query contract and reduction over one authorized snapshot."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import asdict, replace
from datetime import date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

from argus.domain.business.reporting import ReportIdentity, ReportRow, summarize
from argus.domain.recording.currency import (
    format_minor_units,
    normalize_currency,
    parse_minor_units,
)
from argus.domain.recording.errors import RecordingInputError

CALENDAR = "America/Santo_Domingo"
Family = Literal["sale", "purchase"]
Stage = Literal["needs_review", "awaiting_approval", "ready_for_export"]
DocumentKind = Literal["invoice", "receipt", "credit_note", "unknown"]
Column = Literal[
    "date",
    "family",
    "stage",
    "counterparty",
    "currency",
    "gross_amount",
    "recorded_amount",
    "proposed_amount",
    "category",
    "funding",
    "document_kind",
    "fiscal_classification",
    "note",
]
DEFAULT_COLUMNS: tuple[Column, ...] = (
    "date",
    "family",
    "stage",
    "counterparty",
    "currency",
    "gross_amount",
)


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Period(Contract):
    kind: Literal["all", "custom", "this_month", "last_month", "this_year"] = "all"
    from_date: date | None = None
    to_date: date | None = None

    @model_validator(mode="after")
    def bounds(self) -> Period:
        if self.kind == "custom":
            if (
                self.from_date is None
                or self.to_date is None
                or self.from_date > self.to_date
            ):
                raise ValueError("custom period requires ordered inclusive dates")
        elif self.from_date is not None or self.to_date is not None:
            raise ValueError("only custom periods accept dates")
        return self


class ResolvedPeriod(Contract):
    from_date: date | None
    to_date: date | None
    calendar: Literal["America/Santo_Domingo"] = CALENDAR


class ReportFilters(Contract):
    q: str = Field(default="", max_length=200)
    period: Period = Period()
    record_families: tuple[Family, ...] = ()
    review_stages: tuple[Stage, ...] = ()
    has_document: bool | None = None
    currencies: tuple[str, ...] = Field(default=(), max_length=200)
    amount_min: str | None = None
    amount_max: str | None = None
    counterparties: tuple[str, ...] = Field(default=(), max_length=200)
    categories: tuple[str, ...] = Field(default=(), max_length=200)
    funding_sources: tuple[str, ...] = Field(default=(), max_length=200)
    document_kinds: tuple[DocumentKind, ...] = ()
    fiscal_classifications: tuple[str, ...] = Field(default=(), max_length=100)

    @model_validator(mode="after")
    def amounts(self) -> ReportFilters:
        try:
            for currency in self.currencies:
                if normalize_currency(currency) != currency:
                    raise ValueError("currency must use its canonical code")
            if self.amount_min is not None or self.amount_max is not None:
                if len(set(self.currencies)) != 1:
                    raise ValueError("amount range requires one currency")
                values = [
                    parse_minor_units(value, self.currencies[0])
                    if value is not None
                    else None
                    for value in (self.amount_min, self.amount_max)
                ]
                if any(value is not None and value < 0 for value in values):
                    raise ValueError("amount range uses gross magnitude")
                if all(value is not None for value in values) and values[0] > values[1]:
                    raise ValueError("amount range must be ordered")
        except RecordingInputError as error:
            raise ValueError(error.code) from None
        for values in (
            self.counterparties,
            self.categories,
            self.funding_sources,
            self.fiscal_classifications,
        ):
            if any(not value or len(value) > 128 for value in values):
                raise ValueError("invalid filter key")
        return self


class ReportRecipe(Contract):
    schema_version: Literal[1] = 1
    filters: ReportFilters = ReportFilters()
    columns: tuple[Column, ...] = DEFAULT_COLUMNS
    sort: Literal["date_desc"] = "date_desc"

    @model_validator(mode="after")
    def unique_columns(self) -> ReportRecipe:
        if not self.columns or len(set(self.columns)) != len(self.columns):
            raise ValueError("columns must be nonempty and unique")
        return self


class ReportRequest(ReportRecipe):
    page: int = Field(default=1, ge=1, strict=True)
    page_size: Literal[25, 50, 100] = 25


class ReportRecord(Contract):
    row_id: str
    draft_id: str | None = None
    linked_activity_ids: tuple[str, ...] = ()
    revision: int
    report_date: date | None
    date_basis: Literal["document_issue", "activity_effective"]
    family: Family | None = None
    stage: Stage | None = None
    technical_state: str | None = None
    workflow_blockers: tuple[str, ...] = ()
    currency: str | None = None
    gross_amount: str | None = None
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
    document_kind: DocumentKind = "unknown"
    fiscal_classification: str = "unknown"
    fiscal_number: str | None = None
    note: str | None = None
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
    ]
    matching_count: int
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


class ReportAnswer(Contract):
    items: tuple[ReportRecord, ...]
    matching_count: int
    page: int
    page_size: int
    page_count: int
    totals: tuple[Total, ...]
    fingerprint: str
    captured_at: datetime
    resolved_period: ResolvedPeriod
    excluded_unknown_dates: int
    counterparties: tuple[FilterOption, ...]
    categories: tuple[str, ...]
    funding_sources: tuple[FundingOption, ...]
    coverage_notes: tuple[str, ...] = (
        "records_only_evidence_separate",
        "legal_cancellation_coverage_unavailable",
        "source_document_subtype_may_be_unknown",
        "counterparty_identity_requires_explicit_tax_id",
    )


def resolve_period(period: Period, observed_at: datetime) -> ResolvedPeriod:
    today = observed_at.astimezone(ZoneInfo(CALENDAR)).date()
    start, end = period.from_date, period.to_date
    if period.kind in ("this_month", "last_month"):
        start = today.replace(day=1)
        if period.kind == "last_month":
            end = start - timedelta(days=1)
            start = end.replace(day=1)
        else:
            end = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(
                days=1
            )
    elif period.kind == "this_year":
        start, end = date(today.year, 1, 1), date(today.year, 12, 31)
    return ResolvedPeriod(from_date=start, to_date=end)


def _text(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold().strip()


def _matches(row: ReportRecord, filters: ReportFilters, period: ResolvedPeriod) -> bool:
    if period.from_date is not None and (
        row.report_date is None
        or not period.from_date <= row.report_date <= period.to_date
    ):
        return False
    if filters.q and not any(
        _text(filters.q) in _text(value or "")
        for value in (row.counterparty, row.note, row.counterparty_key, row.fiscal_number)
    ):
        return False
    for values, value in (
        (filters.record_families, row.family),
        (filters.review_stages, row.stage),
        (filters.currencies, row.currency),
        (filters.counterparties, row.counterparty_key),
        (filters.categories, row.category_key),
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


def _totals(
    rows: tuple[ReportRecord, ...], identity: ReportIdentity, observed_at: datetime
) -> tuple[Total, ...]:
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
    result.extend(_document_totals(result, rows))
    return tuple(result)


def _document_totals(
    components: list[Total], rows: tuple[ReportRecord, ...]
) -> list[Total]:
    groups: dict[tuple[str | None, str], list[Total]] = {}
    for component in components:
        if component.basis in ("document_gross_amount", "document_credit_adjustment"):
            groups.setdefault((component.currency, component.kind), []).append(component)
    totals = []
    for (currency, kind), members in groups.items():
        # An unlinked credit cannot safely be assigned to either document family.
        ambiguous = (
            sum(
                row.document_kind == "credit_note"
                and row.family is None
                and row.currency == currency
                for row in rows
            )
            if kind != "unknown"
            else 0
        )
        known = sum(member.known_amount_minor for member in members)
        unknown = sum(member.unknown_count for member in members) + ambiguous
        unsupported = sum(member.unsupported_count for member in members)
        complete = unknown == unsupported == 0
        totals.append(
            Total(
                currency=currency,
                kind=kind,
                basis="document_family_amount",
                matching_count=sum(member.matching_count for member in members)
                + ambiguous,
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
    request: ReportRequest,
    observed_at: datetime,
) -> tuple[ReportRecord, ...]:
    period = resolve_period(request.filters.period, observed_at)
    return tuple(
        sorted(
            (row for row in records if _matches(row, request.filters, period)),
            key=lambda row: (
                row.report_date is None,
                -(row.report_date or date.min).toordinal(),
                row.row_id,
            ),
        )
    )


def run_query(
    identity: ReportIdentity,
    records: tuple[ReportRecord, ...] | list[ReportRecord],
    request: ReportRequest,
    observed_at: datetime,
) -> ReportAnswer:
    ids = [row.row_id for row in records]
    effects = [effect for row in records for effect in row.linked_activity_ids]
    if len(ids) != len(set(ids)) or len(effects) != len(set(effects)):
        raise ValueError("duplicate canonical report record or activity")
    period = resolve_period(request.filters.period, observed_at)
    rows = matching_records(records, request, observed_at)
    semantic = request.model_dump(mode="json", exclude={"page", "page_size", "columns"})
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
    options = {
        "counterparties": sorted(
            (row.counterparty_key, row.counterparty or "")
            for row in records
            if row.counterparty_key
        ),
        "categories": sorted({row.category_key for row in records}),
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
    parties: dict[str, set[str]] = {}
    for row in records:
        if row.counterparty_key:
            parties.setdefault(row.counterparty_key, set()).add(
                row.counterparty or row.counterparty_key
            )
    offset = (request.page - 1) * request.page_size
    return ReportAnswer(
        items=rows[offset : offset + request.page_size],
        matching_count=len(rows),
        page=request.page,
        page_size=request.page_size,
        page_count=(len(rows) + request.page_size - 1) // request.page_size,
        totals=_totals(rows, identity, observed_at),
        fingerprint=fingerprint,
        captured_at=observed_at,
        resolved_period=period,
        excluded_unknown_dates=excluded_unknown_dates,
        counterparties=tuple(
            FilterOption(key=key, labels=tuple(sorted(labels)))
            for key, labels in sorted(parties.items())
        ),
        categories=tuple(sorted({row.category_key for row in records})),
        funding_sources=tuple(funding_options[key] for key in sorted(funding_options)),
    )
