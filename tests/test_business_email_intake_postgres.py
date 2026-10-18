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
        self.sender = "proveedor@example.test"
        self.authentication = None
        self.provider_from = None

    async def preview_from(self, email_id: str) -> str | None:
        return self.sender

    async def raw_message(self, email_id: str, *, budget=None) -> ReceivedEmail:
        reservation = await budget.reserve() if budget else None
        self.calls += 1
        if budget:
            await budget.settle(reservation, len(self.raw))
        return ReceivedEmail(
            self.raw, self.recipients, self.authentication, self.provider_from
        )


def fresh_alias() -> str:
    return f"a{uuid4().hex[:8]}"


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
            "business_email_retired_aliases",
            "business_email_senders",
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
def test_new_receipt_address_uses_the_chosen_alias(address_client, rig):
    alias = fresh_alias()
    response = address_client.post("/business/email", json={"alias": alias})
    assert response.status_code == 201, response.text
    address = response.json()["receiving_address"]
    domain = address.split("@", 1)[1]
    assert address == f"{alias}@{domain}"
    assert len(address) <= 254
    replay = address_client.post("/business/email", json={"alias": alias})
    assert replay.status_code == 200
    assert replay.json()["receiving_address"] == address


@pytest.mark.owner_acts
def test_a_taken_alias_is_refused_without_logging_the_address(
    address_client, rig, email_logs
):
    alias = fresh_alias()
    created = address_client.post("/business/email", json={"alias": alias})
    assert created.status_code == 201, created.text
    rig["store"].deactivate_routes(rig["route"].space_id)
    again = address_client.post("/business/email", json={"alias": alias})
    assert again.status_code == 422, again.text
    body = again.json()["detail"]
    assert body["code"] == "email_alias_unavailable"
    assert body["detail"] == "Ese nombre no está disponible. Prueba otro."
    assert alias not in str(email_logs)
    assert any(record["message"] == "email_alias_unavailable" for record in email_logs)


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
    alias = fresh_alias()
    assert len(old.recipient.split("@", 1)[0]) < 40
    if rotate:
        created = address_client.post("/business/email", json={"alias": alias})
        assert created.status_code == 201, created.text
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
                "where space_id=%s and active and recipient=%s",
                (old.space_id, old.recipient),
            ).fetchone()[0]
            == 0
        )
        assert db.execute(
            "select count(*) from public.business_email_routes "
            "where space_id=%s and active and split_part(recipient,'@',1)=%s",
            (old.space_id, alias),
        ).fetchone()[0] == int(rotate)
        assert (
            db.execute(
                "select count(*) from public.business_email_deliveries "
                "where id=%s and state='rejected' and error_code='email_route_unavailable'",
                (rejected.id,),
            ).fetchone()[0]
            == 1
        )


@pytest.mark.owner_acts
def test_alias_change_keeps_the_delivery_and_retires_the_old_recipient(
    address_client, rig
):
    created = address_client.post("/business/email", json={"alias": fresh_alias()})
    assert created.status_code == 201, created.text
    old = created.json()["receiving_address"]
    delivery = rig["runtime"].enqueue_resend(str(uuid4()), (old,))
    nxt = fresh_alias()
    changed = address_client.post("/business/email/address", json={"alias": nxt})
    assert changed.status_code == 200, changed.text
    assert changed.json()["alias"] == nxt
    saved = rig["store"].get(delivery.id, rig["route"].space_id)
    assert saved.route_id == delivery.route_id
    assert saved.recipients == (old,)
    bounced = rig["runtime"].enqueue_resend(str(uuid4()), (old,))
    assert bounced.state == "rejected"
    assert bounced.error_code == "email_alias_retired"
    assert bounced.bounce_text.startswith("Esta dirección ya no recibe recibos.")
    assert nxt not in bounced.bounce_text
    route_id = saved.route_id
    with rig["pool"].connection() as db, pytest.raises(psycopg.errors.RaiseException):
        db.execute(
            "update public.business_email_routes set space_id="
            "(select id from public.spaces where id<>%s limit 1) where id=%s",
            (rig["route"].space_id, route_id),
        )


