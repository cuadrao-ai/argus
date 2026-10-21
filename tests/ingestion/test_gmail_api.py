"""Gmail routes over the real auth dependency and startup wiring."""

from unittest.mock import patch

import pytest
from argus.api import state as api_state
from argus.api.gmail import gmail_connector, revoke_only_adapter
from argus.api.ingestion import ingestion_hub
from argus.api.main import app
from argus.domain.ingestion.gmail.config import SCOPE
from argus.domain.ingestion.gmail.state import InMemoryStateLedger
from argus.domain.owner_scope import PERSONAL
from fastapi.testclient import TestClient

from tests.ingestion.conftest import ALICE, BOB, GUEST, bearer
from tests.ingestion.gmail_api_support import (  # noqa: F401
    URL,
    authorize,
    connect,
    gmail_env,
    google,
    logs,
    state_of,
)
from tests.ingestion.gmail_fakes import CLIENT_SECRET
from tests.ingestion.gmail_mailbox import MAILBOX

ROOT = "/api/v1/financial-connections"


def _routes(connection_id="00000000-0000-4000-8000-000000000000"):
    return [
        ("post", f"{URL}/authorize", None),
        ("post", f"{URL}/callback", {"code": "c", "state": "s"}),
        ("get", f"{URL}/{connection_id}/senders", None),
        ("put", f"{URL}/{connection_id}/senders", {"senders": []}),
        ("get", f"{URL}/{connection_id}/sender-suggestions", None),
        ("post", f"{URL}/{connection_id}/sync", None),
    ]


def _call(client, method, path, body, token):  # noqa: ANN001, ANN202
    kwargs = {"headers": bearer(token)}
    if body is not None:
        kwargs["json"] = body
    return getattr(client, method)(path, **kwargs)


def test_flag_off_hides_every_gmail_route(surface_env, gateway):  # noqa: ANN001
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        patch("argus.api.dependencies.auth_session_is_active", return_value=True),
        TestClient(app) as client,
    ):
        assert gmail_connector() is None
        for method, path, body in _routes():
            response = _call(client, method, path, body, ALICE)
            assert response.status_code == 404
            assert response.json()["code"] == "financial_connections_unavailable"


@pytest.mark.parametrize(
    "unset",
    ["GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_OAUTH_REDIRECT_URI",
     "ARGUS_INGESTION_SECRET_KEY"],
)  # fmt: skip
def test_missing_configuration_keeps_gmail_off_but_the_surface_on(
    unset,
    monkeypatch,
    ingestion_env,
    gateway,  # noqa: ANN001
):
    monkeypatch.delenv(unset)
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        patch("argus.api.dependencies.auth_session_is_active", return_value=True),
        TestClient(app) as client,
    ):
        assert gmail_connector() is None and ingestion_hub() is not None
        adapter = ingestion_hub().adapter("gmail")
        # Disconnect can still forget sender rows (and, with the sealing key,
        # revoke at Google).
        assert adapter is revoke_only_adapter() and adapter is not None
        response = client.post(f"{URL}/authorize", headers=bearer(ALICE))
        assert response.status_code == 404
        assert client.get(ROOT, headers=bearer(ALICE)).status_code == 200


def test_insecure_redirect_uri_keeps_gmail_off(monkeypatch, ingestion_env, gateway):  # noqa: ANN001
    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", "http://app.example.test/cb")
    with patch.object(api_state, "supabase_gateway", gateway), TestClient(app):
        assert gmail_connector() is None


def test_guests_and_anonymous_callers_are_refused(client, google):  # noqa: ANN001, F811
    assert client.post(f"{URL}/authorize", headers=bearer(GUEST)).status_code == 403
    assert client.post(f"{URL}/authorize").status_code == 401


def test_connect_choose_senders_sync_and_disconnect(client, google, logs):  # noqa: ANN001, F811
    created = connect(client, google)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["created"] is True
    assert body["connection"]["label"] == "j***@example.test"
    assert [s["sender"] for s in body["senders"]] == ["banco-ejemplo.test"]
    connection_id = body["connection"]["id"]

    replaced = client.put(
        f"{URL}/{connection_id}/senders",
        json={"senders": ["Alerts@Card-Example.test", "banco-ejemplo.test"]},
        headers=bearer(ALICE),
    )
    assert replaced.status_code == 200
    assert [(s["sender"], s["kind"]) for s in replaced.json()["senders"]] == [
        ("alerts@card-example.test", "address"),
        ("banco-ejemplo.test", "domain"),
    ]
    listed = client.get(f"{URL}/{connection_id}/senders", headers=bearer(ALICE))
    assert listed.json() == replaced.json()

    synced = client.post(f"{URL}/{connection_id}/sync", headers=bearer(ALICE))
    assert synced.status_code == 200
    summary = synced.json()["sync"]
    assert (summary["status"], summary["mode"], summary["candidates"]) == (
        "synced", "initial", 6,
    )  # fmt: skip
    assert synced.json()["connection"]["last_success_at"] is not None

    ended = client.post(f"{ROOT}/{connection_id}/disconnect", headers=bearer(ALICE))
    assert ended.status_code == 200
    assert ended.json()["provider_revocation"] == "revoked"
    assert ended.json()["unreviewed_removed"] == 6
    assert google.count("/revoke") == 1 and google.revoked
    gone = client.get(f"{URL}/{connection_id}/senders", headers=bearer(ALICE))
    assert gone.json()["senders"] == []
    after = client.post(f"{URL}/{connection_id}/sync", headers=bearer(ALICE))
    assert after.status_code == 409
    assert after.json()["code"] == "financial_connection_disconnected"

    # Nothing secret or identifying reached a response or a log line.
    assert any("Gmail sync finished" in line for line in logs)
    secrets = [CLIENT_SECRET, MAILBOX, *google.refresh_tokens, *google.access]
    responses = [created.text, replaced.text, listed.text, synced.text, ended.text]
    for secret in secrets:
        assert not any(secret in text for text in responses + logs), secret


