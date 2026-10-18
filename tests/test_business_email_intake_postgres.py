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

    async def raw_message(self, email_id: str, *, budget=None) -> ReceivedEmail:
        reservation = await budget.reserve() if budget else None
        self.calls += 1
        if budget:
            await budget.settle(reservation, len(self.raw))
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
        principal_id=users["owner"],
        granted_by=users["other"],
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
            user_id=rig["users"]["owner"], connection_id=connection_id, scope=scope
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
    ] == [delivery.id]


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


def test_a_route_names_the_business_owner_and_one_address_is_live(rig):
    store, users, space_id = rig["store"], rig["users"], rig["route"].space_id
    assert (
        store.create_route(
            recipient=f"recibos-{uuid4().hex[:8]}@recibos.example.test",
            space_id=space_id,
            principal_id=users["owner"],
            granted_by=users["other"],
            grant_id=str(rig["grant"]),
        ).id
        == rig["route"].id
    )
    assert store.deactivate_routes(space_id) == 1
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        store.create_route(
            recipient=f"recibos-{uuid4().hex[:8]}@recibos.example.test",
            space_id=space_id,
            principal_id=users["other"],
            granted_by=users["other"],
            grant_id=str(rig["grant"]),
        )
    assert store.route_for_space(space_id) is None


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


def test_the_earliest_save_of_a_file_is_found_by_business_and_bytes(rig, users):  # noqa: ANN001
    """On Postgres every document of a Business belongs to its owner (the
    connection's owner_space_id and user_id are pinned to spaces(id,
    created_by)), so the Business's first save of these bytes is the answer,
    and a save in another Business never counts."""

    import hashlib

    documents, space = rig["documents"], rig["route"].space_id
    content = message()
    digest = hashlib.sha256(content).hexdigest()
    assert documents.store.earliest_saved(space_id=space, sha256=digest) is None
    asyncio.run(
        documents.upload(
            user_id=users["owner"],
            scope=BusinessSpace(space),
            content=content,
            filename="a.eml",
            media_type="message/rfc822",
            consent=False,
        )
    )
    first = documents.store.earliest_saved(space_id=space, sha256=digest)
    assert first is not None
    # The same bytes again are the same document: the first save stays the answer.
    asyncio.run(
        documents.upload(
            user_id=users["owner"],
            scope=BusinessSpace(space),
            content=content,
            filename="b.eml",
            media_type="message/rfc822",
            consent=False,
        )
    )
    assert documents.store.earliest_saved(space_id=space, sha256=digest) == first
    assert documents.store.earliest_saved(space_id=str(uuid4()), sha256=digest) is None
    assert documents.store.earliest_saved(space_id=space, sha256="0" * 64) is None


@pytest.fixture
def address_client(rig, actions, monkeypatch):
    from argus.api.business import BusinessContext, require_business_document_write
    from argus.api.routers import email_intake as api
    from argus.domain.business.scope import BusinessScope
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()

    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = str(uuid4())
        return await call_next(request)

    app.state.financial_accounts_pool = rig["pool"]
    context = BusinessContext(
        scope=BusinessScope(rig["users"]["owner"], BusinessSpace(rig["route"].space_id)),
        service=None,
    )
    app.dependency_overrides[require_business_document_write] = lambda: context
    app.include_router(api.router)
    monkeypatch.setattr(api, "email_intake", lambda: rig["runtime"])
    monkeypatch.setattr(api, "ingestion_hub", lambda: rig["documents"].hub)
    rig["documents"].hub.sink = actions[0].imports
    monkeypatch.setattr(api, "webhook_enabled", lambda: True)
    monkeypatch.setenv("CUADRAO_BUSINESS_EMAIL_DOMAIN", "recibos.example.test")
    rig["store"].deactivate_routes(rig["route"].space_id)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def email_logs():
    from loguru import logger

    records = []
    handler = logger.add(lambda message: records.append(message.record))
    try:
        yield records
    finally:
        logger.remove(handler)


