"""Quick take has an isolated model route and keeps existing receipt accounting."""

from __future__ import annotations

import json
from pathlib import Path
from typing import get_args

import httpx
import pytest
import respx
from argus.llm import openrouter
from argus.llm.openrouter_tasks import OpenRouterTask
from pydantic import BaseModel

from tests.test_environment_scripts import (
    _contract_array,
    _real_workflow_api_env_payload,
    _render_env_payload,
    _run_render_release_audit,
    _workflow_env_payload,
)

LUNA_MODEL = "openai/gpt-5.6-luna"


@pytest.fixture(autouse=True)
def tier_environment(monkeypatch: pytest.MonkeyPatch, provider_free_env) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    for tier in ("UTILITY", "CHAT", "STRUCTURED", "CONTEXT"):
        monkeypatch.setenv(f"ARGUS_{tier}_MODEL", f"{tier.lower()}/primary")
        monkeypatch.setenv(f"ARGUS_{tier}_FALLBACK_MODEL", f"{tier.lower()}/fallback")
    monkeypatch.setenv("ARGUS_READOUT_MODEL", LUNA_MODEL)
    monkeypatch.setenv("ARGUS_READOUT_FALLBACK_MODEL", LUNA_MODEL)


def test_quick_take_resolves_only_the_readout_tier_and_deduplicates_luna() -> None:
    assert openrouter.openrouter_model_tier_for_task("result_summary") == "readout"
    assert openrouter.resolve_openrouter_model(task="result_summary") == LUNA_MODEL
    assert (
        openrouter.resolve_openrouter_model(task="result_summary", fallback=True)
        == LUNA_MODEL
    )
    assert openrouter.openrouter_model_candidates(task="result_summary") == [LUNA_MODEL]


def test_missing_readout_configuration_cannot_borrow_another_tier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARGUS_READOUT_MODEL", "")
    monkeypatch.setenv("ARGUS_READOUT_FALLBACK_MODEL", "")
    assert openrouter.openrouter_model_candidates(task="result_summary") == []
    assert openrouter.resolve_openrouter_model(task="result_summary") == ""


@pytest.mark.parametrize(
    "task,tier",
    [
        ("name_suggestion", "utility"),
        ("memory_sensitivity", "utility"),
        ("clarification", "chat"),
        ("chat_composer", "chat"),
        ("discovery_voicing", "chat"),
        ("knowledge_voicing", "chat"),
        ("interpretation", "structured"),
        ("interpretation_repair", "structured"),
        ("asset_mention_preflight", "structured"),
        ("field_fidelity", "structured"),
        ("discovery_extraction", "structured"),
        ("discovery_model_knowledge", "structured"),
        ("knowledge_route", "structured"),
        ("capability_conflict", "context"),
    ],
)
def test_other_tasks_keep_their_existing_model_routes(
    task: OpenRouterTask, tier: str
) -> None:
    assert openrouter.openrouter_model_candidates(task=task) == [
        f"{tier}/primary",
        f"{tier}/fallback",
    ]


def test_breakdown_cannot_dispatch_through_openrouter() -> None:
    assert "result_breakdown" not in get_args(OpenRouterTask)
    with pytest.raises(KeyError):
        openrouter.openrouter_model_candidates(task="result_breakdown")
    with pytest.raises(KeyError):
        openrouter.openrouter_profile_for_task("result_breakdown")


def test_distinct_chat_fallback_still_records_fallback_usage() -> None:
    receipt = openrouter.record_openrouter_route_receipt(
        task="chat_composer",
        model_name="chat/fallback",
        mode="json_schema",
        schema_name="readout_tier_test",
        latency_ms=1,
        outcome="succeeded",
    )
    assert receipt.fallback_used is True


@pytest.mark.asyncio
@pytest.mark.parametrize("valid", [True, False])
async def test_luna_attempt_preserves_receipt_usage_and_never_tries_another_model(
    monkeypatch: pytest.MonkeyPatch, valid: bool
) -> None:
    class Draft(BaseModel):
        text: str

    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-test-key")
    content = json.dumps({"text": "An uneven historical ride."}) if valid else "invalid"
    capture = openrouter.begin_openrouter_route_receipt_capture()
    try:
        with respx.mock(assert_all_called=True) as mock:
            route = mock.post("https://openrouter.ai/api/v1/chat/completions").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "choices": [{"message": {"content": content}}],
                        "usage": {
                            "prompt_tokens": 100,
                            "completion_tokens": 20,
                            "total_tokens": 120,
                            "cost": 0.001,
                        },
                    },
                )
            )
            arguments = {
                "task": "result_summary",
                "messages": [{"role": "user", "content": "Explain the stored result."}],
                "schema_model": Draft,
                "schema_name": "readout_tier_test",
            }
            if valid:
                result = await openrouter.invoke_openrouter_json_schema(**arguments)
                assert result.text == "An uneven historical ride."
            else:
                with pytest.raises(ValueError):
                    await openrouter.invoke_openrouter_json_schema(**arguments)
            assert route.call_count == 1
            request = json.loads(route.calls[0].request.content)
            assert request["model"] == LUNA_MODEL
            assert "tools" not in request
    finally:
        receipts = openrouter.end_openrouter_route_receipt_capture(capture)
    assert len(receipts) == 1
    receipt = receipts[0]
    assert receipt.task == "result_summary"
    assert receipt.tier == "readout"
    assert receipt.model == receipt.fallback_model == LUNA_MODEL
    assert receipt.fallback_used is False
    assert receipt.outcome == ("succeeded" if valid else "failed")
    if valid:
        assert receipt.token_usage == {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "total_tokens": 120,
        }
        assert receipt.usage_cost_usd == 0.001


@pytest.mark.parametrize(
    "contract",
    ["ARGUS_QA_REQUIRED_ENV", "ARGUS_RENDER_API_ENV", "ARGUS_RENDER_WORKFLOW_PROOF_ENV"],
)
def test_readout_models_reach_each_runtime_environment_contract(contract: str) -> None:
    values = _contract_array(contract)
    for key in ("ARGUS_READOUT_MODEL", "ARGUS_READOUT_FALLBACK_MODEL"):
        assert values.count(key) == 1


@pytest.mark.parametrize("service", ["argus-api", "argus-backtests"])
@pytest.mark.parametrize("key", ["ARGUS_READOUT_MODEL", "ARGUS_READOUT_FALLBACK_MODEL"])
def test_release_audit_rejects_missing_readout_model_configuration(
    tmp_path: Path, service: str, key: str
) -> None:
    api_rows = json.loads(_real_workflow_api_env_payload())
    if service == "argus-api":
        api_rows = [row for row in api_rows if row["envVar"]["key"] != key]
    result = _run_render_release_audit(
        tmp_path,
        expect_mode="real-workflow",
        api_env_json=json.dumps(api_rows),
        web_env_json=_render_env_payload("cuadrao-web"),
        workflow_env_json=_workflow_env_payload(
            omit={key} if service == "argus-backtests" else set()
        ),
        isolate=True,
    )
    assert result.returncode == 1
    assert f"drift {service}:{key}" in result.stdout
    assert "status=drift" in result.stdout
