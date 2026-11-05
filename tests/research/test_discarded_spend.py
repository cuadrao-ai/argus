"""Spend locks (#569): a turn records what it paid, whatever it published.

The rail can pay a provider and publish none of what came back: a claim that
retrieved no public publisher, a retry the turn preferred not to keep, an
answer that could not be read. Every one of those used to reach the cost
ledger as zero. These tests hold the line in both directions, that a discarded
response is still billed and that a reader is never shown what it cost.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from argus.api import state as api_state
from argus.api.chat import research_evidence as evidence
from argus.domain.research.contracts import ResearchUsage, combined_research_usage
from argus.domain.supabase_gateway import SupabaseGateway

from tests.research.conftest import (
    PROVIDER_PAGE,
    agent_response,
    request_body,
    run_research_turn,
    set_research_query,
    typed_answer_text,
    wire_grounded_client,
)
from tests.test_supabase_gateway import _RecordingSupabaseClient

# One response's recorded invoice, the fixture every canned document bills at.
ONE_RESPONSE_USD = 0.0487
# The fake clock advances this much across each provider call.
CALL_LATENCY_MS = 250


class _LedgerGateway(SupabaseGateway):
    def __init__(self) -> None:
        super().__init__(client=_RecordingSupabaseClient())
        self.entries: list[dict[str, Any]] = []

    def create_cost_ledger_entry(self, *, entry: dict[str, Any]) -> dict[str, Any]:
        row = super().create_cost_ledger_entry(entry=entry)
        self.entries.append(row)
        return row


class _SteppingClock:
    """Stands in for the provider module's clock so a turn's latency is the
    sum of its calls rather than however fast the canned transport answered."""

    def __init__(self, step_seconds: float) -> None:
        self._step = step_seconds
        self._now = 0.0

    def monotonic(self) -> float:
        now = self._now
        self._now += self._step
        return now


@pytest.fixture
def stepping_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    from argus.domain.research import perplexity_agent

    # run_research reads the clock once before and once after each call.
    monkeypatch.setattr(perplexity_agent, "time", _SteppingClock(CALL_LATENCY_MS / 1000))


@pytest.fixture
def ledger(monkeypatch: pytest.MonkeyPatch) -> _LedgerGateway:
    gateway = _LedgerGateway()
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)
    return gateway


def _settle(result, ledger: _LedgerGateway) -> dict[str, Any]:
    """Run the turn's sidecar through the same settlement the API calls."""
    reader_bytes = json.dumps(result.stage_patch, sort_keys=True).encode()
    evidence.settle_research_turn(
        dict(result.stage_patch),
        user_id="user-569",
        conversation_id="c-569",
        message_id="m-569",
        request_id="r-569",
    )
    assert len(ledger.entries) == 1
    assert ledger.entries[0]["status"] is None
    assert ledger.entries[0]["metadata"] == {
        "research_ledger_contract": "argus_research_ledger/v2"
    }
    assert json.dumps(result.stage_patch, sort_keys=True).encode() == reader_bytes
    return ledger.entries[0]


def _provider_only_document() -> dict[str, Any]:
    """A company answer whose only citation is the provider's own page, so no
    public publisher survives selection."""
    return agent_response(
        text="Advertising drove Netflix's growth.",
        tickers=["NFLX"],
        sources=[PROVIDER_PAGE],
    )


