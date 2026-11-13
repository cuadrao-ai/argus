"""The expiry rides the documents worker's sweep loop: at most one run an hour,
extraction on or off, and nothing at all when its setting is 0."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from argus.domain.business.actions.document_purge import DocumentExpiry
from argus.domain.ingestion.documents.config import DocumentJobSettings
from argus.domain.ingestion.documents.jobs import sweep_forever

START = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now


def _expiry(every: timedelta) -> tuple[DocumentExpiry, Clock, list[datetime]]:
    clock, runs = Clock(), []
    expiry = DocumentExpiry(None, None, every=every, clock=clock)
    expiry.run = runs.append
    return expiry, clock, runs


def test_a_thirty_second_loop_runs_the_expiry_once_an_hour():
    expiry, clock, runs = _expiry(timedelta(hours=1))
    for _ in range(2 * 120 + 1):
        expiry.tick()
        clock.now += timedelta(seconds=30)
    assert runs == [START, START + timedelta(hours=1), START + timedelta(hours=2)]


def test_zero_turns_the_expiry_off():
    expiry, clock, runs = _expiry(timedelta(0))
    for _ in range(10):
        expiry.tick()
        clock.now += timedelta(hours=1)
    assert runs == []


def test_the_setting_defaults_to_one_hour(monkeypatch):
    for name in ("CUADRAO", "ARGUS"):
        monkeypatch.delenv(f"{name}_DOCUMENT_PURGE_EVERY_SECONDS", raising=False)
    assert DocumentJobSettings().purge_every_seconds == 3600
    monkeypatch.setenv("CUADRAO_DOCUMENT_PURGE_EVERY_SECONDS", "0")
    assert DocumentJobSettings().purge_every_seconds == 0


@pytest.mark.asyncio
async def test_upkeep_runs_while_extraction_is_off_and_survives_a_failure(monkeypatch):
    monkeypatch.setenv("CUADRAO_DOCUMENT_EXTRACTION_ENABLED", "false")
    calls: list[str] = []

    class Jobs:
        def sweep(self) -> None:
            calls.append("sweep")

    def upkeep() -> None:
        calls.append("upkeep")
        raise RuntimeError("storage down")

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(sweep_forever(Jobs(), 0.01, upkeep), 0.1)
    assert calls and set(calls) == {"upkeep"}
