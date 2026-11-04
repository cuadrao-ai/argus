"""Uploads spend a 60-a-minute budget per person and no daily one. Prepare and
the reading toggle keep their own minute budgets."""

from __future__ import annotations

import pytest
from argus.api.documents import _minute

from tests.business.conftest import ALICE
from tests.business.test_business_api import Owner, started


@pytest.fixture
def alice(biz, identities):  # noqa: ANN001
    return started(Owner(biz, ALICE, identities[ALICE]["id"]))


def _post_budget(owner: Owner, path: str, **headers: str):
    if path == "/receipts":
        return owner.upload(consent=False)
    if path == "/receipt-reading":
        shown = owner.get("/receipt-reading").json()
        return owner.post(
            path,
            {
                "enabled": True,
                "scope_version": shown["scope_version"],
                "disclosure_token": shown["disclosure_token"],
            },
        )
    return owner.post(path, **headers)


def test_sixty_uploads_a_minute_pass_and_the_sixty_first_waits(alice: Owner):
    _minute.reset()
    uploaded = [_post_budget(alice, "/receipts") for _ in range(60)]
    assert [item.status_code for item in uploaded] == [200] * 60, uploaded[-1].text
    refused = _post_budget(alice, "/receipts")
    assert refused.status_code == 429
    assert refused.json()["code"] == "document_rate_limited"
    assert refused.headers["Retry-After"]


def test_prepare_and_the_reading_toggle_keep_their_own_minute_budgets(alice: Owner):
    _minute.reset()
    reading = _post_budget(alice, "/receipt-reading")
    assert reading.status_code == 200, reading.text
    receipt_id = alice.upload().json()["id"]
    prepares = [
        _post_budget(
            alice,
            f"/receipts/{receipt_id}/prepare",
            **{"X-Extraction-Consent": "true"},
        )
        for _ in range(5)
    ]
    assert [item.status_code for item in prepares] == [200] * 5
    blocked = _post_budget(
        alice, f"/receipts/{receipt_id}/prepare", **{"X-Extraction-Consent": "true"}
    )
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "document_rate_limited"
    toggles = [_post_budget(alice, "/receipt-reading") for _ in range(4)]
    assert all(item.status_code != 429 for item in toggles)
    limited = _post_budget(alice, "/receipt-reading")
    assert limited.status_code == 429
    assert limited.json()["code"] == "document_rate_limited"
    assert alice.upload().status_code == 200
