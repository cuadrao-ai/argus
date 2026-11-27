"""Routing proof on the signed webhook and the migrated disposable database."""

import pytest
from argus.domain.ingestion.whatsapp.held import held_files

from tests.business_reading_support import turn_reading
from tests.ingestion.whatsapp_support import RECEIPT_PNG
from tests.test_whatsapp_webhook_postgres import (
    Webhook,
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
async def test_signed_file_with_no_eligible_destination_stays_private(webhook: Webhook):
    with webhook.pool.connection() as db:
        space = db.execute(
            "select id::text from public.spaces where created_by=%s and kind='business'",
            (webhook.owner,),
        ).fetchone()[0]
    turn_reading(webhook.documents.business_receipt_consent, space, webhook.owner, False)

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
