"""Plaid webhooks end to end: signature gate, status changes, triggered sync."""

import hashlib
import json
import time

import jwt
import pytest
from argus.api.ingestion import ingestion_hub
from argus.domain.owner_scope import PERSONAL
from cryptography.hazmat.primitives.asymmetric import ec

from tests.ingestion.conftest import ALICE, bearer
from tests.ingestion.plaid_api_support import (  # noqa: F401
    URL,
    connect,
    plaid,
    plaid_env,
)
from tests.ingestion.plaid_fakes import ITEM_ID, page, txn

KID = "6c5516e1-92dc-479e-a8ff-5a51992e0002"
PRIVATE = ec.generate_private_key(ec.SECP256R1())


@pytest.fixture
def signed(plaid):  # noqa: ANN001, F811
    jwk = jwt.algorithms.ECAlgorithm.to_jwk(PRIVATE.public_key(), as_dict=True)
    jwk.update(alg="ES256", kid=KID, use="sig", created_at=1_700_000_000, expired_at=None)
    plaid.jwk = jwk
    return plaid


def deliver(client, payload: dict, *, iat: int | None = None, tamper: bool = False):  # noqa: ANN001
    body = json.dumps(payload, indent=2).encode()
    token = jwt.encode(
        {
            "iat": iat if iat is not None else int(time.time()),
            "request_body_sha256": hashlib.sha256(body).hexdigest(),
        },
        PRIVATE,
        algorithm="ES256",
        headers={"kid": KID},
    )
    if tamper:
        body = body.replace(b"sandbox", b"sandbax")
    return (
        client.post(
            f"{URL}/webhook",
            content=body,
            headers={"Plaid-Verification": token, "Content-Type": "application/json"},
        ),
        token,
        body,
    )


def sync_event(code: str = "SYNC_UPDATES_AVAILABLE") -> dict:
    return {
        "webhook_type": "TRANSACTIONS",
        "webhook_code": code,
        "item_id": ITEM_ID,
        "initial_update_complete": True,
        "historical_update_complete": True,
        "environment": "sandbox",
    }


def item_event(code: str, error_code: str | None = None) -> dict:
    event = {
        "webhook_type": "ITEM",
        "webhook_code": code,
        "item_id": ITEM_ID,
        "environment": "sandbox",
    }
    if error_code:
        event["error"] = {"error_type": "ITEM_ERROR", "error_code": error_code}
    return event


def stored(client, identities, connection_id):  # noqa: ANN001
    return ingestion_hub().connections.get(
        user_id=identities[ALICE]["id"], connection_id=connection_id, scope=PERSONAL
    )


def test_signed_sync_webhook_triggers_one_sync_and_replays_are_harmless(
    client, signed, identities
):  # noqa: ANN001
    connection_id = connect(client).json()["connection"]["id"]
    signed.sync["c1"] = [
        page(added=[txn("t2", 7)], next_cursor="c2"),
        page(next_cursor="c2"),
    ]
    response, token, body = deliver(client, sync_event())
    assert response.status_code == 200 and response.json() == {"received": True}
    assert stored(client, identities, connection_id).cursor == "c2"
    syncs = signed.paths().count("/transactions/sync")
    # The identical delivery again: verified, recognized, no extra work.
    again = client.post(
        f"{URL}/webhook", content=body, headers={"Plaid-Verification": token}
    )
    assert (
        again.status_code == 200 and signed.paths().count("/transactions/sync") == syncs
    )
    # A fresh, separately signed retry syncs again and finds nothing new.
    assert deliver(client, sync_event("DEFAULT_UPDATE"))[0].status_code == 200
    assert stored(client, identities, connection_id).cursor == "c2"
    sink = ingestion_hub().sink
    assert sorted(k[2] for k in sink.evidence) == ["t1", "t2"]


@pytest.mark.parametrize(
    "case", ["no_header", "tampered", "old", "wrong_kid", "oversized"]
)
def test_unverified_webhooks_are_rejected_without_detail(client, signed, case):  # noqa: ANN001
    connect(client)
    before = signed.paths().count("/transactions/sync")
    if case == "no_header":
        response = client.post(f"{URL}/webhook", content=json.dumps(sync_event()))
    elif case == "tampered":
        response = deliver(client, sync_event(), tamper=True)[0]
    elif case == "old":
        response = deliver(client, sync_event(), iat=int(time.time()) - 360)[0]
    elif case == "oversized":
        response = deliver(client, {**sync_event(), "padding": "x" * 70_000})[0]
    else:
        signed.jwk = {**signed.jwk, "kid": "another"}
        response = deliver(client, sync_event())[0]
    assert response.status_code == 400
    assert response.json()["code"] == "plaid_webhook_rejected"
    assert response.json()["detail"] == "Webhook could not be verified."
    assert signed.paths().count("/transactions/sync") == before


