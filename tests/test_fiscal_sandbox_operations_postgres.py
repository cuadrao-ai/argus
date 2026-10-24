from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import pytest
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.custody_graph import FAMILIES, _identity
from psycopg.errors import CheckViolation, InsufficientPrivilege

from tests import test_financial_accounts_postgres as shared
from tests.fiscal import conftest as fixtures

users = fixtures.users
case_factory = fixtures.case_factory
lane = fixtures.lane

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not shared.DSN, reason="Disposable database required"),
]


async def prepare(lane):
    return await lane.service.prepare(lane.owner, lane.grant, lane.case.case_id)


def callback(lane, **changes):
    event = dict(
        type="documents.emissionFinished",
        id=lane.provider.provider_id,
        companyIdentification=lane.case.issuer,
        documentNumber=lane.case.number,
        status="FINISHED",
        legalStatus="ACCEPTED",
    )
    event.update(changes)
    return json.dumps(event).encode()


async def test_concurrent_prepare_and_submit_one_contact(lane):
    states = await asyncio.gather(
        prepare(lane),
        lane.service.prepare(lane.member, lane.member_grant, lane.case.case_id),
    )
    assert states[0].id == states[1].id
    results = await asyncio.gather(
        *[
            lane.service.submit(
                lane.owner, lane.grant, states[0].id, states[0].payload_digest
            )
            for _ in range(8)
        ]
    )
    assert lane.provider.calls == 1
    assert all(result.id == states[0].id for result in results)
    final = await lane.service.get(lane.owner, lane.grant, states[0].id)
    assert final.state.legal == "ACCEPTED"


async def test_accept_then_500_and_process_loss_never_reissues(lane):
    operation = await prepare(lane)
    lane.provider.fail_create = True
    first = await lane.service.submit(
        lane.owner, lane.grant, operation.id, operation.payload_digest
    )
    assert first.state.submission == "unknown"
    for _ in range(3):
        await lane.service.submit(
            lane.owner, lane.grant, operation.id, operation.payload_digest
        )
    assert lane.provider.calls == 1
    assert (await lane.service.callback(callback(lane))) == "stored"
    final = await lane.service.get(lane.owner, lane.grant, operation.id)
    assert final.state.legal == "ACCEPTED"
    assert final.provider_id == lane.provider.provider_id


async def test_crash_after_marker_before_transport_and_stale_lease(lane):
    operation = await prepare(lane)
    _, permit = await asyncio.to_thread(
        lane.store.claim, lane.owner, lane.grant, operation.id, operation.payload_digest
    )
    assert permit is not None
    await lane.service.submit(
        lane.owner, lane.grant, operation.id, operation.payload_digest
    )
    assert lane.provider.calls == 0
    with lane.store.pool.connection() as db:
        db.execute(
            "update public.business_fiscal_operations set next_check=clock_timestamp()-interval '1 second' where id=%s",
            (operation.id,),
        )
    await lane.service.reconcile()
    state = await lane.service.get(lane.owner, lane.grant, operation.id)
    assert state.state.submission == "unknown"
    assert state.state.needs_review
    lane.store.record(operation.id, lane.provider.event("poll"), lease=uuid4())
    assert (
        await lane.service.get(lane.owner, lane.grant, operation.id)
    ).provider_id is None


async def test_callback_before_response_duplicate_reorder_conflict(lane):
    operation = await prepare(lane)
    lane.provider.entered, lane.provider.resume = asyncio.Event(), asyncio.Event()
    submission = asyncio.create_task(
        lane.service.submit(
            lane.owner, lane.grant, operation.id, operation.payload_digest
        )
    )
    await lane.provider.entered.wait()
    await lane.service.callback(callback(lane))
    await lane.service.callback(callback(lane))
    await lane.service.callback(json.dumps(json.loads(callback(lane)), indent=2).encode())
    lane.provider.resume.set()
    await submission
    await lane.service.callback(callback(lane, status="REGISTERED", legalStatus=None))
    await lane.service.callback(callback(lane, legalStatus="REJECTED"))
    state = await lane.service.get(lane.owner, lane.grant, operation.id)
    assert state.state.legal == "ACCEPTED"
    assert state.state.processing == "FINISHED"
    assert state.state.needs_review
    with lane.store.pool.connection() as db:
        assert (
            db.execute(
                "select count(*) from public.business_fiscal_observations where operation_id=%s and source='callback'",
                (operation.id,),
            ).fetchone()[0]
            == 3
        )


