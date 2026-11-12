"""Perplexity Agent client parsing locks: deterministic, sanitized, bounded."""

from __future__ import annotations

import pytest
from argus.domain.research.config import RESEARCH_CONFIG_SPECS
from argus.domain.research.contracts import ResearchUnavailableError
from argus.domain.research.perplexity_agent import (
    _TOOL_RESULT_READERS,
    PerplexityAgentClient,
    _sanitize_answer,
)

from tests.research.conftest import (
    RecordingTransport,
    agent_response,
    recorded_agent_response,
    request_body,
)


def _client(documents) -> tuple[PerplexityAgentClient, RecordingTransport]:
    transport = RecordingTransport(documents)
    return PerplexityAgentClient("test-key", transport=transport), transport


def test_run_research_builds_documented_request_and_parses_packet() -> None:
    client, transport = _client(
        [
            agent_response(
                lookup_rows=[
                    ("The Walt Disney Company", "DIS", "The Walt Disney Company"),
                    ("EUR/USD exchange rate", "NOT_FOUND", ""),
                    ("header", "TICKER", "name"),
                ],
                sources=[
                    "https://www.perplexity.ai/finance/AAPL",
                    "https://www.sec.gov/a",
                ],
            )
        ]
    )
    packet = client.run_research("What is Apple at?", RESEARCH_CONFIG_SPECS["fast"])

    body = request_body(transport.requests[0])
    assert body["models"] == ["openai/gpt-5.6-sol", "anthropic/claude-opus-4-7"]
    assert "model" not in body, "the fallback chain replaces the single model"
    assert body["tools"] == [{"type": "finance_search"}]
    assert body["max_steps"] == RESEARCH_CONFIG_SPECS["fast"].max_steps
    assert body["max_output_tokens"] == 1024
    assert packet.usage.invocations == 1
    assert packet.usage.finance_search_invocations == 1
    assert packet.usage.web_search_invocations == 0
    assert packet.usage.fetch_url_invocations == 0
    assert packet.usage.input_tokens == 15_950
    assert packet.usage.output_tokens == 298
    assert packet.usage.model == "openai/gpt-5.6-sol"
    assert packet.usage.cost_usd == pytest.approx(0.0487)
    # Provider hosts are scrubbed; public sources survive as typed citations.
    assert [source.url for source in packet.sources] == ["https://www.sec.gov/a"]
    # NOT_FOUND and header rows never become candidates.
    assert [pair.symbol for pair in packet.name_pairs] == ["DIS"]


def test_usage_cost_uses_served_model_tokens_and_every_tool_count() -> None:
    client, transport = _client(
        [
            agent_response(
                model="anthropic/claude-opus-4-7",
                input_tokens=20_000,
                output_tokens=4_000,
                invocations=2,
                web_search_invocations=3,
                fetch_url_invocations=4,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
                # Synthetic bill for this explicit tool-count arithmetic case.
                cost_overrides={
                    "input_cost": 0.1,
                    "output_cost": 0.1,
                    "cache_creation_cost": 0,
                    "cache_read_cost": 0,
                    "tool_calls_cost": 0.0195,
                    "tool_calls_cost_details": {
                        "finance_search": 0.01,
                        "search_web": 0.0075,
                        "fetch_url": 0.002,
                    },
                    "total_cost": 0.2195,
                },
            )
        ]
    )

    packet = client.run_research("compare", RESEARCH_CONFIG_SPECS["fast"])

    assert request_body(transport.requests[0])["models"][0] == "openai/gpt-5.6-sol"
    # The invoice names the model that served; a fallback is priced as itself.
    assert packet.usage.model == "anthropic/claude-opus-4-7"
    assert packet.usage.input_tokens == 20_000
    assert packet.usage.output_tokens == 4_000
    assert packet.usage.finance_search_invocations == 2
    assert packet.usage.web_search_invocations == 3
    assert packet.usage.fetch_url_invocations == 4
    assert packet.usage.invocations == 2
    # 0.2 model tokens + 2*0.005 + 3*0.0025 + 4*0.0005 tool invocations.
    assert packet.usage.cost_usd == pytest.approx(0.2195)


def test_usage_cost_matches_the_committed_live_cached_response() -> None:
    client, _ = _client([recorded_agent_response()])

    packet = client.run_research("quote Apple", RESEARCH_CONFIG_SPECS["fast"])

    assert packet.usage.cost_usd == pytest.approx(0.0487)
    assert packet.usage.cache_creation_input_tokens == 6_754
    assert packet.usage.cache_read_input_tokens == 9_115


