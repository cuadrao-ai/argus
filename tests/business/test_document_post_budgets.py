"""Upload, prepare, and the reading toggle spend separate minute budgets."""

from __future__ import annotations

import pytest
from argus.api.documents import _day, _minute

from tests.business.conftest import ALICE
from tests.business.test_business_api import Owner, started


@pytest.fixture
def alice(biz, identities):  # noqa: ANN001
    return started(Owner(biz, ALICE, identities[ALICE]["id"]))


def _post_budget(owner: Owner, path: str, **headers: str):
    if path == "/receipts":
        return owner.upload()
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


def test_four_uploads_then_a_retry_and_each_budget_holds_its_limit(alice: Owner):
    _minute.reset()
    _day.reset()
    reading = _post_budget(alice, "/receipt-reading")
    assert reading.status_code == 200, reading.text
    uploaded = [_post_budget(alice, "/receipts") for _ in range(4)]
    assert [item.status_code for item in uploaded] == [200, 200, 200, 200]
    receipt_id = uploaded[0].json()["id"]
    retry = _post_budget(
        alice, f"/receipts/{receipt_id}/prepare", **{"X-Extraction-Consent": "true"}
    )
    assert retry.status_code == 200, retry.text
    fifth = _post_budget(alice, "/receipts")
    assert fifth.status_code == 200, fifth.text
    sixth = _post_budget(alice, "/receipts")
    assert sixth.status_code == 429
    assert sixth.json()["code"] == "document_rate_limited"
    prepares = [
        _post_budget(
            alice,
            f"/receipts/{receipt_id}/prepare",
            **{"X-Extraction-Consent": "true"},
        )
        for _ in range(4)
    ]
    assert [item.status_code for item in prepares] == [200, 200, 200, 200]
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
