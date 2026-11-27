"""A sender assigns a private file under their current grant without buying a second read."""

import asyncio
from datetime import timedelta
from uuid import UUID, uuid4

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
    enable(desk)
    held.link_sender(desk)
    return desk


def capture(sender):
    row = held.upload(sender)
    inbound(sender, row)
    return row


def inbound(sender, row):
    with sender.pool.connection() as db:
        db.execute(
            "insert into public.whatsapp_inbound_messages"
            "(provider_message_key,sender_hash,status,destination_owner_id,sender_link_id,"
            "connection_id,received_at,updated_at) values (%s,%s,'captured',%s,%s,%s,%s,%s)",
            (
                row.provider_message_key,
                sender.sender_hash,
                sender.owner,
                row.sender_link_id,
                row.connection_id,
                sender.now,
                sender.now,
            ),
        )


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


@pytest.mark.parametrize(
    "change",
    ["disconnected", "relinked", "consent_revoked", "no_eligible", "changed_route"],
)
def test_queued_held_file_rechecks_original_authority_at_provider_admission(
    sender, monkeypatch, change
):
    from argus.domain.ingestion.whatsapp.receipt_consent import receipt_consent_store
    from argus.domain.ingestion.whatsapp.store_postgres import PostgresWhatsAppStore

    row = capture(sender)
    if change in ("disconnected", "relinked"):
        assert PostgresWhatsAppStore(sender.pool).revoke(
            destination_owner_id=sender.owner, now=sender.now
        )
        if change == "relinked":
            # The replacement is fully authorized for its own new deliveries.
            held.link_sender(sender)
            assert receipt_consent_store(sender.pool).status(UUID(sender.owner))[
                "enabled"
            ]
    elif change == "consent_revoked":
        receipt_consent_store(sender.pool).revoke(UUID(sender.owner))
    elif change == "no_eligible":
        with sender.pool.connection() as db:
            db.execute(
                "update public.business_client_grants set revoked_at=now() where id=%s",
                (sender.grant,),
            )
    else:
        monkeypatch.setattr(
            "argus.domain.ingestion.whatsapp.receipt_consent.receipt_provider_route",
            lambda: {"gateway": "another-test-route"},
        )
    assert held.read(sender, row) == "document_reading_not_allowed"
    assert counts(sender) == (0, 0) and sender.extractor.calls == 0
    [private] = sender.files.list_for_user(sender.owner)
    assert private.state == "held"
    assert private.reason == (
        "no_eligible_business" if change == "no_eligible" else "read_failed"
    )
    assert (
        sender.service.store.job(
            user_id=sender.owner, connection_id=row.connection_id
        ).provider_calls
        == 0
    )


def test_next_day_held_retry_checks_consent_again(sender):
    from argus.domain.ingestion.email_intake.budget import next_business_day
    from argus.domain.ingestion.whatsapp.receipt_consent import receipt_consent_store

    from workflows.read_resume import ReadResume

    row = capture(sender)
    sender.files.budget().charge(sender.owner, sender.now)
    assert held.read(sender, row) == "whatsapp_held_read_budget_day"
    receipt_consent_store(sender.pool).revoke(UUID(sender.owner))
    sender.now = next_business_day(sender.now) + timedelta(seconds=1)
    ReadResume(sender.service).run(sender.now)
    assert held.read(sender, row) == "document_reading_not_allowed"
    assert sender.extractor.calls == 0 and counts(sender) == (0, 1)


def test_already_admitted_held_read_finishes_after_disconnect(sender, monkeypatch):
    from argus.domain.ingestion.whatsapp.store_postgres import PostgresWhatsAppStore

    row = capture(sender)
    extract_for_business(sender, monkeypatch)
    extract = sender.extractor.extract

    async def disconnect_after_call(**kwargs):
        result = await extract(**kwargs)
        assert PostgresWhatsAppStore(sender.pool).revoke(
            destination_owner_id=sender.owner, now=sender.now
        )
        return result

    monkeypatch.setattr(sender.extractor, "extract", disconnect_after_call)
    assert held.read(sender, row) == "prepared"
    assert sender.files.list_for_user(sender.owner)[0].state == "assigned"
    assert sender.extractor.calls == 1 and counts(sender) == (1, 0)