def test_aggregated_multistep_tokens_do_not_invent_a_long_context_charge() -> None:
    client, _ = _client(
        [
            agent_response(
                input_tokens=300_000,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
                output_tokens=1_000,
                invocations=0,
                cost_overrides={
                    "input_cost": 1.2,
                    "output_cost": 0.02,
                    "cache_creation_cost": 0.0,
                    "cache_read_cost": 0.0,
                    "tool_calls_cost": 0.0,
                    "tool_calls_cost_details": {},
                    "total_cost": 1.22,
                },
            )
        ]
    )

    packet = client.run_research("multi-step", RESEARCH_CONFIG_SPECS["fast"])

    assert packet.usage.cost_usd == pytest.approx(1.22)


@pytest.mark.parametrize(
    ("cache_creation_input_tokens", "cache_read_input_tokens", "cost_overrides"),
    [
        pytest.param(
            0,
            0,
            {
                "input_cost": 1.63201,
                "output_cost": 0.0,
                "cache_creation_cost": 0.0,
                "cache_read_cost": 0.0,
                "total_cost": 1.63201,
            },
            id="uncached-input",
        ),
        pytest.param(
            272_001,
            0,
            {
                "input_cost": 0.0,
                "output_cost": 0.0,
                "cache_creation_cost": 2.04001,
                "cache_read_cost": 0.0,
                "total_cost": 2.04001,
            },
            id="cache-creation",
        ),
        pytest.param(
            0,
            272_001,
            {
                "input_cost": 0.0,
                "output_cost": 0.0,
                "cache_creation_cost": 0.0,
                "cache_read_cost": 0.16320,
                "total_cost": 0.16320,
            },
            id="cache-read",
        ),
    ],
)
def test_aggregated_multistep_tokens_reject_an_impossible_tier_blend(
    cache_creation_input_tokens: int,
    cache_read_input_tokens: int,
    cost_overrides: dict[str, float],
) -> None:
    client, _ = _client(
        [
            agent_response(
                input_tokens=272_001,
                output_tokens=0,
                invocations=0,
                cache_creation_input_tokens=cache_creation_input_tokens,
                cache_read_input_tokens=cache_read_input_tokens,
                cost_overrides={
                    "tool_calls_cost": 0.0,
                    "tool_calls_cost_details": {},
                    **cost_overrides,
                },
            )
        ]
    )

    packet = client.run_research("impossible blend", RESEARCH_CONFIG_SPECS["fast"])
    assert packet.answer_markdown
    assert packet.usage.cost_usd is None


def test_aggregated_multistep_tokens_accept_a_feasible_tier_blend() -> None:
    client, _ = _client(
        [
            agent_response(
                input_tokens=273_001,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
                output_tokens=100,
                invocations=0,
                cost_overrides={
                    # One 272,001-token long-context call plus a 1,000-token
                    # short-context call can produce this aggregate component.
                    "input_cost": 2.72501,
                    "output_cost": 0.0045,
                    "cache_creation_cost": 0.0,
                    "cache_read_cost": 0.0,
                    "tool_calls_cost": 0.0,
                    "tool_calls_cost_details": {},
                    "total_cost": 2.72951,
                },
            )
        ]
    )

    packet = client.run_research("feasible blend", RESEARCH_CONFIG_SPECS["fast"])

    assert packet.usage.cost_usd == pytest.approx(2.72951)


@pytest.mark.parametrize(
    ("input_cost", "output_cost", "total_cost"),
    [
        pytest.param(1.2, 0.045, 1.245, id="short-input-long-output"),
        pytest.param(3.0, 0.02, 3.02, id="long-input-short-output"),
    ],
)
def test_aggregated_multistep_tokens_reject_inconsistent_tiers(
    input_cost: float, output_cost: float, total_cost: float
) -> None:
    client, _ = _client(
        [
            agent_response(
                input_tokens=300_000,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
                output_tokens=1_000,
                invocations=0,
                cost_overrides={
                    "input_cost": input_cost,
                    "output_cost": output_cost,
                    "cache_creation_cost": 0.0,
                    "cache_read_cost": 0.0,
                    "tool_calls_cost": 0.0,
                    "tool_calls_cost_details": {},
                    "total_cost": total_cost,
                },
            )
        ]
    )

    packet = client.run_research("inconsistent tiers", RESEARCH_CONFIG_SPECS["fast"])
    assert packet.answer_markdown
    assert packet.usage.cost_usd is None


def test_provider_total_must_match_its_cost_components() -> None:
    client, _ = _client([agent_response(cost_overrides={"total_cost": 9.99})])

    packet = client.run_research("q", RESEARCH_CONFIG_SPECS["fast"])
    assert packet.answer_markdown
    assert packet.usage.cost_usd is None


