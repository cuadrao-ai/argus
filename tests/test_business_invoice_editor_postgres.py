from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.contracts.invoicing import (
    CustomerInput,
    CustomerWrite,
    InvoiceDraft,
    InvoiceWrite,
)
from argus.domain.business.fiscal_sandbox.service import Service
from argus.domain.business.fiscal_sandbox.store import Store as FiscalStore
from argus.domain.business.invoicing.preparation import prepare
from argus.domain.business.invoicing.queries import Query, customers, invoices
from argus.domain.business.invoicing.store import InvoiceError, Store
from psycopg.errors import CheckViolation, InsufficientPrivilege

from tests import test_business_invoice_editor as unit_fixtures
from tests import test_financial_accounts_postgres as shared
from tests.fiscal import conftest as fiscal_fixtures

case_factory = fiscal_fixtures.case_factory
lane = fiscal_fixtures.lane
users = fiscal_fixtures.users
draft = unit_fixtures.draft
pytestmark = pytest.mark.skipif(not shared.DSN, reason="Disposable database required")


@pytest.fixture
def editor(lane):
    with lane.store.pool.connection() as db:
        db.execute(
            "update public.spaces set name=%s,business_rnc=%s,business_tax_id_type='rnc',business_provided_details=jsonb_build_object('address',%s::text) where id=%s",
            (
                lane.case.payload["sender"]["companyName"],
                lane.case.issuer,
                lane.case.payload["sender"]["address"],
                lane.owner.space_id,
            ),
        )
    return Store(lane.store.pool)


def create(editor, lane, data):
    return editor.save_invoice(
        lane.owner, lane.grant, None, InvoiceWrite(data=data), uuid4().hex
    )


def test_reload_partial_draft_keeps_every_field_and_no_customer_side_effect(editor, lane):
    data = InvoiceDraft(
        customer_input=CustomerInput(name="unfinished", email="unfinished"),
        notes="notes",
        instructions="instructions",
        terms="terms",
        currency="EUR",
    )
    saved = create(editor, lane, data)
    reloaded = Store(lane.store.pool).invoice(lane.owner, lane.grant, saved.id)
    assert reloaded == saved
    assert reloaded.data == data
    assert reloaded.amounts is None
    assert reloaded.payment_state == "unknown"
    assert reloaded.outstanding_amount is None
    assert customers(editor, lane.owner, lane.grant, Query()).total == 0


