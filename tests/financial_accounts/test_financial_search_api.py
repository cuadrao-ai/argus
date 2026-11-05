from uuid import uuid4

from financial_accounts.conftest import ALICE, BOB, GUEST


def test_search_route_gates_owner_payload_and_query_validation(client, monkeypatch):
    headers = {"Authorization": f"Bearer {ALICE}"}
    created = client.post(
        "/api/v1/financial-accounts",
        headers=headers | {"Idempotency-Key": str(uuid4())},
        json={"type": "cash", "currency": "DOP", "nickname": "Café"},
    )
    assert created.status_code == 201
    path = "/api/v1/financial-search"
    page = client.get(path, headers=headers, params={"q": "cafe"}).json()
    assert page["items"][0]["account"] == created.json()
    for token, status in [(BOB, 200), (GUEST, 403), ("invalid-token", 401)]:
        response = client.get(path, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == status
        if status == 200:
            assert response.json()["items"] == []
    for params in (
        {"limit": 0},
        {"limit": 51},
        {"q": "a" * 513},
        {"kind": "document"},
        {"currency": "usd"},
        {"cursor": "x" * 2049},
    ):
        assert client.get(path, headers=headers, params=params).status_code == 422
    monkeypatch.setenv("ARGUS_FINANCIAL_ACCOUNTS_ENABLED", "false")
    assert client.get(path).status_code == 404


def test_exact_expectation_read_hides_other_owner_and_missing_ids(client):
    headers = {"Authorization": f"Bearer {ALICE}"}
    response = client.post(
        "/api/v1/financial-plan/expectations",
        headers=headers | {"Idempotency-Key": str(uuid4())},
        json={
            "kind": "bill",
            "title": "Expected rent",
            "currency": "DOP",
            "amount": "10",
            "schedule": {"cadence": "once", "start_date": "2028-01-01"},
        },
    )
    assert response.status_code == 201, response.text
    item = response.json()["expectation"]
    path = "/api/v1/financial-plan/expectations/" + item["id"]
    assert client.get(path, headers=headers).json() == item
    assert client.get(path, headers={"Authorization": f"Bearer {BOB}"}).status_code == 404
    assert (
        client.get(
            "/api/v1/financial-plan/expectations/" + str(uuid4()), headers=headers
        ).status_code
        == 404
    )
