"""The additive client path preserves caller drafts and the existing invoice owner."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Literal

import pytest
from argus.domain.research.config import RESEARCH_CONFIG_SPECS
from argus.domain.research.contracts import MAX_ANSWER_CHARS, ResearchUnavailableError
from argus.domain.research.perplexity_agent import (
    PerplexityAgentClient,
    StructuredAgentLimits,
)
from pydantic import BaseModel, ConfigDict

from tests.research.conftest import (
    RecordingTransport,
    agent_response,
    fetch_url_results_item,
    request_body,
    search_results_item,
)


class Figure(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    fact_key: str
    value: float | str


class Draft(BaseModel):
    """Caller-owned fixture for the generic structured response transport."""

    model_config = ConfigDict(extra="forbid", strict=True)
    language: Literal["en", "es-419"]
    text: str
    figures: list[Figure]


@pytest.fixture
def draft():
    return {
        "language": "es-419",
        "text": "El rendimiento fue 15.1%.",
        "figures": [
            {
                "fact_key": "portfolio.total_return",
                "value": 15.126,
            }
        ],
    }


def document(draft):
    return agent_response(text=json.dumps(draft), status="completed")


def run(document, *, spec=None, **limits):
    transport = RecordingTransport([document])
    client = PerplexityAgentClient("test-key", transport=transport)
    spec = spec or RESEARCH_CONFIG_SPECS["balanced"].model_copy(
        update={"tools": ("web_search", "fetch_url"), "language": "es"}
    )
    result = client.run_structured(
        "Explain this run",
        spec,
        schema_model=Draft,
        schema_name="readout_draft",
        instructions="Caller-owned readout instructions.",
        limits=StructuredAgentLimits(**limits) if limits else None,
    )
    return result, transport


def test_structured_call_uses_caller_schema_and_existing_request_options(draft):
    spec = RESEARCH_CONFIG_SPECS["balanced"].model_copy(
        update={
            "tools": ("web_search", "fetch_url"),
            "language": "es",
            "recency": "month",
            "source_domains": ("sec.gov",),
            "timeout_seconds": 17,
        }
    )
    result, transport = run(document(draft), spec=spec)
    body = request_body(transport.requests[0])
    assert body["models"] == list(spec.models)
    assert body["tools"] == [
        {
            "type": "web_search",
            "search_context_size": spec.search_context_size,
            "filters": {
                "search_recency_filter": "month",
                "search_domain_filter": ["sec.gov"],
            },
        },
        {"type": "fetch_url"},
    ]
    assert body["language_preference"] == "es"
    assert body["max_steps"] == spec.max_steps
    assert body["max_output_tokens"] == spec.max_output_tokens
    assert body["instructions"] == "Caller-owned readout instructions."
    assert body["response_format"]["json_schema"]["name"] == "readout_draft"
    schema = body["response_format"]["json_schema"]["schema"]
    assert schema["required"] == ["language", "text", "figures"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["figures"]["items"]["additionalProperties"] is False
    assert "$defs" not in schema and "$ref" not in json.dumps(schema)
    assert transport.requests[0].extensions["timeout"]["read"] == spec.timeout_seconds
    assert result.draft == draft
    assert result.usage.cost_usd == pytest.approx(0.0487)
    assert result.provider_response_id == "resp_test"


def test_structured_call_retains_complete_raw_text_without_research_cleanup(draft):
    draft["text"] = (
        "finance_search — retained [source](https://www.perplexity.ai/x) "
        + "a" * MAX_ANSWER_CHARS
    )
    result, _ = run(document(draft))
    assert result.draft == draft


def test_structured_call_collects_all_existing_source_channels(draft):
    response = document(draft)
    response["output"][:0] = [
        search_results_item(
            {"url": "https://www.sec.gov/a", "title": "Filing", "date": "2026-09-08"}
        ),
        fetch_url_results_item({"url": "https://example.com/b", "title": "Report"}),
    ]
    response["output"][-1]["content"][0]["annotations"] = [
        {
            "url": "https://example.com/c",
            "title": "Annotated source",
            "date": "2026-09-07",
        },
        {"url": "https://www.sec.gov/a"},
        {"url": "https://www.perplexity.ai/provider"},
    ]
    result, _ = run(response)
    assert [source.url for source in result.sources] == [
        "https://www.sec.gov/a",
        "https://example.com/b",
        "https://example.com/c",
    ]
    assert result.sources[0].source_date == "2026-09-08"
    assert result.tool_results == (
        "search_results",
        "fetch_url_results",
        "finance_results",
    )


@pytest.mark.parametrize(
    "status", ["incomplete", "failed", "cancelled", "in_progress", "queued"]
)
def test_unfinished_response_rejects_even_valid_draft_and_retains_invoice(draft, status):
    response = document(draft)
    response["status"] = status
    with pytest.raises(ResearchUnavailableError) as caught:
        run(response)
    assert caught.value.reason == "malformed_response"
    assert caught.value.usage.cost_usd == pytest.approx(0.0487)


@pytest.mark.parametrize(
    "defect",
    [
        "invalid_json",
        "plain_prose",
        "wrong_schema",
        "extra_field",
        "nested_extra",
        "wrong_type",
        "empty_output",
        "malformed_item",
        "malformed_content",
        "refusal",
        "incomplete_message",
        "incomplete_details",
    ],
)
def test_malformed_structured_output_fails_whole_with_usage(draft, defect):
    response = document(draft)
    message = response["output"][-1]
    if defect == "invalid_json":
        message["content"][0]["text"] = '{"language":'
    elif defect == "plain_prose":
        message["content"][0]["text"] = "A plain answer cannot carry the caller contract."
    elif defect == "wrong_schema":
        message["content"][0]["text"] = '{"answer_markdown":"Answer","rows":[]}'
    elif defect in {"extra_field", "nested_extra", "wrong_type"}:
        if defect == "extra_field":
            draft["unexpected"] = "discarding this would be partial"
        elif defect == "nested_extra":
            draft["figures"][0]["unexpected"] = "not in strict schema"
        else:
            draft["figures"][0]["value"] = True
        message["content"][0]["text"] = json.dumps(draft)
    elif defect == "empty_output":
        response["output"] = []
    elif defect == "malformed_item":
        response["output"].append("invalid")
    elif defect == "malformed_content":
        message["content"].append("invalid")
    elif defect == "refusal":
        message["content"].append({"type": "refusal", "refusal": "Refused"})
    elif defect == "incomplete_message":
        message["status"] = "incomplete"
    elif defect == "incomplete_details":
        response["incomplete_details"] = {"reason": "max_output_tokens"}
    with pytest.raises(ResearchUnavailableError) as caught:
        run(response)
    assert caught.value.reason == "malformed_response"
    assert caught.value.usage.cost_usd == pytest.approx(0.0487)


def test_structured_call_reuses_unpriced_spend_handling(draft, monkeypatch):
    from argus.domain.research import perplexity_agent

    recorded = []
    monkeypatch.setattr(perplexity_agent, "record_unpriced_spend", recorded.append)
    response = document(draft)
    response.pop("usage")
    result, _ = run(response)
    assert result.draft == draft
    assert result.usage.cost_usd is None
    assert len(recorded) == 1
    assert recorded[0].provider_response_id == result.provider_response_id


def test_new_method_does_not_mutate_the_callers_spec_or_response(draft):
    spec = RESEARCH_CONFIG_SPECS["fast"]
    original = spec.model_dump()
    response = document(draft)
    before = deepcopy(response)
    run(response, spec=spec)
    assert spec.model_dump() == original
    assert response == before


def test_structured_request_limits_use_documented_root_and_tool_keys(draft):
    limits = {
        "max_tool_calls": 4,
        "parallel_tool_calls": False,
        "web_search_max_tokens": 8000,
        "web_search_max_tokens_per_page": 2000,
        "web_search_max_results": 4,
        "fetch_url_max_urls": 2,
        "fetch_url_total_budget_tokens": 8000,
    }
    _, transport = run(document(draft), **limits)
    body = request_body(transport.requests[0])
    assert body["max_tool_calls"] == 4
    assert body["parallel_tool_calls"] is False
    tools = {tool["type"]: tool for tool in body["tools"]}
    assert tools["web_search"]["max_tokens"] == 8000
    assert tools["web_search"]["max_tokens_per_page"] == 2000
    assert tools["web_search"]["max_results"] == 4
    assert tools["fetch_url"] == {
        "type": "fetch_url",
        "max_urls": 2,
        "total_budget_tokens": 8000,
    }
    assert "finance_search" not in tools
    assert not (set(limits) - {"max_tool_calls", "parallel_tool_calls"}) & body.keys()


def test_structured_limits_are_omitted_unless_the_caller_supplies_them(draft):
    _, transport = run(document(draft))
    body = request_body(transport.requests[0])
    assert "max_tool_calls" not in body
    assert "parallel_tool_calls" not in body
    assert not any(
        "total_budget_tokens" in tool or "max_results" in tool for tool in body["tools"]
    )


@pytest.mark.parametrize(
    "limits",
    [
        {"max_tool_calls": -1},
        {"max_tool_calls": True},
        {"parallel_tool_calls": 1},
        {"web_search_max_tokens": 0},
        {"web_search_max_tokens_per_page": -2},
        {"web_search_max_results": 51},
        {"fetch_url_max_urls": 11},
        {"fetch_url_total_budget_tokens": 120001},
    ],
)
def test_invalid_limits_are_rejected_before_any_request(draft, limits):
    transport = RecordingTransport([document(draft)])
    client = PerplexityAgentClient("test-key", transport=transport)
    with pytest.raises(ValueError):
        client.run_structured(
            "Explain",
            RESEARCH_CONFIG_SPECS["balanced"],
            schema_model=Draft,
            schema_name="readout_draft",
            instructions="Explain",
            limits=StructuredAgentLimits(**limits),
        )
    assert transport.requests == []


def test_zero_tool_call_limit_remains_explicit(draft):
    _, transport = run(document(draft), max_tool_calls=0)
    assert request_body(transport.requests[0])["max_tool_calls"] == 0
