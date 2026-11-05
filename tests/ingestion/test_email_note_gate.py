"""Unverified mail is read or approved only as Pendiente, with the note beside it."""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest
from argus.domain.ingestion.documents.service import DocumentServiceError

from tests.ingestion.test_email_intake_service import _authorize, message, png, rig

NOTE = "No pudimos verificar este remitente."
SENDER = "proveedor@example.test"
FAIL = {"spf": "pass", "dkim": "fail", "dmarc": "fail"}
NO_POLICY = {"spf": "pass", "dkim": "gray", "dmarc": "gray"}


async def _delivered(world, authentication):
    world.provider.authentication = authentication
    world.provider.provider_from = SENDER
    delivery = world.enqueue()
    assert await world.runtime.next()
    space = world.route.space_id
    draft = str(uuid4())
    parts = [p.document_id for p in world.store.parts(delivery.id) if p.document_id]
    world.store.link_draft_documents(space, draft, parts)
    return delivery, draft


@pytest.mark.asyncio
@pytest.mark.parametrize("authentication", [FAIL, NO_POLICY], ids=["failed", "none"])
async def test_a_held_sender_authorized_later_stays_refused(authentication):
    world = rig()
    delivery, draft = await _delivered(world, authentication)
    space = world.route.space_id
    saved = world.store.get(delivery.id, space)
    assert (saved.inbox_group, saved.auth_result, saved.review_note) == (
        "remitentes_nuevos",
        "failed",
        None,
    )
    assert world.store.email_document_standing(space, draft) == "new"
    _authorize(world)
    assert world.store.email_document_standing(space, draft) == "new"


@pytest.mark.asyncio
async def test_a_retry_after_the_sender_was_removed_stays_refused_once_reauthorized(
    monkeypatch,
):
    world = rig(message(("a.png", "image/png", png()), ("b.png", "image/png", png())))
    _authorize(world)
    space = world.route.space_id
    original = world.documents.upload
    failing = {"b.png"}

    async def upload(**kwargs):
        if kwargs["filename"] in failing:
            failing.clear()
            raise DocumentServiceError("document_storage_unavailable", retryable=True)
        return await original(**kwargs)

    monkeypatch.setattr(world.documents, "upload", upload)
    delivery, _ = await _delivered(world, FAIL)
    first = world.store.get(delivery.id, space)
    assert (first.state, first.inbox_group, first.review_note) == (
        "partial",
        "bandeja",
        NOTE,
    )
    [rule] = world.store.list_senders(space)
    world.store.remove_sender(space, rule.id)
    world.clock.advance(11)
    assert await world.runtime.next()
    retried = world.store.get(delivery.id, space)
    assert (retried.inbox_group, retried.auth_result, retried.review_note) == (
        "remitentes_nuevos",
        "failed",
        None,
    )
    _authorize(world)
    draft = str(uuid4())
    parts = [p.document_id for p in world.store.parts(delivery.id) if p.document_id]
    world.store.link_draft_documents(space, draft, parts)
    assert world.store.email_document_standing(space, draft) == "new"


@pytest.mark.asyncio
async def test_a_row_from_before_the_note_is_refused():
    world = rig()
    _authorize(world)
    delivery, draft = await _delivered(world, FAIL)
    space = world.route.space_id
    assert world.store.email_document_standing(space, draft) == "authorized"
    world.store._deliveries[delivery.id] = replace(
        world.store.get(delivery.id, space),
        inbox_group="remitentes_nuevos",
        review_note=None,
    )
    assert world.store.email_document_standing(space, draft) == "new"


STORED = [
    (None, "bandeja", NOTE, "new"),
    ("unknown", "bandeja", NOTE, "new"),
    ("ambiguous", "bandeja", NOTE, "new"),
    ("no_result", "bandeja", NOTE, "new"),
    ("none", "bandeja", NOTE, "new"),
    ("failed", "bandeja", None, "new"),
    ("failed", "remitentes_nuevos", NOTE, "new"),
    ("failed", "bandeja", NOTE, "authorized"),
    ("aligned", "bandeja", None, "authorized"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("auth_result", "group", "note", "standing"), STORED)
async def test_each_stored_verdict_reads_only_as_the_gate_allows(
    auth_result, group, note, standing
):
    world = rig()
    _authorize(world)
    delivery, draft = await _delivered(world, FAIL)
    space = world.route.space_id
    world.store._deliveries[delivery.id] = replace(
        world.store.get(delivery.id, space),
        auth_result=auth_result,
        inbox_group=group,
        review_note=note,
    )
    assert world.store.email_document_standing(space, draft) == standing