def test_a_missing_public_sources_turn_bills_both_calls_it_paid_for(
    monkeypatch, ledger, stepping_clock
) -> None:
    """#569: the claim is not publishable and the packet is thrown away, but
    the two provider calls behind it were real."""
    set_research_query(
        monkeypatch,
        globals(),
        question_kind="company_lookup",
        symbols=["NFLX"],
        requires_publisher_sources=True,
    )
    transport = wire_grounded_client(
        monkeypatch, [_provider_only_document(), _provider_only_document()]
    )

    result = run_research_turn("What were Netflix's main growth drivers?")

    assert result is not None
    assert len(transport.requests) == 2, "the publisher-only retry ran"
    sidecar = result.stage_patch["research"]
    assert sidecar["degraded"] == {"code": "research_unavailable_missing_public_sources"}
    assert sidecar["usage"]["invocations"] == 2
    assert sidecar["usage"]["cost_usd"] == pytest.approx(2 * ONE_RESPONSE_USD)
    assert sidecar["usage"]["latency_ms"] == 2 * CALL_LATENCY_MS
    assert sidecar["usage"]["cache_status"] == "miss"

    entry = _settle(result, ledger)
    assert entry["billable_quantity"] == 1
    assert entry["cost_amount"] == pytest.approx(2 * ONE_RESPONSE_USD)
    assert entry["cost_source"] == "provider_reported"
    assert entry["latency_ms"] == 2 * CALL_LATENCY_MS
    assert entry["usage_metadata"]["invocations"] == 2
    assert (
        entry["usage_metadata"]["degraded_code"]
        == "research_unavailable_missing_public_sources"
    )


def test_the_missing_public_sources_reader_sees_the_same_honest_turn(
    monkeypatch,
) -> None:
    """Recording the cost is not publishing the packet: the note, the empty
    source list and the absent rows are exactly what they were."""
    set_research_query(
        monkeypatch,
        globals(),
        question_kind="company_lookup",
        symbols=["NFLX"],
        requires_publisher_sources=True,
    )
    wire_grounded_client(
        monkeypatch, [_provider_only_document(), _provider_only_document()]
    )

    result = run_research_turn("What were Netflix's main growth drivers?")

    assert result is not None
    answer = result.stage_patch["assistant_response"]
    assert answer.startswith(
        "I couldn't verify that explanation with a public source, so I won't "
        "present it as fact."
    )
    assert "Advertising drove" not in answer
    sidecar = result.stage_patch["research"]
    assert sidecar["sources"] == [] and sidecar["rows"] == []
    assert sidecar["peers"] == []
    # The turn is classed and shaped exactly as the fabricated packet was.
    assert sidecar["shape"] == "balanced"
    assert sidecar["capability_class"] == "balanced_lookup"
    assert sidecar["anchor_symbols"] == ["NFLX"]
    assert result.decision.reason_codes == ["research_answer_balanced_lookup"]
    # Nothing the reader is handed names the invoice.
    for key in ("cost", "usd", "$0.0", "latency"):
        assert key not in answer.lower()


def test_a_retry_the_turn_kept_still_bills_the_answer_it_replaced(
    monkeypatch, ledger, stepping_clock
) -> None:
    """The publisher retry succeeds and its packet is published; the first
    call it replaced was paid for all the same."""
    set_research_query(
        monkeypatch,
        globals(),
        question_kind="company_lookup",
        symbols=["NFLX"],
        requires_publisher_sources=True,
    )
    published = agent_response(
        text="Netflix grew on membership and pricing.",
        tickers=["NFLX"],
        sources=["https://ir.netflix.net/financials/quarterly-earnings/"],
    )
    transport = wire_grounded_client(monkeypatch, [_provider_only_document(), published])

    result = run_research_turn("What were Netflix's main growth drivers?")

    assert result is not None
    assert len(transport.requests) == 2
    sidecar = result.stage_patch["research"]
    assert "degraded" not in sidecar
    assert sidecar["usage"]["invocations"] == 2
    assert sidecar["usage"]["cost_usd"] == pytest.approx(2 * ONE_RESPONSE_USD)
    assert sidecar["usage"]["latency_ms"] == 2 * CALL_LATENCY_MS
    assert _settle(result, ledger)["cost_amount"] == pytest.approx(2 * ONE_RESPONSE_USD)


