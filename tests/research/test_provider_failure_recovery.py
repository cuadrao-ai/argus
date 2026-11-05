"""Research provider failures (#609): typed, asked again inside the call's
deadline only when no paid work can have started, then ended on the recovery
discovery already uses, under the no-search answer wherever that answer runs.

Every provider here is scripted, and so is time: a retry's wait is asserted,
never slept. The failures are the five the issue names (a 500, a 429 with
Retry-After, a timeout, a 400 and a missing key), plus a connection refused
before the request was sent and one dropped mid-request, which the founder's
paid-work rule tells apart.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from argus.agent_runtime import research_calculation
from argus.agent_runtime import research_grounded as grounded
from argus.agent_runtime.calculated_answer import CalculatedAnswer
from argus.agent_runtime.recovery_messages import (
    DURABLE_RETRY_RECOVERY_CODES,
    RECOVERY_FALLBACK_MESSAGES,
)
from argus.api import state as api_state
from argus.api.chat.research_evidence import record_research_turn_evidence
from argus.domain.research import perplexity_agent
from argus.domain.research.config import RESEARCH_CONFIG_SPECS
from argus.domain.research.contracts import ResearchUnavailableError
from argus.domain.research.perplexity_agent import PerplexityAgentClient
from argus.domain.supabase_gateway import SupabaseGateway

from tests.research.conftest import (
    agent_response,
    request_body,
    run_research_turn,
    set_research_query,
)
from tests.test_supabase_gateway import _RecordingSupabaseClient

FAST = RESEARCH_CONFIG_SPECS["fast"]
QUESTION = "What is Apple trading at right now?"
BACKOFF = perplexity_agent._FIRST_BACKOFF_SECONDS
ATTEMPTS = perplexity_agent._MAX_ATTEMPTS

Step = Callable[[httpx.Request], httpx.Response]


class ScriptedClock:
    """Monotonic time that moves only when a wait or a timed-out request moves it."""

    def __init__(self) -> None:
        self.now = 0.0
        self.waits: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.waits.append(seconds)
        self.now += seconds


class ScriptedProvider(httpx.BaseTransport):
    """Plays one scripted step per request and records every request."""

    def __init__(self, steps: list[Step]) -> None:
        self.steps = list(steps)
        self.requests: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.steps.pop(0)(request)


def status(code: int, headers: dict[str, str] | None = None) -> Step:
    return lambda _request: httpx.Response(
        code, headers=headers, json={"error": {"message": "scripted"}}
    )


def answer() -> Step:
    document = agent_response()
    return lambda _request: httpx.Response(200, json=document)


def timeout(clock: ScriptedClock) -> Step:
    def step(request: httpx.Request) -> httpx.Response:
        # A read timeout fires only once the attempt's whole budget has passed.
        clock.now += budget(request)
        raise httpx.ReadTimeout("scripted", request=request)

    return step


def budget(request: httpx.Request) -> float:
    return request.extensions["timeout"]["read"]


def transport_error(error: type[httpx.TransportError]) -> Step:
    def step(request: httpx.Request) -> httpx.Response:
        raise error("scripted", request=request)

    return step


def scripted_client(
    clock: ScriptedClock, steps: list[Step], *, api_key: str = "k"
) -> tuple[PerplexityAgentClient, ScriptedProvider]:
    provider = ScriptedProvider(steps)
    client = PerplexityAgentClient(
        api_key, transport=provider, clock=clock.monotonic, sleep=clock.sleep
    )
    return client, provider


@dataclass(frozen=True)
class Failure:
    name: str
    steps: Callable[[ScriptedClock], list[Step]]
    reason: str
    status: int | None
    transient: bool
    attempts: int
    waits: tuple[float, ...]
    # Attempts the provider may have billed without answering.
    unanswered: int = 0
    api_key: str = "k"

    @property
    def recovery_code(self) -> str:
        return (
            "research_lookup_failed" if self.transient else "research_lookup_unavailable"
        )

    @property
    def degraded(self) -> dict[str, Any]:
        return {
            "code": f"research_unavailable_{self.reason}",
            **({"status": self.status} if self.status is not None else {}),
        }


RETRY_AFTER_SECONDS = 7

FAILURES = [
    Failure(
        "http_500",
        lambda _clock: [status(500)] * ATTEMPTS,
        reason="http_error",
        status=500,
        transient=True,
        attempts=ATTEMPTS,
        waits=(BACKOFF, 2 * BACKOFF),
    ),
    Failure(
        "http_429_retry_after",
        lambda _clock: [status(429, {"Retry-After": str(RETRY_AFTER_SECONDS)})]
        * ATTEMPTS,
        reason="http_error",
        status=429,
        transient=True,
        attempts=ATTEMPTS,
        waits=(RETRY_AFTER_SECONDS, RETRY_AFTER_SECONDS),
    ),
    Failure(
        "timeout",
        lambda clock: [timeout(clock)],
        reason="timeout",
        status=None,
        transient=True,
        attempts=1,
        waits=(),
        unanswered=1,
    ),
    Failure(
        "connection_refused",
        lambda _clock: [transport_error(httpx.ConnectError)] * ATTEMPTS,
        reason="transport",
        status=None,
        transient=True,
        attempts=ATTEMPTS,
        waits=(BACKOFF, 2 * BACKOFF),
    ),
    Failure(
        "connection_dropped",
        lambda _clock: [transport_error(httpx.RemoteProtocolError)],
        reason="transport",
        status=None,
        transient=True,
        attempts=1,
        waits=(),
        unanswered=1,
    ),
    Failure(
        "http_400",
        lambda _clock: [status(400)],
        reason="http_error",
        status=400,
        transient=False,
        attempts=1,
        waits=(),
    ),
    Failure(
        "not_configured",
        lambda _clock: [],
        reason="not_configured",
        status=None,
        transient=False,
        attempts=0,
        waits=(),
        api_key="",
    ),
]


# --- The client: asked again only when no paid work can have started -------


@pytest.mark.parametrize("failure", FAILURES, ids=lambda failure: failure.name)
def test_each_failure_is_retried_only_when_no_paid_work_can_have_started(
    monkeypatch: pytest.MonkeyPatch, failure: Failure
) -> None:
    unpriced: list[Any] = []
    monkeypatch.setattr(perplexity_agent, "record_unpriced_spend", unpriced.append)
    clock = ScriptedClock()
    client, provider = scripted_client(
        clock, failure.steps(clock), api_key=failure.api_key
    )

    with pytest.raises(ResearchUnavailableError) as raised:
        client.run_research(QUESTION, FAST)

    error = raised.value
    assert (error.reason, error.status, error.transient) == (
        failure.reason,
        failure.status,
        failure.transient,
    )
    assert len(provider.requests) == failure.attempts
    assert clock.waits == list(failure.waits)
    assert clock.now <= FAST.timeout_seconds, "every attempt ends inside one deadline"
    assert len({request.content for request in provider.requests}) <= 1
    # An attempt the provider may have billed without answering is on record.
    assert [(spend.reason, spend.provider_response_id) for spend in unpriced] == [
        ("unanswered_attempt", None)
    ] * failure.unanswered


def test_a_transient_failure_that_clears_answers_inside_the_same_deadline() -> None:
    clock = ScriptedClock()
    client, provider = scripted_client(clock, [status(500), status(503), answer()])

    packet = client.run_research(QUESTION, FAST)

    assert packet.answer_markdown.startswith("Apple closed")
    assert clock.waits == [BACKOFF, 2 * BACKOFF]
    # A retry gets what is left of the one deadline, never a fresh ceiling.
    assert [budget(request) for request in provider.requests] == [
        FAST.timeout_seconds,
        FAST.timeout_seconds - BACKOFF,
        FAST.timeout_seconds - 3 * BACKOFF,
    ]


def test_a_rate_limit_waits_exactly_what_retry_after_asks() -> None:
    clock = ScriptedClock()
    client, provider = scripted_client(
        clock, [status(429, {"Retry-After": str(RETRY_AFTER_SECONDS)}), answer()]
    )

    packet = client.run_research(QUESTION, FAST)

    assert packet.answer_markdown.startswith("Apple closed")
    assert clock.waits == [RETRY_AFTER_SECONDS]
    assert budget(provider.requests[1]) == FAST.timeout_seconds - RETRY_AFTER_SECONDS


def test_a_wait_that_would_leave_under_half_the_deadline_is_not_taken() -> None:
    clock = ScriptedClock()
    too_long = str(int(FAST.timeout_seconds / 2) + 1)
    client, provider = scripted_client(clock, [status(429, {"Retry-After": too_long})])

    with pytest.raises(ResearchUnavailableError) as raised:
        client.run_research(QUESTION, FAST)

    assert raised.value.status == 429 and raised.value.transient
    assert len(provider.requests) == 1
    assert clock.waits == []


def test_retry_after_as_a_past_http_date_asks_again_at_once() -> None:
    clock = ScriptedClock()
    client, provider = scripted_client(
        clock,
        [status(503, {"Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"}), answer()],
    )

    client.run_research(QUESTION, FAST)

    assert clock.waits == [0.0]
    assert len(provider.requests) == 2


def test_a_poll_is_left_to_the_poller_and_not_retried_by_the_client() -> None:
    clock = ScriptedClock()
    client, provider = scripted_client(clock, [status(500)])

    with pytest.raises(ResearchUnavailableError):
        client.poll_background("resp_bg1", timeout_seconds=FAST.timeout_seconds)

    assert len(provider.requests) == 1
    assert clock.waits == []


@pytest.mark.parametrize(
    ("error", "retried"),
    [
        (httpx.ConnectError, True),
        (httpx.ConnectTimeout, True),
        (httpx.PoolTimeout, True),
        (httpx.ReadTimeout, False),
        (httpx.ReadError, False),
        (httpx.WriteTimeout, False),
        (httpx.WriteError, False),
        (httpx.RemoteProtocolError, False),
    ],
    ids=lambda value: value.__name__ if isinstance(value, type) else str(value),
)
def test_a_transport_error_is_asked_again_only_when_the_request_never_left_argus(
    monkeypatch: pytest.MonkeyPatch, error: type[httpx.TransportError], retried: bool
) -> None:
    unpriced: list[Any] = []
    monkeypatch.setattr(perplexity_agent, "record_unpriced_spend", unpriced.append)
    clock = ScriptedClock()
    client, provider = scripted_client(clock, [transport_error(error), answer()])

    if retried:
        assert client.run_research(QUESTION, FAST).answer_markdown.startswith("Apple")
    else:
        with pytest.raises(ResearchUnavailableError) as raised:
            client.run_research(QUESTION, FAST)
        assert raised.value.transient and raised.value.sent

    assert len(provider.requests) == (2 if retried else 1)
    assert len(unpriced) == (0 if retried else 1)


def test_an_unmapped_os_error_fails_closed_as_a_sent_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unpriced: list[Any] = []
    monkeypatch.setattr(perplexity_agent, "record_unpriced_spend", unpriced.append)

    def step(_request: httpx.Request) -> httpx.Response:
        raise OSError("scripted socket failure")

    clock = ScriptedClock()
    client, provider = scripted_client(clock, [step, answer()])

    with pytest.raises(ResearchUnavailableError) as raised:
        client.run_research(QUESTION, FAST)

    error = raised.value
    assert (error.reason, error.transient, error.sent) == ("transport", True, True)
    assert len(provider.requests) == 1
    assert [spend.reason for spend in unpriced] == ["unanswered_attempt"]


def submitted() -> Step:
    return lambda _request: httpx.Response(
        200, json={"id": "resp_bg1", "status": "queued"}
    )


@pytest.mark.parametrize(
    ("first", "sent"),
    [
        (status(500), 2),
        (status(429, {"Retry-After": "1"}), 2),
        (transport_error(httpx.ConnectError), 2),
        (transport_error(httpx.ReadTimeout), 1),
        (transport_error(httpx.RemoteProtocolError), 1),
    ],
    ids=[
        "http_500",
        "http_429",
        "connection_refused",
        "read_timeout",
        "connection_dropped",
    ],
)
def test_a_background_submission_is_sent_again_only_when_no_run_can_have_started(
    monkeypatch: pytest.MonkeyPatch, first: Step, sent: int
) -> None:
    unpriced: list[Any] = []
    monkeypatch.setattr(perplexity_agent, "record_unpriced_spend", unpriced.append)
    clock = ScriptedClock()
    client, provider = scripted_client(clock, [first, submitted()])

    if sent == 2:
        assert client.submit_background(QUESTION, FAST) == "resp_bg1"
        assert unpriced == []
    else:
        with pytest.raises(ResearchUnavailableError) as raised:
            client.submit_background(QUESTION, FAST)
        # A run may already be billing: no Retry for the reader, and it is on record.
        assert raised.value.run_may_be_billing and not raised.value.transient
        assert [spend.reason for spend in unpriced] == ["unanswered_attempt"]

    assert len(provider.requests) == sent


@pytest.mark.parametrize(
    ("steps", "code"),
    [
        ([transport_error(httpx.ReadTimeout)], "research_lookup_unavailable"),
        ([transport_error(httpx.RemoteProtocolError)], "research_lookup_unavailable"),
        ([status(503)] * ATTEMPTS, "research_lookup_failed"),
    ],
    ids=["read_timeout", "connection_dropped", "server_error"],
)
def test_a_background_submission_offers_retry_only_when_no_run_can_be_billing(
    monkeypatch: pytest.MonkeyPatch, steps: list[Step], code: str
) -> None:
    from argus.api.chat import research_jobs

    from tests.research.test_research_jobs import _job_request, _JobGateway

    unpriced: list[Any] = []
    monkeypatch.setattr(perplexity_agent, "record_unpriced_spend", unpriced.append)
    gateway = _JobGateway()
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)
    client, provider = scripted_client(ScriptedClock(), list(steps))
    monkeypatch.setattr(research_jobs, "_client", lambda: client)
    runtime_result: dict[str, Any] = {"research_job_request": _job_request()}

    job = research_jobs.apply_research_job_request(
        runtime_result,
        user_id="u1",
        conversation_id="c1",
        request_message_id="m1",
        request_id="r1",
    )

    retryable = code in DURABLE_RETRY_RECOVERY_CODES
    assert job is None and gateway.rows == {}
    assert runtime_result["recovery"] == {"code": code, "retryable": retryable}
    assert len(provider.requests) == len(steps)
    assert len(unpriced) == (0 if retryable else 1)


@pytest.mark.parametrize(
    ("error", "transient"),
    [
        (ResearchUnavailableError("http_error", status=500), True),
        (ResearchUnavailableError("http_error", status=503), True),
        (ResearchUnavailableError("http_error", status=429), True),
        (ResearchUnavailableError("timeout"), True),
        (ResearchUnavailableError("transport"), True),
        (ResearchUnavailableError("http_error", status=400), False),
        (ResearchUnavailableError("http_error", status=404), False),
        (ResearchUnavailableError("not_configured", status=401), False),
        (ResearchUnavailableError("not_configured"), False),
        (ResearchUnavailableError("malformed_response"), False),
        (ResearchUnavailableError("empty_answer"), False),
        (ResearchUnavailableError("timeout", run_may_be_billing=True), False),
    ],
)
def test_transient_is_derived_from_the_status_or_the_reason(
    error: ResearchUnavailableError, transient: bool
) -> None:
    assert error.transient is transient


@pytest.mark.parametrize(
    ("error", "ruled_out"),
    [
        (ResearchUnavailableError("http_error", status=500), True),
        (ResearchUnavailableError("http_error", status=503), True),
        (ResearchUnavailableError("http_error", status=429), True),
        (ResearchUnavailableError("transport", sent=False), True),
        (ResearchUnavailableError("timeout", sent=False), True),
        (ResearchUnavailableError("timeout"), False),
        (ResearchUnavailableError("transport"), False),
        (ResearchUnavailableError("http_error", status=400), False),
        (ResearchUnavailableError("not_configured", sent=False), False),
        (ResearchUnavailableError("malformed_response"), False),
    ],
)
def test_paid_work_is_ruled_out_only_by_a_429_a_5xx_or_a_request_never_sent(
    error: ResearchUnavailableError, ruled_out: bool
) -> None:
    assert error.paid_work_ruled_out is ruled_out


# --- The turn: the no-search answer with the recovery under it, or the recovery
# alone, and the outage is recorded -------------------------------------------

NO_LOOKUP_ANSWER = (
    "From Argus market data, Apple last closed at $312.41 on 2026-08-06; "
    "today's price could not be looked up."
)
ANSWERED = CalculatedAnswer(
    answer_text=NO_LOOKUP_ANSWER,
    patch={},
    template=None,
    question_field=None,
    pending=None,
)


def _wire(
    monkeypatch: pytest.MonkeyPatch,
    failure: Failure,
    *,
    answered: CalculatedAnswer | None = None,
) -> list[dict[str, Any]]:
    """Script the provider's failure and the no-search answer, which cannot run
    unless ``answered`` is given. Returns the calls the no-search answer took."""
    set_research_query(
        monkeypatch, globals(), question_kind="live_quote", symbols=["AAPL"]
    )
    calls: list[dict[str, Any]] = []

    def _answer_without_lookup(**kwargs: Any) -> CalculatedAnswer | None:
        calls.append(kwargs)
        return answered

    monkeypatch.setattr(
        research_calculation, "answer_without_lookup", _answer_without_lookup
    )
    if not failure.api_key:
        monkeypatch.setattr(grounded, "_client", lambda: None)
        return calls
    clock = ScriptedClock()
    client, _provider = scripted_client(clock, failure.steps(clock))
    monkeypatch.setattr(grounded, "_client", lambda: client)
    return calls


@pytest.mark.parametrize("failure", FAILURES, ids=lambda failure: failure.name)
def test_a_failed_lookup_nothing_answers_ends_on_its_recovery_alone(
    monkeypatch: pytest.MonkeyPatch, failure: Failure
) -> None:
    calls = _wire(monkeypatch, failure)

    result = run_research_turn(QUESTION)

    assert result is not None
    assert [call["message"] for call in calls] == [QUESTION]
    patch = result.stage_patch
    code = failure.recovery_code
    assert patch["recovery"] == {"code": code, "retryable": failure.transient}
    # Only the transient code settles with a durable retry, as discovery's does.
    assert (code in DURABLE_RETRY_RECOVERY_CODES) is failure.transient
    assert patch["assistant_response"] == RECOVERY_FALLBACK_MESSAGES[code]
    assert "next_experiments" not in patch
    sidecar = patch["research"]
    assert sidecar["degraded"] == failure.degraded
    assert sidecar["rows"] == []
    assert sidecar["sources"] == []
    assert sidecar["anchor_symbols"] == ["AAPL"]


@pytest.mark.parametrize("failure", FAILURES, ids=lambda failure: failure.name)
def test_the_no_search_answer_carries_the_failed_lookups_recovery_under_it(
    monkeypatch: pytest.MonkeyPatch, failure: Failure
) -> None:
    calls = _wire(monkeypatch, failure, answered=ANSWERED)

    result = run_research_turn(QUESTION)

    assert result is not None and result.outcome == "ready_to_respond"
    assert [call["message"] for call in calls] == [QUESTION]
    assert [subject["symbol"] for subject in calls[0]["subjects"]] == ["AAPL"]
    patch = result.stage_patch
    assert patch["assistant_response"].startswith(NO_LOOKUP_ANSWER)
    assert patch["recovery"] == {
        "code": failure.recovery_code,
        "retryable": failure.transient,
        "under_answer": True,
    }
    # History and naming filters read the degraded flag, so the answer keeps it.
    assert patch["research"]["degraded"] == failure.degraded


@pytest.mark.parametrize(
    "failure", [FAILURES[0], FAILURES[-1]], ids=lambda failure: failure.name
)
def test_a_no_search_question_for_the_readers_figures_carries_no_recovery(
    monkeypatch: pytest.MonkeyPatch, failure: Failure
) -> None:
    asked = dataclasses.replace(ANSWERED, question_field="periods", pending={})
    _wire(monkeypatch, failure, answered=asked)

    result = run_research_turn(QUESTION)

    assert result is not None and result.outcome == "await_user_reply"
    assert result.stage_patch["requested_field"] == "periods"
    assert "recovery" not in result.stage_patch
    assert result.stage_patch["research"]["degraded"] == failure.degraded


def test_a_failed_survey_ends_on_its_recovery_without_a_no_search_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_research_query(monkeypatch, globals(), question_kind="market_pulse", symbols=[])

    def _never(**_: Any) -> None:
        raise AssertionError("a survey names no subject to answer without a lookup")

    monkeypatch.setattr(research_calculation, "answer_without_lookup", _never)
    monkeypatch.setattr(grounded, "_client", lambda: None)

    result = run_research_turn("What's moving in the market?")

    assert result is not None
    assert result.stage_patch["recovery"] == {
        "code": "research_lookup_unavailable",
        "retryable": False,
    }


def test_a_turn_whose_retry_clears_publishes_the_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_research_query(
        monkeypatch, globals(), question_kind="live_quote", symbols=["AAPL"]
    )
    clock = ScriptedClock()
    client, provider = scripted_client(clock, [status(500), answer()])
    monkeypatch.setattr(grounded, "_client", lambda: client)

    result = run_research_turn(QUESTION)

    assert result is not None
    assert "recovery" not in result.stage_patch
    assert result.stage_patch["assistant_response"].startswith("Apple closed")
    assert clock.waits == [BACKOFF]
    assert request_body(provider.requests[0]) == request_body(provider.requests[1])


class _LedgerGateway(SupabaseGateway):
    def __init__(self) -> None:
        super().__init__(client=_RecordingSupabaseClient())
        self.entries: list[dict[str, Any]] = []

    def create_cost_ledger_entry(self, *, entry: dict[str, Any]) -> dict[str, Any]:
        row = super().create_cost_ledger_entry(entry=entry)
        self.entries.append(row)
        return row


@pytest.mark.parametrize("failure", FAILURES, ids=lambda failure: failure.name)
def test_the_ledger_counts_an_outage_by_its_code_and_status(
    monkeypatch: pytest.MonkeyPatch, failure: Failure
) -> None:
    ledger = _LedgerGateway()
    monkeypatch.setattr(api_state, "supabase_gateway", ledger)
    _wire(monkeypatch, failure)

    result = run_research_turn(QUESTION)
    assert result is not None
    record_research_turn_evidence(
        research=result.stage_patch["research"],
        user_id="u1",
        conversation_id="c1",
        message_id="m1",
        request_id="r1",
    )

    metadata = ledger.entries[-1]["usage_metadata"]
    assert metadata["degraded_code"] == failure.degraded["code"]
    assert metadata.get("degraded_status") == failure.status


# --- The chat route: the same settlement and retry discovery uses -----------


def _final_payload(stream: str) -> dict[str, Any]:
    events = [
        json.loads(line.removeprefix("data: "))
        for line in stream.splitlines()
        if line.startswith("data: {")
    ]
    finals = [event for event in events if event.get("type") == "final"]
    assert len(finals) == 1
    return finals[0]["payload"]


def _ask(api, conversation_id: str) -> dict[str, Any]:
    response = api.post(
        "/api/v1/chat/stream",
        json={"conversation_id": conversation_id, "message": QUESTION, "language": "en"},
    )
    assert response.status_code == 200
    return _final_payload(response.text)


def _messages(api, conversation_id: str) -> list[dict[str, Any]]:
    return api.get(f"/api/v1/conversations/{conversation_id}/messages").json()["items"]


# --- A registered call: its recovery speaks for its turn only when it is alone -


TRANSIENT_RECOVERY = {"code": "research_lookup_failed", "retryable": True}