def test_idempotency_and_concurrent_stale_writes_are_separate(editor, lane, draft):
    key = uuid4().hex
    body = InvoiceWrite(data=draft)
    with ThreadPoolExecutor(max_workers=6) as workers:
        saved = list(
            workers.map(
                lambda _: Store(lane.store.pool).save_invoice(
                    lane.owner, lane.grant, None, body, key
                ),
                range(6),
            )
        )
    assert len({item.id for item in saved}) == 1
    with pytest.raises(ActionError, match="idempotency"):
        editor.save_invoice(
            lane.owner,
            lane.grant,
            None,
            InvoiceWrite(data=draft.model_copy(update={"notes": "different"})),
            key,
        )

    def write(value):
        try:
            return editor.save_invoice(
                lane.owner,
                lane.grant,
                saved[0].id,
                InvoiceWrite(
                    data=draft.model_copy(update={"notes": value}), expected_version=1
                ),
                uuid4().hex,
            )
        except InvoiceError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(write, ["first", "second"]))
    errors = [r for r in results if isinstance(r, InvoiceError)]
    assert len(errors) == 1
    assert errors[0].attempted["data"]["notes"] in {"first", "second"}
    assert errors[0].current_version == 2
    assert editor.invoice(lane.owner, lane.grant, saved[0].id).version == 2
    with lane.store.pool.connection() as db:
        assert (
            db.execute(
                "select count(*) from public.business_invoice_revisions where invoice_id=%s",
                (saved[0].id,),
            ).fetchone()[0]
            == 2
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("lane", ["E31", "E32"], indirect=True)
async def test_snapshot_contact_edits_reload_and_single_contact(editor, lane, draft):
    customer = editor.save_customer(
        lane.owner,
        lane.grant,
        None,
        CustomerWrite(data=draft.customer_input),
        uuid4().hex,
    )
    data = draft.model_copy(
        update={"customer_id": customer.id, "document_type": lane.case.kind}
    )
    saved = create(editor, lane, data)
    prepared = prepare(
        editor, lane.service, lane.owner, lane.grant, saved.id, saved.version
    )
    assert prepared.operation.invoice_id == saved.id
    assert prepared.operation.invoice_revision_id == saved.revision_id
    editor.save_customer(
        lane.owner,
        lane.grant,
        customer.id,
        CustomerWrite(
            data=customer.data.model_copy(update={"name": "Changed"}),
            expected_version=1,
            archived=True,
        ),
        uuid4().hex,
    )
    assert (
        Store(lane.store.pool)
        .invoice(lane.owner, lane.grant, saved.id)
        .data.customer_input.name
        == draft.customer_input.name
    )
    assert (
        prepare(
            editor, lane.service, lane.owner, lane.grant, saved.id, saved.version
        ).operation.id
        == prepared.operation.id
    )
    with pytest.raises(InvoiceError, match="already_prepared"):
        editor.save_invoice(
            lane.owner,
            lane.grant,
            saved.id,
            InvoiceWrite(data=data, expected_version=1),
            uuid4().hex,
        )
    restored = Service(
        FiscalStore(lane.store.pool),
        lane.provider,
        lane.service.settings,
        lane.service.cases,
    )
    outcomes = await asyncio.gather(
        *[
            restored.submit(
                lane.owner,
                lane.grant,
                prepared.operation.id,
                prepared.operation.payload_digest,
            )
            for _ in range(5)
        ]
    )
    assert lane.provider.calls == 1
    assert all(
        item.state.legal == "ACCEPTED" or item.state.submission == "contacted"
        for item in outcomes
    )
    final = editor.invoice(lane.owner, lane.grant, saved.id)
    assert final.operation.state.legal == "ACCEPTED"
    assert final.amounts.total == "35.40"
    assert final.delivery_state == "not_sent"
    with lane.store.pool.connection() as db:
        snapshot = db.execute(
            "select issue_snapshot from public.business_invoices where id=%s", (saved.id,)
        ).fetchone()[0]
        assert snapshot["customer"]["name"] == draft.customer_input.name
        assert snapshot["case"]["payload"]["totals"]["totalAmount"] == 35.4
        with pytest.raises(CheckViolation), db.transaction():
            db.execute(
                "update public.business_invoice_revisions set data='{}' where id=%s",
                (saved.revision_id,),
            )


@pytest.mark.asyncio
async def test_uncertain_create_late_callback_and_artifact_failure_never_reissue(
    editor, lane, draft
):
    saved = create(editor, lane, draft)
    prepared = prepare(editor, lane.service, lane.owner, lane.grant, saved.id, 1)
    lane.provider.fail_create = True
    operation = await lane.service.submit(
        lane.owner, lane.grant, prepared.operation.id, prepared.operation.payload_digest
    )
    assert operation.state.submission == "unknown"
    await lane.service.submit(
        lane.owner, lane.grant, operation.id, operation.payload_digest
    )
    lane.store.callback(lane.case, lane.provider.event("callback"))
    assert (
        editor.invoice(lane.owner, lane.grant, saved.id).operation.state.legal
        == "ACCEPTED"
    )
    lane.provider.fail_artifact = True
    with pytest.raises(ActionError, match="artifact_unavailable"):
        await lane.service.artifact(lane.owner, lane.grant, operation.id, "pdf")
    assert lane.provider.calls == 1
    assert (
        editor.invoice(lane.owner, lane.grant, saved.id).operation.state.legal
        == "ACCEPTED"
    )


def test_cross_business_revocation_and_read_only_fail_before_writes(editor, lane, draft):
    saved = create(editor, lane, draft)
    stranger = TrustedActor(
        actor_id=lane.owner.actor_id, space_id=uuid4(), actor_kind="member"
    )
    with pytest.raises(ActionError):
        editor.invoice(stranger, lane.grant, saved.id)
    with lane.store.pool.connection() as db:
        db.execute(
            "update public.business_client_grants set business_role='viewer' where id=%s",
            (lane.member_grant,),
        )
    assert editor.invoice(lane.member, lane.member_grant, saved.id).id == saved.id
    with pytest.raises(ActionError):
        editor.save_invoice(
            lane.member, lane.member_grant, None, InvoiceWrite(data=draft), uuid4().hex
        )
    with lane.store.pool.connection() as db:
        db.execute(
            "update public.business_client_grants set revoked_at=clock_timestamp() where id=%s",
            (lane.member_grant,),
        )
    with pytest.raises(ActionError):
        editor.invoice(lane.member, lane.member_grant, saved.id)
    with pytest.raises(ActionError):
        prepare(editor, lane.service, lane.member, lane.member_grant, saved.id, 1)
    assert lane.provider.calls == 0


def test_new_tables_deny_direct_clients(editor, lane, draft):
    create(editor, lane, draft)
    with lane.store.pool.connection() as db:
        for table in (
            "business_customers",
            "business_invoices",
            "business_invoice_revisions",
            "business_invoice_commands",
        ):
            assert db.execute(
                "select relrowsecurity from pg_class where oid=%s::regclass",
                ("public." + table,),
            ).fetchone()[0]
            for role in ("anon", "authenticated"):
                with pytest.raises(InsufficientPrivilege), db.transaction():
                    db.execute("set local role " + role)
                    db.execute("select * from public." + table)


@pytest.mark.asyncio
async def test_query_counts_and_totals_share_filters_but_stage_counts_are_period_scoped(
    editor, lane, draft
):
    saved = create(editor, lane, draft)
    create(editor, lane, draft.model_copy(update={"currency": "USD", "notes": "other"}))
    prepared = prepare(editor, lane.service, lane.owner, lane.grant, saved.id, 1)
    await lane.service.submit(
        lane.owner, lane.grant, prepared.operation.id, prepared.operation.payload_digest
    )
    page = invoices(editor, lane.owner, lane.grant, Query(currency="DOP"))
    assert page.total == 1
    assert page.stage_counts == {"draft": 1, "issued": 1}
    assert page.summaries[0].billed == "35.40"
    assert page.summaries[0].outstanding is None
    empty = invoices(editor, lane.owner, lane.grant, Query(search="no match"))
    assert empty.total == 0
    assert empty.stage_counts == page.stage_counts


def test_closed_business_denies_every_editor_boundary(editor, lane, draft):
    from argus.domain.business.lifecycle import PostgresBusinessLifecycle

    saved = create(editor, lane, draft)
    with lane.store.pool.connection() as db:
        name = db.execute(
            "select name from public.spaces where id=%s", (lane.owner.space_id,)
        ).fetchone()[0]
    PostgresBusinessLifecycle(lane.store.pool).close(
        owner_id=str(lane.owner.actor_id),
        space_id=str(lane.owner.space_id),
        confirmation=name,
        idempotency_key=uuid4().hex,
    )
    calls = [
        lambda: editor.invoice(lane.owner, lane.grant, saved.id),
        lambda: invoices(editor, lane.owner, lane.grant, Query()),
        lambda: create(editor, lane, draft),
        lambda: prepare(editor, lane.service, lane.owner, lane.grant, saved.id, 1),
    ]
    for call in calls:
        with pytest.raises(ActionError):
            call()
    assert lane.provider.calls == 0


def test_concurrent_prepare_uses_one_operation_and_number_cannot_be_reassigned(
    editor, lane, draft
):
    saved = create(editor, lane, draft)
    with ThreadPoolExecutor(max_workers=4) as workers:
        results = list(
            workers.map(
                lambda _: prepare(
                    editor, lane.service, lane.owner, lane.grant, saved.id, 1
                ),
                range(4),
            )
        )
    assert len({r.operation.id for r in results}) == 1
    other = create(editor, lane, draft)
    with pytest.raises(ActionError, match="fiscal_identity_conflict"):
        prepare(editor, lane.service, lane.owner, lane.grant, other.id, 1)
    assert editor.invoice(lane.owner, lane.grant, other.id).operation is None


@pytest.mark.asyncio
async def test_cancelled_saved_invoice_contact_cannot_be_repeated(editor, lane, draft):
    saved = create(editor, lane, draft)
    prepared = prepare(editor, lane.service, lane.owner, lane.grant, saved.id, 1)
    lane.provider.entered, lane.provider.resume = asyncio.Event(), asyncio.Event()
    operation = prepared.operation
    task = asyncio.create_task(
        lane.service.submit(
            lane.owner, lane.grant, operation.id, operation.payload_digest
        )
    )
    await lane.provider.entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    result = await lane.service.submit(
        lane.owner, lane.grant, operation.id, operation.payload_digest
    )
    assert result.state.submission == "unknown"
    assert lane.provider.calls == 1
    lane.store.callback(lane.case, lane.provider.event("callback"))
    assert (
        editor.invoice(lane.owner, lane.grant, saved.id).operation.state.legal
        == "ACCEPTED"
    )


def test_preparation_changes_query_version_and_foreign_customer_is_not_linkable(
    editor, lane, draft, users
):
    from psycopg.types.json import Jsonb

    from tests.test_business_spaces_migration_postgres import space

    saved = create(editor, lane, draft)
    before = invoices(editor, lane.owner, lane.grant, Query()).query_version
    prepare(editor, lane.service, lane.owner, lane.grant, saved.id, 1)
    assert invoices(editor, lane.owner, lane.grant, Query()).query_version != before
    with lane.store.pool.connection() as db:
        other_business = space(db, users["other"])
        other_customer = db.execute(
            "insert into public.business_customers(space_id,data) values(%s,%s) returning id",
            (other_business, Jsonb(draft.customer_input.model_dump(mode="json"))),
        ).fetchone()[0]
    with pytest.raises(ActionError, match="business_record_not_found"):
        create(editor, lane, draft.model_copy(update={"customer_id": other_customer}))


@pytest.mark.asyncio
async def test_conflicting_legal_evidence_is_excluded_from_billed_summary(
    editor, lane, draft
):
    saved = create(editor, lane, draft)
    prepared = prepare(editor, lane.service, lane.owner, lane.grant, saved.id, 1)
    operation = prepared.operation
    await lane.service.submit(
        lane.owner, lane.grant, operation.id, operation.payload_digest
    )
    lane.store.record(operation.id, lane.provider.event("callback", legal="REJECTED"))
    page = invoices(editor, lane.owner, lane.grant, Query())
    assert page.stage_counts == {"uncertain": 1}
    assert page.summaries == ()
    assert page.items[0].operation.state.legal == "ACCEPTED"
    assert page.items[0].operation.state.needs_review
