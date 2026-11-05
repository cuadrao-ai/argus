from uuid import uuid4

from financial_accounts.conftest import ALICE, BOB, GUEST


def test_budget_http_contract_replay_duplicate_scope_and_owner_isolation(client):
    headers = {"Authorization": f"Bearer {ALICE}", "Idempotency-Key": str(uuid4())}
    aid = client.post(
        "/api/v1/financial-accounts",
        headers=headers,
        json={"type": "credit_card", "currency": "DOP"},
    ).json()["id"]
    body = {
        "name": "Groceries",
        "limit": "150",
        "currency": "DOP",
        "month": "2026-09",
        "account_ids": [aid],
        "category_ids": ["groceries"],
        "include_uncategorized": False,
    }
    path = "/api/v1/financial-plan/budgets"
    first = client.post(path, headers=headers, json=body)
    assert first.status_code == 201, first.text
    bid = first.json()["budget"]["id"]
    assert client.post(path, headers=headers, json=body).json()["replayed"]
    duplicate = client.post(
        path, headers=headers | {"Idempotency-Key": str(uuid4())}, json=body
    )
    assert (
        duplicate.status_code == 409
        and duplicate.json()["code"] == "budget_scope_conflict"
    )
    detail = client.get(path + "/" + bid, headers=headers).json()
    assert detail["spent_minor"] == "0" and detail["remaining_minor"] == "15000"
    assert client.get("/api/v1/financial-home", headers=headers).json()["budgets"] == [
        detail
    ]
    assert client.get("/api/v1/financial-plan", headers=headers).json()["budgets"] == [
        detail
    ]
    hit = client.get(
        "/api/v1/financial-search?kind=budget&q=groceries", headers=headers
    ).json()["items"][0]
    assert hit["kind"] == "budget" and hit["budget"]["id"] == bid
    for owner, status in [(BOB, 404), (GUEST, 403)]:
        h = {"Authorization": f"Bearer {owner}", "Idempotency-Key": str(uuid4())}
        assert client.get(path + "/" + bid, headers=h).status_code == status
        assert (
            client.patch(
                path + "/" + bid,
                headers=h,
                json={"expected_version": 1, "archived": True},
            ).status_code
            == status
        )
    for identifier, replayed in [(bid.upper(), False), (bid, True)]:
        result = client.patch(
            path + "/" + identifier,
            headers=headers | {"Idempotency-Key": "edit"},
            json={"expected_version": 1, "limit": "160"},
        )
        assert result.status_code == 200 and result.json()["replayed"] is replayed
    stale = client.patch(
        path + "/" + bid,
        headers=headers | {"Idempotency-Key": "stale"},
        json={"expected_version": 1, "limit": "1"},
    )
    assert stale.status_code == 409
