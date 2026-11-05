"""Connected-source list and disconnect over the real auth dependency."""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from argus.api import state as api_state
from argus.api.ingestion import ingestion_hub
from argus.api.main import app
from argus.domain.owner_scope import PERSONAL, OwnerScope
from fastapi.testclient import TestClient

from tests.ingestion.conftest import ALICE, BOB, GUEST, bearer

NOW = datetime(2026, 10, 1, 13, 0, tzinfo=timezone.utc)
URL = "/api/v1/financial-connections"


class FakeSink:
    def __init__(self) -> None:
        self.forgotten: list[tuple[str, str]] = []

    def submit(self, **_kwargs):  # pragma: no cover - not used here
        raise AssertionError

    def forget_connection(
        self, *, user_id: str, connection_id: str, scope: OwnerScope
    ) -> int:
        assert scope == PERSONAL
        self.forgotten.append((user_id, connection_id))
        return 3


class Adapter:
    source = "plaid"

    def __init__(self, fail: bool) -> None:
        self.fail = fail
        self.seen: list[str | None] = []

    def revoke(self, connection, credential):  # noqa: ANN001
        self.seen.append(credential)
        if self.fail:
            raise RuntimeError("provider down")

    def forget(self, connection):  # noqa: ANN001
        self.forgot = connection.status


def connect(identities, token: str, ref: str = "item-1"):  # noqa: ANN001
    hub = ingestion_hub()
    return hub.connections.create(
        user_id=identities[token]["id"],
        source="plaid",
        external_ref=ref,
        label="Chase",
        now=NOW,
        secret=b"sealed",
        scope=PERSONAL,
    )


def test_flag_off_answers_absent_for_everyone(surface_env, gateway):  # noqa: ANN001
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        patch("argus.api.dependencies.auth_session_is_active", return_value=True),
        TestClient(app) as client,
    ):
        signed_in = client.get(URL, headers=bearer(ALICE))
        anonymous = client.get(URL)
    for response in (signed_in, anonymous):
        assert response.status_code == 404
        assert response.json()["code"] == "financial_connections_unavailable"


def test_ingestion_requires_financial_accounts_surface(monkeypatch, gateway):  # noqa: ANN001
    monkeypatch.setenv("ARGUS_INGESTION_ENABLED", "true")
    monkeypatch.setenv("ARGUS_FINANCIAL_ACCOUNTS_ENABLED", "false")
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        TestClient(app) as client,
    ):
        assert ingestion_hub() is None
        assert client.get(URL, headers=bearer(ALICE)).status_code == 404


def test_guests_and_anonymous_callers_are_refused(client):
    assert client.get(URL, headers=bearer(GUEST)).status_code == 403
    assert client.get(URL).status_code == 401


def test_list_shows_status_and_freshness_without_secrets(client, identities):
    row = connect(identities, ALICE)
    body = client.get(URL, headers=bearer(ALICE)).json()
    assert [item["id"] for item in body["items"]] == [row.id]
    item = body["items"][0]
    assert item["status"] == "active" and item["label"] == "Chase"
    assert set(item) == {
        "id", "source", "status", "label", "last_success_at", "last_attempt_at",
        "last_error_code", "attention_code", "attention_at", "created_at",
        "disconnected_at",
    }  # fmt: skip
    assert client.get(URL, headers=bearer(BOB)).json()["items"] == []


@pytest.mark.parametrize("fail", [False, True])
def test_disconnect_always_deletes_local_credential_and_unreviewed_evidence(
    client, identities, fail
):
    hub = ingestion_hub()
    sink = FakeSink()
    adapter = Adapter(fail=fail)
    hub.sink = sink
    hub.register(adapter)
    row = connect(identities, ALICE)
    response = client.post(f"{URL}/{row.id}/disconnect", headers=bearer(ALICE))
    assert response.status_code == 200
    body = response.json()
    assert body["provider_revocation"] == ("failed" if fail else "revoked")
    assert body["unreviewed_removed"] == 3
    assert body["connection"]["status"] == "disconnected"
    stored = hub.connections.get(
        user_id=identities[ALICE]["id"], connection_id=row.id, scope=PERSONAL
    )
    assert stored.secret is None
    assert sink.forgotten == [(identities[ALICE]["id"], row.id)]
    # Connector-owned local state is cleaned up after the connection ended.
    assert adapter.forgot == "disconnected"
    # Repeating is harmless and does not call the provider again.
    again = client.post(f"{URL}/{row.id}/disconnect", headers=bearer(ALICE)).json()
    assert again["provider_revocation"] == "not_applicable"
    assert len(adapter.seen) == 1


def test_disconnect_is_owner_only(client, identities):
    row = connect(identities, ALICE)
    response = client.post(f"{URL}/{row.id}/disconnect", headers=bearer(BOB))
    assert response.status_code == 404
    assert response.json()["code"] == "financial_connection_not_found"
    assert client.post(f"{URL}/nope/disconnect", headers=bearer(ALICE)).status_code == 404
    assert (
        ingestion_hub()
        .connections.get(
            user_id=identities[ALICE]["id"], connection_id=row.id, scope=PERSONAL
        )
        .status
        == "active"
    )


def test_disconnect_without_a_registered_adapter_reports_failed_revocation(
    client, identities
):
    hub = ingestion_hub()
    hub._adapters.pop("plaid", None)
    row = connect(identities, ALICE)  # holds a sealed provider credential
    body = client.post(f"{URL}/{row.id}/disconnect", headers=bearer(ALICE)).json()
    assert body["provider_revocation"] == "failed"
    assert body["connection"]["status"] == "disconnected"


def test_retrying_a_disconnect_finishes_cleanup_that_failed(client, identities):
    hub = ingestion_hub()
    adapter = Adapter(fail=False)
    hub.register(adapter)

    class FlakySink(FakeSink):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        def forget_connection(
            self, *, user_id: str, connection_id: str, scope: OwnerScope
        ) -> int:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("database hiccup")
            return super().forget_connection(
                user_id=user_id, connection_id=connection_id, scope=scope
            )

    sink = FlakySink()
    hub.sink = sink
    row = connect(identities, ALICE)
    first = client.post(f"{URL}/{row.id}/disconnect", headers=bearer(ALICE))
    assert first.status_code == 500
    retry = client.post(f"{URL}/{row.id}/disconnect", headers=bearer(ALICE)).json()
    assert retry["connection"]["status"] == "disconnected"
    assert retry["provider_revocation"] == "not_applicable"
    assert retry["unreviewed_removed"] == 3
    assert sink.forgotten == [(identities[ALICE]["id"], row.id)]
    assert len(adapter.seen) == 1  # the provider is not asked twice
