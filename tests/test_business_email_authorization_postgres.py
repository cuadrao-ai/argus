"""Business email sender authorization at the real Postgres reading boundary."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from argus.api import documents as documents_api
from argus.api import email_intake as intake_api
from argus.domain.ingestion.email_intake.alignment import provider_verdict
from argus.domain.owner_scope import BusinessSpace

from tests import test_business_email_intake_postgres as shared
from tests.business.test_business_email_api import signed
from tests.business_reading_support import turn_reading
from tests.test_business_email_intake_postgres import (
    Provider,
    approve,
    direct_upload,
    message,
    prepare,
    receipt_png,
)

actions = shared.actions
users = shared.users
rig = shared.rig
receipts = shared.receipts
pytestmark = shared.pytestmark


@pytest.fixture
def email_reader_boundary(receipts, monkeypatch):
    world = receipts
    documents = world["runtime"].documents
    extractor = documents.extractor
    extraction = AsyncMock(wraps=extractor.extract)
    monkeypatch.setattr(extractor, "extract", extraction)
    dispatch = AsyncMock(wraps=documents_api.dispatch_preparation)
    monkeypatch.setattr(documents_api, "dispatch_preparation", dispatch)
    monkeypatch.setattr(documents_api, "document_jobs", lambda: None)
    monkeypatch.setattr(intake_api, "documents_service", lambda: documents)
    preparation = Mock(wraps=world["service"].prepare_attachment)
    preflight = Mock(wraps=world["service"].check_attachment_preparation)
    monkeypatch.setattr(world["service"], "prepare_attachment", preparation)
    monkeypatch.setattr(world["service"], "check_attachment_preparation", preflight)
    world["runtime"].read_receipt = intake_api._read_receipt
    world.update(
        extraction=extraction,
        dispatch=dispatch,
        preparation=preparation,
        preflight=preflight,
    )
    return world


def _deliver_for_reader(world, auth):
    world["provider"].authentication = auth
    world["provider"].provider_from = world["provider"].sender
    event = str(uuid4())
    body = json.dumps(
        {
            "type": "email.received",
            "data": {"email_id": event, "to": [world["recipient"]]},
        }
    ).encode()
    response = world["webhook"].post(
        "/webhooks/resend",
        content=body,
        headers={**signed(body), "Content-Type": "application/json"},
    )
    assert response.status_code == 202, response.text
    assert asyncio.run(world["runtime"].next())
    with world["pool"].connection() as db:
        row = db.execute(
            "select id::text from public.business_email_deliveries where external_id=%s",
            (event,),
        ).fetchone()
    return world["store"].get(row[0], world["space"])


def _email_read_observed(world, delivery, case):
    with world["pool"].connection() as db:
        sources = db.execute(
            "select count(*) from public.business_sources where space_id=%s and origin='email'",
            (world["space"],),
        ).fetchone()[0]
        drafts = db.execute(
            "select count(distinct l.draft_id) from public.business_draft_sources l join public.business_sources s on s.id=l.source_id and s.space_id=l.space_id where s.space_id=%s and s.origin='email'",
            (world["space"],),
        ).fetchone()[0]
        preparations = db.execute(
            "select count(*) from public.business_action_receipts where space_id=%s and command->>'action'='prepare_attachment'",
            (world["space"],),
        ).fetchone()[0]
        activities = db.execute(
            "select count(*) from public.financial_activity_groups where user_id=%s",
            (world["owner"],),
        ).fetchone()[0]
    observed = {
        "case": case,
        "extractor_calls": world["extraction"].await_count,
        "dispatch_calls": world["dispatch"].await_count,
        "preflight_calls": world["preflight"].call_count,
        "prepare_attachment_calls": world["preparation"].call_count,
        "business_sources": sources,
        "business_drafts": drafts,
        "preparation_receipts": preparations,
        "recorded_activities": activities,
        "delivery_state": delivery.state,
        "delivery_approved": delivery.approved,
        "delivery_auth": delivery.auth_result,
        "delivery_group": delivery.inbox_group,
        "provider_fixture_fetches": world["provider"].calls,
    }
    return observed


CASES = [
    ("new_aligned", "new", {"dmarc": "pass", "dkim": "pass"}, None, 0),
    ("new_unknown", "new", {"dmarc": "unknown", "dkim": "gray"}, None, 0),
    ("authorized_failed", "authorized", {"dmarc": "fail", "dkim": "fail"}, None, 1),
    ("authorized_unknown", "authorized", {"dmarc": "unknown", "dkim": "gray"}, None, 1),
    ("authorized_gray", "authorized", {"dmarc": "gray", "dkim": "gray"}, None, 1),
    ("authorized_no_result", "authorized", {}, None, 1),
    ("blocked", "blocked", {"dmarc": "pass", "dkim": "pass"}, None, 0),
    (
        "reading_off",
        "authorized",
        {"dmarc": "pass", "dkim": "pass"},
        "before_reading_off",
        0,
    ),
    (
        "queued_reading_off",
        "authorized",
        {"dmarc": "pass", "dkim": "pass"},
        "reading_off",
        0,
    ),
    (
        "queued_sender_blocked",
        "authorized",
        {"dmarc": "pass", "dkim": "pass"},
        "blocked",
        0,
    ),
    (
        "queued_sender_removed",
        "authorized",
        {"dmarc": "pass", "dkim": "pass"},
        "removed",
        0,
    ),
    ("authorized_aligned", "authorized", {"dmarc": "pass", "dkim": "pass"}, None, 1),
    ("authorized_dkim_forward", "authorized", {"dmarc": "gray", "dkim": "pass"}, None, 1),
]


@pytest.mark.parametrize(
    "case,standing,auth,change,expected", CASES, ids=[x[0] for x in CASES]
)
@pytest.mark.owner_acts
def test_only_live_authorized_mail_reaches_automatic_extraction(
    email_reader_boundary, case, standing, auth, change, expected
):
    world = email_reader_boundary
    rule = None
    if standing != "new":
        rule = world["store"].upsert_sender(
            world["space"], "address", world["provider"].sender, standing
        )
    if change == "before_reading_off":
        turn_reading(
            world["documents"].business_receipt_consent,
            world["space"],
            world["owner"],
            False,
        )
    if change in {"reading_off", "blocked", "removed"}:

        async def changed_after_queue(route, connection):
            queued = world["documents"].get(
                user_id=world["owner"],
                connection_id=connection,
                scope=BusinessSpace(world["space"]),
            )
            assert queued.status == "queued" and queued.consent
            if change == "reading_off":
                turn_reading(
                    world["documents"].business_receipt_consent,
                    world["space"],
                    world["owner"],
                    False,
                )
            elif change == "blocked":
                world["store"].upsert_sender(
                    world["space"], "address", world["provider"].sender, "blocked"
                )
            else:
                world["store"].remove_sender(world["space"], rule.id)
            await intake_api._read_receipt(route, connection)

        world["runtime"].read_receipt = changed_after_queue
    delivery = _deliver_for_reader(world, auth)
    observed = _email_read_observed(world, delivery, case)
    assert observed["delivery_approved"] is False
    assert observed["recorded_activities"] == 0
    assert (
        observed["extractor_calls"],
        observed["business_drafts"],
        observed["preparation_receipts"],
    ) == (expected, expected, expected), observed


@pytest.mark.parametrize(
    "auth,expected",
    [
        ({"dmarc": "gray", "dkim": "gray"}, "none"),
        ({"dmarc": "unknown", "dkim": "gray"}, "none"),
        ({"dmarc": "processing_failed", "dkim": "processing_failed"}, "no_result"),
        (None, "no_result"),
        ({"dmarc": "gray", "dkim": "pass"}, "aligned"),
        ({"dmarc": "fail", "dkim": "pass"}, "failed"),
    ],
)
@pytest.mark.owner_acts
def test_outer_provider_authentication_mapping_preserves_forwarding_contract(
    auth, expected
):
    assert (
        provider_verdict(auth, raw=message(), provider_from="proveedor@example.test")
        == expected
    )


@pytest.mark.parametrize("permission", ["sender_blocked", "reading_off"])
@pytest.mark.owner_acts
def test_permission_change_after_email_reader_boundary_dispatch_before_task_blocks_reader(
    email_reader_boundary, monkeypatch, permission
):
    world = email_reader_boundary
    world["store"].upsert_sender(
        world["space"], "address", world["provider"].sender, "authorized"
    )
    original = world["dispatch"]

    async def dispatch_then_withdraw(*args, **kwargs):
        await original(*args, **kwargs)
        if permission == "sender_blocked":
            world["store"].upsert_sender(
                world["space"], "address", world["provider"].sender, "blocked"
            )
        else:
            turn_reading(
                world["documents"].business_receipt_consent,
                world["space"],
                world["owner"],
                False,
            )

    monkeypatch.setattr(documents_api, "dispatch_preparation", dispatch_then_withdraw)
    delivery = _deliver_for_reader(world, {"dmarc": "pass", "dkim": "pass"})
    observed = _email_read_observed(world, delivery, "after_dispatch_" + permission)
    assert (
        observed["extractor_calls"],
        observed["business_drafts"],
        observed["preparation_receipts"],
    ) == (0, 0, 0), observed


@pytest.mark.owner_acts
def test_sender_authorization_is_scoped_to_its_business_and_documents_do_not_cross(
    email_reader_boundary, users, monkeypatch
):
    from argus.api.routers import email_intake as webhook_api
    from argus.domain.ingestion.connections import ConnectionNotFound
    from argus.domain.ingestion.email_intake.service import (
        EmailCapture,
        grant_route_authority,
    )

    from tests.test_business_spaces_migration_postgres import space

    first = email_reader_boundary
    first["store"].upsert_sender(
        first["space"], "address", first["provider"].sender, "authorized"
    )
    delivery_a = _deliver_for_reader(first, {"dmarc": "pass", "dkim": "pass"})
    part_a = first["store"].parts(delivery_a.id)[0]
    with first["pool"].connection() as db:
        space_b = space(db, users["other"])
        grant_b = str(
            db.execute(
                "insert into public.business_client_grants(space_id,grantee_id,issuer_id,capabilities) values(%s,%s,%s,ARRAY['read','prepare','approve']) returning id",
                (space_b, users["other"], users["other"]),
            ).fetchone()[0]
        )
    recipient_b = f"recibos-{uuid4().hex[:8]}@recibos.example.test"
    route_b = first["store"].create_route(
        recipient=recipient_b,
        space_id=space_b,
        principal_id=users["other"],
        granted_by=users["other"],
        grant_id=grant_b,
    )
    base = first["runtime"].documents
    turn_reading(base.business_receipt_consent, space_b, users["other"])
    provider_b = Provider(message(), (recipient_b,))
    runtime_b = EmailCapture(
        first["store"],
        base,
        grant_route_authority(first["pool"]),
        provider_b,
        lambda: True,
        lambda: True,
        intake_api._read_receipt,
    )
    monkeypatch.setattr(webhook_api, "email_intake", lambda: runtime_b)
    second = {
        **first,
        "space": space_b,
        "owner": users["other"],
        "recipient": recipient_b,
        "provider": provider_b,
        "runtime": runtime_b,
    }
    assert first["store"].sender_standing(space_b, provider_b.sender) == "new"
    before = first["extraction"].await_count
    delivery_b = _deliver_for_reader(second, {"dmarc": "pass", "dkim": "pass"})
    part_b = first["store"].parts(delivery_b.id)[0]
    assert part_a.document_id != part_b.document_id
    assert first["store"].get(delivery_a.id, space_b) is None
    assert first["store"].get(delivery_b.id, first["space"]) is None
    with pytest.raises(ConnectionNotFound):
        intake_api._queued_email_reader(route_b, part_a.document_id)
    observed = _email_read_observed(
        second, delivery_b, "business_B_without_sender_authorization"
    )
    assert (
        first["extraction"].await_count - before,
        observed["business_drafts"],
        observed["preparation_receipts"],
    ) == (0, 0, 0), observed


@pytest.mark.owner_acts
def test_attachment_is_associated_before_an_immediate_reader_can_start(
    email_reader_boundary, monkeypatch
):
    world = email_reader_boundary
    documents = world["runtime"].documents
    upload = documents.upload
    route = world["store"].route_for_space(world["space"])

    async def capture_and_race_reader(**kwargs):
        outcome = await upload(**kwargs)
        if kwargs["media_type"] == "image/png":
            await intake_api._read_receipt(route, outcome.connection_id)
        return outcome

    monkeypatch.setattr(documents, "upload", capture_and_race_reader)
    delivery = _deliver_for_reader(world, {"dmarc": "pass", "dkim": "pass"})
    observed = _email_read_observed(
        world, delivery, "reader_before_upload_returns_to_email_capture"
    )
    assert (
        observed["extractor_calls"],
        observed["business_drafts"],
        observed["preparation_receipts"],
    ) == (0, 0, 0), observed


@pytest.mark.owner_acts
def test_a_direct_upload_after_unapproved_mail_can_be_read_and_approved(
    email_reader_boundary,
):
    world = email_reader_boundary
    delivery = _deliver_for_reader(world, {"dmarc": "pass", "dkim": "pass"})
    assert world["extraction"].await_count == 0
    with world["pool"].connection() as db:
        assert db.execute(
            "select count(*) from public.business_action_receipts where space_id=%s"
            " and command->>'action'='receipt_upload'",
            (world["space"],),
        ).fetchone() == (0,)
    [part] = world["store"].parts(delivery.id)
    uploaded = direct_upload(world)
    assert uploaded.connection_id == part.document_id and uploaded.replayed
    assert world["extraction"].await_count == 0
    draft, _ = prepare(world, uploaded.connection_id)
    assert world["extraction"].await_count == 1
    approved = approve(world, draft)
    assert approved.status_code == 200, approved.text


@pytest.mark.owner_acts
def test_old_email_capture_and_duplicate_keep_email_authority(email_reader_boundary):
    world = email_reader_boundary
    first = _deliver_for_reader(world, {"dmarc": "pass", "dkim": "pass"})
    [part] = world["store"].parts(first.id)
    with world["pool"].connection() as db:
        db.execute(
            "update public.financial_document_extractions set created_at=created_at-interval '1 year' where connection_id=%s",
            (part.document_id,),
        )
    second = _deliver_for_reader(world, {"dmarc": "pass", "dkim": "pass"})
    assert world["store"].parts(second.id)[0].document_id == part.document_id
    assert world["extraction"].await_count == 0
    with world["pool"].connection() as db:
        assert db.execute(
            "select origin from public.business_sources where connection_id=%s",
            (part.document_id,),
        ).fetchone() == ("email",)
        assert db.execute(
            "select count(*) from public.business_draft_sources where space_id=%s",
            (world["space"],),
        ).fetchone() == (0,)


def test_email_attachment_link_rolls_back_with_failed_capture(rig):
    from argus.domain.ingestion.email_intake.models import EmailDeliveryPart

    delivery = rig["runtime"].enqueue_resend(str(uuid4()), (rig["route"].recipient,))
    claimed = rig["store"].claim(delivery_id=delivery.id)
    part = EmailDeliveryPart("receipt", "recibo.png", "image/png", "pending", None, None)
    rig["store"].put_part(claimed, part)
    hook = rig["store"].part_capture_hook(claimed, part)

    def refuse_after_link(connection, connection_id):
        hook(connection, connection_id)
        raise RuntimeError("synthetic_capture_abort")

    with pytest.raises(RuntimeError, match="synthetic_capture_abort"):
        asyncio.run(
            rig["documents"].upload(
                user_id=rig["users"]["owner"],
                content=receipt_png(),
                filename="recibo.png",
                media_type="image/png",
                scope=BusinessSpace(rig["route"].space_id),
                on_capture=refuse_after_link,
            )
        )
    [saved] = rig["store"].parts(delivery.id)
    assert saved.document_id is None and saved.state == "pending"
    with rig["pool"].connection() as db:
        assert db.execute(
            "select count(*) from public.business_sources where space_id=%s",
            (rig["route"].space_id,),
        ).fetchone() == (0,)
        assert db.execute(
            "select draft->>'source_available' from public.financial_document_extractions where user_id=%s",
            (rig["users"]["owner"],),
        ).fetchone() == ("false",)


@pytest.mark.owner_acts
def test_an_authorized_delivery_with_no_stored_verdict_is_refused(receipts):
    from argus.domain.business.authority import ActionError

    from tests.test_business_email_intake_postgres import ALIGNED, deliver

    receipts["store"].upsert_sender(
        receipts["space"], "address", receipts["provider"].sender, "authorized"
    )
    attachment = deliver(receipts, ALIGNED)
    with receipts["pool"].connection() as db:
        db.execute(
            "update public.business_email_deliveries set auth_result=null"
            " where space_id=%s",
            (receipts["space"],),
        )
    with pytest.raises(ActionError, match="email_sender_unauthorized"):
        prepare(receipts, attachment)
    assert receipts["documents"].extractor.calls == 0