def test_second_provider_request_checks_the_original_consent_again(sender, monkeypatch):
    from argus.domain.ingestion.whatsapp.receipt_consent import receipt_consent_store

    row = capture(sender)

    async def retry_after_revocation(**kwargs):
        await kwargs["before_request"]()
        sender.extractor.calls += 1
        receipt_consent_store(sender.pool).revoke(UUID(sender.owner))
        await kwargs["before_request"]()
        pytest.fail("a second provider request passed after revocation")

    monkeypatch.setattr(sender.extractor, "extract", retry_after_revocation)
    assert held.read(sender, row) == "document_reading_not_allowed"
    assert sender.extractor.calls == 1 and counts(sender) == (0, 1)
    job = sender.service.store.job(user_id=sender.owner, connection_id=row.connection_id)
    assert job.provider_calls == 1


def test_business_read_rechecks_the_senders_grant_before_provider_admission(
    sender, monkeypatch
):
    row = capture(sender)
    result = assign(sender, row)
    assert result.status == "queued"
    original = sender.extractor.extract

    async def revoke_before_admission(**kwargs):
        with sender.pool.connection() as db:
            db.execute(
                "update public.business_client_grants set revoked_at=now() where id=%s",
                (sender.grant,),
            )
        return await original(**kwargs)

    monkeypatch.setattr(sender.extractor, "extract", revoke_before_admission)
    assert (
        asyncio.run(read_receipt(sender.service, sender.custodian, result.connection_id))
        != "prepared"
    )
    assert counts(sender) == (0, 0) and sender.extractor.calls == 0


def hold_resend(sender, original, *, filename="recent.pdf", media_type="application/pdf"):
    key = uuid4().bytes * 2
    data = sender.service.store.source(
        user_id=sender.owner, connection_id=original.connection_id
    )
    fresh = sender.service.reopen_held_delivery(
        user_id=sender.owner,
        previous_id=original.id,
        message_key=key,
        content=data,
        filename=filename,
        media_type=media_type,
        source_text="recent caption",
    )
    row = sender.files.hold(
        user_id=sender.owner,
        sender_link_id=sender.sender_link_id,
        provider_message_key=key,
        connection_id=fresh.connection_id,
        reason="no_match",
        now=sender.now,
    )
    inbound(sender, row)
    return row


def change_receiving_business(sender):
    from tests.test_business_spaces_migration_postgres import owned_space

    with sender.pool.connection() as db:
        db.execute(
            "update public.business_client_grants set revoked_at=now() where id=%s",
            (sender.grant,),
        )
        new_space = owned_space(db, sender.owner)
    prepare_phone_business(sender.pool, new_space, sender.owner)
    return new_space


@pytest.mark.parametrize("full", [False, True])
def test_resend_after_access_loss_reuses_only_original_private_read(
    sender, monkeypatch, full
):
    monkeypatch.setenv("CUADRAO_WHATSAPP_HELD_READS_PER_DAY", "3")
    original, unrelated = capture(sender), capture(sender)
    for row in (original, unrelated):
        assert held.read(sender, row) == "prepared"
    if full:
        sender.service.read_budget.settings = ReadBudgetSettings(per_day=1)
        sender.service.read_budget.charge(sender.space, sender.now)
    first = assign(sender, original)
    before = counts(sender)
    assert before == (1, 1 + int(full))

    business = change_receiving_business(sender)
    resent = hold_resend(sender, original)
    result = sender.service.adopt(
        user_id=sender.owner, held_id=resent.id, business_id=business
    )
    assert result.connection_id != first.connection_id and result.status == "review_ready"
    destination = dict(user_id=sender.owner, connection_id=result.connection_id)
    draft = sender.service.store.draft(**destination)
    assert (draft.filename, draft.source_text) == ("recent.pdf", "recent caption")
    batch = sender.service.store.get(**destination)
    for candidate in batch.candidates:
        assert candidate.source.connection_id == result.connection_id
        assert all(
            attachment.filename == "recent.pdf" for attachment in candidate.attachments
        )
    assert sender.extractor.calls == 2
    assert counts(sender) == before
    with sender.pool.connection() as db:
        assert db.execute(
            "select coalesce(sum(reads),0) from public.business_read_daily_usage"
            " where business_id=%s",
            (business,),
        ).fetchone() == (0,)
        messages = dict(
            db.execute(
                "select provider_message_key,connection_id::text from public.whatsapp_inbound_messages"
                " where destination_owner_id=%s",
                (sender.owner,),
            ).fetchall()
        )
    assert messages[original.provider_message_key] == first.connection_id
    assert messages[resent.provider_message_key] == result.connection_id
    assert messages[unrelated.provider_message_key] == unrelated.connection_id


