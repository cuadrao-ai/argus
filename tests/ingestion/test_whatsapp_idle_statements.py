"""Count SQL issued by the API and document worker over simulated idle windows."""

from __future__ import annotations

import asyncio
import base64
import signal
from collections import Counter
from collections.abc import Callable
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from argus.api import app_setup, state, whatsapp
from argus.api.routers.whatsapp import webhook_router
from argus.domain.ingestion.documents import objects
from argus.domain.ingestion.secrets import SecretBox
from fastapi import FastAPI
from loguru import logger

from workflows import document_job, document_worker


class EmptyPool:
    def __init__(self) -> None:
        self.statements = Counter()

    def connection(self) -> nullcontext[EmptyPool]:
        return nullcontext(self)

    def transaction(self) -> nullcontext[None]:
        return nullcontext()

    def execute(self, sql: str, params: object = None) -> SimpleNamespace:
        self.statements[sql] += 1
        return SimpleNamespace(
            fetchone=lambda: (0,) if sql.startswith("select count(*)") else None,
            fetchall=lambda: [],
        )


class Clock:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.seconds = 0
        self.elapsed = 0
        self.loop = asyncio.get_running_loop()
        monkeypatch.setattr(self.loop, "time", lambda: self.seconds)
        pending = set()
        to_thread = asyncio.to_thread

        async def tracked(work: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
            if asyncio.get_running_loop() is not self.loop:
                return await to_thread(work, *args, **kwargs)
            task = asyncio.create_task(to_thread(work, *args, **kwargs))
            pending.add(task)
            try:
                return await task
            finally:
                pending.discard(task)

        self.pending = pending
        monkeypatch.setattr(asyncio, "to_thread", tracked)

    def now(self) -> datetime:
        return datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=self.seconds)

    async def advance_to(self, seconds: int) -> None:
        for second in range(self.elapsed, seconds):
            self.seconds = second
            for _ in range(12):
                await asyncio.sleep(0)
                if self.pending:
                    await asyncio.gather(*self.pending)
        self.elapsed = seconds


@pytest.fixture
def idle(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    env = {
        "CUADRAO_WHATSAPP_VERIFY_TOKEN": "fake-verify",
        "CUADRAO_WHATSAPP_APP_SECRET": "fake-app-secret",
        "CUADRAO_WHATSAPP_ACCESS_TOKEN": "fake-access",
        "CUADRAO_WHATSAPP_NUMBER_ID": "1234",
        "CUADRAO_WHATSAPP_SENDER_KEY": "fake-sender",
        "CUADRAO_INGESTION_SECRET_KEY": base64.urlsafe_b64encode(b"k" * 32).decode(),
        "CUADRAO_DOCUMENT_EXTRACTION_ENABLED": "true",
        "CUADRAO_DOCUMENT_JOBS_IDLE_POLL_SECONDS": "60",
        "CUADRAO_DOCUMENT_JOBS_SWEEP_SECONDS": "30",
        "CUADRAO_DOCUMENT_PURGE_EVERY_SECONDS": "3600",
    }
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    def set_switches(*, intake: bool, outbound: bool) -> None:
        monkeypatch.setenv("CUADRAO_WHATSAPP_INTAKE_ENABLED", str(intake))
        monkeypatch.setenv("CUADRAO_WHATSAPP_OUTBOUND_ENABLED", str(outbound))

    return set_switches


def statement_counts(pool: EmptyPool) -> dict[str, int]:
    queries = Counter()
    for sql, count in pool.statements.items():
        if " from public.whatsapp_reply_groups g" in sql:
            queries["due"] += count
        elif sql.startswith("delete from public.whatsapp_reply_"):
            queries["cleanup"] += count
        elif "from public.whatsapp_inbound_messages" in sql:
            queries["inbound"] += count
        elif "whatsapp" in sql:
            queries["other_whatsapp"] += count
        else:
            queries["documents"] += count
    return dict(queries)


def stub_api_dependencies(
    monkeypatch: pytest.MonkeyPatch, clock: Clock, pool: EmptyPool, app: FastAPI
) -> None:
    from argus.api import (
        apple_sign_in,
        bank_matching,
        email_intake,
        financial_accounts,
        fiscal_operations,
        households,
        ingestion,
        personalization_memory,
        profile_images,
    )

    for module, name in (
        (apple_sign_in, "apple_sign_in"),
        (bank_matching, "bank_matching"),
        (email_intake, "email_intake"),
        (financial_accounts, "financial_accounts"),
        (fiscal_operations, "fiscal"),
        (households, "households"),
        (personalization_memory, "personalization_memory"),
        (profile_images, "profile_images"),
    ):
        monkeypatch.setattr(module, f"start_{name}", Mock())
        stop = getattr(module, f"stop_{name}")
        monkeypatch.setattr(
            module,
            f"stop_{name}",
            AsyncMock() if asyncio.iscoroutinefunction(stop) else Mock(),
        )
    app.state.financial_accounts_pool = pool
    monkeypatch.setattr(app_setup, "validate_startup_configuration", Mock())
    monkeypatch.setattr(app_setup, "validate_hosted_openrouter_configuration", Mock())
    monkeypatch.setattr(state, "PERSISTENCE_MODE", "supabase")
    monkeypatch.setattr(state, "CHECKPOINTER_MODE", "memory")
    monkeypatch.setattr(ingestion, "start_ingestion", whatsapp.start_whatsapp)
    monkeypatch.setattr(
        ingestion, "stop_ingestion", lambda app: whatsapp.configure_whatsapp(None)
    )
    documents = SimpleNamespace(
        hub=SimpleNamespace(box=SecretBox(b"k" * 32), clock=clock.now, sink=None)
    )
    monkeypatch.setattr(whatsapp, "documents_service", lambda: documents)
    monkeypatch.setattr(whatsapp, "business_spaces", object)


async def idle_counts(
    clock: Clock, pool: EmptyPool
) -> tuple[dict[str, int], dict[str, int]]:
    await clock.advance_to(300)
    first_five_minutes = statement_counts(pool)
    await clock.advance_to(3600)
    return first_five_minutes, statement_counts(pool)


@pytest.mark.asyncio
@pytest.mark.parametrize("intake,outbound", [(True, True), (True, False), (False, False)])
async def test_api_boot_issues_no_idle_whatsapp_sql(
    monkeypatch: pytest.MonkeyPatch,
    idle: Callable[..., None],
    intake: bool,
    outbound: bool,
) -> None:
    idle(intake=intake, outbound=outbound)
    clock, pool, app = Clock(monkeypatch), EmptyPool(), FastAPI()
    stub_api_dependencies(monkeypatch, clock, pool, app)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(Mock(side_effect=AssertionError))
    ) as client:
        monkeypatch.setattr(
            whatsapp, "httpx", SimpleNamespace(AsyncClient=lambda: client)
        )
        with patch.object(
            clock.loop, "create_task", wraps=clock.loop.create_task
        ) as started:
            async with app_setup.lifespan(app):
                five_minutes, hour = await idle_counts(clock, pool)
            started.assert_not_called()
    logger.info(
        "API intake={} outbound={} five_minutes={} hour={}",
        intake,
        outbound,
        five_minutes,
        hour,
    )
    assert (five_minutes, hour) == ({}, {})


