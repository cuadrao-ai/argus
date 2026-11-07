from datetime import date

import pytest
from argus.domain.business.reporting_query import ReportFilters, ReportRequest, run_query

from tests.business.test_business_reporting_query import IDENTITY, NOW, record


def run(rows, filters, **changes):
    return run_query(
        IDENTITY, rows, ReportRequest(filters=filters, **changes), NOW,
        registros_summary_v2_enabled=True,
    )


@pytest.mark.parametrize(
    "filters,excluded",
    [
        ({"q": "taller"}, {"counterparty": "Colmado"}),
        ({"counterparties": ["supplier-a"]}, {"counterparty_key": "supplier-b"}),
        ({"record_families": ["purchase"]}, {"family": None}),
        ({"currencies": ["DOP"]}, {"currency": "USD"}),
        ({"has_document": True}, {"has_document": False}),
        ({"currencies": ["DOP"], "amount_min": "50.00"}, {"gross_amount": "10.00"}),
        ({"currencies": ["DOP"], "amount_max": "150.00"}, {"gross_amount": "200.00"}),
        ({"categories": ["supplies"]}, {"category_key": "other"}),
        ({"funding_sources": ["cash"]}, {"funding_key": "bank"}),
        ({"document_kinds": ["invoice"]}, {"document_kind": "receipt"}),
        ({"fiscal_classifications": ["B01"]}, {"fiscal_classification": "B02"}),
        ({"expense_types": ["missing"]}, {"dgii_606": None}),
        (
            {
                "period": {
                    "kind": "custom",
                    "from_date": "2026-10-01",
                    "to_date": "2026-10-31",
                }
            },
            {"report_date": date(2026, 9, 1)},
        ),
    ],
)
def test_fiscal_count_uses_each_table_filter_before_pagination(filters, excluded):
    matching = record(
        "match",
        stage="needs_fiscal_data",
        counterparty="Taller",
        counterparty_key="supplier-a",
        has_document=True,
        category_key="supplies",
        funding_key="cash",
        document_kind="invoice",
        fiscal_classification="B01",
        dgii_606={"expense_type": None, "payment_form": None},
    )
    rows = [matching.model_copy(update={"row_id": f"match-{i}"}) for i in range(30)]
    rows += [matching.model_copy(update={"row_id": "excluded", **excluded})]
    rows += [matching.model_copy(update={"row_id": "ready", "stage": "ready_for_export"})]
    request_filters = ReportFilters(**filters)
    answer = run(rows, request_filters, page=2)
    assert answer.overview.needs_fiscal_data == 30
    assert answer.matching_count == 31
    assert len(answer.items) == 6
    narrowed = run(
        rows, request_filters.model_copy(update={"review_stages": ("needs_fiscal_data",)})
    )
    assert narrowed.matching_count == answer.overview.needs_fiscal_data


@pytest.mark.parametrize(
    "stages,expected",
    [([], 1), (["needs_fiscal_data", "ready_for_export"], 1), (["ready_for_export"], 0)],
)
def test_fiscal_count_respects_existing_review_stages(stages, expected):
    rows = [
        record("missing", stage="needs_fiscal_data"),
        record("ready", stage="ready_for_export"),
    ]
    answer = run(rows, ReportFilters(review_stages=stages))
    assert answer.overview.needs_fiscal_data == expected
    assert answer.overview.ready_for_export == 1


def test_fiscal_count_is_zero_when_search_matches_no_rows():
    answer = run(
        [record(stage="needs_fiscal_data", counterparty="Taller")],
        ReportFilters(q="absent"),
    )
    assert answer.overview.needs_fiscal_data == answer.matching_count == 0
