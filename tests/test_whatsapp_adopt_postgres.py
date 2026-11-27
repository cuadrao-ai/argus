"""A sender assigns a private file under their current grant without buying a second read."""

import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
from argus.domain.business.read_budget import ReadBudgetSettings
from argus.domain.ingestion.documents.service import DocumentServiceError
from argus.domain.ingestion.email_intake.budget import business_day
from argus.domain.ingestion.whatsapp.senders import postgres_senders

from tests import test_business_actions_postgres as business
from tests import test_whatsapp_held_files_postgres as held
from tests.document_reads_support import read_receipt
from tests.ingestion.whatsapp_link_support import prepare_phone_business

users, pool, desk = held.users, held.pool, held.desk
actions = business.actions
reads_finish_inside_the_request = held.reads_finish_inside_the_request
pytestmark = held.pytestmark


@pytest.fixture
def sender(desk, actions):
    desk.custodian, desk.owner = desk.owner, desk.other
    desk.space = str(actions[1].actor.space_id)
    desk.grant = str(actions[2])
    return desk


def capture(sender):
    row = held.upload(sender)
    sender_hash = uuid4().bytes * 2
    with sender.pool.connection() as db:
        db.execute(
            "insert into public.whatsapp_sender_links"
            "(id,destination_owner_id,wa_id_hash,last4,reply_language,status,linked_at)"
            " values (%s,%s,%s,'0123','es-419','active',%s)",
            (row.sender_link_id, sender.owner, sender_hash, sender.now),
        )
        db.execute(
            "insert into public.whatsapp_inbound_messages"
            "(provider_message_key,sender_hash,status,destination_owner_id,sender_link_id,"
            "connection_id,received_at,updated_at) values (%s,%s,'captured',%s,%s,%s,%s,%s)",
            (
                row.provider_message_key,
                sender_hash,
                sender.owner,
                row.sender_link_id,
                row.connection_id,
                sender.now,
                sender.now,
            ),
        )
    return row


def enable(sender):
    prepare_phone_business(sender.pool, sender.space, sender.custodian)


def counts(sender):
    with sender.pool.connection() as db:
        return tuple(
            db.execute(query, (key,)).fetchone()[0]
            for query, key in (
                (
                    "select coalesce(sum(reads),0) from public.business_read_daily_usage"
                    " where business_id=%s",
                    sender.space,
                ),
                (
                    "select coalesce(sum(reads),0) from public.whatsapp_held_read_usage"
                    " where user_id=%s",
                    sender.owner,
                ),
            )
        )


def assign(sender, row):
    return sender.service.adopt(
        user_id=sender.owner, held_id=row.id, business_id=sender.space
    )


@pytest.mark.parametrize("full", [False, True], ids=["transfer", "business-full"])
def test_assign_after_disconnect_carries_read_once_and_debits_original_day(sender, full):
    row = capture(sender)
    store = sender.service.store
    assert store.save_rebuilt(
        user_id=sender.owner,
        connection_id=row.connection_id,
        content=b"synthetic rebuilt",
        media_type="image/jpeg",
    )
    assert held.read(sender, row) == "prepared"
    assert counts(sender) == (0, 1)
    original = store.get(user_id=sender.owner, connection_id=row.connection_id)
    enable(sender)
    read_day = business_day(sender.now)
    sender.now += timedelta(days=1)
    with sender.pool.connection() as db:
        db.execute(
            "update public.whatsapp_sender_links set status='revoked',revoked_at=%s where id=%s",
            (sender.now, row.sender_link_id),
        )
    if full:
        sender.service.read_budget.settings = ReadBudgetSettings(per_day=1)
        assert sender.service.read_budget.charge(sender.space, sender.now) is None
    result = assign(sender, row)
    replay = assign(sender, row)
    assert replay.connection_id == result.connection_id and replay.replayed
    assert result.status == "review_ready" and result.candidate_count == 1
    assert sender.extractor.calls == 1
    assert counts(sender) == (1, int(full))
    target = dict(user_id=sender.custodian, connection_id=result.connection_id)
    assert store.source(**target) == store.source(
        user_id=sender.owner, connection_id=row.connection_id
    )
    assert store.rebuilt(**target) == ("image/jpeg", b"synthetic rebuilt")
    batch = store.get(**target)
    assert batch.metadata == original.metadata and batch.receipt == original.receipt
    assert batch.candidates[0].source.connection_id == result.connection_id
    assert batch.candidates[0].attachments == original.candidates[0].attachments
    with sender.pool.connection() as db:
        assert db.execute(
            "select reads from public.whatsapp_held_read_usage where user_id=%s and day=%s",
            (sender.owner, read_day),
        ).fetchone() == (int(full),)
        assert db.execute(
            "select connection_id::text,sender_link_id::text from public.whatsapp_inbound_messages"
            " where provider_message_key=%s",
            (row.provider_message_key,),
        ).fetchone() == (result.connection_id, row.sender_link_id)
        assert db.execute(
            "select count(*) from public.financial_import_events where user_id=%s",
            (sender.custodian,),
        ).fetchone() == (1,)
        assert db.execute(
            "select count(*) from public.financial_import_events where user_id=%s",
            (sender.owner,),
        ).fetchone() == (0,)


