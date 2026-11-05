from __future__ import annotations

from datetime import date

import pytest
from argus.domain.business.activity.catalog import project
from argus.domain.business.activity.queries import encode_cursor
from argus.domain.business.contracts.activity import ActivityFilters
from fastapi.testclient import TestClient

from tests.business.test_activity_projection import NONE, row
from tests.business.test_business_api import BASE, Owner, started
from tests.ingestion.conftest import ALICE


@pytest.fixture
def alice(biz: TestClient, identities) -> Owner:
    return started(Owner(biz, ALICE, identities[ALICE]["id"]))


def _get(alice: Owner, params: dict):
    return alice.client.get(BASE + "/activity", params=params, headers=alice.auth)


def test_the_feed_is_empty_without_a_store(alice: Owner):
    page = alice.get("/activity")
    assert (page.status_code, page.json()) == (
        200,
        {"items": [], "next_cursor": None, "actors": []},
    )
    assert page.headers["cache-control"] == "no-store"


def test_only_the_three_page_sizes_are_accepted(alice: Owner):
    for size in ("25", "50", "100"):
        assert alice.get("/activity", limit=size).status_code == 200
    refused = alice.get("/activity", limit="30")
    assert (refused.status_code, refused.json()["code"]) == (422, "validation_error")


def test_a_cursor_the_feed_did_not_issue_is_refused(alice: Owner):
    refused = alice.get("/activity", cursor="not-a-cursor")
    assert (refused.status_code, refused.json()["code"]) == (422, "invalid_cursor")
    assert refused.headers["cache-control"] == "no-store"


def test_a_cursor_continues_only_the_filter_set_that_issued_it(alice: Owner):
    item = project(row({"action": "review_draft"}))
    issued = encode_cursor(
        item, ActivityFilters(areas=("records",), since=date(2026, 10, 1))
    )
    continued = _get(alice, {"cursor": issued, "area": "records", "from": "2026-10-01"})
    assert continued.status_code == 200
    assert continued.json()["actors"] is None
    for params in (
        {"cursor": issued},
        {"cursor": issued, "area": "records"},
        {"cursor": issued, "area": ["records", "documents"], "from": "2026-10-01"},
        {"cursor": issued, "area": "records", "from": "2026-10-01", "to": "2026-10-31"},
    ):
        refused = _get(alice, params)
        assert (refused.status_code, refused.json()["code"]) == (
            422,
            "invalid_cursor",
        ), params
    unfiltered = alice.get("/activity", cursor=encode_cursor(item, NONE))
    assert (unfiltered.status_code, unfiltered.json()["actors"]) == (200, None)


def test_filters_are_validated_at_the_boundary(alice: Owner):
    ok = _get(
        alice,
        {
            "from": "2026-10-01",
            "to": "2026-10-01",
            "actor": ["a" * 32, "b" * 32],
            "area": ["documents", "records"],
            "action_group": ["uploads", "access"],
        },
    )
    assert ok.status_code == 200, ok.text
    reversed_range = _get(alice, {"from": "2026-10-02", "to": "2026-10-01"})
    assert (reversed_range.status_code, reversed_range.json()["code"]) == (
        422,
        "invalid_date_range",
    )
    assert reversed_range.headers["cache-control"] == "no-store"
    for params in (
        {"from": "yesterday"},
        {"to": "2026-13-01"},
        {"actor": "ana@example.test"},
        {"actor": "A" * 32},
        {"actor": ["a" * 32] * 51},
        {"area": "mail"},
        {"action_group": "deletes"},
    ):
        refused = _get(alice, params)
        assert (refused.status_code, refused.json()["code"]) == (
            422,
            "validation_error",
        ), params


def test_the_last_calendar_day_is_refused_as_a_range_end(alice: Owner):
    """The day after 9999-12-31 does not exist, so the range has no end to
    compute; the answer is the same refusal as a reversed range, not a 500."""

    for params in ({"to": "9999-12-31"}, {"from": "9999-12-31", "to": "9999-12-31"}):
        refused = _get(alice, params)
        assert (refused.status_code, refused.json()["code"]) == (
            422,
            "invalid_date_range",
        ), params
        assert refused.headers["cache-control"] == "no-store"
    assert _get(alice, {"from": "9999-12-31"}).status_code == 200
    assert _get(alice, {"to": "9999-12-30"}).status_code == 200