async def test_missed_callback_poll_and_pdf_failure(lane):
    lane.provider.response_changes = dict(
        processing="REGISTERED",
        legal="unreported",
        xml="unreported",
        pdf="unreported",
        xml_url=None,
        pdf_url=None,
    )
    operation = await prepare(lane)
    await lane.service.submit(
        lane.owner, lane.grant, operation.id, operation.payload_digest
    )
    with lane.store.pool.connection() as db:
        db.execute(
            "update public.business_fiscal_operations set next_check=clock_timestamp()-interval '1 second' where id=%s",
            (operation.id,),
        )
    await lane.service.reconcile()
    assert lane.provider.reads == 1
    assert (
        await lane.service.get(lane.owner, lane.grant, operation.id)
    ).state.legal == "ACCEPTED"
    lane.provider.fail_artifact = True
    with pytest.raises(ActionError, match="fiscal_artifact_unavailable"):
        await lane.service.artifact(lane.owner, lane.grant, operation.id, "pdf")
    state = await lane.service.get(lane.owner, lane.grant, operation.id)
    assert state.state.legal == "ACCEPTED"
    assert state.state.pdf == "retrieval_failed"
    assert lane.provider.calls == 1


async def test_revoked_closed_owner_transfer_and_cross_business(lane):
    operation = await prepare(lane)
    with pytest.raises(ActionError):
        await lane.service.submit(
            lane.member, lane.member_grant, operation.id, operation.payload_digest
        )
    stranger = TrustedActor(
        actor_id=lane.owner.actor_id, space_id=uuid4(), actor_kind="member"
    )
    with pytest.raises(ActionError):
        await lane.service.get(stranger, lane.grant, operation.id)
    with lane.store.pool.connection() as db:
        db.execute(
            "update public.business_client_grants set revoked_at=clock_timestamp() where id=%s",
            (lane.grant,),
        )
    with pytest.raises(ActionError):
        await lane.service.submit(
            lane.owner, lane.grant, operation.id, operation.payload_digest
        )
    assert lane.provider.calls == 0


async def test_immutable_intent_direct_rls_and_cascade(lane):
    operation = await prepare(lane)
    with lane.store.pool.connection() as db:
        with pytest.raises(CheckViolation), db.transaction():
            db.execute(
                "update public.business_fiscal_operations set number=%s where id=%s",
                ("E320000000001", operation.id),
            )
        for role in ("anon", "authenticated"):
            with pytest.raises(InsufficientPrivilege), db.transaction():
                db.execute("set local role " + role)
                db.execute("select * from public.business_fiscal_operations")
        await lane.service.submit(
            lane.owner, lane.grant, operation.id, operation.payload_digest
        )
        for role in ("anon", "authenticated"):
            with pytest.raises(InsufficientPrivilege), db.transaction():
                db.execute("set local role " + role)
                db.execute("select * from public.business_fiscal_observations")
    assert "business_fiscal_operations" in FAMILIES
    assert "business_fiscal_observations" in FAMILIES
    rewritten = _identity(
        {
            "prepared_actor": {
                "actor_id": str(lane.owner.actor_id),
                "display_name": "Synthetic",
            }
        },
        str(lane.owner.actor_id),
        str(uuid4()),
        str(uuid4()),
    )
    assert rewritten["prepared_actor"]["actor_id"] != str(lane.owner.actor_id)
    assert rewritten["prepared_actor"]["display_name"] == "Exmiembro"


