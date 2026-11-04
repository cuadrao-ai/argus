"""Open drafts left Registros, so `awaiting_approval` is no stage. A saved view
or an old tab that still names it keeps the stages that remain."""

import pytest
from argus.domain.business.reporting_query import ReportFilters, ReportRequest
from pydantic import ValidationError


@pytest.mark.parametrize(
    ("sent", "kept"),
    [
        (["awaiting_approval"], ()),
        (["awaiting_approval", "exported"], ("exported",)),
        (
            ["needs_fiscal_data", "awaiting_approval", "ready_for_export"],
            ("needs_fiscal_data", "ready_for_export"),
        ),
        (["needs_review"], ("needs_review",)),
    ],
)
def test_removed_stage_is_dropped_from_filters_and_request_bodies(sent, kept):
    assert ReportFilters(review_stages=sent).review_stages == kept
    request = ReportRequest(filters={"review_stages": sent})
    assert request.filters.review_stages == kept


def test_an_unknown_stage_is_still_refused():
    with pytest.raises(ValidationError):
        ReportFilters(review_stages=["awaiting_approval", "not_a_stage"])