def test_a_retry_the_turn_threw_away_is_billed_too(
    monkeypatch, ledger, stepping_clock
) -> None:
    """A survey retry that came back no better is discarded; its invoice is
    not."""
    set_research_query(monkeypatch, globals(), question_kind="market_pulse", symbols=[])
    # Typed, retrieved, and no row at all: the shape that earns the one
    # survey retry.
    figureless = agent_response(text=typed_answer_text("Markets were mixed today.", []))
    transport = wire_grounded_client(monkeypatch, [figureless, figureless])

    result = run_research_turn("Anything moving today?")

    assert result is not None
    assert len(transport.requests) == 2, "the survey retry ran"
    usage = result.stage_patch["research"]["usage"]
    assert usage["cost_usd"] == pytest.approx(2 * ONE_RESPONSE_USD)
    assert usage["latency_ms"] == 2 * CALL_LATENCY_MS
    assert _settle(result, ledger)["cost_amount"] == pytest.approx(2 * ONE_RESPONSE_USD)


def test_an_answer_that_could_not_be_read_still_bills_its_invoice(
    monkeypatch, ledger, stepping_clock
) -> None:
    """A response billed and then rejected for an unreadable answer leaves no
    packet, so the honest note carries the spend instead."""
    set_research_query(
        monkeypatch, globals(), question_kind="live_quote", symbols=["AAPL"]
    )
    empty = agent_response(text="   ", invocations=1)
    wire_grounded_client(monkeypatch, [empty])

    result = run_research_turn("What is AAPL trading at?")

    assert result is not None
    sidecar = result.stage_patch["research"]
    assert sidecar["degraded"] == {"code": "research_unavailable_empty_answer"}
    assert sidecar["usage"]["cost_usd"] == pytest.approx(ONE_RESPONSE_USD)
    assert sidecar["usage"]["latency_ms"] == CALL_LATENCY_MS
    assert sidecar["usage"]["cache_status"] == "miss"

    entry = _settle(result, ledger)
    assert entry["billable_quantity"] == 1
    assert entry["cost_amount"] == pytest.approx(ONE_RESPONSE_USD)


def test_a_served_response_with_a_broken_envelope_still_bills_its_invoice(
    monkeypatch, ledger, stepping_clock
) -> None:
    """Codex round 1: the invoice is read before the output envelope is
    validated, so a billed response Argus cannot even begin to parse is not
    mistaken for a call that never happened."""
    set_research_query(
        monkeypatch, globals(), question_kind="live_quote", symbols=["AAPL"]
    )
    envelope_broken = agent_response()
    envelope_broken["output"] = "not a list"
    wire_grounded_client(monkeypatch, [envelope_broken])

    result = run_research_turn("What is AAPL trading at?")

    assert result is not None
    sidecar = result.stage_patch["research"]
    assert sidecar["degraded"] == {"code": "research_unavailable_malformed_response"}
    assert sidecar["usage"]["cost_usd"] == pytest.approx(ONE_RESPONSE_USD)
    assert sidecar["usage"]["cache_status"] == "miss"
    assert _settle(result, ledger)["cost_amount"] == pytest.approx(ONE_RESPONSE_USD)


def test_a_billed_response_the_parser_chokes_on_degrades_and_bills(
    monkeypatch, ledger, stepping_clock
) -> None:
    """Codex round 2: a nested envelope of the wrong shape used to raise a bare
    TypeError out of the parser, which crashed the turn and took the invoice
    with it. Any way the document fails to parse is a malformed response that
    was paid for."""
    set_research_query(
        monkeypatch, globals(), question_kind="live_quote", symbols=["AAPL"]
    )
    nested_broken = agent_response()
    nested_broken["output"] = [{"type": "message", "content": 1}]
    wire_grounded_client(monkeypatch, [nested_broken])

    result = run_research_turn("What is AAPL trading at?")

    assert result is not None, "the turn answers honestly instead of raising"
    sidecar = result.stage_patch["research"]
    assert sidecar["degraded"] == {"code": "research_unavailable_malformed_response"}
    assert sidecar["usage"]["cost_usd"] == pytest.approx(ONE_RESPONSE_USD)
    assert _settle(result, ledger)["cost_amount"] == pytest.approx(ONE_RESPONSE_USD)