async def test_changed_manifest_identity_conflict(lane):
    await prepare(lane)
    changed = lane.case.model_copy(update={"document_key": str(uuid4())})
    with pytest.raises(ActionError, match="fiscal_identity_conflict"):
        lane.store.prepare(lane.owner, lane.grant, changed)


async def test_unmatched_and_wrong_identity_callback_quarantined(lane):
    await lane.service.callback(callback(lane))
    operation = await prepare(lane)
    await lane.service.callback(
        callback(
            lane, companyIdentification="999999999", business_id=str(lane.owner.space_id)
        )
    )
    state = await lane.service.get(lane.owner, lane.grant, operation.id)
    assert state.provider_id is None
    assert state.state.submission == "prepared"
    with lane.store.pool.connection() as db:
        assert (
            db.execute(
                "select count(*) from public.business_fiscal_observations where operation_id is null and source='callback'"
            ).fetchone()[0]
            >= 2
        )


async def test_commit_failure_prevents_contact(lane):
    operation = await prepare(lane)
    with lane.store.pool.connection() as db:
        db.execute(
            "create function public.fiscal_test_commit_failure() returns trigger language plpgsql as $$ begin raise exception 'synthetic_commit_failure'; end $$"
        )
        db.execute(
            f"create constraint trigger fiscal_test_commit_failure after update on public.business_fiscal_operations deferrable initially deferred for each row when (new.id='{operation.id}'::uuid) execute function public.fiscal_test_commit_failure()"
        )
    try:
        with pytest.raises(Exception, match="synthetic_commit_failure"):
            await lane.service.submit(
                lane.owner, lane.grant, operation.id, operation.payload_digest
            )
        assert lane.provider.calls == 0
        assert (
            await lane.service.get(lane.owner, lane.grant, operation.id)
        ).state.submission == "prepared"
    finally:
        with lane.store.pool.connection() as db:
            db.execute(
                "drop trigger fiscal_test_commit_failure on public.business_fiscal_operations"
            )
            db.execute("drop function public.fiscal_test_commit_failure()")


@pytest.mark.parametrize("early_callback", [False, True])
async def test_cancelled_contact_never_reissues_or_regresses_callback(
    lane, early_callback
):
    operation = await prepare(lane)
    lane.provider.entered, lane.provider.resume = asyncio.Event(), asyncio.Event()
    submission = asyncio.create_task(
        lane.service.submit(
            lane.owner, lane.grant, operation.id, operation.payload_digest
        )
    )
    await lane.provider.entered.wait()
    if early_callback:
        await lane.service.callback(callback(lane))
    submission.cancel()
    with pytest.raises(asyncio.CancelledError):
        await submission
    state = await lane.service.submit(
        lane.owner, lane.grant, operation.id, operation.payload_digest
    )
    assert lane.provider.calls == 1
    assert state.state.submission == ("identified" if early_callback else "unknown")
    assert state.state.legal == ("ACCEPTED" if early_callback else "unreported")


async def test_closed_business_refuses_before_contact(lane):
    from argus.domain.business.lifecycle import PostgresBusinessLifecycle

    operation = await prepare(lane)
    PostgresBusinessLifecycle(lane.store.pool).close(
        owner_id=str(lane.owner.actor_id),
        space_id=str(lane.owner.space_id),
        confirmation="Colmado",
        idempotency_key="synthetic-close",
    )
    with pytest.raises(ActionError, match="business_closed"):
        await lane.service.submit(
            lane.owner, lane.grant, operation.id, operation.payload_digest
        )
    with pytest.raises(ActionError, match="business_closed"):
        await lane.service.get(lane.owner, lane.grant, operation.id)
    assert lane.provider.calls == 0


async def test_fiscal_acceptance_creates_no_financial_records(lane):
    with lane.store.pool.connection() as db:
        before = tuple(
            db.execute(
                "select count(*) from public." + table + " where owner_space_id=%s",
                (lane.case.business_id,),
            ).fetchone()[0]
            for table in (
                "financial_import_events",
                "financial_records",
                "financial_accounts",
            )
        )
    operation = await prepare(lane)
    await lane.service.submit(
        lane.owner, lane.grant, operation.id, operation.payload_digest
    )
    with lane.store.pool.connection() as db:
        after = tuple(
            db.execute(
                "select count(*) from public." + table + " where owner_space_id=%s",
                (lane.case.business_id,),
            ).fetchone()[0]
            for table in (
                "financial_import_events",
                "financial_records",
                "financial_accounts",
            )
        )
    assert before == after == (0, 0, 0)