def test_worker_routes_and_manual_replay_finds_same_destination(sender, monkeypatch):
    row = capture(sender)
    enable(sender)
    extract_for_business(sender, monkeypatch)
    assert held.read(sender, row) == "prepared"
    [assigned] = sender.files.list_for_user(sender.owner)
    assert assigned.state == "assigned" and assigned.assigned_space_id == sender.space
    assert assign(sender, row).connection_id == assigned.assigned_connection_id
    assert counts(sender) == (1, 0) and sender.extractor.calls == 1


def test_unread_assignment_queues_one_business_read(sender):
    row = capture(sender)
    enable(sender)
    result = assign(sender, row)
    assert result.status == "queued" and counts(sender) == (0, 0)
    assert held.read(sender, row) is None
    assert (
        asyncio.run(read_receipt(sender.service, sender.custodian, result.connection_id))
        == "prepared"
    )
    assert sender.extractor.calls == 1 and counts(sender) == (1, 0)


def test_revocation_denies_assignment_and_removes_business_from_picker(sender):
    row = capture(sender)
    enable(sender)
    with sender.pool.connection() as db:
        assert [
            g.space_id for g in postgres_senders(db).eligible_businesses(sender.owner)
        ] == [sender.space]
        db.execute(
            "update public.business_client_grants set revoked_at=now() where id=%s",
            (sender.grant,),
        )
    with pytest.raises(DocumentServiceError, match="business_permission_denied"):
        assign(sender, row)
    with sender.pool.connection() as db:
        assert postgres_senders(db).eligible_businesses(sender.owner) == ()
    assert sender.files.list_for_user(sender.owner)[0].state == "held"
    assert counts(sender) == (0, 0)


def test_held_read_does_not_default_to_last_business_after_revocation(
    sender, monkeypatch
):
    from tests.test_business_spaces_migration_postgres import owned_space

    enable(sender)
    with sender.pool.connection() as db:
        remaining = owned_space(db, sender.owner)
        revoked_rnc = db.execute(
            "select business_rnc from public.spaces where id=%s", (sender.space,)
        ).fetchone()[0]
    prepare_phone_business(sender.pool, remaining, sender.owner)
    row = capture(sender)
    extract = sender.extractor.extract

    async def read_after_revocation(**kwargs):
        with sender.pool.connection() as db:
            db.execute(
                "update public.business_client_grants set revoked_at=now() where id=%s",
                (sender.grant,),
            )
        batch = await extract(**kwargs)
        return batch.model_copy(
            update={
                "receipt": batch.receipt.model_copy(update={"buyer_rnc": revoked_rnc})
            }
        )

    monkeypatch.setattr(sender.extractor, "extract", read_after_revocation)
    assert held.read(sender, row) == "prepared"
    [private] = sender.files.list_for_user(sender.owner)
    assert (private.state, private.reason) == ("held", "no_match")
    assert sender.extractor.calls == 1 and counts(sender) == (0, 1)