def test_a_parser_failure_tells_the_operator_and_not_the_reader() -> None:
    """Codex round 3: the wide catch also covers an Argus-side regression, so
    the frames must reach the log. They must not reach the error'"'"'s detail,
    which a failed research job serves to the reader as `failure_detail`."""
    from argus.domain.research.contracts import ResearchUnavailableError
    from argus.domain.research.perplexity_agent import _packet_from_response

    nested_broken = agent_response()
    nested_broken["output"] = [{"type": "message", "content": 1}]

    with pytest.raises(ResearchUnavailableError) as raised:
        _packet_from_response(nested_broken, latency_ms=10, on_unpriced=lambda _s: None)

    error = raised.value
    assert error.reason == "malformed_response"
    assert error.usage is not None and error.usage.cost_usd == pytest.approx(
        ONE_RESPONSE_USD
    )
    assert error.detail == "response shape not parseable"
    for leaked in ("TypeError", "perplexity_agent", ".py", "Traceback", "/"):
        assert leaked not in error.detail


def test_the_operator_log_names_the_line_that_failed() -> None:
    """Codex round 4: the log has to be able to locate a parser regression,
    so prove its safe origin reaches a sink without attaching exception text."""
    from argus.domain.research.contracts import ResearchUnavailableError
    from argus.domain.research.perplexity_agent import _packet_from_response
    from loguru import logger

    nested_broken = agent_response()
    nested_broken["output"] = [{"type": "message", "content": 1}]

    records: list[str] = []
    sink = logger.add(lambda message: records.append(str(message)), level="WARNING")
    try:
        with pytest.raises(ResearchUnavailableError):
            _packet_from_response(
                nested_broken, latency_ms=10, on_unpriced=lambda _s: None
            )
    finally:
        logger.remove(sink)

    logged = "\n".join(records)
    assert "Research response could not be parsed" in logged
    assert "perplexity_agent.py" in logged, "the frame that failed is named"
    assert "TypeError" in logged


def test_a_response_with_no_invoice_at_all_bills_nothing(
    monkeypatch, ledger, stepping_clock
) -> None:
    """A body that is not an object never reached pricing, so there is no
    invoice to claim and the turn must not invent one."""
    import httpx
    from argus.agent_runtime import research_grounded as grounded
    from argus.domain.research.perplexity_agent import PerplexityAgentClient

    set_research_query(
        monkeypatch, globals(), question_kind="live_quote", symbols=["AAPL"]
    )

    class _NonObjectBody(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=["not", "an", "object"])

    monkeypatch.setattr(
        grounded,
        "_client",
        lambda: PerplexityAgentClient("k", transport=_NonObjectBody()),
    )

    result = run_research_turn("What is AAPL trading at?")

    assert result is not None
    assert result.stage_patch["research"]["usage"] == {
        "invocations": 0,
        "latency_ms": 0,
        "cost_usd": None,
        "cache_status": "bypass",
    }
    assert _settle(result, ledger)["billable_quantity"] == 0


def test_a_turn_that_never_reached_the_provider_bills_nothing(monkeypatch, ledger):
    """The unconfigured path calls no provider, so it bypasses the meter and
    the ledger rather than claiming a zero-cost request."""
    from argus.agent_runtime import research_grounded as grounded

    set_research_query(
        monkeypatch, globals(), question_kind="live_quote", symbols=["AAPL"]
    )
    monkeypatch.setattr(grounded, "_client", lambda: None)

    result = run_research_turn("What is AAPL trading at?")

    assert result is not None
    sidecar = result.stage_patch["research"]
    assert sidecar["degraded"] == {"code": "research_unavailable_not_configured"}
    assert sidecar["usage"] == {
        "invocations": 0,
        "latency_ms": 0,
        "cost_usd": None,
        "cache_status": "bypass",
    }
    assert _settle(result, ledger)["billable_quantity"] == 0