@pytest.mark.asyncio
async def test_disabled_webhook_issues_no_sql(
    monkeypatch: pytest.MonkeyPatch, idle: Callable[..., None]
) -> None:
    idle(intake=False, outbound=True)
    clock, pool, app = Clock(monkeypatch), EmptyPool(), FastAPI()
    stub_api_dependencies(monkeypatch, clock, pool, app)
    app_setup.add_core_middleware_and_handlers(app)
    app.include_router(webhook_router, prefix="/api/v1")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        async with app_setup.lifespan(app):
            get = await client.get(whatsapp.WEBHOOK_PATH)
            post = await client.post(whatsapp.WEBHOOK_PATH, content=b"invalid")
    assert get.status_code == post.status_code == 404
    assert post.json()["code"] == "whatsapp_unavailable"
    assert statement_counts(pool) == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "intake,outbound,access_token,due",
    [
        (True, True, "fake-access", True),
        (True, False, "fake-access", False),
        (True, True, "", False),
        (False, True, "fake-access", False),
    ],
)
async def test_document_worker_paces_idle_whatsapp_sql(
    monkeypatch: pytest.MonkeyPatch,
    idle: Callable[..., None],
    intake: bool,
    outbound: bool,
    access_token: str,
    due: bool,
) -> None:
    idle(intake=intake, outbound=outbound)
    # Only the API holds the webhook credentials.
    monkeypatch.setenv("CUADRAO_WHATSAPP_VERIFY_TOKEN", "")
    monkeypatch.setenv("CUADRAO_WHATSAPP_APP_SECRET", "")
    monkeypatch.setenv("CUADRAO_WHATSAPP_ACCESS_TOKEN", access_token)
    clock, pool = Clock(monkeypatch), EmptyPool()
    handlers = {}
    monkeypatch.setattr(clock.loop, "add_signal_handler", handlers.__setitem__)
    monkeypatch.setattr(document_worker, "require_database_url", lambda: "fake")
    monkeypatch.setattr(
        document_worker, "ConnectionPool", lambda *args, **kwargs: nullcontext(pool)
    )
    monkeypatch.setattr(
        document_worker, "storage_source_objects", objects.InMemorySourceObjects
    )
    monkeypatch.setattr(document_job, "_clock", clock.now)
    worker = asyncio.create_task(document_worker.serve())
    try:
        five_minutes, hour = await idle_counts(clock, pool)
    finally:
        handlers[signal.SIGTERM]()
        await worker
    logger.info(
        "Worker intake={} outbound={} sender_credentials={} five_minutes={} hour={}",
        intake,
        outbound,
        bool(access_token),
        five_minutes,
        hour,
    )
    for interval, counts in ((5, five_minutes), (60, hour)):
        expected = {"cleanup": 3} if intake else {}
        if due:
            expected["due"] = interval
        assert counts.pop("documents") == {5: 44, 60: 324}[interval]
        assert counts == expected