def test_address_and_sender_changes_leave_an_audit_row(rig):
    store, route, actor = rig["store"], rig["route"], rig["users"]["owner"]
    space_id = route.space_id
    previous = route.recipient
    alias = fresh_alias()
    recipient = f"{alias}@recibos.example.test"
    store.change_address(
        route.id,
        alias=alias,
        alias_normalized=alias,
        recipient=recipient,
        review_required=False,
        actor_id=actor,
    )
    store.deactivate_routes(space_id, actor_id=actor)
    sender = store.upsert_sender(
        space_id, "address", "caja@tienda.test", "authorized", actor_id=actor
    )
    store.upsert_sender(
        space_id, "address", "otro@tienda.test", "blocked", actor_id=actor
    )
    assert store.remove_sender(space_id, sender.id, actor_id=actor) is not None
    events = store.address_events(space_id)
    assert [(event.event_type, event.old_address, event.new_address) for event in events] == [
        ("address_changed", previous, recipient),
        ("address_stopped", recipient, None),
        ("sender_authorized", None, "caja@tienda.test"),
        ("sender_blocked", "otro@tienda.test", "otro@tienda.test"),
        ("sender_removed", "caja@tienda.test", None),
    ]
    assert {event.actor_id for event in events} == {actor}
    assert all(event.created_at is not None for event in events)


def _daily(rig) -> tuple[int, int] | None:
    with rig["pool"].connection() as db:
        return db.execute(
            "select messages, bytes_used from public.business_email_daily_usage"
            " where route_id=%s",
            (rig["route"].id,),
        ).fetchone()


def _spoof(rig, messages: int, byte_cap: int) -> None:
    from argus.domain.ingestion.email_intake.budget import DailyEmailBudget

    rig["store"].budget = DailyEmailBudget(messages, byte_cap)
    rig["store"].upsert_sender(
        rig["route"].space_id, "address", "proveedor@example.test", "authorized"
    )
    rig["provider"].authentication = {"spf": "pass", "dkim": "fail", "dmarc": "fail"}
    rig["provider"].provider_from = "proveedor@example.test"
    for _ in range(6):
        rig["runtime"].enqueue_resend(str(uuid4()), (rig["route"].recipient,))
        asyncio.run(rig["runtime"].next())


def test_a_forged_authorized_sender_is_charged_on_postgres(rig):
    from argus.domain.ingestion.documents.config import SOURCE_MAX_BYTES

    _spoof(rig, 100, 2 * SOURCE_MAX_BYTES)
    assert rig["provider"].calls == 2
    assert _daily(rig) == (2, 2 * SOURCE_MAX_BYTES)
    with rig["pool"].connection() as db:
        flags = db.execute(
            "select cap_exempt from public.business_email_deliveries where route_id=%s",
            (rig["route"].id,),
        ).fetchall()
    assert [flag[0] for flag in flags] == [False, False, False, False, False, False]


def test_a_full_message_cap_does_not_fetch_spoofed_mail_on_postgres(rig):
    from argus.domain.ingestion.documents.config import SOURCE_MAX_BYTES

    _spoof(rig, 2, 100 * SOURCE_MAX_BYTES)
    assert rig["provider"].calls == 2
    with rig["pool"].connection() as db:
        flags = db.execute(
            "select cap_exempt from public.business_email_deliveries where route_id=%s",
            (rig["route"].id,),
        ).fetchall()
    assert flags
    assert all(flag[0] is False for flag in flags)


def test_deleting_the_space_keeps_the_alias_taken(rig):
    alias = fresh_alias()
    store = rig["store"]
    store.change_address(
        rig["route"].id,
        alias=alias,
        alias_normalized=alias,
        recipient=f"{alias}@recibos.example.test",
        review_required=False,
    )
    with rig["pool"].connection() as db:
        db.execute("delete from public.spaces where id=%s", (rig["route"].space_id,))
    assert store.alias_taken(alias) is True
