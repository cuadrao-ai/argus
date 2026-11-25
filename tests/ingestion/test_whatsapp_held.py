"""Held reads stay private and expiry preserves shared or assigned files."""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from uuid import uuid4

import pytest
from argus.domain.business.contracts.deletion import PURGE_AFTER
from argus.domain.business.read_budget import (
    HELD_READ_REFUSAL,
    InMemoryHeldReadBudget,
    InMemoryReadBudget,
    ReadBudgetSettings,
)
from argus.domain.ingestion.documents.service import DocumentServiceError
from argus.domain.ingestion.whatsapp.held import HeldFileExpiry, held_files, is_held
from argus.domain.owner_scope import PERSONAL

from tests.ingestion import test_read_budget as budgets
from tests.ingestion import test_whatsapp_idle_statements as idle_tests

rig = budgets.rig
idle = idle_tests.idle
NOW = datetime(2026, 11, 24, 15, tzinfo=timezone.utc)


@pytest.fixture
def intake(monkeypatch):
    for key, value in {
        "INTAKE_ENABLED": "true",
        "VERIFY_TOKEN": "fake",
        "APP_SECRET": "fake",
        "ACCESS_TOKEN": "fake",
        "SENDER_KEY": "fake",
        "NUMBER_ID": "1234",
    }.items():
        monkeypatch.setenv("CUADRAO_WHATSAPP_" + key, value)


async def capture(rig, content=None):
    service, _, clock = rig
    outcome = await service.upload(
        user_id="owner",
        content=content or b"%PDF-" + uuid4().bytes,
        filename="receipt.pdf",
        media_type="application/pdf",
        consent=True,
        scope=PERSONAL,
    )
    return held_files(service.store).hold(
        user_id="owner",
        sender_link_id=str(uuid4()),
        provider_message_key=uuid4().bytes * 2,
        connection_id=outcome.connection_id,
        reason="no_match",
        now=clock(),
    )


def test_held_day_rolls_over_in_santo_domingo():
    business = InMemoryReadBudget()
    held = InMemoryHeldReadBudget(business, per_day=1)
    now = datetime(2026, 11, 24, 3, 59, tzinfo=timezone.utc)
    assert held.charge("owner", now) is None
    assert held.charge("owner", now) == HELD_READ_REFUSAL
    assert held.charge("owner", now + timedelta(minutes=1)) is None
    assert not business._reads


@pytest.mark.parametrize("limit", ["day", "month"])
def test_hand_over_uses_original_day_and_business_rule(limit):
    business = InMemoryReadBudget(ReadBudgetSettings(per_day=1, per_month=1))
    held = InMemoryHeldReadBudget(business, per_day=3)
    old = NOW - timedelta(days=2)
    assert held.charge("owner", old) is None
    assert held.hand_over("owner", "business", NOW, charged_at=old) == "transferred"
    assert sum(held._reads.values()) == 0
    assert sum(business._reads.values()) == 1
    held.charge("owner", old)
    later = NOW if limit == "day" else NOW + timedelta(days=1)
    assert held.hand_over("owner", "business", later, charged_at=old) == "business_full"
    assert sum(held._reads.values()) == sum(business._reads.values()) == 1
    assert held.hand_over("other", "business", NOW) == "no_held_read"


def test_three_argument_transfer_uses_oldest_charge():
    business = InMemoryReadBudget()
    held = InMemoryHeldReadBudget(business)
    held.charge("owner", NOW - timedelta(days=2))
    assert held.hand_over("owner", "business", NOW) == "transferred"
    assert sum(held._reads.values()) == 0


@pytest.mark.asyncio
async def test_cap_keeps_unread_and_records_private(rig, intake, monkeypatch):
    monkeypatch.setenv("CUADRAO_WHATSAPP_HELD_READS_PER_DAY", "1")
    service, reader, _ = rig
    first, second = await capture(rig), await capture(rig)
    await service.resume(
        user_id="owner", connection_id=first.connection_id, scope=PERSONAL
    )
    with pytest.raises(DocumentServiceError, match=HELD_READ_REFUSAL):
        await service.resume(
            user_id="owner", connection_id=second.connection_id, scope=PERSONAL
        )
    assert reader.provider_calls == 1
    draft = service.get(
        user_id="owner", connection_id=second.connection_id, scope=PERSONAL
    )
    assert draft.status == "saved" and draft.error_code == HELD_READ_REFUSAL
    service.hub.sink.submit.assert_not_called()


