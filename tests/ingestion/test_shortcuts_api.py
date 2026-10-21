"""Shortcuts enrollment and intake over the real app, auth and startup wiring."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from argus.api import state as api_state
from argus.api.ingestion import ingestion_hub
from argus.api.main import app
from argus.api.shortcuts import shortcuts_connector
from argus.domain.owner_scope import PERSONAL
from fastapi.testclient import TestClient
from loguru import logger

from tests.ingestion.conftest import ALICE, BOB, GUEST, bearer
from tests.ingestion.shortcuts_support import (
    BATCH,
    DEVICES,
    EVENTS,
    RecordingSink,
    enroll,
    tap,
)


@pytest.fixture
def sink(client) -> RecordingSink:  # noqa: ANN001
    assert shortcuts_connector() is not None
    assert ingestion_hub().adapter("shortcuts") is shortcuts_connector().adapter
    recording = RecordingSink()
    ingestion_hub().sink = recording
    return recording


@pytest.fixture
def logs():
    lines: list[str] = []
    handle = logger.add(lambda message: lines.append(str(message.record)), level="DEBUG")
    yield lines
    logger.remove(handle)


def test_flag_off_answers_absent_even_with_a_device_token(surface_env, gateway):  # noqa: ANN001
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        patch("argus.api.dependencies.auth_session_is_active", return_value=True),
        TestClient(app) as client,
    ):
        enrolled = client.post(DEVICES, json={"device_name": "x"}, headers=bearer(ALICE))
        intake = client.post(EVENTS, json=tap(), headers=bearer("sct1.a.b"))
    assert shortcuts_connector() is None
    for response in (enrolled, intake):
        assert response.status_code == 404
        assert response.json()["code"] == "financial_connections_unavailable"


def test_enrollment_is_registered_only(client):
    assert client.post(DEVICES, json={"device_name": "x"}).status_code == 401
    guest = client.post(DEVICES, json={"device_name": "x"}, headers=bearer(GUEST))
    assert guest.status_code == 403


def test_enrollment_returns_token_once_and_stores_only_a_digest(client, logs, identities):
    body = enroll(client)
    token = body["device_token"]
    assert token.startswith("sct1.") and len(token) > 70
    assert body["intake_url"] == EVENTS
    connection = body["connection"]
    assert connection["source"] == "shortcuts" and connection["label"] == "iPhone de Ana"
    hub = ingestion_hub()
    row = hub.connections.get(
        user_id=identities[ALICE]["id"], connection_id=connection["id"], scope=PERSONAL
    )
    assert row.secret is None and token.split(".")[1] == row.external_ref
    stored = shortcuts_connector().store.get(connection_id=row.id)
    assert stored is not None and len(stored) == 32
    assert token.encode() not in stored and token.split(".")[2].encode() not in stored
    listing = client.get("/api/v1/financial-connections", headers=bearer(ALICE)).text
    assert token not in listing and token.split(".")[2] not in listing
    assert not any(token.split(".")[2] in line for line in logs)


def test_device_limit(client):
    for index in range(5):
        enroll(client, name=f"phone {index}")
    response = client.post(DEVICES, json={"device_name": "six"}, headers=bearer(ALICE))
    assert response.status_code == 409
    assert response.json()["code"] == "shortcuts_device_limit"


@pytest.mark.parametrize(
    "authorization",
    [
        None,
        "Bearer",
        "Basic abc",
        f"Bearer {ALICE}",  # a user session is not a device token
        "Bearer sct1.00000000000000000000000000000000." + "A" * 43,
        "Bearer sct1.zz.short",
    ],
)
def test_unknown_tokens_are_refused_identically(client, sink, authorization):
    good = enroll(client)["device_token"]
    forged = good[:-4] + ("AAAA" if not good.endswith("AAAA") else "BBBB")
    expected = None
    for header in (authorization, f"Bearer {forged}"):
        headers = {"Authorization": header} if header else {}
        response = client.post(EVENTS, json=tap(), headers=headers)
        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == "Bearer"
        body = {k: v for k, v in response.json().items() if k != "request_id"}
        assert expected in (None, body)
        expected = body
    assert expected["code"] == "shortcuts_device_unauthorized"
    assert sink.evidence == {}


def test_intake_records_unsettled_evidence_for_the_device_owner(client, sink, identities):
    token = enroll(client)["device_token"]
    response = client.post(EVENTS, json=tap(), headers=bearer(token))
    assert response.status_code == 200
    receipt = response.json()
    assert receipt["outcome"] == "recorded" and receipt["external_id"].startswith(
        "wallet:e:"
    )
    [(key, candidate)] = sink.evidence.items()
    connection = ingestion_hub().list(user_id=identities[ALICE]["id"], scope=PERSONAL)[0]
    assert key == ("shortcuts", connection.id, receipt["external_id"])
    assert (candidate.status, candidate.direction) == ("unknown", "unknown")
    assert (candidate.amount, candidate.currency) == ("1250", "DOP")
    assert connection.last_success_at is not None
    assert ingestion_hub().list(user_id=identities[BOB]["id"], scope=PERSONAL) == []


def test_repeated_delivery_returns_the_same_receipt(client, sink):
    token = enroll(client)["device_token"]
    first = client.post(EVENTS, json=tap(), headers=bearer(token)).json()
    again = client.post(EVENTS, json=tap(), headers=bearer(token)).json()
    assert again["receipt_id"] == first["receipt_id"]
    assert again["external_id"] == first["external_id"]
    assert again["outcome"] == "unchanged"
    assert len(sink.evidence) == 1


def test_identical_purchases_with_distinct_event_ids_stay_distinct(client, sink):
    token = enroll(client)["device_token"]
    minute = datetime.now(timezone.utc).replace(second=5, microsecond=0)
    one = tap(event_id="a", captured_at=minute.isoformat())
    two = tap(event_id="b", captured_at=(minute + timedelta(seconds=30)).isoformat())
    receipts = [
        client.post(EVENTS, json=e, headers=bearer(token)).json() for e in (one, two)
    ]
    assert receipts[0]["external_id"] != receipts[1]["external_id"]
    assert len(sink.evidence) == 2


def test_ambiguous_dollar_and_explicit_code(client, sink):
    token = enroll(client)["device_token"]
    client.post(EVENTS, json=tap(event_id="1", amount="$12.50"), headers=bearer(token))
    client.post(
        EVENTS,
        json=tap(event_id="2", amount="$12.50", currency="USD"),
        headers=bearer(token),
    )
    by_id = {c.source.external_id: c for c in sink.evidence.values()}
    ambiguous, explicit = sorted(by_id.values(), key=lambda c: c.currency or "")
    assert ambiguous.currency is None and "currency" in ambiguous.uncertain
    assert explicit.currency == "USD" and "currency" not in explicit.uncertain


def test_message_capture_is_accepted_as_inert_text(client, sink):
    token = enroll(client)["device_token"]
    event = {
        "event_id": "m1",
        "kind": "message_capture",
        "source_app": "messages",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "sender": "BancoX",
        "text": "Consumo aprobado RD$500.00",
    }
    response = client.post(EVENTS, json=event, headers=bearer(token))
    assert response.status_code == 200
    [candidate] = sink.evidence.values()
    assert candidate.amount is None and candidate.excerpt == "Consumo aprobado RD$500.00"
    assert candidate.evidence == "unclassified" and "kind" in candidate.unresolved()


def test_without_a_sink_nothing_is_saved_and_the_answer_is_retryable(client, identities):
    token = enroll(client)["device_token"]
    # Reconciliation is the wired sink; an unavailable sink must still be safe.
    ingestion_hub().sink = None
    response = client.post(EVENTS, json=tap(), headers=bearer(token))
    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "shortcuts_intake_unavailable"
    assert body["context"] == {"retryable": True}
    assert "Retry-After" in response.headers
    [connection] = ingestion_hub().list(user_id=identities[ALICE]["id"], scope=PERSONAL)
    assert connection.last_success_at is None


def test_body_cap_extra_fields_and_bad_json(client, sink):
    token = enroll(client)["device_token"]
    big = tap(text=None, merchant="x" * 200, card="y" * 120)
    big["padding"] = "z" * 5000
    too_large = client.post(EVENTS, json=big, headers=bearer(token))
    assert too_large.status_code == 413
    extra = client.post(EVENTS, json=tap(raw_payload="x"), headers=bearer(token))
    assert extra.status_code == 422 and extra.json()["code"] == "shortcuts_event_invalid"
    assert "raw_payload" in extra.json()["context"]["fields"]
    broken = client.post(
        EVENTS,
        content=b"{not json",
        headers={**bearer(token), "Content-Type": "application/json"},
    )
    assert broken.status_code == 422
    assert sink.evidence == {}


def test_events_outside_the_time_window_are_refused(client, sink):
    token = enroll(client)["device_token"]
    now = datetime.now(timezone.utc)
    for when in (now + timedelta(hours=1), now - timedelta(days=31)):
        response = client.post(
            EVENTS, json=tap(captured_at=when.isoformat()), headers=bearer(token)
        )
        assert response.status_code == 422
        assert response.json()["code"] == "shortcuts_event_out_of_window"
    assert sink.evidence == {}


def test_pending_batch_is_idempotent_per_event(client, sink):
    token = enroll(client)["device_token"]
    events = [tap(event_id="p1"), tap(event_id="p2", amount="US$ 3.00")]
    first = client.post(BATCH, json={"events": events}, headers=bearer(token))
    assert first.status_code == 200
    assert [r["outcome"] for r in first.json()["receipts"]] == ["recorded", "recorded"]
    again = client.post(BATCH, json={"events": events}, headers=bearer(token)).json()
    assert [r["outcome"] for r in again["receipts"]] == ["unchanged", "unchanged"]
    assert len(sink.evidence) == 2


def test_stale_capture_in_a_batch_does_not_block_the_rest(client, sink):
    token = enroll(client)["device_token"]
    stale = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    events = [tap(event_id="old", captured_at=stale), tap(event_id="new")]
    body = client.post(BATCH, json={"events": events}, headers=bearer(token)).json()
    assert [r["outcome"] for r in body["receipts"]] == ["out_of_window", "recorded"]
    assert len(sink.evidence) == 1


def test_batch_limits_refuse_before_saving(client, sink):
    token = enroll(client)["device_token"]
    too_many = client.post(
        BATCH,
        json={"events": [tap(event_id=str(i), merchant=None) for i in range(201)]},
        headers=bearer(token),
    )
    assert too_many.status_code == 422
    one_bad = client.post(
        BATCH,
        json={"events": [tap(event_id="ok"), tap(event_id="bad", kind="balance")]},
        headers=bearer(token),
    )
    assert one_bad.status_code == 422
    assert sink.evidence == {}


def test_disconnect_revokes_the_device_token(client, sink, identities):
    enrolled = enroll(client)
    token = enrolled["device_token"]
    assert client.post(EVENTS, json=tap(), headers=bearer(token)).status_code == 200
    connection_id = enrolled["connection"]["id"]
    response = client.post(
        f"/api/v1/financial-connections/{connection_id}/disconnect",
        headers=bearer(ALICE),
    )
    assert response.status_code == 200
    assert response.json()["provider_revocation"] == "revoked"
    assert response.json()["unreviewed_removed"] == 1
    assert shortcuts_connector().store.get(connection_id=connection_id) is None
    refused = client.post(EVENTS, json=tap(event_id="after"), headers=bearer(token))
    assert refused.status_code == 401
    assert sink.evidence == {}


def test_per_device_rate_limit(client, sink):
    token = enroll(client)["device_token"]
    other = enroll(client, name="iPad")["device_token"]
    for index in range(20):
        ok = client.post(EVENTS, json=tap(event_id=f"r{index}"), headers=bearer(token))
        assert ok.status_code == 200
    limited = client.post(EVENTS, json=tap(event_id="r20"), headers=bearer(token))
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) >= 1
    # Another device of the same person is not affected.
    assert client.post(EVENTS, json=tap(), headers=bearer(other)).status_code == 200


def test_tokens_never_reach_logs(client, sink, logs):
    token = enroll(client)["device_token"]
    client.post(EVENTS, json=tap(), headers=bearer(token))
    client.post(EVENTS, json=tap(), headers=bearer(token + "x"))
    secret = token.split(".")[2]
    assert logs and not any(secret in line for line in logs)
    assert not any("Supermercado" in line or "1,250" in line for line in logs)
