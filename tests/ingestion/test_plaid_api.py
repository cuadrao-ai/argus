"""Plaid routes over the real auth dependency with a scripted provider."""

from unittest.mock import patch

from argus.api import state as api_state
from argus.api.ingestion import ingestion_hub
from argus.api.main import app
from argus.api.plaid import configure_plaid_connector
from argus.domain.owner_scope import PERSONAL
from fastapi.testclient import TestClient

from tests.ingestion.conftest import ALICE, BOB, GUEST, bearer
from tests.ingestion.plaid_api_support import (  # noqa: F401
    SECRET,
    URL,
    connect,
    logs,
    plaid,
    plaid_env,
)
from tests.ingestion.plaid_fakes import ACCESS_TOKEN, PUBLIC_TOKEN


def test_flag_off_hides_every_plaid_route(surface_env, gateway):  # noqa: ANN001
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        patch("argus.api.dependencies.auth_session_is_active", return_value=True),
        TestClient(app) as client,
    ):
        responses = [
            client.post(f"{URL}/link-token", headers=bearer(ALICE)),
            client.post(
                f"{URL}/exchange",
                json={"public_token": PUBLIC_TOKEN},
                headers=bearer(ALICE),
            ),
            client.post(
                f"{URL}/webhook", content=b"{}", headers={"Plaid-Verification": "x"}
            ),
            client.post(f"{URL}/abc/sync", headers=bearer(ALICE)),
        ]
    for response in responses:
        assert response.status_code == 404
        assert response.json()["code"] == "financial_connections_unavailable"


def test_unconfigured_plaid_is_absent(client, monkeypatch):  # noqa: ANN001
    configure_plaid_connector(None)
    assert client.post(f"{URL}/link-token", headers=bearer(ALICE)).status_code == 404
    assert client.post(f"{URL}/webhook", content=b"{}").status_code == 404


def test_guests_and_anonymous_callers_are_refused(client, plaid):  # noqa: ANN001, F811
    assert client.post(f"{URL}/link-token", headers=bearer(GUEST)).status_code == 403
    assert client.post(f"{URL}/link-token").status_code == 401


def test_link_exchange_and_initial_sync_without_exposing_tokens(client, plaid, logs):  # noqa: ANN001, F811
    link = client.post(
        f"{URL}/link-token", json={"language": "es"}, headers=bearer(ALICE)
    )
    assert link.status_code == 200 and link.json()["link_token"] == "link-sandbox-new"
    first = connect(client)
    assert first.status_code == 201 and first.json()["created"] is True
    connection = first.json()["connection"]
    assert (
        connection["source"] == "plaid" and connection["label"] == "First Platypus Bank"
    )
    # The initial sync ran after the response.
    sink = ingestion_hub().sink
    assert [c.source.external_id for c in sink.batches[0]] == ["t1"]
    retry = connect(client)
    assert retry.status_code == 200 and retry.json()["created"] is False
    assert retry.json()["connection"]["id"] == connection["id"]
    listed = client.get("/api/v1/financial-connections", headers=bearer(ALICE)).json()
    synced = client.post(f"{URL}/{connection['id']}/sync", headers=bearer(ALICE))
    assert synced.json()["sync"]["status"] == "synced"
    for text in [link.text, first.text, retry.text, synced.text, str(listed), *logs]:
        assert ACCESS_TOKEN not in text and SECRET not in text
    assert any("Plaid sync finished" in line for line in logs)


def test_invalid_public_token_is_a_client_problem(client, plaid):  # noqa: ANN001, F811
    bad = client.post(
        f"{URL}/exchange",
        json={"public_token": "public-sandbox-wrong"},
        headers=bearer(ALICE),
    )
    assert bad.status_code == 422 and bad.json()["code"] == "plaid_request_invalid"
    assert bad.json()["context"] == {"plaid_error_code": "INVALID_PUBLIC_TOKEN"}
    malformed = client.post(
        f"{URL}/exchange",
        json={"public_token": "access-sandbox-x"},
        headers=bearer(ALICE),
    )
    assert malformed.status_code == 422


def test_other_peoples_connections_are_not_found(client, plaid):  # noqa: ANN001, F811
    connection_id = connect(client).json()["connection"]["id"]
    for path in ("sync", "link-token", "reconnected"):
        response = client.post(f"{URL}/{connection_id}/{path}", headers=bearer(BOB))
        assert response.status_code == 404
        assert response.json()["code"] == "financial_connection_not_found"
    assert client.post(f"{URL}/not-a-uuid/sync", headers=bearer(ALICE)).status_code == 404


def test_reauth_round_trip_keeps_cursor_and_freshness(client, plaid, identities, logs):  # noqa: ANN001, F811
    connection_id = connect(client).json()["connection"]["id"]
    healthy = client.post(f"{URL}/{connection_id}/link-token", headers=bearer(ALICE))
    assert healthy.status_code == 409
    plaid.item_error = "ITEM_LOGIN_REQUIRED"
    failed = client.post(f"{URL}/{connection_id}/sync", headers=bearer(ALICE)).json()
    assert failed["sync"]["error_code"] == "plaid_item_login_required"
    assert failed["connection"]["status"] == "needs_reauth"
    fresh = failed["connection"]["last_success_at"]
    assert fresh is not None
    update = client.post(f"{URL}/{connection_id}/link-token", headers=bearer(ALICE))
    assert (
        update.status_code == 200 and update.json()["link_token"] == "link-sandbox-update"
    )
    plaid.item_error = None
    restored = client.post(
        f"{URL}/{connection_id}/reconnected", headers=bearer(ALICE)
    ).json()
    assert restored["status"] == "active" and restored["last_error_code"] is None
    row = ingestion_hub().connections.get(
        user_id=identities[ALICE]["id"], connection_id=connection_id, scope=PERSONAL
    )
    assert row.cursor == "c1" and restored["last_success_at"] == fresh
    assert any("plaid_item_login_required" in line for line in logs)
    assert not any(ACCESS_TOKEN in line or SECRET in line for line in logs)


def test_disconnect_revokes_the_item(client, plaid, logs):  # noqa: ANN001, F811
    connection_id = connect(client).json()["connection"]["id"]
    body = client.post(
        f"/api/v1/financial-connections/{connection_id}/disconnect", headers=bearer(ALICE)
    ).json()
    assert body["provider_revocation"] == "revoked" and body["unreviewed_removed"] == 1
    assert "/item/remove" in plaid.paths()
    gone = client.post(f"{URL}/{connection_id}/sync", headers=bearer(ALICE))
    assert gone.status_code == 409
    assert ACCESS_TOKEN not in str(body)
    assert not any(ACCESS_TOKEN in line or SECRET in line for line in logs)
