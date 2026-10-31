"""The Recepcion sender list through the real app: shape, order and status."""

from __future__ import annotations

from datetime import datetime, timezone

from tests.business.test_business_api import Owner, alice  # noqa: F401
from tests.business.test_business_email_api import runtime  # noqa: F401

T1 = datetime(2026, 10, 31, 9, 0, tzinfo=timezone.utc)
T2 = datetime(2026, 10, 31, 9, 30, tzinfo=timezone.utc)


def _seen(store, space, address, verdict, at):  # noqa: ANN001
    store.clock = lambda: at
    store.record_sender(space, address, verdict)


def test_the_list_is_pending_then_authorized_then_blocked_with_tags(
    alice: Owner,  # noqa: F811
    runtime,  # noqa: F811
) -> None:
    space = alice.scope().owner.space_id
    store = runtime.store
    assert (
        alice.post(
            "/email/senders",
            {"kind": "address", "value": "zz@bloqueado.test", "status": "blocked"},
        ).status_code
        == 201
    )
    assert (
        alice.post(
            "/email/senders",
            {"kind": "address", "value": "caja@tienda.test", "status": "authorized"},
        ).status_code
        == 201
    )
    _seen(store, space, "caja@tienda.test", "aligned", T1)
    _seen(store, space, "viejo@proveedor.test", "failed", T1)
    _seen(store, space, "nuevo@proveedor.test", "no_result", T2)
    response = alice.get("/email/senders")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    items = response.json()["items"]
    assert [(i["value"], i["status"], i["tag"]) for i in items] == [
        ("nuevo@proveedor.test", "pending", "unverified"),
        ("viejo@proveedor.test", "pending", "unverified"),
        ("caja@tienda.test", "authorized", "verified"),
        ("zz@bloqueado.test", "blocked", None),
    ]
    assert set(items[0]) == {
        "id",
        "kind",
        "value",
        "status",
        "tag",
        "last_auth_result",
        "last_seen_at",
    }
    assert (items[0]["last_auth_result"], items[0]["last_seen_at"]) == (
        "no_result",
        "2026-10-31T09:30:00Z",
    )
    assert (items[3]["last_auth_result"], items[3]["last_seen_at"]) == (None, None)


def test_autorizar_and_bloquear_on_a_pending_row_keep_its_trace(
    alice: Owner,  # noqa: F811
    runtime,  # noqa: F811
) -> None:
    space = alice.scope().owner.space_id
    _seen(runtime.store, space, "nuevo@proveedor.test", "failed", T1)
    pending = alice.get("/email/senders").json()["items"][0]
    authorized = alice.post(
        "/email/senders",
        {"kind": "address", "value": "nuevo@proveedor.test", "status": "authorized"},
    )
    assert authorized.status_code == 200, authorized.text
    assert authorized.json() == {**pending, "status": "authorized"}
    blocked = alice.post(
        "/email/senders",
        {"kind": "address", "value": "nuevo@proveedor.test", "status": "blocked"},
    )
    assert blocked.json() == {**pending, "status": "blocked"}


def test_a_client_cannot_set_pending(alice: Owner, runtime) -> None:  # noqa: F811
    refused = alice.post(
        "/email/senders",
        {"kind": "address", "value": "nuevo@proveedor.test", "status": "pending"},
    )
    assert refused.status_code == 422, refused.text
    assert runtime.store.list_senders(alice.scope().owner.space_id) == []
