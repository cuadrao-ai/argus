"""Routing proof on the signed webhook and the migrated disposable database."""

import asyncio
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from argus.api.documents import DocumentContext, require_saved_document_context
from argus.api.main import app
from argus.domain.business.spaces import PostgresSpaceStore
from argus.domain.ingestion.documents.service import DocumentServiceError
from argus.domain.ingestion.whatsapp.held import held_files, is_held
from argus.domain.ingestion.whatsapp.receipt_consent import receipt_consent_store
from argus.domain.owner_scope import PERSONAL
from faker import Faker

from tests.business_reading_support import ROUTE, turn_reading
from tests.ingestion.whatsapp_cases import image
from tests.ingestion.whatsapp_link_support import prepare_phone_business
from tests.ingestion.whatsapp_support import RECEIPT_PNG, encode
from tests.test_whatsapp_webhook_postgres import (
    MEDIA_ID,
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
    assert len(webhook.replies) == 2

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
