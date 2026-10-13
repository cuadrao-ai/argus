"""On real Postgres, an emailed receipt is read on its own through the owner's
own Business grant while the owner's permission is on, and waits saved and
unread once it is off; the permission is the stored one, read fresh."""

from __future__ import annotations

import io
from email.message import EmailMessage
from uuid import uuid4

import pytest
from argus.api.email_intake import EmailReader, automatic_read_gate
from argus.domain.business.actions import BusinessActions
from argus.domain.ingestion.connections_postgres import PostgresConnectionRepository
from argus.domain.ingestion.documents.service import DocumentsService
from argus.domain.ingestion.documents.store_postgres import PostgresDocumentStore
from argus.domain.ingestion.email_intake.ai_consent import (
    EmailConsentRequest,
    EmailConsentStore,
)
from argus.domain.ingestion.email_intake.service import (
    EmailCapture,
    grant_route_authority,
)
from argus.domain.ingestion.email_intake.store import PostgresEmailStore
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.owner_scope import BusinessSpace
from PIL import Image

from tests import test_business_actions_postgres as shared
from tests.document_sources_support import source_objects
from tests.test_business_email_intake_postgres import Provider
from tests.test_whatsapp_receipt_read_postgres import Extractor

actions = shared.actions
users = shared.users
pytestmark = shared.pytestmark


def message(color: str) -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", (32, 32), color).save(stream, format="PNG")
    msg = EmailMessage()
    msg["From"] = "proveedor@example.test"
    msg["Subject"] = "Factura"
    msg.set_content("Adjunto la factura.")
    msg.add_attachment(
        stream.getvalue(), maintype="image", subtype="png", filename="recibo.png"
    )
    return msg.as_bytes()


@pytest.fixture
def world(actions, users):  # noqa: ANN001
    service, context, grant = actions
    pool = service.authority.pool
    owner, space_id = str(context.owner_id), str(context.actor.space_id)
    with pool.connection() as db:
        db.execute(
            "insert into public.business_client_grants(space_id,grantee_id,issuer_id,capabilities)"
            " select %s,%s,%s,ARRAY['read','prepare','approve'] where not exists"
            " (select 1 from public.business_client_grants where space_id=%s and grantee_id=%s"
            " and revoked_at is null)",
            (space_id, owner, owner, space_id, owner),
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
    store = PostgresEmailStore(pool)
    recipient = f"recibos-{uuid4().hex[:8]}@recibos.example.test"
    route = store.create_route(
        recipient=recipient,
        space_id=space_id,
        principal_id=owner,
        granted_by=users["other"],
        grant_id=str(grant),
    )
    consent = EmailConsentStore(
        pool,
        lambda: {
            "gateway": "openrouter",
            "interpretation": [{"model": "scripted-fixture"}],
            "reply": [],
        },
    )
    provider = Provider(message("white"), (recipient,))
    runtime = EmailCapture(
        store,
        documents,
        grant_route_authority(pool),
        provider,
        lambda: True,
        lambda: True,
        reading=consent.reading_allowed,
        reader=EmailReader(documents),
    )
    documents.add_read_gate(automatic_read_gate(runtime, consent))
    return dict(
        pool=pool,
        documents=documents,
        extractor=extractor,
        store=store,
        route=route,
        consent=consent,
        provider=provider,
        runtime=runtime,
        owner=owner,
        space=space_id,
    )


def _drafts(world):  # noqa: ANN001, ANN201
    scope = BusinessSpace(world["space"])
    return [
        world["documents"].get(user_id=world["owner"], connection_id=c.id, scope=scope)
        for c in world["documents"].hub.connections.list(
            user_id=world["owner"], scope=scope
        )
    ]


def _enable(world):  # noqa: ANN001
    view = world["consent"].status(world["space"], world["owner"], "es-419")
    world["consent"].enable(
        world["space"],
        world["owner"],
        EmailConsentRequest(
            action="enable", disclosure_token=view["disclosure_token"], language="es-419"
        ),
        str(uuid4()),
    )


@pytest.mark.asyncio
async def test_with_the_permission_on_the_attachment_is_read_through_the_owners_grant_and_off_it_waits(
    world,  # noqa: ANN001
) -> None:
    # Before the owner answered: saved, unread, nothing sent to the provider.
    first = world["runtime"].enqueue_resend(str(uuid4()), (world["route"].recipient,))
    assert await world["runtime"].next()
    assert [d.status for d in _drafts(world) if d.filename == "recibo.png"] == ["saved"]
    assert world["extractor"].calls == 0
    # The owner turns reading on: the next email is read and lands in review.
    _enable(world)
    world["provider"].raw = message("red")
    second = world["runtime"].enqueue_resend(str(uuid4()), (world["route"].recipient,))
    assert await world["runtime"].next()
    drafts = _drafts(world)
    read = [d for d in drafts if d.filename == "recibo.png" and d.consent]
    assert len(read) == 1 and read[0].status == "review_ready"
    assert world["extractor"].calls == 1
    assert read[0].read_by == "email_switch"
    with world["pool"].connection() as db:
        states = db.execute(
            "select d.id::text, d.state from public.business_email_deliveries d"
            " where d.space_id=%s order by d.received_at",
            (world["space"],),
        ).fetchall()
    assert [s for _, s in states] == ["captured", "captured"]
    assert {i for i, _ in states} == {first.id, second.id}
    # The first email's attachment was never read after the fact.
    assert sum(1 for d in drafts if d.filename == "recibo.png") == 2
    # Turned off: a third email waits saved and unread; the provider is not called.
    world["consent"].revoke(world["space"], world["owner"])
    world["provider"].raw = message("blue")
    world["runtime"].enqueue_resend(str(uuid4()), (world["route"].recipient,))
    assert await world["runtime"].next()
    assert world["extractor"].calls == 1
    unread = [
        d for d in _drafts(world) if d.filename == "recibo.png" and d.status == "saved"
    ]
    assert len(unread) == 2 and all(not d.consent for d in unread)
