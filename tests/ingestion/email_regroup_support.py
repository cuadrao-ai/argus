"""One scenario for re-placing held emails on a sender rule, run on both stores."""

from __future__ import annotations

from typing import Callable
from uuid import uuid4

NOTE = "No pudimos verificar este remitente."
SENDER = "Caja <Caja@Tienda.test>"


def held_scenario(store, route, other_space: str, place: Callable) -> None:  # noqa: ANN001
    """``place(delivery_id, **columns)`` writes a delivery's columns directly."""

    space_id = route.space_id

    def held(space: str, sender: str, auth: str | None, state: str = "captured") -> str:
        delivery = store.enqueue(
            "resend",
            str(uuid4()),
            (route.recipient,),
            route_id=route.id,
            space_id=space_id,
            principal_id=route.principal_id,
        )
        place(
            delivery.id,
            space_id=space,
            state=state,
            sender=sender,
            inbox_group="remitentes_nuevos",
            auth_result=auth,
            review_note=NOTE if auth == "unknown" else None,
        )
        return delivery.id

    aligned = held(space_id, SENDER, "aligned")
    failed = held(space_id, "caja@tienda.test", "failed")
    unknown = held(space_id, SENDER, "unknown")
    legacy = held(space_id, SENDER, None)
    reading = held(space_id, SENDER, "aligned", state="processing")
    stranger = held(space_id, "otro@tienda.test", "aligned")
    elsewhere = held(other_space, SENDER, "aligned")

    def row(delivery_id: str, space: str = space_id):  # noqa: ANN202
        saved = store.get(delivery_id, space)
        return (saved.inbox_group, saved.review_note, saved.state, saved.error_code)

    def waiting() -> int:
        return sum(
            item.inbox_group == "remitentes_nuevos" for item in store.list(space_id)
        )

    before = waiting()
    store.upsert_sender(space_id, "address", "caja@tienda.test", "authorized")
    moved = store.regroup_held(space_id, "caja@tienda.test", "authorized")
    assert moved == 2
    assert waiting() == before - moved
    assert row(aligned) == ("bandeja", None, "captured", None)
    assert row(failed) == ("bandeja", NOTE, "captured", None)
    assert row(unknown) == ("remitentes_nuevos", NOTE, "captured", None)
    assert row(legacy) == ("remitentes_nuevos", None, "captured", None)
    assert row(reading) == ("remitentes_nuevos", None, "processing", None)
    assert row(stranger) == ("remitentes_nuevos", None, "captured", None)
    assert row(elsewhere, other_space) == ("remitentes_nuevos", None, "captured", None)
    assert store.regroup_held(space_id, "caja@tienda.test", "authorized") == 0
    assert row(failed) == ("bandeja", NOTE, "captured", None)
    # A save that no longer stands moves nothing.
    assert store.regroup_held(space_id, "caja@tienda.test", "blocked") == 0

    before = waiting()
    store.upsert_sender(space_id, "address", "caja@tienda.test", "blocked")
    moved = store.regroup_held(space_id, SENDER, "blocked")
    assert moved == 2
    assert waiting() == before - moved
    assert row(unknown) == (None, None, "rejected", "email_sender_blocked")
    assert row(legacy) == (None, None, "rejected", "email_sender_blocked")
    assert row(aligned) == ("bandeja", None, "captured", None)
    assert row(reading) == ("remitentes_nuevos", None, "processing", None)
    assert row(stranger) == ("remitentes_nuevos", None, "captured", None)
    assert row(elsewhere, other_space) == ("remitentes_nuevos", None, "captured", None)
    assert store.regroup_held(space_id, SENDER, "blocked") == 0
