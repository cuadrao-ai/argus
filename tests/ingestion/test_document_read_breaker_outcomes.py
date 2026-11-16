"""Every call the breaker admits tells the breaker how it ended, exactly once.
A call that failed for now is a failure. Every other end of a sent call is an
answer, a wrong answer and a refused key included: the provider is up. A call
that was admitted and never sent gives its turn back. A read the breaker held
back was not admitted, so it reports nothing."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
from argus.domain.ingestion.documents import breaker as breaking
from argus.domain.ingestion.documents import preparation
from argus.domain.ingestion.documents.breaker import COOLDOWN, BreakerState
from argus.domain.ingestion.documents.config import (
    BREAKER_COOLDOWN_SECONDS,
    BREAKER_FAILURES,
    DocumentJobSettings,
)
from argus.domain.ingestion.documents.failures import CONFIG_ALERT, READS_PAUSED
from argus.domain.ingestion.documents.jobs import run_attempt
from argus.domain.ingestion.documents.worker import DocumentWorker

from tests.ingestion.test_document_read_retries import (
    FAILED,
    OK,
    UNREADABLE,
    Rig,
    open_the_breaker,
    rig,  # noqa: F401
    status,
)
from tests.ingestion.test_read_budget_local_refusals import poppler

BUDGET_SPENT = "business_read_budget_day"
# A sent call the provider answered, though the read still fails: the alerts
# it writes about our own setup.
ANSWERED = [
    pytest.param(ValueError("Incomplete document response"), 0, id="cut answer"),
    pytest.param(UNREADABLE, 0, id="unreadable receipt"),
    pytest.param(status(400), 0, id="refused request"),
    pytest.param(status(401), 1, id="refused key"),
    pytest.param(status(403), 1, id="forbidden key"),
]


def asks(rig: Rig) -> list[str]:  # noqa: F811
    """What the breaker is asked and told from now on, in order."""
    heard: list[str] = []
    for ask in ("admit", "failed", "succeeded", "unsent"):
        real = getattr(rig.breaker, ask, None)

        def spy(now: datetime, *probe: str | None, ask=ask, real=real):  # noqa: ANN001, ANN202
            heard.append(ask)
            return None if real is None else real(now, *probe)

        rig.monkeypatch.setattr(rig.breaker, ask, spy, raising=False)
    return heard


async def probing(rig: Rig) -> DocumentWorker:  # noqa: F811
    """The breaker is open and its cooldown has passed: the next read sent is
    the probe."""
    rig.answers(status(503))
    await open_the_breaker(rig)
    rig.clock.pass_(BREAKER_COOLDOWN_SECONDS)
    return DocumentWorker(rig.service, DocumentJobSettings())


@pytest.mark.asyncio
@pytest.mark.parametrize("answer, alerts", ANSWERED)
async def test_a_probe_the_provider_answers_closes_the_breaker(rig, answer, alerts):  # noqa: F811
    """The finding: the probe's answer came back wrong, the receipt went to
    Necesitan atención, and the probe stayed out, so every other read waited
    for it to be given up."""
    worker = await probing(rig)
    provider = rig.answers(answer, OK)
    probe = worker._take(rig.clock())

    await run_attempt(rig.service, *probe)
    assert rig.draft(probe[0]).status == "needs_attention"
    assert (provider.calls, rig.breaker.state) == (1, BreakerState())
    assert len([line for line in rig.logs if CONFIG_ALERT in line]) == alerts

    # No other read waits for a probe that already ended.
    following = worker._take(rig.clock())
    assert following is not None and following[0] != probe[0]
    assert await run_attempt(rig.service, *following) == "prepared"
    assert provider.calls == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("answer, alerts", ANSWERED)
async def test_an_answered_failure_never_counts_toward_opening(rig, answer, alerts):  # noqa: F811
    rig.answers(status(503))
    for _ in range(BREAKER_FAILURES - 1):
        await rig.queued()
        assert await rig.take() == FAILED
        rig.clock.pass_(1)
    almost = rig.breaker.state
    assert len(almost.failures) == BREAKER_FAILURES - 1 and almost.opened_at is None

    rig.answers(answer)
    for _ in range(2):
        connection = await rig.queued()
        await rig.take()
        assert rig.draft(connection).status == "needs_attention"
    assert rig.breaker.state == almost


@pytest.mark.asyncio
@pytest.mark.parametrize("stopped_by", ["spent budget", "lost lease"])
async def test_a_probe_that_was_never_sent_gives_its_turn_back(rig, stopped_by):  # noqa: F811
    """The probe was admitted and then refused here, before the provider: the
    breaker stays open with its cooldown as it was, and the next read probes."""
    worker = await probing(rig)
    provider, opened = rig.answers(OK), rig.breaker.state
    with rig.monkeypatch.context() as local:
        if stopped_by == "spent budget":
            local.setattr(rig.budget, "charge", lambda *_: BUDGET_SPENT)
        else:
            local.setattr(rig.store, "mark_provider_call", lambda **_: False)
        assert await run_attempt(rig.service, *worker._take(rig.clock())) not in (
            "prepared",
            READS_PAUSED,
        )
    assert (provider.calls, rig.breaker.state) == (0, opened)
    assert not any("probe_failed" in line for line in rig.logs)

    assert await run_attempt(rig.service, *worker._take(rig.clock())) == "prepared"
    assert (provider.calls, rig.breaker.state) == (1, BreakerState())


TIMEOUT = httpx.ReadTimeout("slow")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "answers, heard",
    [
        pytest.param([OK], ["admit", "succeeded"], id="answer"),
        pytest.param([status(503)], ["admit", "failed"], id="503"),
        pytest.param([TIMEOUT], ["admit", "failed"] * 2, id="two timeouts"),
        pytest.param(
            [TIMEOUT, OK],
            ["admit", "failed", "admit", "succeeded"],
            id="timeout then answer",
        ),
        pytest.param(
            [TIMEOUT, status(400)],
            ["admit", "failed", "admit", "succeeded"],
            id="timeout then refusal",
        ),
        *(
            pytest.param([answer.values[0]], ["admit", "succeeded"], id=answer.id)
            for answer in ANSWERED
        ),
    ],
)
async def test_each_admitted_call_tells_the_breaker_its_end_once(rig, answers, heard):  # noqa: F811
    rig.answers(*answers)
    await rig.queued()
    told = asks(rig)
    await rig.take()
    assert told == heard


@pytest.mark.asyncio
async def test_a_timeout_then_a_refusal_here_ends_both_calls_once(rig):  # noqa: F811
    """The first call timed out; the second was admitted and the budget
    refused it: one failure, one turn given back."""
    rig.answers(TIMEOUT)
    await rig.queued()
    told, charge, charges = asks(rig), rig.budget.charge, iter([None, BUDGET_SPENT])
    rig.monkeypatch.setattr(
        rig.budget, "charge", lambda *at: charge(*at) or next(charges)
    )
    await rig.take()
    assert told == ["admit", "failed", "admit", "unsent"]
    assert len(rig.breaker.state.failures) == 1


@pytest.mark.asyncio
async def test_a_read_that_was_never_admitted_tells_the_breaker_nothing(rig):  # noqa: F811
    # A file refused here never asks to be sent.
    rig.monkeypatch.setattr(preparation, "_run", poppler("Pages: 1\nEncrypted: yes\n"))
    rig.answers(OK)
    await rig.queued()
    told = asks(rig)
    await rig.take()
    assert told == []

    # A read the open breaker holds back asked and was refused: nothing to end.
    rig.monkeypatch.setattr(preparation, "_run", poppler("Pages: 1\nEncrypted: no\n"))
    rig.breaker.state = BreakerState(opened_at=rig.clock())
    await rig.queued()
    assert await rig.take() == READS_PAUSED
    assert told == ["admit"]
    assert rig.breaker.state == BreakerState(opened_at=rig.clock())


def test_only_the_current_probe_gives_its_turn_back():
    start = datetime(2026, 11, 16, tzinfo=timezone.utc)
    opened = BreakerState(opened_at=start)
    out, _ = breaking.admitted(opened, start + COOLDOWN, "current")
    assert breaking.unsent(out, "current") == opened
    assert breaking.unsent(out) == out, "a call admitted while closed holds no turn"
    assert breaking.unsent(out, "given up") == out
    closed = BreakerState(failures=(start,))
    assert breaking.unsent(closed, "current") == closed
    # The turn that was given back is the next asker's, at once.
    again, admission = breaking.admitted(opened, start + COOLDOWN, "next")
    assert (admission.until, again.probe_id) == (None, "next")
