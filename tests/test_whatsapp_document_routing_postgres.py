"""Routing proof on the signed webhook and the migrated disposable database."""

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from argus.api.documents import DocumentContext, require_saved_document_context
from argus.api.main import app
from argus.api.whatsapp import whatsapp_runtime
from argus.domain.business.spaces import PostgresSpaceStore
from argus.domain.ingestion.documents.service import DocumentServiceError
from argus.domain.ingestion.whatsapp.held import held_files, is_held
from argus.domain.ingestion.whatsapp.receipt_consent import receipt_consent_store
from argus.domain.owner_scope import PERSONAL
from faker import Faker

from tests.business_reading_support import ROUTE, turn_reading
from tests.ingestion.whatsapp_cases import image
from tests.ingestion.whatsapp_link_support import prepare_phone_business
from tests.ingestion.whatsapp_support import RECEIPT_PNG, Media, encode, fixture
from tests.test_whatsapp_webhook_postgres import (
    MEDIA_ID,
    MESSAGE_ID,
    Webhook,
    _assert_interrupted,
    actions,
    pytestmark,
    reads_finish_inside_the_request,
    users,
    webhook,
)

__all__ = ["actions", "pytestmark", "reads_finish_inside_the_request", "users", "webhook"]


def test_both_business_pin_triggers_are_gone(actions):
    with actions[0].authority.pool.connection() as db:
        assert (
            db.execute(
                "select tgname from pg_trigger where not tgisinternal and "
                "(tgrelid, tgname) in (('public.whatsapp_sender_links'::regclass, "
                "'fill_sender_link_space'), ('public.whatsapp_inbound_messages'::regclass, "
                "'whatsapp_capture_same_space'))"
            ).fetchall()
            == []
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("loss", ["reading", "fiscal_id"])
@pytest.mark.parametrize("when", ["before_capture", "before_settlement"])
async def test_signed_file_with_no_eligible_destination_stays_private(
    webhook: Webhook, loss, when, monkeypatch
):
    with webhook.pool.connection() as db:
        space = db.execute(
            "select id::text from public.spaces where created_by=%s and kind='business'",
            (webhook.owner,),
        ).fetchone()[0]

    def withdraw():
        if loss == "reading":
            turn_reading(
                webhook.documents.business_receipt_consent, space, webhook.owner, False
            )
        else:
            with webhook.pool.connection() as db:
                db.execute(
                    "update public.spaces set business_rnc=null where id=%s", (space,)
                )

    if when == "before_capture":
        withdraw()
    else:
        upload = webhook.documents.upload

        async def upload_then_withdraw(**kwargs):
            result = await upload(**kwargs)
            withdraw()
            return result

        monkeypatch.setattr(webhook.documents, "upload", upload_then_withdraw)

    response = await webhook.post(webhook.signed_receipt(RECEIPT_PNG))

    assert response.status_code == 200
    held = held_files(webhook.documents.store).list_for_user(webhook.owner)
    assert [item.reason for item in held] == ["no_eligible_business"]
    with webhook.pool.connection() as db:
        assert db.execute(
            "select c.owner_space_id, d.preparation_job from "
            "public.financial_source_connections c join public.financial_document_extractions d "
            "on d.connection_id=c.id where c.id=%s",
            (held[0].connection_id,),
        ).fetchone() == (None, None)

    inbound = webhook.store.inbound(webhook.key)
    assert (inbound.status, inbound.sender_link_id, inbound.connection_id) == (
        "captured",
        held[0].sender_link_id,
        held[0].connection_id,
    )
    assert (
        webhook.documents.store.source(
            user_id=webhook.owner, connection_id=inbound.connection_id
        )
        == RECEIPT_PNG
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("consented", [True, False])
async def test_multi_business_duplicate_retains_one_private_file_and_read(
    webhook: Webhook, consented, monkeypatch
):
    monkeypatch.setattr(
        "argus.domain.ingestion.whatsapp.receipt_consent.receipt_provider_route",
        lambda: ROUTE,
    )
    space, _ = PostgresSpaceStore(webhook.pool).create_additional(
        webhook.owner, Faker().company(), "DO", str(uuid4())
    )
    prepare_phone_business(webhook.pool, space.id, webhook.owner)
    if not consented:
        receipt_consent_store(webhook.pool).revoke(UUID(webhook.owner))
    raw = webhook.signed_receipt(RECEIPT_PNG)
    assert (await webhook.post(raw)).status_code == 200
    [held] = held_files(webhook.documents.store).list_for_user(webhook.owner)
    [(connection, draft, job, binding)] = webhook.drafts()
    assert connection == held.connection_id
    assert draft["status"] == ("queued" if consented else "saved")
    assert bool(job) == consented
    assert binding is None
    inbound = webhook.store.inbound(webhook.key)
    assert inbound.sender_link_id == held.sender_link_id and inbound.status == "captured"

    resent = encode(image(MEDIA_ID, "wamid.SECOND-DELIVERY"), webhook.clock.now)
    assert (await webhook.post(resent)).status_code == 200
    assert held_files(webhook.documents.store).list_for_user(webhook.owner) == [held]
    assert webhook.drafts() == [(connection, draft, job, binding)]
    assert webhook.replies == [
        {"messaging_product": "whatsapp", "status": "read", "message_id": MESSAGE_ID},
    ]

    # A newly unique grant cannot turn a resend into a second Business upload.
    turn_reading(
        webhook.documents.business_receipt_consent, space.id, webhook.owner, False
    )
    resent = encode(image(MEDIA_ID, "wamid.SINGLE-AFTER-HOLD"), webhook.clock.now)
    assert (await webhook.post(resent)).status_code == 200
    assert held_files(webhook.documents.store).list_for_user(webhook.owner) == [held]
    assert webhook.drafts() == [(connection, draft, job, binding)]


@pytest.mark.asyncio
async def test_unavailable_private_storage_requires_redelivery(
    webhook: Webhook, monkeypatch
):
    with webhook.pool.connection() as db:
        db.execute(
            "update public.spaces set business_rnc=null where created_by=%s",
            (webhook.owner,),
        )

    async def unavailable(**kwargs):
        raise DocumentServiceError("document_storage_unavailable", retryable=True)

    raw = webhook.signed_receipt(RECEIPT_PNG)
    with monkeypatch.context() as patch:
        patch.setattr(webhook.documents, "upload", unavailable)
        response = await webhook.post(raw)
    assert (response.status_code, response.json()["code"]) == (
        503,
        "whatsapp_webhook_retry",
    )
    assert held_files(webhook.documents.store).list_for_user(webhook.owner) == []
    assert (await webhook.post(raw)).status_code == 200
    assert (await webhook.post(raw)).status_code == 200
    [held] = held_files(webhook.documents.store).list_for_user(webhook.owner)
    inbound = webhook.store.inbound(webhook.key)
    assert inbound.status == "captured" and inbound.connection_id == held.connection_id


@pytest.mark.asyncio
async def test_private_staging_crash_stays_out_of_personal_listing_and_redelivers(
    webhook: Webhook, monkeypatch
):
    with webhook.pool.connection() as db:
        db.execute(
            "update public.spaces set business_rnc=null where created_by=%s",
            (webhook.owner,),
        )
    monkeypatch.setitem(
        app.dependency_overrides,
        require_saved_document_context,
        lambda: DocumentContext(webhook.documents, webhook.owner),
    )
    upload = webhook.documents.upload
    staged = []

    async def crash_after_upload(**kwargs):
        outcome = await upload(**kwargs)
        staged.append(outcome.connection_id)
        raise asyncio.CancelledError

    raw = webhook.signed_receipt(RECEIPT_PNG)
    with monkeypatch.context() as patch:
        patch.setattr(webhook.documents, "upload", crash_after_upload)
        await _assert_interrupted(webhook, raw)

    [connection_id] = staged
    response = await webhook.client.get("/api/v1/financial-documents")
    assert response.json()["items"] == []
    draft = webhook.documents.get(
        user_id=webhook.owner, connection_id=connection_id, scope=PERSONAL
    )
    assert is_held(draft) and not draft.source_available
    assert held_files(webhook.documents.store).list_for_user(webhook.owner) == []
    assert (await webhook.post(raw)).status_code == 503
    webhook.clock.now = webhook.store.inbound(webhook.key).claim_until + timedelta(
        seconds=1
    )
    assert (await webhook.post(raw)).status_code == 200
    [held] = held_files(webhook.documents.store).list_for_user(webhook.owner)
    assert held.connection_id == connection_id
    assert webhook.store.inbound(webhook.key).sender_link_id == held.sender_link_id


@pytest.mark.asyncio
async def test_losing_the_last_grant_during_a_failed_business_save_is_retryable(
    webhook: Webhook, monkeypatch
):
    raw = webhook.signed_receipt(RECEIPT_PNG)
    attempts = 0

    async def unavailable(**kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            with webhook.pool.connection() as db:
                db.execute(
                    "update public.spaces set business_rnc=null where id=%s",
                    (kwargs["scope"].space_id,),
                )
        raise DocumentServiceError("document_storage_unavailable", retryable=True)

    with monkeypatch.context() as patch:
        patch.setattr(webhook.documents, "upload", unavailable)
        response = await webhook.post(raw)
    assert response.status_code == 503
    assert (await webhook.post(raw)).status_code == 200
    [held] = held_files(webhook.documents.store).list_for_user(webhook.owner)
    assert held.reason == "no_eligible_business"


@pytest.mark.asyncio
async def test_fallback_of_a_business_duplicate_keeps_only_the_senders_caption(
    webhook: Webhook, monkeypatch
):
    from argus.domain.owner_scope import BusinessSpace

    [grant] = webhook.store.eligible_businesses(webhook.owner)
    scope = BusinessSpace(grant.space_id)
    original = await webhook.documents.upload(
        user_id=grant.owner_id,
        content=RECEIPT_PNG,
        filename="existing.png",
        media_type="image/png",
        source_text="Business-only annotation",
        scope=scope,
    )
    upload = webhook.documents.upload

    async def lose_after_duplicate(**kwargs):
        result = await upload(**kwargs)
        assert result.replayed and result.connection_id == original.connection_id
        turn_reading(
            webhook.documents.business_receipt_consent,
            grant.space_id,
            grant.owner_id,
            False,
        )
        return result

    monkeypatch.setattr(webhook.documents, "upload", lose_after_duplicate)
    webhook.signed_receipt(RECEIPT_PNG)
    message = image(MEDIA_ID, "wamid.RESHARED")
    message["entry"][0]["changes"][0]["value"]["messages"][0]["image"]["caption"] = (
        "Sender copy"
    )
    assert (await webhook.post(encode(message, webhook.clock.now))).status_code == 200
    [held] = held_files(webhook.documents.store).list_for_user(webhook.owner)
    private = webhook.documents.get(
        user_id=webhook.owner, connection_id=held.connection_id, scope=PERSONAL
    )
    assert private.source_text == "Sender copy" and private.filename != "existing.png"
    business = webhook.documents.get(
        user_id=grant.owner_id, connection_id=original.connection_id, scope=scope
    )
    assert business.source_text == "Business-only annotation"


@pytest.mark.asyncio
async def test_second_grant_does_not_reread_a_previous_direct_receipt(webhook: Webhook):
    raw = webhook.signed_receipt(RECEIPT_PNG)
    assert (await webhook.post(raw)).status_code == 200
    [before] = webhook.drafts()
    original = webhook.store.inbound(webhook.key).connection_id
    space, _ = PostgresSpaceStore(webhook.pool).create_additional(
        webhook.owner, Faker().company(), "DO", str(uuid4())
    )
    prepare_phone_business(webhook.pool, space.id, webhook.owner)
    resent = encode(image(MEDIA_ID, "wamid.SECOND-GRANT"), webhook.clock.now)
    assert (await webhook.post(resent)).status_code == 200
    assert webhook.drafts() == [before]
    assert held_files(webhook.documents.store).list_for_user(webhook.owner) == []
    resent_key = whatsapp_runtime().intake.keys.message("wamid.SECOND-GRANT")
    assert webhook.store.inbound(resent_key).connection_id == original
    assert webhook.replies == [
        {"messaging_product": "whatsapp", "status": "read", "message_id": MESSAGE_ID},
    ]


@pytest.mark.asyncio
async def test_vanished_private_stage_redelivers_instead_of_acknowledging(
    webhook: Webhook, monkeypatch
):
    with webhook.pool.connection() as db:
        db.execute(
            "update public.spaces set business_rnc=null where created_by=%s",
            (webhook.owner,),
        )
    raw = webhook.signed_receipt(RECEIPT_PNG)
    upload = webhook.documents.upload

    async def remove_stage(**kwargs):
        staged = await upload(**kwargs)
        with webhook.pool.connection() as db:
            db.execute(
                "delete from public.financial_source_connections where id=%s",
                (staged.connection_id,),
            )
        return staged

    with monkeypatch.context() as patch:
        patch.setattr(webhook.documents, "upload", remove_stage)
        assert (await webhook.post(raw)).status_code == 503
    assert not held_files(webhook.documents.store).list_for_user(webhook.owner)
    webhook.clock.now = webhook.store.inbound(webhook.key).claim_until + timedelta(
        seconds=1
    )
    assert (await webhook.post(raw)).status_code == 200
    [held] = held_files(webhook.documents.store).list_for_user(webhook.owner)
    assert webhook.store.inbound(webhook.key).connection_id == held.connection_id


@pytest.mark.asyncio
async def test_revoked_sender_keeps_a_shared_receipt_another_sender_already_published(
    webhook: Webhook, users, monkeypatch
):
    from tests.ingestion.whatsapp_link_support import NOTICE
    from tests.ingestion.whatsapp_support import BOB_PHONE

    [business] = webhook.store.eligible_businesses(webhook.owner)
    editor = users["other"]
    with webhook.pool.connection() as db:
        db.execute(
            "insert into public.business_client_grants(space_id,grantee_id,issuer_id,business_role)"
            " values(%s,%s,%s,'editor')",
            (business.space_id, editor, webhook.owner),
        )
    intake = whatsapp_runtime().intake
    issued = intake.issue_code(
        destination_owner_id=editor, reply_language="es-419", disclosure=NOTICE
    )
    assert webhook.store.redeem_code(
        code_digest=intake.keys.code(issued.code),
        sender_hash=intake.keys.sender(BOB_PHONE),
        last4=BOB_PHONE[-4:],
        now=webhook.clock.now,
    )
    first = webhook.signed_receipt(RECEIPT_PNG)
    second_id = "wamid.SECOND-SENDER"
    second = encode(image(MEDIA_ID, second_id, BOB_PHONE), webhook.clock.now)
    upload = webhook.documents.upload
    first_saved = asyncio.Event()
    release = asyncio.Event()

    async def pause_first(**kwargs):
        result = await upload(**kwargs)
        if not first_saved.is_set():
            first_saved.set()
            await release.wait()
        return result

    monkeypatch.setattr(webhook.documents, "upload", pause_first)
    task = asyncio.create_task(webhook.post(first))
    try:
        await asyncio.wait_for(first_saved.wait(), 5)
        assert (await webhook.post(second)).status_code == 200
        webhook.store.revoke(destination_owner_id=webhook.owner, now=webhook.clock.now)
    finally:
        release.set()
    assert (await task).status_code == 200
    assert webhook.store.inbound(webhook.key).error_code == "sender_link_revoked"
    receipt = webhook.store.inbound(intake.keys.message(second_id)).connection_id
    assert (
        webhook.documents.store.source(user_id=webhook.owner, connection_id=receipt)
        == RECEIPT_PNG
    )
    connection = webhook.documents.hub.connections.get_any_scope(
        user_id=webhook.owner, connection_id=receipt
    )
    assert connection.status != "disconnected"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("sole_business", "caption"),
    [(False, "private note"), (True, "new note"), (True, None)],
    ids=["private", "sole_business", "sole_business_no_caption"],
)
async def test_resend_after_assigned_business_loses_eligibility_reuses_the_receipt(
    webhook: Webhook, monkeypatch, sole_business: bool, caption: str | None
):
    from tests.document_reads_support import read_receipt
    from tests.test_whatsapp_receipt_read_postgres import Extractor

    monkeypatch.setattr(
        "argus.domain.ingestion.whatsapp.receipt_consent.receipt_provider_route",
        lambda: ROUTE,
    )
    webhook.clock.now = datetime.now(timezone.utc)
    docs = webhook.documents
    extractor = Extractor()
    monkeypatch.setattr(docs, "extractor", extractor)
    [a] = webhook.store.eligible_businesses(webhook.owner)
    b, _ = PostgresSpaceStore(webhook.pool).create_additional(
        webhook.owner, Faker().company(), "DO", str(uuid4())
    )
    prepare_phone_business(webhook.pool, b.id, webhook.owner)
    webhook.graph.media[MEDIA_ID] = Media(RECEIPT_PNG, "image/png")

    def delivery(message_id, filename, note):
        document = {"id": MEDIA_ID, "filename": filename, "mime_type": "image/png"}
        if note is not None:
            document["caption"] = note
        return encode(
            fixture("document_message.json", id=message_id, document=document),
            webhook.clock.now,
        )

    assert (
        await webhook.post(delivery(MESSAGE_ID, "a.png", "A only"))
    ).status_code == 200
    files = held_files(docs.store)
    [original] = files.list_for_user(webhook.owner)
    assert await read_receipt(docs, webhook.owner, original.connection_id) == "prepared"
    assert extractor.calls == 1
    assigned = docs.adopt(
        user_id=webhook.owner, held_id=original.id, business_id=a.space_id
    )
    assert webhook.store.inbound(webhook.key).connection_id == assigned.connection_id

    def usage():
        with webhook.pool.connection() as db:
            return (
                db.execute(
                    "select business_id::text,reads from public.business_read_daily_usage where business_id=any(%s::uuid[]) order by 1",
                    ([a.space_id, b.id],),
                ).fetchall(),
                db.execute(
                    "select reads from public.whatsapp_held_read_usage where user_id=%s order by day",
                    (webhook.owner,),
                ).fetchall(),
            )

    before = usage()
    turn_reading(docs.business_receipt_consent, a.space_id, webhook.owner, False)
    if not sole_business:
        turn_reading(docs.business_receipt_consent, b.id, webhook.owner, False)
    webhook.clock.now += timedelta(seconds=1)
    message_id = "wamid.AFTER-A-ACCESS-LOSS"
    raw = delivery(message_id, "resent.png", caption)
    if not sole_business:
        created = []
        objects = docs.store.objects
        put = objects.put

        def record_put(path, content, media_type):
            put(path, content, media_type)
            created.append(path)

        def fail_publication(*args, **kwargs):
            raise ConnectionError("temporary persistence failure")

        with monkeypatch.context() as patch:
            patch.setattr(objects, "put", record_put)
            patch.setattr(type(files), "hold", fail_publication)
            assert (await webhook.post(raw)).status_code == 503
        assert created and all(objects.get(path) is None for path in created)
        assert [row.id for row in files.list_for_user(webhook.owner)] == [original.id]
        pending = webhook.store.inbound(
            whatsapp_runtime().intake.keys.message(message_id)
        )
        webhook.clock.now = pending.claim_until + timedelta(seconds=1)
    assert (await webhook.post(raw)).status_code == 200
    first, second = files.list_for_user(webhook.owner)
    assert first.id == original.id and first.assigned_space_id == a.space_id
    assert first.connection_id != second.connection_id
    inbound = webhook.store.inbound(whatsapp_runtime().intake.keys.message(message_id))
    if sole_business:
        assert second.state == "assigned" and second.assigned_space_id == b.id
        assert inbound.connection_id == second.assigned_connection_id
        assert (
            docs.store.get(user_id=webhook.owner, connection_id=inbound.connection_id)
            is not None
        )
    else:
        assert second.state == "held" and second.reason == "no_eligible_business"
        assert inbound.connection_id == second.connection_id
        assert (
            docs.store.source(user_id=webhook.owner, connection_id=inbound.connection_id)
            == RECEIPT_PNG
        )
    received = docs.store.draft(
        user_id=webhook.owner, connection_id=inbound.connection_id
    )
    assert (received.filename, received.source_text) == ("resent.png", caption)
    replies_before_duplicate = webhook.replies.copy()
    resent = delivery("wamid.DUPLICATE-AFTER-A-LOSS", "duplicate.png", None)
    assert (await webhook.post(resent)).status_code == 200
    assert len(files.list_for_user(webhook.owner)) == 2
    assert webhook.replies == replies_before_duplicate

    if not sole_business:
        from argus.api import whatsapp
        from argus.api.routers import whatsapp as link_routes
        from argus.domain.business.contracts.deletion import PURGE_AFTER
        from argus.domain.ingestion.whatsapp.held import HeldFileExpiry

        context = whatsapp.WhatsAppSenderContext(
            whatsapp_runtime(),
            webhook.owner,
            webhook.store.destination_link(destination_owner_id=webhook.owner),
        )
        monkeypatch.setitem(
            app.dependency_overrides, whatsapp.require_whatsapp_sender, lambda: context
        )
        monkeypatch.setattr(link_routes, "documents_service", lambda: docs)

        async def held_count():
            response = await webhook.client.get("/api/v1/whatsapp/link")
            assert response.status_code == 200
            return response.json()["held_count"]

        assert await held_count() == 1
        with webhook.pool.connection() as db:
            db.execute(
                "update public.whatsapp_held_files set held_at=%s where id=%s",
                (webhook.clock.now - PURGE_AFTER - timedelta(seconds=1), second.id),
            )
        expiry = HeldFileExpiry(webhook.pool, docs.store.objects, clock=webhook.clock)
        for _ in range(2):
            expiry.tick()
            assert await held_count() == 0
            webhook.clock.now += timedelta(hours=1)
        assert (
            docs.store.draft(user_id=webhook.owner, connection_id=second.connection_id)
            is None
        )
        assert (
            docs.store.source(user_id=webhook.owner, connection_id=second.connection_id)
            is None
        )
    assert (
        docs.store.source(user_id=webhook.owner, connection_id=assigned.connection_id)
        == RECEIPT_PNG
    )
    a_receipt = docs.store.draft(
        user_id=webhook.owner, connection_id=assigned.connection_id
    )
    assert (a_receipt.filename, a_receipt.source_text) == ("a.png", "A only")
    assert usage() == before and extractor.calls == 1
