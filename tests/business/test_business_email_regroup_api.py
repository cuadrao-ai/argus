"""Saving a sender rule through the API re-places that sender's held emails."""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from tests.business.test_business_api import alice  # noqa: F401
from tests.business.test_business_email_api import _route_for, runtime  # noqa: F401
from tests.ingestion.email_regroup_support import NOTE


def test_authorizing_a_sender_moves_its_held_email_to_the_tray(alice, runtime):  # noqa: F811
    store = runtime.store
    route = _route_for(store, alice, "ferreterianunez@recibos.example.test")
    space_id = alice.scope().owner.space_id
    delivery = store.enqueue(
        "resend", str(uuid4()), (route.recipient,), route_id=route.id, space_id=space_id
    )
    store._deliveries[delivery.id] = replace(
        store._deliveries[delivery.id],
        state="captured",
        sender="Caja <caja@tienda.test>",
        inbox_group="remitentes_nuevos",
        auth_result="failed",
    )
    response = alice.post(
        "/email/senders",
        {"kind": "address", "value": "Caja@Tienda.test", "status": "authorized"},
    )
    assert response.status_code == 201, response.text
    inbox = alice.get("/email/inbox").json()["groups"]
    groups = {group["id"]: group["items"] for group in inbox}
    assert groups["remitentes_nuevos"] == []
    [item] = groups["bandeja"]
    assert (item["id"], item["review_note"], item["sender_standing"]) == (
        delivery.id,
        NOTE,
        "authorized",
    )