def _synthetic_pdf():
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] >>",
    ]
    body = b"%PDF-1.4\n"
    offsets = [0]
    for index, value in enumerate(objects, 1):
        offsets.append(len(body))
        body += str(index).encode() + b" 0 obj\n" + value + b"\nendobj\n"
    position = len(body)
    body += b"xref\n0 4\n0000000000 65535 f \n"
    body += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    return (
        body
        + f"trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n{position}\n%%EOF\n".encode()
    )


@pytest.mark.parametrize("lane", ["E31", "E32"], indirect=True)
async def test_both_document_contracts_complete_local_transport_workflow(
    lane, monkeypatch
):
    from argus.domain.business.fiscal_sandbox import provider as module
    from argus.domain.business.fiscal_sandbox.config import Settings
    from argus.domain.business.fiscal_sandbox.provider import STORAGE_HOST, Provider

    case = lane.case
    provider_id = "01J00000000000000000000001"
    section = "fiscalInvoice" if case.kind == "E31" else "invoice"
    endpoint = "/fiscal-invoices" if case.kind == "E31" else "/invoices"
    base = f"https://{STORAGE_HOST}/users/{uuid4()}/opaque/ulid/{section}"
    xml_url, pdf_url = (
        f"{base}/doc-{provider_id}.xml?private=signed",
        f"{base}/pdf/doc-{provider_id}.pdf?private=signed",
    )
    creates = []

    async def fetch(method, url, **kwargs):
        if method == "POST":
            creates.append(kwargs["payload"])
            assert url == module.API_ORIGIN + endpoint
            data = dict(
                id=provider_id,
                encf=case.number,
                companyIdentification=case.issuer,
                status="REGISTERED",
            )
        elif url.startswith(module.API_ORIGIN):
            assert url == module.API_ORIGIN + endpoint + "/" + provider_id
            data = dict(
                id=provider_id,
                documentNumber=case.number,
                companyIdentification=case.issuer,
                status="FINISHED",
                legalStatus="ACCEPTED",
                xml=xml_url,
                pdf=pdf_url,
            )
        else:
            assert kwargs.get("token") is None
            if url == xml_url:
                return (
                    f"<ECF><Encabezado><IdDoc><eNCF>{case.number}</eNCF></IdDoc><Emisor><RNCEmisor>{case.issuer}</RNCEmisor></Emisor></Encabezado></ECF>".encode(),
                    "application/xml",
                )
            assert url == pdf_url
            return _synthetic_pdf(), "application/pdf"
        return json.dumps(data).encode(), "application/json"

    async def addresses(*args, **kwargs):
        return [(None, None, None, None, ("8.8.8.8", 443))]

    monkeypatch.setattr(module, "curl", fetch)
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", addresses)
    lane.service.provider = Provider(
        Settings(
            api_token="synthetic-token",
            storage_host=STORAGE_HOST,
            storage_path_prefix="/users/",
        )
    )
    operation = await prepare(lane)
    for _ in range(2):
        await lane.service.submit(
            lane.owner, lane.grant, operation.id, operation.payload_digest
        )
    assert len(creates) == 1 and creates[0] == case.payload
    assert b"<ECF>" in await lane.service.artifact(
        lane.owner, lane.grant, operation.id, "xml"
    )
    assert (
        await lane.service.artifact(lane.owner, lane.grant, operation.id, "pdf")
    ).startswith(b"%PDF-")
    final = await lane.service.get(lane.owner, lane.grant, operation.id)
    assert final.state.legal == "ACCEPTED"
    assert final.state.xml == final.state.pdf == "available"
