"""End to end over HTTP: connector evidence reaches the one review queue and is
recorded only after the person confirms it."""

import base64
import os

import httpx
import pytest
from argus.api.ingestion import ingestion_hub
from argus.api.plaid import configure_plaid_connector, plaid_connector
from argus.domain.ingestion.plaid.connector import PlaidConnector
from argus.domain.ingestion.reconcile.service import ReconciliationService
from argus.domain.owner_scope import PERSONAL

from tests.ingestion.conftest import ALICE, BOB, GUEST, bearer
from tests.ingestion.plaid_fakes import PUBLIC_TOKEN, FakePlaid, page, txn
from tests.ingestion.shortcuts_support import EVENTS, enroll, tap

IMPORTS = "/api/v1/financial-imports"


@pytest.fixture(autouse=True)
def provider_env(monkeypatch):
    key = base64.urlsafe_b64encode(os.urandom(32)).decode()
    monkeypatch.setenv("ARGUS_INGESTION_SECRET_KEY", key)
    monkeypatch.setenv("PLAID_CLIENT_ID", "client-id")
    monkeypatch.setenv("PLAID_SECRET", "plaid-secret-value")
    monkeypatch.setenv("PLAID_ENV", "sandbox")


@pytest.fixture
def plaid(client):  # noqa: ANN001
    started = plaid_connector()
    fake = FakePlaid(sync={None: [page(added=[txn("t1", 4.5)], next_cursor="c1")]})
    hub = ingestion_hub()
    connector = PlaidConnector(hub, started.config, transport=httpx.MockTransport(fake))
    hub.register(connector.adapter)
    configure_plaid_connector(connector)
    return fake


def _user(client):  # noqa: ANN001
    accounts = ingestion_hub().sink.money.accounts
    owners = {s.account.user_id for s in accounts._repository._accounts.values()}
    [owner] = owners
    return owner


