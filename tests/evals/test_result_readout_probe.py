"""Hermetic HTTP and invoice proof for the two Luna readout providers."""

import asyncio
import copy
import json
from contextlib import ExitStack
from pathlib import Path

import httpx
import pytest
import respx

from tests.evals import test_result_readout_eval as fixture_owner
from tests.evals.result_readout_eval import (
    CostGuard,
    load_fixture_set,
    measurement_can_continue,
)
from tests.evals.result_readout_probe import (
    cost_accounting,
    install_http_guards,
    run_probe,
)
from tests.research.conftest import agent_response, search_results_item

provider_rates = fixture_owner.provider_rates
task_configuration = fixture_owner.task_configuration

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
PERPLEXITY_URL = "https://api.perplexity.ai/v1/agent"


def observations():
    return {
        "requests": [],
        "provider_responses": [],
        "guard_failures": [],
        "blocked_dispatches": [],
    }


def payload_for(task, tasks):
    if task == "result_summary":
        payload = {
            "model": tasks[task]["model"],
            "max_tokens": tasks[task]["max_output_tokens"],
            "messages": [],
        }
        schema = "QuickTakeDraft"
    else:
        payload = copy.deepcopy(tasks[task]["request_limits"])
        schema = "ResultBreakdownDraft"
    payload["response_format"] = {"json_schema": {"name": schema}}
    return payload


@pytest.mark.asyncio
@pytest.mark.parametrize("async_client", [False, True])
@pytest.mark.parametrize(
    "failure", [httpx.ReadTimeout, asyncio.CancelledError, BaseException]
)
async def test_failed_and_canceled_attempts_retain_safe_receipt_and_reservation(
    monkeypatch, task_configuration, provider_rates, async_client, failure
):
    def fail(*args, **kwargs):
        raise failure("secret-test-value")

    async def fail_async(*args, **kwargs):
        fail()

    monkeypatch.setattr(httpx.Client, "request", fail)
    monkeypatch.setattr(httpx.AsyncClient, "request", fail_async)
    guard = CostGuard(budget_usd=4, rates=provider_rates, tasks=task_configuration)
    report = observations()
    task = "result_summary" if async_client else "result_breakdown"
    with ExitStack() as stack:
        install_http_guards(stack, guard=guard, observations=report, live=True)
        with pytest.raises(failure):
            if async_client:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        OPENROUTER_URL, json=payload_for(task, task_configuration)
                    )
            else:
                with httpx.Client() as client:
                    client.post(
                        PERPLEXITY_URL, json=payload_for(task, task_configuration)
                    )
    receipt = report["requests"][0]
    assert receipt["reserved_usd"] == pytest.approx(guard.reserved_usd)
    assert receipt["outcome"] in {"failed", "canceled"}
    assert receipt["error"]["code"] and receipt["error"]["message"]
    assert "secret-test-value" not in json.dumps(report)
    assert cost_accounting(guard=guard, observations=report)["unknown_cost_attempts"] == 1


def test_missing_actual_cost_continues_only_with_complete_reservations():
    probe = {
        "cost_complete": False,
        "unknown_cost_attempts": 1,
        "all_attempts_reserved": True,
        "guard_failures": [],
    }
    assert measurement_can_continue(probe)
    assert not measurement_can_continue({**probe, "all_attempts_reserved": False})
    assert not measurement_can_continue({**probe, "guard_failures": ["unpriced_model"]})


def test_mixed_actual_and_unknown_costs_have_honest_upper_bound(
    task_configuration, provider_rates
):
    guard = CostGuard(budget_usd=4, rates=provider_rates, tasks=task_configuration)
    report = observations()
    for task in task_configuration:
        reservation = guard.reserve(payload_for(task, task_configuration), task=task)
        report["requests"].append(
            {"attempt_id": guard.attempts, "reserved_usd": reservation}
        )
    actual_cost = 0.001
    report["provider_responses"].append({"attempt_id": 2, "usage": {"cost": actual_cost}})
    accounted = cost_accounting(guard=guard, observations=report)
    unknown_reserve = report["requests"][0]["reserved_usd"]
    assert accounted["observed_cost_usd"] == pytest.approx(actual_cost)
    assert accounted["unknown_cost_attempts"] == 1
    assert accounted["unknown_cost_reserved_usd"] == pytest.approx(unknown_reserve)
    assert accounted["accounted_upper_bound_usd"] == pytest.approx(
        actual_cost + unknown_reserve
    )
    assert not accounted["cost_complete"]
    assert accounted["all_attempts_reserved"]


