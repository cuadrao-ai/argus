"""Idle pacing uses simulated time; reads and shutdown keep their existing pace."""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import yaml
from argus.domain.ingestion.documents import worker as worker_module
from argus.domain.ingestion.documents.config import (
    DocumentJobSettings,
    load_document_job_settings,
)
from argus.domain.ingestion.documents.worker import DocumentWorker


@pytest.fixture
def idle_worker(monkeypatch):
    monkeypatch.setenv("CUADRAO_DOCUMENT_EXTRACTION_ENABLED", "true")
    monkeypatch.delenv("CUADRAO_DOCUMENT_JOBS_IDLE_POLL_SECONDS", raising=False)
    monkeypatch.delenv("ARGUS_DOCUMENT_JOBS_IDLE_POLL_SECONDS", raising=False)

    async def sweep(*args):
        await asyncio.Event().wait()

    monkeypatch.setattr(worker_module, "sweep_forever", sweep)
    store = SimpleNamespace(pull=Mock(return_value=None))
    service = SimpleNamespace(
        store=store, hub=SimpleNamespace(clock=lambda: datetime.now(timezone.utc))
    )
    worker = DocumentWorker(service, DocumentJobSettings())
    monkeypatch.setattr(worker, "_read", AsyncMock(return_value="prepared"))
    return worker


async def simulate(worker, monkeypatch, *, steps=None, seconds=None):
    stop = asyncio.Event()
    waits = []
    real_wait = asyncio.wait

    async def wait(tasks, *, timeout=None, **kwargs):
        if timeout is None:
            return await real_wait(tasks, **kwargs)
        waits.append(timeout)
        await asyncio.sleep(0)  # Run completed reads and their callbacks, not the clock.
        await asyncio.sleep(0)
        if (steps and len(waits) >= steps) or (seconds and sum(waits) >= seconds):
            stop.set()
        return set(), set(tasks)

    monkeypatch.setattr(worker_module.asyncio, "wait", wait)
    await worker.run(stop)
    return waits


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ceiling,expected",
    [(1, [1] * 8), (5, [1, 2, 4, 5, 5, 5, 5, 5]), (60, [1, 2, 4, 8, 16, 32, 60, 60])],
)
async def test_empty_checks_reach_but_never_exceed_the_ceiling(
    idle_worker, monkeypatch, ceiling, expected
):
    idle_worker.settings = DocumentJobSettings(idle_poll_seconds=ceiling)
    waits = await simulate(idle_worker, monkeypatch, steps=8)
    assert waits == expected
    assert idle_worker.service.store.pull.call_count == 8


@pytest.mark.asyncio
async def test_finding_work_resets_the_idle_wait(idle_worker, monkeypatch):
    idle_worker.service.store.pull.side_effect = (
        [None] * 4 + [("source", "attempt")] + [None] * 8
    )
    waits = await simulate(idle_worker, monkeypatch, steps=8)
    assert waits == [1, 2, 4, 5, 1, 2, 4, 5]
    idle_worker._read.assert_awaited_once_with("source", "attempt")


@pytest.mark.asyncio
async def test_running_reads_keep_the_busy_pace(idle_worker, monkeypatch):
    read = asyncio.create_task(asyncio.Event().wait())
    idle_worker.reads.add(read)
    # Completing the read before drain avoids testing a real timeout.

    async def drain():
        read.cancel()
        await asyncio.gather(read, return_exceptions=True)

    monkeypatch.setattr(idle_worker, "_drain", drain)
    assert await simulate(idle_worker, monkeypatch, steps=8) == [1] * 8


@pytest.mark.asyncio
async def test_stop_interrupts_the_long_idle_wait(idle_worker, monkeypatch):
    stop = asyncio.Event()
    idle_worker.settings = DocumentJobSettings(idle_poll_seconds=60)
    real_wait = asyncio.wait
    timeouts = []

    async def wait(tasks, *, timeout=None, **kwargs):
        if timeout is None:
            return await real_wait(tasks, **kwargs)
        timeouts.append(timeout)
        assert len(timeouts) <= 7, "the idle loop never reached its ceiling"
        if timeout < 60:
            return set(), set(tasks)
        asyncio.get_running_loop().call_soon(stop.set)
        # No timeout: only the stop signal can end this wait.
        done, pending = await real_wait(tasks, **kwargs)
        assert done and not pending
        return done, pending

    monkeypatch.setattr(worker_module.asyncio, "wait", wait)
    await idle_worker.run(stop)
    assert timeouts == [1, 2, 4, 8, 16, 32, 60]


@pytest.mark.asyncio
@pytest.mark.parametrize("ceiling,checks", [(1, 600), (5, 122), (60, 15)])
async def test_ten_idle_minutes_count_database_checks(
    idle_worker, monkeypatch, ceiling, checks
):
    idle_worker.settings = DocumentJobSettings(idle_poll_seconds=ceiling)
    await simulate(idle_worker, monkeypatch, seconds=600)
    assert idle_worker.service.store.pull.call_count == checks


@pytest.mark.parametrize("value,expected", [(None, 5), ("60", 60), ("1", 1)])
def test_idle_setting_default_and_override(monkeypatch, value, expected):
    monkeypatch.delenv("CUADRAO_DOCUMENT_JOBS_IDLE_POLL_SECONDS", raising=False)
    monkeypatch.delenv("ARGUS_DOCUMENT_JOBS_IDLE_POLL_SECONDS", raising=False)
    if value is not None:
        monkeypatch.setenv("CUADRAO_DOCUMENT_JOBS_IDLE_POLL_SECONDS", value)
    assert load_document_job_settings().idle_poll_seconds == expected


def test_invalid_settings_keep_the_default_idle_ceiling(monkeypatch):
    monkeypatch.setenv("CUADRAO_DOCUMENT_JOBS_IDLE_POLL_SECONDS", "0")
    assert load_document_job_settings().idle_poll_seconds == 5


def test_idle_ceiling_is_declared_per_environment():
    root = Path(__file__).resolve().parents[2]
    key = "CUADRAO_DOCUMENT_JOBS_IDLE_POLL_SECONDS"
    services = yaml.safe_load((root / "render.yaml").read_text())["services"]
    for name, value in (
        ("cuadrao-documents-worker", "5"),
        ("cuadrao-documents-worker-staging", "60"),
    ):
        service = next(s for s in services if s["name"] == name)
        assert next(e["value"] for e in service["envVars"] if e["key"] == key) == value
    manifest = json.loads((root / "scripts/ops/staging_env_manifest.json").read_text())
    entry = next(
        e for e in manifest["services"]["documents_worker"]["entries"] if e["name"] == key
    )
    assert entry["value"] == "60"
    assert entry["production"] == {"value": "5"}
    assert f"{key}=5\n" in (root / ".env.example").read_text()