def checking_account(client, token=ALICE):  # noqa: ANN001
    response = client.post(
        "/api/v1/financial-accounts",
        json={"type": "checking", "currency": "USD", "nickname": "Chase"},
        headers={**bearer(token), "Idempotency-Key": os.urandom(8).hex()},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_reconciliation_is_the_wired_sink(client):  # noqa: ANN001
    assert isinstance(ingestion_hub().sink, ReconciliationService)


def test_plaid_import_is_reviewed_then_recorded_once(client, plaid):  # noqa: ANN001, F811
    account = checking_account(client)
    exchange = client.post(
        "/api/v1/financial-connections/plaid/exchange",
        json={"public_token": PUBLIC_TOKEN},
        headers=bearer(ALICE),
    )
    assert exchange.status_code == 201, exchange.text
    [event] = client.get(IMPORTS, headers=bearer(ALICE)).json()["items"]
    assert event["observations"][0]["source"] == "plaid"
    assert event["facts"]["amount"] == "4.5" and event["facts"]["currency"] == "USD"
    assert "account_id" in event["unresolved"]
    # A draft changes no account: same version, same balance, no activity.
    before_draft = client.get(
        f"/api/v1/financial-accounts/{account}", headers=bearer(ALICE)
    ).json()
    assert before_draft["version"] == 1
    assert (
        ingestion_hub().sink.money.purchases(user_id=_user(client), scope=PERSONAL)[
            "items"
        ]
        == []
    )

    resolved = client.patch(
        f"{IMPORTS}/{event['id']}",
        json={"version": event["version"], "changes": {"account_id": account}},
        headers=bearer(ALICE),
    ).json()
    assert resolved["unresolved"] == []
    assert resolved["account_shared_with_household"] is False
    preview = client.post(
        f"{IMPORTS}/{event['id']}/preview", json={}, headers=bearer(ALICE)
    ).json()["preview"]
    assert preview["ready"] is True
    body = {
        "version": resolved["version"],
        "request": {
            **preview["reviewed_request"],
            "preview_token": preview["preview_token"],
        },
    }
    missing_key = client.post(
        f"{IMPORTS}/{event['id']}/accept", json=body, headers=bearer(ALICE)
    )
    assert missing_key.status_code == 400
    headers = {**bearer(ALICE), "Idempotency-Key": "accept-t1"}
    accepted = client.post(f"{IMPORTS}/{event['id']}/accept", json=body, headers=headers)
    assert accepted.status_code == 200, accepted.text
    activity = accepted.json()["activity"]
    assert activity["amount"] == "4.50" and activity["kind"] == "expense"
    assert activity["note"] == "Blue Bottle Coffee"
    replay = client.post(f"{IMPORTS}/{event['id']}/accept", json=body, headers=headers)
    assert replay.json()["replayed"] is True
    assert replay.json()["activity"]["activity_id"] == activity["activity_id"]
    other_key = client.post(
        f"{IMPORTS}/{event['id']}/accept",
        json=body,
        headers={**bearer(ALICE), "Idempotency-Key": "another"},
    )
    assert other_key.status_code == 409
    assert other_key.json()["code"] == "import_already_accepted"
    detail = client.get(
        f"/api/v1/financial-activities/{activity['activity_id']}", headers=bearer(ALICE)
    )
    assert detail.status_code == 200
    after = client.get(f"/api/v1/financial-accounts/{account}", headers=bearer(ALICE))
    assert after.json()["version"] == before_draft["version"] + 1
    assert (
        len(
            ingestion_hub().sink.money.purchases(user_id=_user(client), scope=PERSONAL)[
                "items"
            ]
        )
        == 1
    )
    assert client.get(IMPORTS, headers=bearer(ALICE)).json()["items"] == []
    [done] = client.get(f"{IMPORTS}?state=accepted", headers=bearer(ALICE)).json()[
        "items"
    ]
    assert done["activity_id"] == activity["activity_id"]


def test_imports_are_private_and_versioned(client, plaid):  # noqa: ANN001, F811
    client.post(
        "/api/v1/financial-connections/plaid/exchange",
        json={"public_token": PUBLIC_TOKEN},
        headers=bearer(ALICE),
    )
    [event] = client.get(IMPORTS, headers=bearer(ALICE)).json()["items"]
    assert client.get(IMPORTS, headers=bearer(BOB)).json()["items"] == []
    assert client.get(f"{IMPORTS}/{event['id']}", headers=bearer(BOB)).status_code == 404
    assert client.get(IMPORTS, headers=bearer(GUEST)).status_code == 403
    stale = client.post(
        f"{IMPORTS}/{event['id']}/dismiss",
        json={"version": event["version"] + 5},
        headers=bearer(ALICE),
    )
    assert stale.status_code == 409 and stale.json()["code"] == "stale_version"
    dismissed = client.post(
        f"{IMPORTS}/{event['id']}/dismiss",
        json={"version": event["version"]},
        headers=bearer(ALICE),
    )
    assert dismissed.json()["state"] == "dismissed"
    assert client.get(f"{IMPORTS}/not-a-uuid", headers=bearer(ALICE)).status_code == 404
    unknown = client.patch(
        f"{IMPORTS}/{event['id']}",
        json={"version": 1, "changes": {"activity_id": "x"}},
        headers=bearer(ALICE),
    )
    assert unknown.status_code == 422


def test_shortcuts_tap_lands_in_review_and_disconnect_removes_drafts(client):  # noqa: ANN001
    device = enroll(client)
    response = client.post(
        EVENTS, json=tap(amount="US$ 4.50"), headers=bearer(device["device_token"])
    )
    assert response.status_code == 200, response.text
    [event] = client.get(IMPORTS, headers=bearer(ALICE)).json()["items"]
    [observation] = event["observations"]
    assert observation["source"] == "shortcuts" and observation["status"] == "unknown"
    assert event["facts"]["currency"] == "USD" and event["facts"]["amount"] == "4.5"
    ended = client.post(
        f"/api/v1/financial-connections/{device['connection']['id']}/disconnect",
        headers=bearer(ALICE),
    ).json()
    assert ended["unreviewed_removed"] == 1
    assert client.get(IMPORTS, headers=bearer(ALICE)).json()["items"] == []


def test_flag_off_hides_the_queue(surface_env, gateway):  # noqa: ANN001
    from unittest.mock import patch

    from argus.api import state as api_state
    from argus.api.main import app
    from fastapi.testclient import TestClient

    with (
        patch.object(api_state, "supabase_gateway", gateway),
        patch("argus.api.dependencies.auth_session_is_active", return_value=True),
        TestClient(app) as test_client,
    ):
        for response in (
            test_client.get(IMPORTS, headers=bearer(ALICE)),
            test_client.get(IMPORTS),
        ):
            assert response.status_code == 404


def test_invalid_review_input_is_a_client_problem(client, plaid):  # noqa: ANN001, F811
    account = checking_account(client)
    client.post(
        "/api/v1/financial-connections/plaid/exchange",
        json={"public_token": PUBLIC_TOKEN},
        headers=bearer(ALICE),
    )
    [event] = client.get(IMPORTS, headers=bearer(ALICE)).json()["items"]
    event = client.patch(
        f"{IMPORTS}/{event['id']}",
        json={"version": event["version"], "changes": {"account_id": account}},
        headers=bearer(ALICE),
    ).json()
    bogus = client.post(
        f"{IMPORTS}/{event['id']}/preview",
        json={"overrides": {"kind": "bogus"}},
        headers=bearer(ALICE),
    )
    assert bogus.status_code == 422 and bogus.json()["code"] == "activity_invalid"
    stored = client.patch(
        f"{IMPORTS}/{event['id']}",
        json={"version": event["version"], "changes": {"kind": "bogus"}},
        headers=bearer(ALICE),
    )
    assert stored.status_code == 422 and stored.json()["code"] == "kind_invalid"
    merge = client.post(
        f"{IMPORTS}/{event['id']}/merge",
        json={"version": event["version"], "into_event_id": event["id"]},
        headers=bearer(ALICE),
    )
    assert merge.status_code == 422
