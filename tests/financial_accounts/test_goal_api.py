from uuid import uuid4

import pytest

from financial_accounts.conftest import ALICE, BOB, GUEST


def test_goal_http_commands_snapshot_search_and_owner_boundary(client):
    headers = {"Authorization": f"Bearer {ALICE}", "Idempotency-Key": str(uuid4())}
    account = client.post(
        "/api/v1/financial-accounts",
        headers=headers,
        json={
            "type": "savings",
            "currency": "DOP",
            "amount": "1000",
            "as_of": "2026-09-01T12:00:00-04:00",
        },
    ).json()
    path = "/api/v1/financial-plan/goals"
    response = client.post(
        path,
        headers=headers,
        json={
            "name": "Emergency",
            "currency": "DOP",
            "target": "1500",
            "destination_account_id": account["id"],
        },
    )
    assert response.status_code == 200, response.text
    goal = response.json()["goal"]["goal"]
    body = {
        "changes": [
            {
                "goal_id": goal["id"],
                "expected_version": 1,
                "account_id": account["id"],
                "amount": "600",
            }
        ],
        "expected_account_versions": {account["id"]: account["version"]},
    }
    allocated = client.put(path + "/allocations", headers=headers, json=body)
    assert allocated.status_code == 200, allocated.text
    assert allocated.json()["goals"][0]["supported_minor"] == "60000"
    assert client.put(path + "/allocations", headers=headers, json=body).json()[
        "replayed"
    ]
    stale = client.put(
        path + "/allocations", headers=headers | {"Idempotency-Key": "stale"}, json=body
    )
    assert stale.status_code == 409
    for owner, status in [(BOB, 404), (GUEST, 403)]:
        h = {"Authorization": f"Bearer {owner}", "Idempotency-Key": str(uuid4())}
        assert client.get(path + "/" + goal["id"], headers=h).status_code == status
        assert (
            client.patch(
                path + "/" + goal["id"],
                headers=h,
                json={"expected_version": 2, "archived": True},
            ).status_code
            == status
        )
    home = client.get("/api/v1/financial-home", headers=headers).json()["goals"][0]
    plan = client.get("/api/v1/financial-plan", headers=headers).json()["goals"][0]
    hit = client.get(
        "/api/v1/financial-search?kind=goal&q=emergency", headers=headers
    ).json()["items"][0]
    assert (
        home["supported_minor"]
        == plan["supported_minor"]
        == hit["goal"]["supported_minor"]
        == "60000"
    )
    assert hit["goal"]["goal"]["id"] == goal["id"]
    assert client.patch(
        path + "/" + goal["id"],
        headers=headers | {"Idempotency-Key": "archive"},
        json={"expected_version": 2, "archived": True},
    ).json()["goal"]["goal"]["archived"]
    assert client.get("/api/v1/financial-home", headers=headers).json()["goals"] == []


@pytest.mark.parametrize("clear_date", [False, True])
def test_null_archive_edit_keeps_goal_reads_valid_and_date_clearable(client, clear_date):
    headers = {"Authorization": f"Bearer {ALICE}", "Idempotency-Key": str(uuid4())}
    created = client.post(
        "/api/v1/financial-plan/goals",
        headers=headers,
        json={
            "name": "Reserve",
            "currency": "DOP",
            "target": "1500",
            "target_date": "2026-12-01",
        },
    )
    assert created.status_code == 200, created.text
    gid = created.json()["goal"]["goal"]["id"]
    body = {"expected_version": 1, "archived": None}
    if clear_date:
        body["target_date"] = None
    edited = client.patch(
        "/api/v1/financial-plan/goals/" + gid,
        headers=headers,
        json=body,
    )
    assert edited.status_code == 200, edited.text
    results = [edited.json()["goal"]]
    for path, collection in [
        ("/api/v1/financial-plan/goals/" + gid, None),
        ("/api/v1/financial-home", "goals"),
        ("/api/v1/financial-plan", "goals"),
        ("/api/v1/financial-search?kind=goal&q=reserve", "items"),
    ]:
        response = client.get(path, headers=headers)
        assert response.status_code == 200, response.text
        value = response.json()
        if collection:
            value = value[collection][0]
        results.append(value["goal"] if collection == "items" else value)
    for result in results:
        assert result["goal"]["id"] == gid
        assert result["goal"]["version"] == 2
        assert result["goal"]["archived"] is False
        assert result["goal"]["target_date"] == (None if clear_date else "2026-12-01")
        assert result["supported_minor"] == "0"
        assert result["remaining_minor"] == "150000"