def test_provider_tool_cost_must_match_actual_invocation_counts() -> None:
    client, _ = _client(
        [
            agent_response(
                cost_overrides={
                    "tool_calls_cost": 0.0,
                    "tool_calls_cost_details": {"finance_search": 0.0},
                    "total_cost": 0.02,
                }
            )
        ]
    )

    packet = client.run_research("q", RESEARCH_CONFIG_SPECS["fast"])
    assert packet.answer_markdown
    assert packet.usage.cost_usd is None


def test_unknown_served_model_rate_is_unpriced() -> None:
    client, _ = _client([agent_response(model="vendor/new-model")])

    packet = client.run_research("q", RESEARCH_CONFIG_SPECS["fast"])
    assert packet.answer_markdown
    assert packet.usage.model == "vendor/new-model"
    assert packet.usage.cost_usd is None


def test_missing_required_token_usage_is_unpriced() -> None:
    response = agent_response()
    del response["usage"]["input_tokens"]
    client, _ = _client([response])

    packet = client.run_research("q", RESEARCH_CONFIG_SPECS["fast"])
    assert packet.answer_markdown
    assert packet.usage.cost_usd is None


@pytest.mark.parametrize(
    ("input_tokens", "input_cost", "output_cost", "expected_cost_usd"),
    [
        (272_000, 1.088, 0.02, 1.108),
        (272_001, 2.72001, 0.045, 2.76501),
    ],
)
def test_gpt_5_6_sol_uses_the_documented_long_context_rate(
    input_tokens: int, input_cost: float, output_cost: float, expected_cost_usd: float
) -> None:
    client, _ = _client(
        [
            agent_response(
                input_tokens=input_tokens,
                output_tokens=1_000,
                invocations=0,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
                cost_overrides={
                    "input_cost": input_cost,
                    "output_cost": output_cost,
                    "cache_creation_cost": 0.0,
                    "cache_read_cost": 0.0,
                    "tool_calls_cost": 0.0,
                    "tool_calls_cost_details": {},
                    "total_cost": expected_cost_usd,
                },
            )
        ]
    )

    packet = client.run_research("q", RESEARCH_CONFIG_SPECS["fast"])

    assert packet.usage.cost_usd == pytest.approx(expected_cost_usd)


def test_balanced_spec_sends_reasoning_and_all_three_tools() -> None:
    client, transport = _client([agent_response()])
    client.run_research("history", RESEARCH_CONFIG_SPECS["balanced"])
    body = request_body(transport.requests[0])
    assert body["reasoning"] == {"effort": "low"}
    assert body["tools"] == [
        {"type": "web_search", "search_context_size": "medium"},
        {"type": "finance_search"},
        {"type": "fetch_url"},
    ]


def test_empty_answer_raises_unavailable() -> None:
    client, _ = _client([agent_response(text="  ")])
    with pytest.raises(ResearchUnavailableError) as excinfo:
        client.run_research("q", RESEARCH_CONFIG_SPECS["fast"])
    assert excinfo.value.reason == "empty_answer"


def test_auth_errors_map_to_not_configured() -> None:
    transport = RecordingTransport([])
    transport.documents = []

    class Denied(RecordingTransport):
        def handle_request(self, request):  # type: ignore[override]
            return __import__("httpx").Response(401, json={})

    client = PerplexityAgentClient("k", transport=Denied([]))
    with pytest.raises(ResearchUnavailableError) as excinfo:
        client.run_research("q", RESEARCH_CONFIG_SPECS["fast"])
    assert excinfo.value.reason == "not_configured"


def test_missing_key_never_sends_a_request() -> None:
    transport = RecordingTransport([agent_response()])
    client = PerplexityAgentClient("   ", transport=transport)
    with pytest.raises(ResearchUnavailableError) as excinfo:
        client.run_research("q", RESEARCH_CONFIG_SPECS["fast"])
    assert excinfo.value.reason == "not_configured"
    assert transport.requests == []


def test_background_submit_and_poll_lifecycle() -> None:
    completed = agent_response(text="Deep answer", status="completed")
    client, transport = _client(
        [
            {"id": "resp_bg1", "status": "queued"},
            {"id": "resp_bg1", "status": "in_progress"},
            completed,
        ]
    )
    # The submit consumes the first canned document; the polls consume the rest.
    spec = RESEARCH_CONFIG_SPECS["thorough"]
    background_id = client.submit_background("compare", spec)
    assert background_id == "resp_bg1"
    assert request_body(transport.requests[0])["background"] is True

    first = client.poll_background(background_id)
    assert first.status in ("queued", "in_progress") and not first.terminal
    final = client.poll_background(background_id)
    assert final.terminal and final.status == "completed"
    assert final.packet is not None and final.packet.answer_markdown == "Deep answer"