@pytest.mark.parametrize(
    ("event", "status", "code"),
    [
        (
            item_event("ERROR", "ITEM_LOGIN_REQUIRED"),
            "needs_reauth",
            "plaid_item_login_required",
        ),
        (
            item_event("USER_PERMISSION_REVOKED", "USER_PERMISSION_REVOKED"),
            "error",
            "plaid_user_permission_revoked",
        ),
    ],
)
def test_item_webhooks_record_actionable_status_and_keep_freshness(
    client, signed, identities, event, status, code
):  # noqa: ANN001
    connection_id = connect(client).json()["connection"]["id"]
    fresh = stored(client, identities, connection_id).last_success_at
    assert fresh is not None
    assert deliver(client, event)[0].status_code == 200
    row = stored(client, identities, connection_id)
    assert (row.status, row.last_error_code) == (status, code)
    assert row.last_success_at == fresh and row.cursor == "c1"
    assert row.attention_code is None
    listed = client.get("/api/v1/financial-connections", headers=bearer(ALICE)).json()
    assert listed["items"][0]["last_error_code"] == code


@pytest.mark.parametrize(
    ("webhook_code", "attention"),
    [
        ("PENDING_EXPIRATION", "plaid_pending_expiration"),
        ("PENDING_DISCONNECT", "plaid_pending_disconnect"),
    ],
)
def test_expiring_consent_flags_attention_that_syncs_keep_and_update_mode_clears(
    client, signed, identities, webhook_code, attention
):  # noqa: ANN001
    connection_id = connect(client).json()["connection"]["id"]
    assert deliver(client, item_event(webhook_code))[0].status_code == 200
    row = stored(client, identities, connection_id)
    assert (row.status, row.last_error_code) == ("active", None)
    assert row.attention_code == attention and row.attention_at is not None
    # A successful sync does not hide the warning.
    synced = client.post(f"{URL}/{connection_id}/sync", headers=bearer(ALICE)).json()
    assert synced["sync"]["status"] == "synced"
    assert synced["connection"]["status"] == "active"
    assert synced["connection"]["attention_code"] == attention
    # Update mode is offered for it, and finishing it clears the warning.
    update = client.post(f"{URL}/{connection_id}/link-token", headers=bearer(ALICE))
    assert update.status_code == 200
    restored = client.post(
        f"{URL}/{connection_id}/reconnected", headers=bearer(ALICE)
    ).json()
    assert restored["status"] == "active"
    assert restored["attention_code"] is None and restored["attention_at"] is None
    assert stored(client, identities, connection_id).cursor == "c1"


def test_login_repaired_restores_after_a_health_check(client, signed, identities):  # noqa: ANN001
    connection_id = connect(client).json()["connection"]["id"]
    deliver(client, item_event("ERROR", "ITEM_LOGIN_REQUIRED"))
    assert stored(client, identities, connection_id).status == "needs_reauth"
    deliver(client, item_event("PENDING_EXPIRATION"))
    deliver(client, item_event("LOGIN_REPAIRED"))
    repaired = stored(client, identities, connection_id)
    assert repaired.status == "active" and repaired.last_error_code is None
    # Re-sealing the existing envelope (set_secret) also clears attention.
    assert repaired.attention_code is None
    assert "/item/get" in signed.paths()


def test_unknown_items_and_other_environments_are_acknowledged_and_ignored(
    client, signed, identities
):  # noqa: ANN001
    connection_id = connect(client).json()["connection"]["id"]
    syncs = signed.paths().count("/transactions/sync")
    assert (
        deliver(client, {**sync_event(), "item_id": "item-unknown"})[0].status_code == 200
    )
    assert (
        deliver(client, {**sync_event(), "environment": "production"})[0].status_code
        == 200
    )
    production_error = {
        **item_event("ERROR", "ITEM_LOGIN_REQUIRED"),
        "environment": "production",
    }
    assert deliver(client, production_error)[0].status_code == 200
    assert signed.paths().count("/transactions/sync") == syncs
    assert stored(client, identities, connection_id).status == "active"


def test_a_delivery_whose_handling_failed_is_processed_when_retried(
    client, signed, identities, monkeypatch
):  # noqa: ANN001
    from argus.api.plaid import plaid_connector

    connection_id = connect(client).json()["connection"]["id"]
    signed.sync["c1"] = [page(added=[txn("t2", 7)], next_cursor="c2")]
    webhooks = plaid_connector().webhooks
    planned = webhooks.plan

    def unavailable(payload):  # noqa: ANN001, ANN202
        raise RuntimeError("database unavailable")

    body = json.dumps(sync_event()).encode()
    token = jwt.encode(
        {
            "iat": int(time.time()),
            "request_body_sha256": hashlib.sha256(body).hexdigest(),
        },
        PRIVATE,
        algorithm="ES256",
        headers={"kid": KID},
    )
    headers = {"Plaid-Verification": token, "Content-Type": "application/json"}
    monkeypatch.setattr(webhooks, "plan", unavailable)
    failed = client.post(f"{URL}/webhook", content=body, headers=headers)
    assert failed.status_code == 500
    assert stored(client, identities, connection_id).cursor == "c1"
    # Plaid retries the same signed delivery: it is handled, not skipped.
    monkeypatch.setattr(webhooks, "plan", planned)
    retried = client.post(f"{URL}/webhook", content=body, headers=headers)
    assert retried.status_code == 200
    assert stored(client, identities, connection_id).cursor == "c2"
