"""Email receiving on real Postgres: route binding, capture, revocation, isolation."""

from __future__ import annotations

import asyncio
import io
from email.message import EmailMessage
from uuid import uuid4

import psycopg
import pytest
from argus.domain.ingestion.connections_postgres import PostgresConnectionRepository
from argus.domain.ingestion.documents.service import DocumentsService
from argus.domain.ingestion.documents.store_postgres import PostgresDocumentStore
from argus.domain.ingestion.email_intake.provider import ReceivedEmail
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
from tests.ingestion.whatsapp_support import RefusingExtractor

actions = shared.actions
users = shared.users
pytestmark = shared.pytestmark


class Provider:
    def __init__(self, raw: bytes, recipients: tuple[str, ...]) -> None:
        self.raw, self.recipients, self.calls = raw, recipients, 0

    async def raw_message(self, email_id: str) -> ReceivedEmail:
        self.calls += 1
        return ReceivedEmail(self.raw, self.recipients)


def message() -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", (32, 32), "white").save(stream, format="PNG")
    msg = EmailMessage()
    msg["From"] = "proveedor@example.test"
    msg["Subject"] = "Factura"
    msg.set_content("Adjunto la factura.")
    msg.add_attachment(
        stream.getvalue(), maintype="image", subtype="png", filename="recibo.png"
    )
    return msg.as_bytes()


@pytest.fixture
def rig(actions, users):
    service, context, grant = actions
    pool = service.authority.pool
    connections = PostgresConnectionRepository(pool)
    hub = IngestionHub(connections, box=None, sink=None, clock=service.imports.clock)
    documents = DocumentsService(
        hub, PostgresDocumentStore(pool, source_objects()), RefusingExtractor()
    )
    store = PostgresEmailStore(pool)
    recipient = f"recibos-{uuid4().hex[:8]}@recibos.example.test"
    route = store.create_route(
        recipient=recipient,
        space_id=str(context.actor.space_id),
        principal_id=users["other"],
        granted_by=users["owner"],
        grant_id=str(grant),
    )
    provider = Provider(message(), (recipient,))
    runtime = EmailCapture(
        store,
        documents,
        grant_route_authority(pool),
        provider,
        lambda: True,
        lambda: True,
    )
    yield dict(
        pool=pool,
        store=store,
        documents=documents,
        runtime=runtime,
        route=route,
        provider=provider,
        grant=grant,
        context=context,
        users=users,
    )


def test_route_capture_lands_in_the_business_as_unprepared_documents(rig):
    delivery = rig["runtime"].enqueue_resend(str(uuid4()), (rig["route"].recipient,))
    assert (delivery.state, delivery.route_id) == ("received", rig["route"].id)
    assert asyncio.run(rig["runtime"].next())
    saved = rig["store"].get(delivery.id, rig["route"].space_id)
    assert (saved.state, saved.error_code, saved.subject) == ("captured", None, "Factura")
    parts = rig["store"].parts(delivery.id)
    assert [(p.filename, p.state) for p in parts] == [("recibo.png", "captured")]
    scope = BusinessSpace(rig["route"].space_id)
    for connection_id in (saved.original_document_id, parts[0].document_id):
        draft = rig["documents"].get(
            user_id=rig["users"]["other"], connection_id=connection_id, scope=scope
        )
        assert draft.consent is False and draft.status == "saved"
    # The same event again is the same row; nothing is fetched or saved twice.
    assert (
        rig["runtime"].enqueue_resend(delivery.external_id, (rig["route"].recipient,)).id
        == delivery.id
    )
    assert not asyncio.run(rig["runtime"].next())
    assert rig["provider"].calls == 1
    assert rig["store"].membership(rig["route"].space_id)[parts[0].document_id][
        "delivery_ids"
    ] == {delivery.id}


def test_revoked_grant_rejects_new_mail_and_the_route_cannot_move(rig):
    with rig["pool"].connection() as db:
        db.execute(
            "update public.business_client_grants set revoked_at=now() where id=%s",
            (rig["grant"],),
        )
    rejected = rig["runtime"].enqueue_resend(str(uuid4()), (rig["route"].recipient,))
    assert (rejected.state, rejected.error_code, rejected.route_id) == (
        "rejected",
        "email_route_revoked",
        None,
    )
    assert rig["provider"].calls == 0
    with rig["pool"].connection() as db, pytest.raises(psycopg.errors.RaiseException):
        db.execute(
            "update public.business_email_routes set space_id=(select id from public.spaces where id<>%s limit 1) where id=%s",
            (rig["route"].space_id, rig["route"].id),
        )
    assert rig["store"].deactivate_routes(rig["route"].space_id) == 1
    assert rig["store"].route_for_space(rig["route"].space_id) is None


def test_clients_cannot_read_the_queue(rig):
    with rig["pool"].connection() as db:
        db.execute("set local role authenticated")
        for table in (
            "business_email_routes",
            "business_email_deliveries",
            "business_email_parts",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with db.transaction():
                    db.execute(f"select count(*) from public.{table}")