def test_a_repeated_freeform_answer_reports_and_bills_its_new_call(
    monkeypatch, ledger, stepping_clock
) -> None:
    """Each freeform turn reports and bills the response it actually retrieved."""
    set_research_query(
        monkeypatch,
        globals(),
        question_kind="company_lookup",
        symbols=["NFLX"],
        requires_publisher_sources=True,
    )
    transport = wire_grounded_client(
        monkeypatch,
        [
            agent_response(
                text="Netflix grew on membership and pricing.",
                tickers=["NFLX"],
                sources=["https://ir.netflix.net/financials/quarterly-earnings/"],
            )
        ]
        * 2,
    )

    first = run_research_turn("What were Netflix's main growth drivers?")
    second = run_research_turn("What were Netflix's main growth drivers?")

    assert first is not None and second is not None
    assert len(transport.requests) == 2, "the second turn retrieves its own answer"
    served = second.stage_patch["research"]["usage"]
    assert served["cache_status"] == "miss"
    assert served["cost_usd"] == pytest.approx(ONE_RESPONSE_USD)
    assert served["invocations"] == first.stage_patch["research"]["usage"]["invocations"]
    # Both the sidecar and ledger describe this turn's new retrieval.
    entry = _settle(second, ledger)
    assert entry["billable_quantity"] == 1
    assert entry["cost_amount"] == pytest.approx(ONE_RESPONSE_USD)
    assert entry["cost_source"] == "provider_reported"
    assert entry["latency_ms"] == CALL_LATENCY_MS


def test_repeated_answer_usage_excludes_the_previous_turn_retry(
    monkeypatch, stepping_clock
) -> None:
    """A later question owns fresh usage, without inheriting the earlier retry."""
    set_research_query(
        monkeypatch,
        globals(),
        question_kind="company_lookup",
        symbols=["NFLX"],
        requires_publisher_sources=True,
    )
    published = agent_response(
        text="Netflix grew on membership and pricing.",
        tickers=["NFLX"],
        sources=["https://ir.netflix.net/financials/quarterly-earnings/"],
    )
    transport = wire_grounded_client(
        monkeypatch, [_provider_only_document(), published, published]
    )

    paid = run_research_turn("What were Netflix's main growth drivers?")
    served = run_research_turn("What were Netflix's main growth drivers?")

    assert paid is not None and served is not None
    assert len(transport.requests) == 3, "the second turn makes one fresh call"
    assert paid.stage_patch["research"]["usage"]["cost_usd"] == pytest.approx(
        2 * ONE_RESPONSE_USD
    )
    assert served.stage_patch["research"]["usage"] == {
        "invocations": 1,
        "latency_ms": CALL_LATENCY_MS,
        "cost_usd": pytest.approx(ONE_RESPONSE_USD),
        "cache_status": "miss",
    }


def test_the_publisher_retry_still_drops_the_provider_only_channel(
    monkeypatch, stepping_clock
) -> None:
    """The accumulator sits on the call seam, so the retry it records is the
    same one the contract describes."""
    set_research_query(
        monkeypatch,
        globals(),
        question_kind="company_lookup",
        symbols=["NFLX"],
        requires_publisher_sources=True,
    )
    transport = wire_grounded_client(
        monkeypatch, [_provider_only_document(), _provider_only_document()]
    )

    run_research_turn("What were Netflix's main growth drivers?")

    assert "finance_search" not in [
        tool["type"] for tool in request_body(transport.requests[1])["tools"]
    ]


# --- the combine itself


def test_the_turn_total_adds_every_response_it_read() -> None:
    total = combined_research_usage(
        [
            ResearchUsage(
                invocations=1,
                web_search_invocations=2,
                model="a",
                latency_ms=100,
                cost_usd=0.01,
                input_tokens=10,
                output_tokens=5,
            ),
            ResearchUsage(
                invocations=3,
                web_search_invocations=1,
                model="b",
                latency_ms=250,
                cost_usd=0.02,
                input_tokens=20,
                output_tokens=7,
            ),
        ]
    )
    assert total.invocations == 4
    assert total.web_search_invocations == 3
    assert total.latency_ms == 350
    assert total.cost_usd == pytest.approx(0.03)
    assert total.input_tokens == 30 and total.output_tokens == 12


