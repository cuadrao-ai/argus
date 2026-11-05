from datetime import datetime, timezone
from uuid import uuid4

from financial_accounts.conftest import ALICE, BOB, GUEST


def test_plan_http_round_trip_selection_cutover_and_access(client):
    headers = {"Authorization": f"Bearer {ALICE}"}

    def post(path, body):
        response = client.post(
            "/api/v1" + path,
            headers=headers | {"Idempotency-Key": str(uuid4())},
            json=body,
        )
        assert response.status_code in (200, 201), response.text
        return response.json()

    account = post(
        "/financial-accounts",
        {
            "type": "cash",
            "currency": "DOP",
            "amount": "100",
            "as_of": "2026-09-01T12:00:00-04:00",
        },
    )
    today = client.get("/api/v1/financial-plan", headers=headers).json()["start_date"]
    expectation = post(
        "/financial-plan/expectations",
        {
            "kind": "bill",
            "title": "Rent",
            "currency": "DOP",
            "amount": "25",
            "account_id": account["id"],
            "schedule": {"cadence": "once", "start_date": today},
        },
    )["expectation"]
    selection = client.put(
        "/api/v1/financial-plan/selection",
        headers=headers | {"Idempotency-Key": "selection"},
        json={
            "expected_version": 0,
            "account_ids": [account["id"]],
            "time_zone": "America/Santo_Domingo",
        },
    )
    assert selection.status_code == 200, selection.text
    occurrence = client.get("/api/v1/financial-plan", headers=headers).json()[
        "occurrences"
    ][0]
    wrapper = {
        "expected_version": expectation["version"],
        "activity": {
            "kind": "expense",
            "account_id": account["id"],
            "amount": "25",
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    path = "/financial-plan/occurrences/" + occurrence["id"] + "/fulfillment"
    preview = post(path + "/preview", wrapper)["money"]
    wrapper["activity"] = preview["reviewed_request"] | {
        "preview_token": preview["preview_token"]
    }
    receipt = post(path, wrapper)
    assert receipt["occurrence"]["status"] == "fulfilled"
    for user, expected in [(BOB, 404), (GUEST, 403)]:
        response = client.get(
            "/api/v1/financial-plan/occurrences/" + occurrence["id"] + "/candidates",
            headers={"Authorization": f"Bearer {user}"},
        )
        assert response.status_code == expected, response.text
    unsafe = client.patch(
        "/api/v1/financial-plan/expectations/" + expectation["id"],
        headers=headers | {"Idempotency-Key": "unsafe"},
        json={
            "expected_version": 1,
            "schedule": {"cadence": "once", "start_date": today},
            "effective_date": today,
        },
    )
    assert unsafe.status_code == 422 and unsafe.json()["code"] == "plan_cutover_unsafe"
    assert "earliest_effective_date" in unsafe.json()

    native_body = {"expected_version": 1, "amount": "30"}
    for identifier, replayed in [
        (expectation["id"].upper(), False),
        (expectation["id"], True),
    ]:
        native_edit = client.patch(
            "/api/v1/financial-plan/expectations/" + identifier,
            headers=headers | {"Idempotency-Key": "native-edit"},
            json=native_body,
        )
        assert native_edit.status_code == 200, native_edit.text
        assert native_edit.json()["expectation"]["amount"] == "30.00"
        assert native_edit.json()["replayed"] is replayed
