"""On real Postgres, a receipt that arrived by WhatsApp is read through the
owner's own Business grant, as the web upload does, and settles in review,
only while the owner's stored receipt-reading setting is on."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

import pytest
from argus.domain.business.actions import BusinessActions
from argus.domain.business.authority import ActionError
from argus.domain.business.spaces import PostgresSpaceStore
from argus.domain.ingestion.connections_postgres import PostgresConnectionRepository
from argus.domain.ingestion.contract import Attachment
from argus.domain.ingestion.documents.extractor import batch_from_result
from argus.domain.ingestion.documents.models import DocumentDraft, ExtractionResult
from argus.domain.ingestion.documents.service import DocumentsService
from argus.domain.ingestion.documents.store_postgres import PostgresDocumentStore
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.ingestion.whatsapp.replies import compose_reply
from argus.domain.ingestion.whatsapp.store_postgres import PostgresWhatsAppStore

from tests import test_business_actions_postgres as shared
from tests.business_reading_support import ROUTE, reading_setting, turn_reading
from tests.document_extractor_support import StubPreparation, start_request
from tests.document_reads_support import read_receipt
from tests.document_sources_support import source_objects
from tests.ingestion import whatsapp_cases as cases
from tests.ingestion.whatsapp_support import ALICE_PHONE, RECEIPT_PNG, Media

actions = shared.actions
users = shared.users
pytestmark = shared.pytestmark


@pytest.fixture
def reads_finish_inside_the_request() -> None:
    """Each test takes the queued attempt after capture."""


class Extractor(StubPreparation):
    def __init__(self) -> None:
        self.calls = 0

    async def extract(self, **kwargs: Any):  # noqa: ANN201
        await start_request(kwargs)
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
                receipt=dict(payment_status="paid", total="250.50", currency="DOP"),
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


@pytest.fixture(autouse=True)
def _route(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "argus.domain.ingestion.whatsapp.receipt_consent.receipt_provider_route",
        lambda: ROUTE,
    )


def _rig(actions, users):  # noqa: ANN001, ANN202
    """Real Postgres, Business actions wired, the owner's grant seeded and the
    owner's receipt reading on."""

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
    documents.business_receipt_consent = reading_setting(pool)
    owner, space = str(context.owner_id), str(context.actor.space_id)
    turn_reading(documents.business_receipt_consent, space, owner)
    world = cases.build_world(
        documents=documents,
        store=PostgresWhatsAppStore(pool),
        clock=cases.Clock(),
        alice=owner,
        bob=users["other"],
        spaces=PostgresSpaceStore(pool),
    )
    return world, extractor


async def _capture(world: cases.World) -> str:
    await world.link(world.alice, ALICE_PHONE)
    media_id = "700000000000201"
    world.graph.media[media_id] = Media(RECEIPT_PNG, "image/png")
    await world.deliver(cases.image(media_id, "wamid.READ-PG"))
    [connection_id] = world.captures(world.alice)
    return connection_id


def _draft(world: cases.World, connection_id: str) -> DocumentDraft:
    return world.documents.get(
        user_id=world.alice,
        connection_id=connection_id,
        scope=world.business(world.alice),
    )


@pytest.mark.asyncio
async def test_a_whatsapp_receipt_is_read_through_the_owners_grant(actions, users):  # noqa: ANN001
    world, extractor = _rig(actions, users)
    connection_id = await _capture(world)
    assert _draft(world, connection_id).status == "queued"
    await read_receipt(world.documents, world.alice, connection_id)
    assert _draft(world, connection_id).status == "review_ready"
    assert extractor.calls == 1


@pytest.mark.asyncio
async def test_the_acknowledgement_is_the_only_reply_for_a_completed_read(  # noqa: ANN201
    actions,
    users,  # noqa: ANN001
):
    world, extractor = _rig(actions, users)
    connection_id = await _capture(world)
    replies = world.transport.bodies()
    assert len(replies) == 2
    assert replies[-1] == compose_reply("captured_reading", language="es-419")
    await read_receipt(world.documents, world.alice, connection_id)
    assert extractor.calls == 1
    assert _draft(world, connection_id).status == "review_ready"
    assert world.transport.bodies() == replies


@pytest.mark.asyncio
async def test_a_switch_turned_off_after_capture_stops_the_read(actions, users):  # noqa: ANN001
    world, extractor = _rig(actions, users)
    connection_id = await _capture(world)
    turn_reading(
        world.documents.business_receipt_consent,
        str(actions[1].actor.space_id),
        world.alice,
        False,
    )
    await read_receipt(world.documents, world.alice, connection_id)
    assert extractor.calls == 0
    assert _draft(world, connection_id).status == "saved"


@pytest.mark.asyncio
async def test_only_the_receiving_owner_can_be_the_actor(actions, users):  # noqa: ANN001
    world, extractor = _rig(actions, users)
    connection_id = await _capture(world)
    accountant = str(actions[1].actor.actor_id)
    assert accountant != world.alice
    assert await read_receipt(world.documents, accountant, connection_id) is None
    assert extractor.calls == 0


@pytest.mark.asyncio
async def test_a_read_that_cannot_start_waits_saved_with_its_reason(  # noqa: ANN201
    actions,
    users,
    monkeypatch,  # noqa: ANN001
):
    world, extractor = _rig(actions, users)

    def refused(*_: Any, **__: Any) -> None:
        raise ActionError("permission_denied", "business_permission_denied")

    monkeypatch.setattr(BusinessActions, "resolve_actor", refused)
    connection_id = await _capture(world)
    draft = _draft(world, connection_id)
    assert (draft.status, draft.error_code) == ("saved", "business_permission_denied")
    assert extractor.calls == 0


@pytest.mark.asyncio
async def test_a_read_refused_by_the_owners_own_grant_records_the_literal_code(
    actions, users, monkeypatch
):  # noqa: ANN001
    """No fake: the owner's grant loses prepare in the table the authority
    reads, so the read cannot start, and the saved draft records
    ``business_permission_denied``."""

    world, extractor = _rig(actions, users)
    _, context, _ = actions
    documents = world.documents
    upload = documents.upload

    async def revoke_after_save(**kwargs):
        outcome = await upload(**kwargs)
        with documents.business_actions.authority.pool.connection() as db:
            db.execute(
                "insert into public.business_client_grants(space_id,grantee_id,issuer_id,business_role,capabilities) values(%s,%s,%s,'owner',array['read','prepare','approve'])",
                (context.actor.space_id, users["other"], context.owner_id),
            )
            changed = db.execute(
                "update public.business_client_grants set business_role='viewer'"
                " where space_id=%s and grantee_id=%s and revoked_at is null",
                (context.actor.space_id, context.owner_id),
            ).rowcount
        # Exactly the owner's one live grant lost prepare; the refusal below is its doing.
        assert changed == 1
        return outcome

    monkeypatch.setattr(documents, "upload", revoke_after_save)
    connection_id = await _capture(world)
    draft = _draft(world, connection_id)
    assert (draft.status, draft.error_code) == ("saved", "business_permission_denied")
    assert extractor.calls == 0
