from uuid import uuid4

import pytest

from financial_accounts.conftest import ALICE, BOB, GUEST


def test_http_financial_loop_home_persistence_isolation_and_replay(client):
    headers = {"Authorization": f"Bearer {ALICE}"}
    account = client.post(
        "/api/v1/financial-accounts",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "type": "checking",
            "currency": "DOP",
            "amount": "10000",
            "as_of": "2026-09-01T08:00:00-04:00",
        },
    ).json()
    path = "/api/v1/financial-accounts/" + account["id"]
    body = {
        "expected_version": account["version"],
        "amount": "2000",
        "occurred_at": "2026-09-02T12:00:00-04:00",
        "note": "Groceries",
    }
    preview = client.post(path + "/activity/preview", headers=headers, json=body)
    assert preview.status_code == 200, preview.text
    assert preview.json()["after"]["amount_minor"] == 800000
    body["preview_token"] = preview.json()["preview_token"]
    key = str(uuid4())
    first = client.post(
        path + "/activity", headers={**headers, "Idempotency-Key": key}, json=body
    )
    assert first.status_code == 201, first.text
    expense = first.json()["activity"]
    check = {
        "expected_version": 2,
        "amount": "7500",
        "as_of": "2026-09-03T12:00:00-04:00",
        "note": "Bank app",
    }
    preview = client.post(path + "/balance-checks/preview", headers=headers, json=check)
    assert preview.json()["difference_minor"] == -50000
    check["preview_token"] = preview.json()["preview_token"]
    checked = client.post(
        path + "/balance-checks",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json=check,
    )
    assert checked.status_code == 201, checked.text
    replay = client.post(
        path + "/activity", headers={**headers, "Idempotency-Key": key}, json=body
    )
    assert replay.status_code == 200 and replay.json()["replayed"]
    assert replay.json()["account"]["version"] == 3
    late = {
        "expected_version": 3,
        "amount": "500",
        "occurred_at": "2026-09-02T10:00:00-04:00",
        "coverage": [
            {"observation_id": checked.json()["check"]["record_id"], "included": True}
        ],
    }
    late["preview_token"] = client.post(
        path + "/activity/preview", headers=headers, json=late
    ).json()["preview_token"]
    result = client.post(
        path + "/activity",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json=late,
    )
    assert result.status_code == 201, result.text
    assert result.json()["account"]["balance"]["amount_minor"] == 750000
    home = client.get("/api/v1/financial-home", headers=headers).json()
    assert home["currencies"][0]["net_worth_minor"] == "750000"
    assert home["currencies"][0]["recorded_spending_minor"] == "250000"
    assert client.get(path, headers=headers).json()["balance"]["amount_minor"] == 750000
    assert (
        client.get(path + "/balance-checks", headers=headers).json()["items"][0][
            "unexplained_minor"
        ]
        == 0
    )
    for suffix in (
        "",
        "/activity",
        "/balance-checks",
        "/activity/" + expense["record_id"],
    ):
        assert (
            client.get(
                path + suffix, headers={"Authorization": f"Bearer {BOB}"}
            ).status_code
            == 404
        )
    assert (
        client.get(
            "/api/v1/financial-home", headers={"Authorization": f"Bearer {GUEST}"}
        ).status_code
        == 403
    )


@pytest.mark.usefixtures("legacy_blank_accounts")
def test_opening_route_cannot_bypass_review_after_expense(client):
    headers = {"Authorization": f"Bearer {ALICE}"}
    account = client.post(
        "/api/v1/financial-accounts",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"type": "cash", "currency": "DOP"},
    ).json()
    path = "/api/v1/financial-accounts/" + account["id"]
    body = {
        "expected_version": 1,
        "amount": "50",
        "occurred_at": "2026-09-02T12:00:00-04:00",
    }
    body["preview_token"] = client.post(
        path + "/activity/preview", headers=headers, json=body
    ).json()["preview_token"]
    client.post(
        path + "/activity",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json=body,
    )
    denied = client.put(
        path + "/opening", headers=headers, json={"expected_version": 2, "amount": "100"}
    )
    assert denied.status_code == 400
    assert client.get(path, headers=headers).json()["balance"]["state"] == "unknown"


@pytest.mark.usefixtures("legacy_blank_accounts")
def test_native_uppercase_ids_return_committed_opening_and_activity(client):
    headers = {"Authorization": f"Bearer {ALICE}"}
    account = client.post(
        "/api/v1/financial-accounts",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"type": "cash", "currency": "USD"},
    ).json()
    path = "/api/v1/financial-accounts/" + account["id"].upper()
    opening = {
        "expected_version": 1,
        "amount": "100",
        "as_of": "2026-09-01T08:00:00-04:00",
    }
    opening["preview_token"] = client.post(
        path + "/opening/preview", headers=headers, json=opening
    ).json()["preview_token"]
    response = client.put(
        path + "/opening",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json=opening,
    )
    assert response.status_code == 200, response.text
    assert response.json()["balance"]["amount_minor"] == 10000
    body = {
        "expected_version": 2,
        "amount": "10",
        "occurred_at": "2026-09-01T12:00:00-04:00",
        "coverage": [
            {
                "observation_id": response.json()["opening"]["record_id"].upper(),
                "included": True,
            }
        ],
    }
    body["preview_token"] = client.post(
        path + "/activity/preview", headers=headers, json=body
    ).json()["preview_token"]
    expense = client.post(
        path + "/activity",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json=body,
    )
    assert expense.status_code == 201, expense.text
    assert (
        client.get(
            path + "/activity/" + expense.json()["activity"]["record_id"].upper(),
            headers=headers,
        ).status_code
        == 200
    )