def test_resend_after_unread_assignment_settles_its_own_later_read(sender):
    from argus.domain.ingestion.documents.jobs import PreparationJobs
    from argus.domain.owner_scope import PERSONAL

    original = capture(sender)
    assert assign(sender, original).status == "queued"
    business = change_receiving_business(sender)
    resent = hold_resend(sender, original)
    sender.service.queue(
        user_id=sender.owner,
        connection_id=resent.connection_id,
        consent=True,
        scope=PERSONAL,
    )
    PreparationJobs(sender.service).start(
        user_id=sender.owner, connection_id=resent.connection_id
    )
    assert held.read(sender, resent) == "prepared"
    assert counts(sender) == (0, 1)

    routed = sender.service.route_saved_hold(user_id=sender.owner, held_id=resent.id)
    assert routed[0] == business and routed[1].status == "review_ready"
    assert sender.extractor.calls == 1
    assert counts(sender) == (0, 0)
    with sender.pool.connection() as db:
        assert db.execute(
            "select sum(reads) from public.business_read_daily_usage"
            " where business_id=%s",
            (business,),
        ).fetchone() == (1,)


def test_new_delivery_matches_saved_buyer_against_only_current_grants(
    sender, monkeypatch
):
    from argus.domain.business.spaces import PostgresSpaceStore
    from faker import Faker

    from tests.test_business_spaces_migration_postgres import owned_space

    buyer = Faker().numerify("1########")
    extract = sender.extractor.extract

    async def read_buyer(**kwargs):
        batch = await extract(**kwargs)
        return batch.model_copy(
            update={"receipt": batch.receipt.model_copy(update={"buyer_rnc": buyer})}
        )

    monkeypatch.setattr(sender.extractor, "extract", read_buyer)
    original = capture(sender)
    assert held.read(sender, original) == "prepared"
    assign(sender, original)
    with sender.pool.connection() as db:
        db.execute(
            "update public.business_client_grants set revoked_at=now() where id=%s",
            (sender.grant,),
        )
    resent = hold_resend(sender, original)
    assert (
        sender.service.route_saved_hold(user_id=sender.owner, held_id=resent.id) is None
    )
    assert (
        next(
            r.reason
            for r in sender.files.list_for_user(sender.owner)
            if r.id == resent.id
        )
        == "no_eligible_business"
    )
    with sender.pool.connection() as db:
        b = owned_space(db, sender.owner)
        db.execute(
            "update public.spaces set business_rnc=%s,business_tax_id_type='rnc' where id=%s",
            (buyer, b),
        )
    c, _ = PostgresSpaceStore(sender.pool).create_additional(
        sender.owner, Faker().company(), "DO", str(uuid4())
    )
    for eligible in (b, c.id):
        prepare_phone_business(sender.pool, eligible, sender.owner)
    destination, result = sender.service.route_saved_hold(
        user_id=sender.owner, held_id=resent.id
    )
    assert destination == b and result.status == "review_ready"
    assert sender.extractor.calls == 1 and counts(sender) == (1, 0)


def test_resent_private_hold_expires_without_erasing_assigned_receipt(sender):
    from argus.domain.business.contracts.deletion import PURGE_AFTER

    row = capture(sender)
    assert held.read(sender, row) == "prepared"
    assert sender.service.store.save_rebuilt(
        user_id=sender.owner,
        connection_id=row.connection_id,
        content=b"prior rebuilt",
        media_type="image/jpeg",
    )
    result = assign(sender, row)
    target = dict(user_id=sender.custodian, connection_id=result.connection_id)
    retained = (
        sender.service.store.source(**target),
        sender.service.store.rebuilt(**target),
    )
    with sender.pool.connection() as db:
        db.execute(
            "update public.business_client_grants set revoked_at=now() where id=%s",
            (sender.grant,),
        )
    before = counts(sender)
    resent = hold_resend(sender, row)
    sender.now += PURGE_AFTER + timedelta(seconds=1)
    with sender.pool.connection() as db:
        private_path, image_path = db.execute(
            "select source_path,rebuilt_path from public.financial_document_extractions where connection_id=%s",
            (resent.connection_id,),
        ).fetchone()
    assert resent.connection_id in private_path and image_path is None
    assert sender.service.store.objects.get(private_path) == retained[0]
    assert sender.files.expire(resent.id, sender.now, sender.owner)
    assert sender.service.store.objects.get(private_path) is None
    assert (
        sender.service.store.draft(
            user_id=sender.owner, connection_id=resent.connection_id
        )
        is None
    )
    assert (
        sender.service.store.source(**target),
        sender.service.store.rebuilt(**target),
    ) == retained
    assert counts(sender) == before
    assert sender.extractor.calls == 1