@pytest.mark.parametrize("cost", [-1, float("inf"), float("nan"), True, "0.001", 10])
def test_invalid_or_excess_actual_cost_stops_before_another_request(
    monkeypatch, task_configuration, provider_rates, cost
):
    calls = []

    def response(*args, **kwargs):
        calls.append(kwargs)
        result = httpx.Response(200, json={})
        result.json = lambda: {"usage": {"cost": cost}}
        return result

    monkeypatch.setattr(httpx.Client, "request", response)
    guard = CostGuard(budget_usd=4, rates=provider_rates, tasks=task_configuration)
    report = observations()
    with ExitStack() as stack:
        install_http_guards(stack, guard=guard, observations=report, live=True)
        with httpx.Client() as client:
            client.post(
                OPENROUTER_URL, json=payload_for("result_summary", task_configuration)
            )
            with pytest.raises(ValueError, match="prior_guard_failure"):
                client.post(
                    PERPLEXITY_URL,
                    json=payload_for("result_breakdown", task_configuration),
                )
    assert len(calls) == 1
    assert not cost_accounting(guard=guard, observations=report)["cost_complete"]


@pytest.fixture
def probe_request(monkeypatch, provider_rates):
    from argus.domain.research import credentials
    from argus.domain.result_readout_research import (
        RESULT_RESEARCH_MODEL as RESULT_BREAKDOWN_MODEL,
    )
    from argus.llm import openrouter, openrouter_key_policy

    monkeypatch.setattr(openrouter, "resolve_openrouter_api_key", lambda: "test-only")
    monkeypatch.setattr(
        openrouter_key_policy, "resolve_openrouter_api_key", lambda: "test-only"
    )
    monkeypatch.setattr(credentials, "perplexity_api_key", lambda: "test-only")
    monkeypatch.setenv("ARGUS_READOUT_MODEL", RESULT_BREAKDOWN_MODEL)
    monkeypatch.setenv("ARGUS_READOUT_FALLBACK_MODEL", RESULT_BREAKDOWN_MODEL)
    for rate in provider_rates.values():
        rate["model"] = RESULT_BREAKDOWN_MODEL
    case = load_fixture_set(
        Path(__file__).with_name("result_readout_fixtures.json"), live=False
    )["cases"][0]
    return {
        "case": case,
        "language": "en",
        "live": False,
        "budget_usd": 4,
        "rates": provider_rates,
        "max_input_bytes": 90000,
    }


def test_free_probe_uses_both_production_builders_without_http(probe_request):
    with respx.mock(assert_all_called=True):
        report = run_probe(probe_request)
    assert report["requests"] == []
    assert report["http_attempts"] == 0
    assert [p["task"] for p in report["preflight_payloads"]] == [
        "result_summary",
        "result_breakdown",
    ]
    limits = report["configuration"]["tasks"]["result_breakdown"]["request_limits"]
    assert {tool["type"] for tool in limits["tools"]} == {"web_search", "fetch_url"}
    assert limits["max_tool_calls"] == 4
    assert limits["parallel_tool_calls"] is False
    assert report["preflight_payloads"][1]["prior_quick_take_allowance_bytes"] == 8192
    assert report["configuration"]["credentials_present"] == {
        "openrouter": True,
        "perplexity_agent": True,
    }


def draft(*, deeper=False):
    value = {"language": "en", "text": "The historical ride was uneven.", "figures": []}
    return value