@pytest.mark.owner_acts
def test_new_receipt_address_has_128_random_bits(address_client, rig):
    import re

    response = address_client.post("/business/email")
    assert response.status_code == 201, response.text
    address = response.json()["receiving_address"]
    assert re.fullmatch(r"recibos-[0-9a-f]{32}@recibos\.example\.test", address)
    assert len(address) <= 254
    replay = address_client.post("/business/email")
    assert replay.status_code == 200
    assert replay.json()["receiving_address"] == address


@pytest.mark.owner_acts
@pytest.mark.parametrize("collisions", [1, 3, 4])
def test_recipient_collision_retries_are_bounded(
    address_client, rig, monkeypatch, email_logs, collisions
):
    from argus.api.routers import email_intake as api

    old = rig["route"].recipient
    taken = old.split("@", 1)[0].removeprefix("recibos-")
    sizes = []

    def token_hex(size):
        sizes.append(size)
        return taken if len(sizes) <= collisions else uuid4().hex

    monkeypatch.setattr(api.secrets, "token_hex", token_hex)
    response = address_client.post("/business/email")
    assert sizes == [16] * min(collisions + 1, 4)
    if collisions == 4:
        assert response.status_code == 503, response.text
        assert response.json()["detail"]["code"] == "email_route_unavailable"
        assert rig["store"].route_for_space(rig["route"].space_id) is None
        assert any(r["message"] == "email_route_collision_exhausted" for r in email_logs)
    else:
        assert response.status_code == 201, response.text
        assert response.json()["receiving_address"] != old
    assert sum(r["message"] == "email_route_collision" for r in email_logs) == collisions
    assert old not in str(email_logs)


def test_concurrent_route_creates_keep_one_live_route(rig):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    store, old = rig["store"], rig["route"]
    store.deactivate_routes(old.space_id)
    barrier = Barrier(2)

    def create(_):
        barrier.wait(timeout=5)
        return store.create_route(
            recipient=f"recibos-{uuid4().hex}@recibos.example.test",
            space_id=old.space_id,
            principal_id=old.principal_id,
            granted_by=old.granted_by,
            grant_id=old.grant_id,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        routes = list(executor.map(create, range(2)))
    assert routes[0].id == routes[1].id
    with rig["pool"].connection() as db:
        assert (
            db.execute(
                "select count(*) from public.business_email_routes where space_id=%s and active",
                (old.space_id,),
            ).fetchone()[0]
            == 1
        )


@pytest.mark.owner_acts
@pytest.mark.parametrize("rotate", [False, True])
def test_inactive_short_address_is_rejected_and_logged(
    address_client, rig, email_logs, rotate
):
    old = rig["route"]
    assert len(old.recipient.split("@", 1)[0]) < 40
    if rotate:
        assert address_client.post("/business/email").status_code == 201
    rejected = rig["runtime"].enqueue_resend(str(uuid4()), (old.recipient,))
    assert (rejected.state, rejected.error_code, rejected.route_id) == (
        "rejected",
        "email_route_unavailable",
        None,
    )
    assert not asyncio.run(rig["runtime"].next())
    assert rig["provider"].calls == 0
    assert any(r["message"] == "email_route_unavailable" for r in email_logs)
    assert old.recipient not in str(email_logs)
    with rig["pool"].connection() as db:
        assert (
            db.execute(
                "select count(*) from public.business_email_routes "
                "where space_id=%s and active and length(split_part(recipient,'@',1))<40",
                (old.space_id,),
            ).fetchone()[0]
            == 0
        )
        assert db.execute(
            "select count(*) from public.business_email_routes "
            "where space_id=%s and active and length(split_part(recipient,'@',1))=40",
            (old.space_id,),
        ).fetchone()[0] == int(rotate)
        assert (
            db.execute(
                "select count(*) from public.business_email_deliveries "
                "where id=%s and state='rejected' and error_code='email_route_unavailable'",
                (rejected.id,),
            ).fetchone()[0]
            == 1
        )