def test_a_total_an_invoice_did_not_establish_is_unknown_not_partial() -> None:
    """Half a total understates the spend as confidently as a wrong one."""
    total = combined_research_usage(
        [
            ResearchUsage(invocations=1, latency_ms=100, cost_usd=0.01),
            ResearchUsage(invocations=None, latency_ms=250, cost_usd=None),
        ]
    )
    assert total.invocations is None
    assert total.cost_usd is None
    # Latency is Argus's own measurement, so it is known whatever the invoice
    # did or did not say.
    assert total.latency_ms == 350


def test_one_response_is_reported_as_itself() -> None:
    only = ResearchUsage(invocations=1, model="a", latency_ms=100, cost_usd=0.01)
    assert combined_research_usage([only]) == only
    assert combined_research_usage([]) == ResearchUsage()


# --- the thorough path: a run that was billed and could not be published


class _FailingJobGateway(_LedgerGateway):
    """Only what the failure path touches: the row it fails and the ledger it
    writes."""

    def __init__(self) -> None:
        super().__init__()
        self.failed: list[tuple[str, str]] = []

    def mark_backtest_job_failed(
        self, *, user_id: str, job_id: str, failure_code: str, **_kw: Any
    ) -> None:
        self.failed.append((job_id, failure_code))


def test_a_thorough_run_billed_for_an_unreadable_answer_reaches_the_ledger(
    monkeypatch,
) -> None:
    """The job fails and its note carries no sidecar, so the spend is told to
    the ledger directly rather than disappearing with the answer."""
    from argus.api.chat import research_jobs

    gateway = _FailingJobGateway()
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)

    research_jobs._fail_job(
        job_id="job-569",
        user_id="u-569",
        detail="empty_answer: ",
        job_request={"capability_class": "thorough_research", "language": "en"},
        request_id="r-569",
        billed_reason="empty_answer",
        billed_usage=ResearchUsage(
            invocations=2, model="m", latency_ms=9100, cost_usd=0.42
        ),
    )

    assert gateway.failed == [("job-569", "research_failed")]
    assert len(gateway.entries) == 1
    entry = gateway.entries[0]
    assert entry["status"] is None
    assert entry["metadata"] == {"research_ledger_contract": "argus_research_ledger/v2"}
    assert entry["task"] == "thorough_research"
    assert entry["billable_quantity"] == 1
    assert entry["cost_amount"] == pytest.approx(0.42)
    assert entry["cost_source"] == "provider_reported"
    assert entry["latency_ms"] == 9100
    assert entry["usage_metadata"]["invocations"] == 2
    assert entry["usage_metadata"]["degraded_code"] == "research_unavailable_empty_answer"


def test_a_thorough_failure_that_was_never_billed_writes_no_ledger_row(
    monkeypatch,
) -> None:
    """A deadline, a transport loss or a poller crash paid nothing, and an
    unbilled failure must not read as a request."""
    from argus.api.chat import research_jobs

    gateway = _FailingJobGateway()
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)

    research_jobs._fail_job(
        job_id="job-570",
        user_id="u-569",
        detail="background deadline exceeded",
        job_request={"capability_class": "thorough_research", "language": "en"},
    )

    assert gateway.failed == [("job-570", "research_failed")]
    assert gateway.entries == []


def test_an_unreadable_completed_run_carries_its_invoice_off_the_poll() -> None:
    """The seam between the two: poll_background turns the rejection into a
    terminal failure, and the invoice rides along."""
    from argus.domain.research.perplexity_agent import PerplexityAgentClient

    from tests.research.conftest import RecordingTransport

    document = agent_response(text="   ")
    document["status"] = "completed"
    client = PerplexityAgentClient("k", transport=RecordingTransport([document]))

    poll = client.poll_background("resp_bg1")

    assert poll.status == "failed"
    assert poll.failure_reason == "empty_answer"
    assert poll.usage is not None
    assert poll.usage.cost_usd == pytest.approx(ONE_RESPONSE_USD)