def test_failed_background_poll_reports_detail() -> None:
    client, _ = _client([{"id": "x", "status": "failed", "error": {"message": "boom"}}])
    poll = client.poll_background("x")
    assert poll.terminal and poll.status == "failed"
    assert poll.packet is None
    assert "boom" in (poll.failure_detail or "")


def test_sanitizer_strips_provider_links_and_typographic_dashes() -> None:
    text = (
        "Revenue grew from $245B—a 14.9% rise. Window 2019–2024. "
        "[Source](https://www.perplexity.ai/finance/MSFT) and "
        "[SEC filing](https://www.sec.gov/f). "
        "| FY2022 | $31.6B | — |"
    )
    cleaned = _sanitize_answer(text)
    assert "perplexity.ai" not in cleaned
    assert "—" not in cleaned and "–" not in cleaned
    assert "2019-2024" in cleaned
    assert "$245B, a 14.9% rise" in cleaned
    # A lone dash cell stays an empty-value marker, not punctuation.
    assert "| - |" in cleaned
    assert "[SEC filing](https://www.sec.gov/f)" in cleaned


@pytest.mark.parametrize(
    "malformation", ["missing_usage", "usage_not_an_object", "malformed_tool_count"]
)
def test_tool_output_is_the_retrieval_record_when_the_invoice_is_lost(
    malformation: str,
) -> None:
    """Recorded responses carry one finance_results item per finance call.
    That output survives a lost invoice, and the counts the invoice would
    have established are unknown, not zero."""
    response = agent_response()
    if malformation == "missing_usage":
        del response["usage"]
    elif malformation == "usage_not_an_object":
        response["usage"] = "unavailable"
    else:
        response["usage"]["tool_calls_details"] = {
            "finance_search": {"invocation": "one"}
        }
    client, _ = _client([response])

    packet = client.run_research("q", RESEARCH_CONFIG_SPECS["fast"])

    assert packet.tool_results == ("finance_results",)
    assert packet.usage.invocations is None
    assert packet.usage.finance_search_invocations is None
    assert packet.usage.web_search_invocations is None
    assert packet.usage.fetch_url_invocations is None
    assert packet.usage.cost_usd is None


def test_a_response_that_ran_no_tool_reports_a_confirmed_zero() -> None:
    """Recorded zero-tool responses omit tool_calls_details and bill no tool;
    that is an established zero, distinct from an unknown count."""
    client, _ = _client(
        [
            agent_response(
                invocations=0,
                # Synthetic bill: the recorded invoice minus its finance call.
                cost_overrides={
                    "tool_calls_cost": 0.0,
                    "tool_calls_cost_details": {},
                    "total_cost": 0.0437,
                },
            )
        ]
    )

    packet = client.run_research("q", RESEARCH_CONFIG_SPECS["fast"])

    assert packet.tool_results == ()
    assert packet.usage.invocations == 0
    assert packet.usage.finance_search_invocations == 0
    assert packet.usage.web_search_invocations == 0
    assert packet.usage.fetch_url_invocations == 0
    assert packet.usage.cost_usd == pytest.approx(0.0437)


def test_every_tool_result_item_is_kept_in_provider_order() -> None:
    response = agent_response(web_search_invocations=1)
    response["output"].insert(
        2,
        {
            "type": "search_results",
            "results": [{"url": "https://www.sec.gov/b", "title": "Filing"}],
        },
    )
    client, _ = _client([response])

    packet = client.run_research("q", RESEARCH_CONFIG_SPECS["balanced"])

    assert packet.tool_results == ("finance_results", "search_results")


@pytest.mark.parametrize("kind", sorted(_TOOL_RESULT_READERS))
def test_every_kind_the_parser_reads_is_retrieval_evidence_without_an_invoice(
    kind: str,
) -> None:
    """The invariant behind #541: reading a tool result is what records it,
    so a kind the parser learns to read can never be missing from the
    retrieval record. Parametrized over the parser's own table so a new
    reader is covered the moment it is registered."""
    response = agent_response(invocations=0)
    del response["usage"]
    response["output"].insert(1, {"type": kind})
    client, _ = _client([response])

    packet = client.run_research("q", RESEARCH_CONFIG_SPECS["fast"])

    assert packet.tool_results == (kind,)
    assert not packet.sources, "the bare item must prove retrieval on its own"