def test_failed_revocation_still_deletes_credential(client, google, identities):  # noqa: ANN001, F811
    connection_id = connect(client, google).json()["connection"]["id"]
    google.fail["revoke"] = [(503, {"error": "backend"})]
    ended = client.post(f"{ROOT}/{connection_id}/disconnect", headers=bearer(ALICE))
    assert ended.json()["provider_revocation"] == "failed"
    stored = ingestion_hub().connections.get(
        user_id=identities[ALICE]["id"], connection_id=connection_id, scope=PERSONAL
    )
    assert stored.secret is None and stored.status == "disconnected"
    # The forget hook still deletes the sender allowlist.
    assert gmail_connector().senders.list(connection_id=connection_id) == []


def test_reconnect_returns_200_with_the_same_connection(client, google):  # noqa: ANN001, F811
    first = connect(client, google).json()["connection"]["id"]
    again = connect(client, google, senders=None)
    assert again.status_code == 200
    assert again.json()["created"] is False and again.json()["connection"]["id"] == first
    assert [s["sender"] for s in again.json()["senders"]] == ["banco-ejemplo.test"]
    assert len(client.get(ROOT, headers=bearer(ALICE)).json()["items"]) == 1


@pytest.mark.parametrize(
    ("case", "status", "code"),
    [
        ("bad_state", 400, "gmail_oauth_state_invalid"),
        ("partial_scope", 422, "gmail_scope_not_granted"),
        ("bad_code", 400, "gmail_authorization_code_invalid"),
        ("bad_sender", 422, "gmail_sender_invalid"),
        ("owned_elsewhere", 409, "gmail_mailbox_unavailable"),
    ],
)
def test_callback_failures_are_actionable_problems(client, google, case, status, code):  # noqa: ANN001, F811
    url = authorize(client)
    scopes = ("openid",) if case == "partial_scope" else (SCOPE,)
    issued, state = google.issue_code(url, scopes=scopes)
    body = {"code": issued, "state": state}
    if case == "bad_state":
        body["state"] = state_of(authorize(client, BOB))
    elif case == "bad_code":
        body["code"] = "4/not-issued"
    elif case == "bad_sender":
        body["senders"] = ["x OR in:anywhere"]
    elif case == "owned_elsewhere":
        assert connect(client, google, token=BOB).status_code == 201
    response = client.post(f"{URL}/callback", json=body, headers=bearer(ALICE))
    assert response.status_code == status, response.text
    assert response.json()["code"] == code
    if case == "bad_sender":
        # The state was not consumed: the person can fix the list and retry.
        body["senders"] = ["banco-ejemplo.test"]
        retry = client.post(f"{URL}/callback", json=body, headers=bearer(ALICE))
        assert retry.status_code == 201


def test_another_persons_connection_looks_absent(client, google):  # noqa: ANN001, F811
    connection_id = connect(client, google).json()["connection"]["id"]
    for method, path, body in _routes(connection_id)[2:]:
        response = _call(client, method, path, body, BOB)
        assert response.status_code == 404, path
        assert response.json()["code"] == "financial_connection_not_found"


def test_sender_suggestions_come_from_headers_only(client, google):  # noqa: ANN001, F811
    connection_id = connect(client, google).json()["connection"]["id"]
    response = client.get(
        f"{URL}/{connection_id}/sender-suggestions", headers=bearer(ALICE)
    )
    assert response.status_code == 200
    found = {s["sender"]: s for s in response.json()["suggestions"]}
    assert found["alerts@card-example.test"]["messages"] == 2
    assert found["alerts@card-example.test"]["authenticated"] is True
    assert "alertas@banco-ejemplo.test" not in found  # already allowed
    assert found["ofertas@tienda-ficticia.test"]["domain"] == "tienda-ficticia.test"
    assert not [q for _, p, q in google.calls if q.get("format") == ["full"]]


def test_revoked_grant_on_suggestions_marks_needs_reauth(client, google):  # noqa: ANN001, F811
    connection_id = connect(client, google).json()["connection"]["id"]
    google.revoked.update(google.refresh_tokens)
    response = client.get(
        f"{URL}/{connection_id}/sender-suggestions", headers=bearer(ALICE)
    )
    assert (
        response.status_code == 409 and response.json()["code"] == "gmail_token_revoked"
    )
    item = client.get(ROOT, headers=bearer(ALICE)).json()["items"][0]
    assert item["status"] == "needs_reauth"


def test_sync_without_a_sink_reports_no_sink(client, google):  # noqa: ANN001, F811
    connection_id = connect(client, google).json()["connection"]["id"]
    ingestion_hub().sink = None
    response = client.post(f"{URL}/{connection_id}/sync", headers=bearer(ALICE))
    assert response.json()["sync"]["status"] == "no_sink"
    assert response.json()["connection"]["last_success_at"] is None


def test_a_person_over_the_state_limit_gets_429(client, google):  # noqa: ANN001, F811
    gmail_connector().oauth.states.ledger = InMemoryStateLedger(per_user=0)
    code, state = google.issue_code(authorize(client))
    response = client.post(
        f"{URL}/callback", json={"code": code, "state": state}, headers=bearer(ALICE)
    )
    assert response.status_code == 429
    assert response.json()["code"] == "gmail_oauth_rate_limited"