@pytest.mark.asyncio
async def test_one_actual_provider_call_and_replay_no_record(rig, intake):
    from tests.test_whatsapp_receipt_read_postgres import Extractor

    service, _, _ = rig
    service.extractor = reader = Extractor()
    business = service.read_budget = InMemoryReadBudget()
    row = await capture(rig)
    for _ in range(2):
        result = await service.resume(
            user_id="owner", connection_id=row.connection_id, scope=PERSONAL
        )
        assert result.status == "review_ready"
    assert reader.calls == 1
    assert sum(held_files(service.store).budget()._reads.values()) == 1
    assert not business._reads
    service.hub.sink.submit.assert_not_called()


@pytest.mark.asyncio
async def test_expiry_old_new_second_run(rig):
    service, _, clock = rig
    old = await capture(rig)
    clock.now += PURGE_AFTER + timedelta(seconds=1)
    new = await capture(rig)
    files = held_files(service.store)
    assert files.expire(old.id, clock())
    assert not files.expire(old.id, clock())
    assert not files.expire(new.id, clock())
    assert service.store.draft(user_id="owner", connection_id=old.connection_id) is None
    assert service.store.source(user_id="owner", connection_id=new.connection_id)


@pytest.mark.asyncio
async def test_failure_keeps_draft_assignment_wins_retry(rig, monkeypatch):
    service, _, clock = rig
    row = await capture(rig)
    files = held_files(service.store)
    clock.now += PURGE_AFTER + timedelta(seconds=1)
    with monkeypatch.context() as patch:
        patch.setattr(
            service.store.objects, "remove", Mock(side_effect=RuntimeError("temporary"))
        )
        with pytest.raises(RuntimeError):
            files.expire(row.id, clock())
    assert service.store.draft(user_id="owner", connection_id=row.connection_id)
    assert files.settle(
        user_id="owner",
        held_id=row.id,
        business_id="business",
        connection_id="assigned",
        now=clock(),
    )
    assert not files.expire(row.id, clock())
    assert not files.expire(row.id, clock())
    assert service.store.source(user_id="owner", connection_id=row.connection_id)


@pytest.mark.asyncio
async def test_same_bytes_reuse_draft_and_newer_message_defers_expiry(rig):
    service, _, clock = rig
    first = await capture(rig, b"%PDF-identical")
    clock.now += PURGE_AFTER + timedelta(seconds=1)
    second = await capture(rig, b"%PDF-identical")
    assert first.connection_id == second.connection_id
    files = held_files(service.store)
    assert not files.expire(first.id, clock())
    clock.now += PURGE_AFTER + timedelta(seconds=1)
    assert files.expire(first.id, clock())
    assert all(r.state == "expired" for r in files.list_for_user("owner"))


@pytest.mark.asyncio
async def test_shared_original_rebuilt_preserve_both_drafts(rig):
    service, _, clock = rig
    row = await capture(rig, b"%PDF-shared")
    other = service.hub.connections.create(
        user_id="owner",
        source="statement",
        external_ref=str(uuid4()),
        label=None,
        now=clock(),
        scope=PERSONAL,
    )
    draft = service.store.draft(user_id="owner", connection_id=row.connection_id)
    service.store.capture(
        user_id="owner",
        draft=draft.model_copy(update={"connection_id": other.id, "resolution": {}}),
        content=b"%PDF-shared",
    )
    for target in (row.connection_id, other.id):
        service.store.save_rebuilt(
            user_id="owner",
            connection_id=target,
            content=b"rebuilt",
            media_type="image/jpeg",
        )
    before = dict(service.store.objects.objects)
    clock.now += PURGE_AFTER + timedelta(seconds=1)
    assert not held_files(service.store).expire(row.id, clock())
    assert service.store.objects.objects == before
    assert all(
        service.store.draft(user_id="owner", connection_id=t)
        for t in (row.connection_id, other.id)
    )


@pytest.mark.asyncio
async def test_partial_erasure_cannot_assign_and_retry_finishes(rig, monkeypatch):
    service, _, clock = rig
    row = await capture(rig)
    service.store.save_rebuilt(
        user_id="owner",
        connection_id=row.connection_id,
        content=b"rebuilt",
        media_type="image/jpeg",
    )
    files = held_files(service.store)
    remove = service.store.objects.remove
    calls = []

    def partial(path):
        calls.append(path)
        if len(calls) == 2:
            raise RuntimeError("partial")
        remove(path)

    clock.now += PURGE_AFTER + timedelta(seconds=1)
    with monkeypatch.context() as patch:
        patch.setattr(service.store.objects, "remove", partial)
        with pytest.raises(RuntimeError):
            files.expire(row.id, clock())
    assert service.store.draft(user_id="owner", connection_id=row.connection_id)
    assert not files.settle(
        user_id="owner",
        held_id=row.id,
        business_id="business",
        connection_id="assigned",
        now=clock(),
    )
    assert files.expire(row.id, clock())
    assert not service.store.objects.objects


