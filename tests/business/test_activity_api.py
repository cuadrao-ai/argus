from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.business.test_business_api import Owner, started
from tests.ingestion.conftest import ALICE


@pytest.fixture
def alice(biz: TestClient, identities) -> Owner:
    return started(Owner(biz, ALICE, identities[ALICE]["id"]))


def test_the_feed_is_empty_without_a_store(alice: Owner):
    page = alice.get("/activity")
    assert (page.status_code, page.json()) == (200, {"items": [], "next_cursor": None})
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
