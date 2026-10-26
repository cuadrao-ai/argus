from datetime import date, datetime, timezone

import pytest
from argus.domain.business.reporting import ReportIdentity
from argus.domain.business.reporting_preferences import ReportRequestV2
from argus.domain.business.reporting_query import ReportRecord, ReportRequest, run_query
from pydantic import ValidationError

NOW = datetime(2026, 10, 26, tzinfo=timezone.utc)
IDENTITY = ReportIdentity("business", "actor", "owner", None, "")


def row(identifier, **fields):
    return ReportRecord(
        row_id=identifier,
        revision=1,
        report_date=date(2026, 10, 20),
        date_basis="document_issue",
        currency="DOP",
        gross_amount="10.00",
        **fields,
    )


def test_v1_remains_strict_and_v2_preserves_columns_and_density():
    with pytest.raises(ValidationError):
        ReportRequest(sort="name_asc")
    with pytest.raises(ValidationError):
        ReportRequest(presentation={"density": 40})
    request = ReportRequestV2(sort="name_asc", presentation={"density": 56})
    assert request.presentation.order[0] == "counterparty"
    assert request.presentation.hidden == ("funding",)
    assert request.page_size == 25
    with pytest.raises(ValidationError):
        ReportRequestV2(presentation={"hidden": ["currency"]})


def test_search_is_literal_accent_insensitive_and_overview_ignores_table_filters():
    rows = [
        row("1", counterparty="Café", stage="needs_review"),
        row("2", attachment_filenames=("José.pdf",), stage="awaiting_approval"),
    ]
    answer = run_query(IDENTITY, rows, ReportRequestV2(filters={"q": "JOSE"}), NOW)
    assert [r.row_id for r in answer.items] == ["2"]
    assert answer.overview.needs_review == 1
    assert answer.overview.awaiting_approval == 1
    assert not run_query(IDENTITY, rows, ReportRequestV2(filters={"q": "%"}), NOW).items


def test_sort_nulls_last_stable_ties_and_currency_guard():
    rows = [
        row("b", counterparty="Café"),
        row("a", counterparty="Cafe"),
        row("c", counterparty=None),
    ]
    for order in ("name_asc", "name_desc"):
        answer = run_query(IDENTITY, rows, ReportRequestV2(sort=order), NOW)
        assert [r.row_id for r in answer.items] == ["a", "b", "c"]
    mixed = [*rows, rows[0].model_copy(update={"row_id": "usd", "currency": "USD"})]
    answer = run_query(IDENTITY, mixed, ReportRequestV2(sort="amount_asc"), NOW)
    assert answer.effective_sort == "date_desc"
    assert answer.sort_unavailable_reason == "amount_sort_requires_single_known_currency"


def test_v2_amount_input_uses_fifteen_significant_whole_digits_only():
    ReportRequestV2(
        filters={"currencies": ["DOP"], "amount_min": "000999999999999999.99"}
    )
    with pytest.raises(ValidationError):
        ReportRequestV2(filters={"currencies": ["DOP"], "amount_min": "1000000000000000"})
    ReportRequest(filters={"currencies": ["DOP"], "amount_min": "1000000000000000"})


def test_all_time_search_and_overview_cover_rows_beyond_a_hundred():
    rows = [
        row(
            str(index),
            stage="needs_review",
            attachment_filenames=("José.pdf",) if index == 102 else (),
        ).model_copy(update={"report_date": date(2020 + index % 6, 1, 1)})
        for index in range(103)
    ]
    answer = run_query(IDENTITY, rows, ReportRequestV2(page_size=100), NOW)
    assert answer.matching_count == 103 and len(answer.items) == 100
    assert answer.resolved_period.from_date is None
    assert answer.overview.needs_review == 103
    matched = run_query(IDENTITY, rows, ReportRequestV2(filters={"q": "jose"}), NOW)
    assert matched.matching_count == 1 and matched.items[0].row_id == "102"
    assert matched.overview.needs_review == 103


@pytest.mark.parametrize(
    "sort,expected",
    [
        ("amount_asc", ["a", "b", "null"]),
        ("amount_desc", ["b", "a", "null"]),
        ("date_asc", ["a", "b", "null"]),
        ("date_desc", ["b", "a", "null"]),
    ],
)
def test_exact_amount_and_date_sort_orders_with_null_last(sort, expected):
    first = row("a").model_copy(
        update={"gross_amount": "90071992547409.91", "report_date": date(2020, 1, 1)}
    )
    second = row("b").model_copy(
        update={"gross_amount": "90071992547409.92", "report_date": date(2025, 1, 1)}
    )
    missing = row("null").model_copy(update={"gross_amount": None, "report_date": None})
    answer = run_query(
        IDENTITY, [second, missing, first], ReportRequestV2(sort=sort), NOW
    )
    assert [record.row_id for record in answer.items] == expected
