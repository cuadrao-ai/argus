"""On real Postgres, a receipt that arrived by WhatsApp is read through the
owner's own Business grant, as the web upload does, and settles in review."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from types import SimpleNamespace
from typing import Any

import pytest
from argus.api.whatsapp import DocumentsDestination, _whatsapp_read_gate
from argus.domain.business.actions import BusinessActions
from argus.domain.business.authority import ActionError
from argus.domain.business.scope import resolve_business_scope
from argus.domain.business.spaces import PostgresSpaceStore
from argus.domain.ingestion.connections_postgres import PostgresConnectionRepository
from argus.domain.ingestion.contract import Attachment
from argus.domain.ingestion.documents.extractor import batch_from_result
from argus.domain.ingestion.documents.models import ExtractionResult
from argus.domain.ingestion.documents.service import DocumentsService
from argus.domain.ingestion.documents.store_postgres import PostgresDocumentStore
from argus.domain.ingestion.hub import IngestionHub

from tests import test_business_actions_postgres as shared
from tests.document_sources_support import source_objects
from tests.ingestion.whatsapp_support import RECEIPT_PNG

actions = shared.actions
users = shared.users
pytestmark = shared.pytestmark


class Extractor:
    def __init__(self) -> None:
        self.calls = 0

    async def extract(self, **kwargs: Any):  # noqa: ANN201
        self.calls += 1
        result = ExtractionResult.model_validate(
            dict(
                complete=True,
                readable=True,
                pages_read=[1],
                observations=[
                    dict(
                        page=1,
                        row=1,
                        evidence="transaction",
                        amount="250.50",
                        currency="DOP",
                        direction="outflow",
                        kind_hint="expense",
                        merchant="Synthetic shop",
                    )
                ],
                receipt=dict(total="250.50", currency="DOP"),
            )
        )
        digest = sha256(kwargs["content"]).hexdigest()
        batch = batch_from_result(
            result, digest, kwargs["connection_id"], datetime.now(timezone.utc), 1
        )
        attachment = Attachment(
            external_id=digest,
            sha256=digest,
            media_type=kwargs["media_type"],
            size_bytes=len(kwargs["content"]),
            filename=kwargs["filename"],
        )
        return batch.model_copy(
            update={
                "metadata": {"sha256": digest},
                "candidates": tuple(
                    c.model_copy(update={"attachments": (attachment,)})
                    for c in batch.candidates
                ),
            }
        )


def _rig(actions, switch):  # noqa: ANN001, ANN202
    """Real Postgres, Business actions wired, the owner's grant seeded."""

    service, context, _ = actions
    pool = service.authority.pool
    with pool.connection() as db:
        db.execute(
            "insert into public.business_client_grants(space_id,grantee_id,issuer_id,capabilities)"
            " select %s,%s,%s,ARRAY['read','prepare','approve'] where not exists"
            " (select 1 from public.business_client_grants where space_id=%s and grantee_id=%s"
            " and revoked_at is null)",
            (
                context.actor.space_id,
                context.owner_id,
                context.owner_id,
                context.actor.space_id,
                context.owner_id,
            ),
        )
    hub = IngestionHub(
        PostgresConnectionRepository(pool),
        box=None,
        sink=service.imports,
        clock=service.imports.clock,
    )
    extractor = Extractor()
    documents = DocumentsService(
        hub,
        PostgresDocumentStore(pool, source_objects()),
        extractor,
        business_actions=BusinessActions(pool, hub.sink),
        business_preparation_required=True,
    )
    reading = lambda _owner: switch["on"]  # noqa: E731
    owner = str(context.owner_id)
    documents.read_gate = _whatsapp_read_gate(
        SimpleNamespace(capture_owner=lambda **_: owner), reading
    )
    destination = DocumentsDestination(documents, PostgresSpaceStore(pool), reading)
    return destination, documents, extractor, owner


async def _capture(destination, owner):  # noqa: ANN001, ANN202
    captured = await destination.capture(
        owner_id=owner,
        content=RECEIPT_PNG,
        filename="whatsapp-image",
        media_type="image/png",
    )
    return captured.connection_id


def _draft(destination, owner, connection_id):  # noqa: ANN001, ANN202
    scope = resolve_business_scope(destination.spaces, owner)
    return destination.documents.get(
        user_id=owner, connection_id=connection_id, scope=scope.owner
    )


@pytest.mark.asyncio
async def test_a_whatsapp_receipt_is_read_through_the_owners_grant(actions):  # noqa: ANN001
    destination, _, extractor, owner = _rig(actions, {"on": True})
    connection_id = await _capture(destination, owner)
    result = await destination.read(owner_id=owner, connection_id=connection_id)
    assert result is not None and result[0] == "review_ready"
    assert extractor.calls == 1


@pytest.mark.asyncio
async def test_a_switch_turned_off_after_capture_stops_the_read(actions):  # noqa: ANN001
    switch = {"on": True}
    destination, _, extractor, owner = _rig(actions, switch)
    connection_id = await _capture(destination, owner)
    switch["on"] = False
    await destination.read(owner_id=owner, connection_id=connection_id)
    assert extractor.calls == 0
    assert _draft(destination, owner, connection_id).status == "saved"


@pytest.mark.asyncio
async def test_only_the_receiving_owner_can_be_the_actor(actions):  # noqa: ANN001
    destination, _, extractor, owner = _rig(actions, {"on": True})
    connection_id = await _capture(destination, owner)
    accountant = str(actions[1].actor.actor_id)
    assert accountant != owner
    assert (
        await destination.read(owner_id=accountant, connection_id=connection_id) is None
    )
    assert extractor.calls == 0


@pytest.mark.asyncio
async def test_a_read_that_cannot_start_waits_saved_with_its_reason(  # noqa: ANN201
    actions,
    monkeypatch,  # noqa: ANN001
):
    destination, documents, extractor, owner = _rig(actions, {"on": True})
    connection_id = await _capture(destination, owner)

    def refused(*_: Any, **__: Any) -> None:
        raise ActionError("permission_denied", "business_permission_denied")

    monkeypatch.setattr(documents.business_actions, "resolve_actor", refused)
    with pytest.raises(ActionError):
        await destination.read(owner_id=owner, connection_id=connection_id)
    draft = _draft(destination, owner, connection_id)
    assert (draft.status, draft.error_code) == ("saved", "business_permission_denied")
    assert extractor.calls == 0


@pytest.mark.asyncio
async def test_a_read_refused_by_the_owners_own_grant_records_the_literal_code(actions):  # noqa: ANN001
    """No fake: the owner's grant loses prepare in the table the authority
    reads, so the read cannot start for a permission reason, and the draft
    records exactly ``business_permission_denied``."""

    destination, documents, extractor, owner = _rig(actions, {"on": True})
    connection_id = await _capture(destination, owner)
    _, context, _ = actions
    with documents.business_actions.authority.pool.connection() as db:
        changed = db.execute(
            "update public.business_client_grants set capabilities=ARRAY['read','approve']"
            " where space_id=%s and grantee_id=%s and revoked_at is null",
            (context.actor.space_id, context.owner_id),
        ).rowcount
    # Exactly the owner's one live grant lost prepare; the refusal below is its doing.
    assert changed == 1
    with pytest.raises(ActionError) as refused:
        await destination.read(owner_id=owner, connection_id=connection_id)
    assert refused.value.result.code == "business_permission_denied"
    draft = _draft(destination, owner, connection_id)
    assert (draft.status, draft.error_code) == ("saved", "business_permission_denied")
    assert extractor.calls == 0