@pytest.mark.parametrize(
    "failure,reason",
    [
        ("unreadable_document", "read_failed"),
        ("whatsapp_held_read_budget_day", "held_read_cap"),
    ],
)
def test_private_row_explains_unsuccessful_read(sender, monkeypatch, failure, reason):
    row = capture(sender)
    if reason == "held_read_cap":
        sender.files.budget().charge(sender.owner, sender.now)
    else:

        async def reject(**kwargs):
            await kwargs["before_request"]()
            raise DocumentServiceError(failure)

        monkeypatch.setattr(sender.extractor, "extract", reject)
    assert held.read(sender, row) == failure
    [private] = sender.files.list_for_user(sender.owner)
    assert (private.state, private.reason) == ("held", reason)


def test_interrupted_route_retries_saved_batch_without_copy_or_charge_left_behind(
    sender, monkeypatch
):
    from argus.domain.ingestion.documents.jobs import PreparationJobs

    row = capture(sender)
    enable(sender)
    original_objects = dict(sender.objects.objects)
    extract_for_business(sender, monkeypatch)

    def interrupt(*args, **kwargs):
        raise RuntimeError("synthetic interrupted assignment")

    with monkeypatch.context() as patch:
        patch.setattr(held.PostgresHeldFiles, "settle", interrupt)
        assert held.read(sender, row) == "document_extraction_failed"
    assert sender.objects.objects == original_objects
    assert counts(sender) == (0, 1)
    [private] = sender.files.list_for_user(sender.owner)
    assert private.state == "held"
    sender.now += timedelta(minutes=4)
    PreparationJobs(sender.service).sweep()
    assert held.read(sender, row) == "prepared"
    assert sender.files.list_for_user(sender.owner)[0].state == "assigned"
    assert sender.extractor.calls == 1 and counts(sender) == (1, 0)


def extract_for_business(sender, monkeypatch):
    with sender.pool.connection() as db:
        tax_id = db.execute(
            "select business_rnc from public.spaces where id=%s", (sender.space,)
        ).fetchone()[0]
    extract = sender.extractor.extract

    async def read_match(**kwargs):
        batch = await extract(**kwargs)
        return batch.model_copy(
            update={"receipt": batch.receipt.model_copy(update={"buyer_rnc": tax_id})}
        )

    monkeypatch.setattr(sender.extractor, "extract", read_match)


def test_charge_rolls_back_when_marker_cannot_be_saved(sender, monkeypatch):
    from argus.domain.ingestion.documents.store_postgres import PostgresDocumentStore

    row = capture(sender)
    update = PostgresDocumentStore.update

    def refuse_marker(store, **kwargs):
        if "held_read_charged_at" in kwargs["draft"].resolution:
            return False
        return update(store, **kwargs)

    monkeypatch.setattr(PostgresDocumentStore, "update", refuse_marker)
    assert held.read(sender, row) == "document_lease_lost"
    assert sender.extractor.calls == 0
    assert counts(sender) == (0, 0)


@pytest.mark.parametrize("automatic", [False, True], ids=["assignment", "worker"])
def test_arrival_event_names_only_the_receiving_business(sender, monkeypatch, automatic):
    received = []
    monkeypatch.setattr(
        "argus.domain.business.analytics.document_received",
        lambda **event: received.append(event),
    )
    row = capture(sender)
    if automatic:
        enable(sender)
        extract_for_business(sender, monkeypatch)
    assert held.read(sender, row) == "prepared"
    if not automatic:
        assert received == []
        enable(sender)
    assign(sender, row)
    assign(sender, row)
    assert [
        (event["business_id"], event["user_id"], event["channel"]) for event in received
    ] == [(sender.space, sender.owner, "whatsapp")]
