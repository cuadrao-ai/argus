"""A stored sender verdict gates reading and approval, and a retry keeps it."""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest
from argus.domain.ingestion.documents.service import DocumentServiceError

from tests.ingestion.test_email_intake_service import _authorize, message, png, rig

NOTE = "No pudimos verificar este remitente."


@pytest.mark.asyncio
async def test_an_authorized_delivery_with_no_stored_verdict_is_refused():
    world = rig()
    _authorize(world)
    world.provider.authentication = {"spf": "pass", "dkim": "pass", "dmarc": "pass"}
    world.provider.provider_from = "proveedor@example.test"
    delivery = world.enqueue()
    assert await world.runtime.next()
    space = world.route.space_id
    [part] = world.store.parts(delivery.id)
    draft = str(uuid4())
    world.store.link_draft_documents(space, draft, [part.document_id])
    assert world.store.email_document_standing(space, draft) == "authorized"
    saved = world.store._deliveries[delivery.id]
    world.store._deliveries[delivery.id] = replace(saved, auth_result=None)
    assert world.store.email_document_standing(space, draft) == "new"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("authentication", "verdict"),
    [
        ({"spf": "pass", "dkim": "pass", "dmarc": "pass"}, ("bandeja", "aligned", None)),
        ({"spf": "pass", "dkim": "fail", "dmarc": "fail"}, ("bandeja", "failed", NOTE)),
    ],
)
async def test_a_retry_keeps_the_stored_verdict(monkeypatch, authentication, verdict):
    world = rig(message(("a.png", "image/png", png()), ("b.png", "image/png", png())))
    _authorize(world)
    world.provider.authentication = authentication
    world.provider.provider_from = "proveedor@example.test"
    original = world.documents.upload
    failing = {"b.png"}

    async def upload(**kwargs):
        if kwargs["filename"] in failing:
            failing.clear()
            raise DocumentServiceError("document_storage_unavailable", retryable=True)
        return await original(**kwargs)

    monkeypatch.setattr(world.documents, "upload", upload)
    delivery = world.enqueue()
    assert await world.runtime.next()
    space = world.route.space_id
    first = world.store.get(delivery.id, space)
    assert first.state == "partial"
    assert (first.inbox_group, first.auth_result, first.review_note) == verdict
    world.clock.advance(11)
    assert await world.runtime.next()
    retried = world.store.get(delivery.id, space)
    assert retried.state == "captured"
    assert (retried.inbox_group, retried.auth_result, retried.review_note) == verdict
    assert world.provider.calls == 1
