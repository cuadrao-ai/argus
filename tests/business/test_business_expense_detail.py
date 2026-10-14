"""GET /api/v1/business/expenses/{id}: one saved expense of this Business with
when it was recorded and its revision; another Business's expense, or any
unknown id, is not found. An expense entered by hand names no receipt and
no draft."""

from __future__ import annotations

from uuid import uuid4

from tests.business.test_business_api import Owner, alice, bob  # noqa: F401


def test_a_hand_entered_expense_opens_as_its_own_detail(alice: Owner) -> None:  # noqa: F811
    account = alice.account("DOP")
    saved = alice.post(
        "/expenses",
        {
            "account_id": account,
            "amount": "2100.00",
            "occurred_on": "2026-10-04",
            "merchant": "Estación Ruta 3",
            "category_id": "transport",
        },
        key=str(uuid4()),
    )
    assert saved.status_code == 201, saved.text
    expense_id = saved.json()["id"]
    [listed] = alice.get(
        "/expenses", **{"from": "2026-10-01", "to": "2026-10-31"}
    ).json()["items"]
    # No receipt and no draft: the wire omits a null draft id.
    assert (listed["id"], listed["receipt_id"], listed.get("draft_id")) == (
        expense_id,
        None,
        None,
    )
    detail = alice.get(f"/expenses/{expense_id}")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert (body["id"], body["merchant"], body["amount"], body["currency"]) == (
        expense_id,
        "Estación Ruta 3",
        "2100.00",
        "DOP",
    )
    assert (body["receipt_id"], body.get("draft_id")) == (None, None)
    assert body["recorded_at"] is not None
    assert body["revision"] == 1


def test_another_business_and_an_unknown_id_stay_closed(alice: Owner, bob: Owner) -> None:  # noqa: F811
    account = alice.account("DOP")
    saved = alice.post(
        "/expenses",
        {
            "account_id": account,
            "amount": "99.00",
            "occurred_on": "2026-10-05",
            "merchant": "Colmado",
            "category_id": "other",
        },
        key=str(uuid4()),
    )
    assert saved.status_code == 201, saved.text
    expense_id = saved.json()["id"]
    bob.start()
    closed = bob.get(f"/expenses/{expense_id}")
    assert (closed.status_code, closed.json()["code"]) == (404, "expense_not_found")
    unknown = alice.get(f"/expenses/{uuid4()}")
    assert (unknown.status_code, unknown.json()["code"]) == (404, "expense_not_found")