@pytest.mark.parametrize(
    "failure",
    [
        "none",
        "quick_http",
        "quick_schema",
        "deep_http",
        "deep_json",
        "deep_schema",
        "deep_language",
        "deep_false_figure",
        "deep_incomplete",
        "deep_malformed_output",
    ],
)
def test_real_composer_paths_dispatch_once_each_and_preserve_raw_invoice(
    probe_request, failure
):
    from argus.domain.result_readout_research import (
        RESULT_RESEARCH_MODEL as RESULT_BREAKDOWN_MODEL,
    )

    free = run_probe(probe_request)
    quick_text = json.dumps(draft()) if failure != "quick_schema" else "{bad json"
    quick_document = {
        "id": "test-only-quick",
        "model": RESULT_BREAKDOWN_MODEL,
        "choices": [{"message": {"content": quick_text}}],
        "usage": {"cost": 0.001},
    }
    deeper = draft(deeper=True)
    if failure == "deep_schema":
        deeper["figures"] = "wrong structure"
    if failure == "deep_language":
        deeper["language"] = "es-419"
    if failure == "deep_false_figure":
        deeper["text"] = "The return was 9999%."
        deeper["figures"] = [{"fact_key": "Total return on starting capital", "value": 9999}]
    raw_text = "{bad json" if failure == "deep_json" else json.dumps(deeper)
    response = agent_response(
        text=raw_text,
        invocations=0,
        model=RESULT_BREAKDOWN_MODEL,
        status="incomplete" if failure == "deep_incomplete" else "completed",
    )
    response["output"].insert(
        0,
        search_results_item(
            {"url": "https://example.com/test-only-evidence", "title": "Test only source"}
        ),
    )
    if failure == "deep_malformed_output":
        response["output"] = 42
    quick_http = (
        httpx.Response(400, json={"error": {"message": "reasoning unsupported"}})
        if failure == "quick_http"
        else httpx.Response(200, json=quick_document)
    )
    deep_http = (
        httpx.Response(400, json={"error": "test-only failure"})
        if failure == "deep_http"
        else httpx.Response(200, json=response)
    )
    with respx.mock(assert_all_called=True) as mock:
        quick_route = mock.post(OPENROUTER_URL).mock(return_value=quick_http)
        deep_route = mock.post(PERPLEXITY_URL).mock(return_value=deep_http)
        result = run_probe(
            {
                **probe_request,
                "live": True,
                "preflight_configuration": free["configuration"],
            }
        )
    assert quick_route.call_count == deep_route.call_count == 1
    assert result["http_attempts"] == 2
    assert len(result["provider_responses"]) == 2
    assert result["attempt_receipts_complete"]
    assert measurement_can_continue(result), result
    assert result["quick_take"]["fallback_used"] == failure.startswith("quick_")
    assert result["breakdown"]["fallback_used"] == failure.startswith("deep_")
    assert result["quick_take"]["complete_text"]
    assert result["breakdown"]["complete_text"]
    if failure == "quick_http":
        assert result["blocked_dispatches"] == [
            {
                "task": "result_summary",
                "provider": "openrouter",
                "reason": "single_attempt_policy",
            }
        ]
        assert result["unknown_cost_attempts"] == 1
    if failure != "deep_http":
        receipt = result["provider_responses"][1]
        assert receipt["raw_response"] == response
        assert receipt["raw_usage"] == response["usage"]
        assert receipt["provider_response_id"] == response["id"]
        assert receipt["raw_drafts"] == (
            [] if failure == "deep_malformed_output" else [raw_text]
        )
        assert result["observed_cost_usd"] >= response["usage"]["cost"]["total_cost"]
        assert result[
            "unpriced_spend"
        ], "First Luna usage must keep the existing unpriced billing path"
    if failure == "deep_language":
        assert result["breakdown"]["failure_mode"] == "language_mismatch"
    if failure == "deep_false_figure":
        assert result["breakdown"]["failure_mode"] == "invalid_figure_reference"
    if failure in {
        "none",
        "quick_http",
        "quick_schema",
        "deep_language",
        "deep_false_figure",
    }:
        assert (
            result["breakdown"]["sources"][0]["url"]
            == "https://example.com/test-only-evidence"
        )


def test_paid_probe_refuses_missing_resolved_launch_metadata() -> None:
    from pathlib import Path

    from argus.api.schemas import BacktestRun

    from tests.evals.result_readout_eval import load_fixture_set
    from tests.evals.result_readout_probe import production_quick_take_payload

    case = load_fixture_set(
        Path(__file__).with_name("result_readout_fixtures.json"), live=False
    )["cases"][0]
    with pytest.raises(ValueError, match="stored_launch_metadata_required"):
        production_quick_take_payload(
            run=BacktestRun.model_validate(case["run"]),
            prompt=case["prompts"]["en"],
            language="en",
            synthetic=False,
        )


def test_quick_take_payload_uses_launch_envelope_and_sibling_card() -> None:
    from pathlib import Path

    from argus.api.schemas import BacktestRun

    from tests.evals.result_readout_eval import load_fixture_set
    from tests.evals.result_readout_probe import production_quick_take_payload

    case = load_fixture_set(
        Path(__file__).with_name("result_readout_fixtures.json"), live=False
    )["cases"][0]
    run = BacktestRun.model_validate(case["run"])
    run.config_snapshot["resolved_strategy"] = {
        "strategy_type": "buy_and_hold",
        "asset_universe": run.symbols,
    }
    run.config_snapshot["resolved_parameters"] = {
        "date_range": run.conversation_result_card["date_range"],
        "timeframe": "1D",
        "capital_amount": 1000,
        "sizing_mode": "capital_amount",
        "engine_config": {"starting_capital": 1000},
        "data_coverage": {"outcome": "adjusted_coverage"},
    }
    run.conversation_result_card["chart"] = {"equity": [{"value": 1123.4}]}
    result = production_quick_take_payload(
        run=run, prompt=case["prompts"]["en"], language="en", synthetic=False
    )
    assert result["envelope"]["execution_status"] == "succeeded"
    assert (
        result["envelope"]["resolved_parameters"]
        == run.config_snapshot["resolved_parameters"]
    )
    assert result["envelope"]["metrics"] == run.metrics
    assert "chart" not in result["envelope"]
    assert result["result_card"]["chart"] == run.conversation_result_card["chart"]
    assert "comparable_same_period" not in json.dumps(result)
    assert result["explanation_context"]["result_card"] == result["result_card"]
