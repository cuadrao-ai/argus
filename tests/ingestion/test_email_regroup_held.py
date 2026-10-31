"""A sender rule re-places that sender's held emails in the memory store."""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from argus.domain.ingestion.email_intake.store import InMemoryEmailStore

from tests.ingestion.email_regroup_support import held_scenario


def _placer(store):  # noqa: ANN001, ANN202
    def place(delivery_id: str, **columns) -> None:  # noqa: ANN003
        store._deliveries[delivery_id] = replace(
            store._deliveries[delivery_id], **columns
        )

    return place


def test_a_rule_re_places_held_emails_in_memory():
    store = InMemoryEmailStore()
    route = store.create_route(
        recipient="caja@recibos.example.test",
        space_id=str(uuid4()),
        principal_id=str(uuid4()),
        granted_by=str(uuid4()),
        grant_id=str(uuid4()),
    )
    held_scenario(store, route, str(uuid4()), _placer(store))