def test_intake_off_expiry_issues_no_query(monkeypatch):
    monkeypatch.setenv("CUADRAO_WHATSAPP_INTAKE_ENABLED", "false")
    pool = Mock()
    HeldFileExpiry(pool, Mock()).tick()
    pool.connection.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("before", [True, False])
@pytest.mark.parametrize(
    "intake_on,outbound", [(False, False), (True, False), (True, True)]
)
async def test_measured_worker_idle_hour(monkeypatch, idle, before, intake_on, outbound):
    import asyncio
    import signal
    from contextlib import nullcontext
    from types import SimpleNamespace

    import httpx
    from argus.domain.ingestion.documents.objects import InMemorySourceObjects
    from argus.domain.ingestion.whatsapp import document_step
    from loguru import logger

    from tests.ingestion.test_whatsapp_idle_statements import (
        Clock,
        EmptyPool,
        idle_counts,
    )
    from workflows import document_job, document_worker, read_resume

    idle(intake=intake_on, outbound=outbound)
    monkeypatch.setattr(
        document_step,
        "httpx",
        SimpleNamespace(
            AsyncClient=lambda: httpx.AsyncClient(
                transport=httpx.MockTransport(Mock(side_effect=AssertionError)),
                trust_env=False,
            )
        ),
    )
    clock, pool = Clock(monkeypatch), EmptyPool()
    handlers = {}
    monkeypatch.setattr(clock.loop, "add_signal_handler", handlers.__setitem__)
    monkeypatch.setattr(document_worker, "require_database_url", lambda: "fake")
    monkeypatch.setattr(
        document_worker, "ConnectionPool", lambda *a, **k: nullcontext(pool)
    )
    monkeypatch.setattr(document_worker, "storage_source_objects", InMemorySourceObjects)
    monkeypatch.setattr(document_job, "_clock", clock.now)
    if before:
        monkeypatch.setattr(
            document_worker,
            "HeldFileExpiry",
            lambda *a, **k: SimpleNamespace(tick=lambda: None),
        )
        from argus.domain.business.read_budget import READ_BUDGET_REFUSALS

        monkeypatch.setattr(
            read_resume,
            "READ_BUDGET_REFUSALS",
            READ_BUDGET_REFUSALS - {HELD_READ_REFUSAL},
        )
    worker = asyncio.create_task(document_worker.serve())
    try:
        _, counts = await idle_counts(clock, pool)
    finally:
        handlers[signal.SIGTERM]()
        await worker
    logger.info(
        "Held worker before={} intake={} outbound={} counts={}",
        before,
        intake_on,
        outbound,
        counts,
    )
    whatsapp = sum(n for sql, n in pool.statements.items() if "whatsapp" in sql)
    expected = 3 + 60 * int(outbound) if intake_on else 0
    assert whatsapp == expected + 7 * int(intake_on and not before)
    assert sum(pool.statements.values()) == 324 + expected + int(intake_on and not before)


@pytest.mark.asyncio
async def test_held_drafts_hidden_before_pagination_even_when_off(rig, monkeypatch):
    from argus.api.documents import DocumentContext, require_saved_document_context
    from argus.api.routers.financial_documents import router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    service, _, _ = rig
    row = await capture(rig)
    visible = await service.upload(
        user_id="owner",
        content=b"%PDF-visible",
        filename="visible.pdf",
        media_type="application/pdf",
        consent=False,
        scope=PERSONAL,
    )
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[require_saved_document_context] = lambda: DocumentContext(
        service, "owner"
    )
    monkeypatch.setenv("CUADRAO_WHATSAPP_INTAKE_ENABLED", "false")
    with TestClient(app) as client:
        response = client.get("/api/v1/financial-documents?limit=1")
    assert response.status_code == 200, response.text
    assert [item["connection_id"] for item in response.json()["items"]] == [
        visible.connection_id
    ]
    assert response.json()["next_offset"] is None
    assert is_held(
        service.get(user_id="owner", connection_id=row.connection_id, scope=PERSONAL)
    )