def test_reopened_image_previews_the_senders_rebuilt_copy_without_pinning_it(sender):
    from argus.domain.business.contracts.deletion import PURGE_AFTER
    from argus.domain.owner_scope import PERSONAL

    from tests.ingestion.whatsapp_support import RECEIPT_PNG

    key = uuid4().bytes * 2
    asyncio.run(
        sender.service.upload(
            user_id=sender.owner,
            content=RECEIPT_PNG,
            media_type="image/png",
            filename="original.png",
            consent=True,
            scope=PERSONAL,
            on_capture=sender.files.capture(
                user_id=sender.owner,
                sender_link_id=sender.sender_link_id,
                provider_message_key=key,
                reason="no_match",
                now=sender.now,
            ),
        )
    )
    [original] = sender.files.list_for_user(sender.owner)
    inbound(sender, original)
    image = sender.service.source_bytes(
        user_id=sender.owner, connection_id=original.connection_id, scope=PERSONAL
    )
    assert image.startswith(b"\xff\xd8")
    assigned = assign(sender, original)
    resent = hold_resend(sender, original, filename="resent.png", media_type="image/png")
    assert (
        sender.service.source_bytes(
            user_id=sender.owner, connection_id=resent.connection_id, scope=PERSONAL
        )
        == image
    )
    assert sender.files.expire(
        resent.id, sender.now + PURGE_AFTER + timedelta(seconds=1), sender.owner
    )
    assert sender.service.store.rebuilt(
        user_id=sender.custodian, connection_id=assigned.connection_id
    ) == ("image/jpeg", image)
    assert sender.extractor.calls == 0


def test_failed_resent_capture_discards_only_unpublished_objects(sender):
    import hashlib

    from argus.domain.ingestion.documents.objects import connection_prefix
    from argus.domain.owner_scope import PERSONAL

    original = capture(sender)
    assign(sender, original)
    content = sender.service.source_bytes(
        user_id=sender.owner, connection_id=original.connection_id, scope=PERSONAL
    )
    key = uuid4().bytes * 2
    digest = hashlib.sha256(content).hexdigest()
    args = dict(
        user_id=sender.owner,
        previous_id=original.id,
        message_key=key,
        content=content,
        filename="recent.pdf",
        media_type="application/pdf",
        source_text=None,
    )
    with pytest.raises(DocumentServiceError, match="held_file_unavailable"):
        sender.service.reopen_held_delivery(**{**args, "user_id": sender.custodian})
    with pytest.raises(DocumentServiceError, match="document_source_changed"):
        sender.service.reopen_held_delivery(**{**args, "content": content + b"different"})
    with pytest.raises(RuntimeError, match="delivery interrupted"):
        with sender.pool.connection() as db, db.transaction():
            saved = sender.service.on_connection(db).reopen_held_delivery(**args)
            path = (
                connection_prefix(user_id=sender.owner, connection_id=saved.connection_id)
                + digest
            )
            assert sender.service.store.objects.get(path) == content
            raise RuntimeError("delivery interrupted")
    cleanup = dict(user_id=sender.owner, message_key=key, digest=digest)
    sender.service.discard_unpublished_held_copy(**cleanup)
    assert sender.service.store.objects.get(path) is None
    retry = sender.service.reopen_held_delivery(**args)
    assert retry.connection_id == saved.connection_id
    sender.service.discard_unpublished_held_copy(**cleanup)
    assert sender.service.store.objects.get(path) == content
    assert sender.service.reopen_held_delivery(**args).replayed
