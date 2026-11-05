from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests.evals import chat_runtime_eval_harness
from tests.evals.chat_runtime_eval_harness import (
    build_semantic_judge_messages,
    capability_context_payload,
    iter_eval_cases,
    parse_sse_events,
    persist_eval_harness_cost_ledger_entries,
)

MANIFEST_PATH = Path(__file__).with_name("chat_runtime_scenarios.json")
EXPECTED_QA_IDS = {f"QA {index}" for index in range(1, 16)}
EXPECTED_WORKSTREAMS = {f"workstream_{index}" for index in range(1, 9)}
VALID_PRIORITIES = {"must_pass", "should_pass", "watch"}
EXPECTED_EVAL_CATEGORIES = {
    "messy_beginner_investing_prompts",
    "partial_strategy_ideas",
    "unsupported_requests",
    "contradictory_requests",
    "recovery_scenarios",
    "reload_refinement_continuity",
    "result_followup_groundedness",
    "why_did_this_happen_contextual_synthesis",
    "next_experiment_usefulness",
    "hallucination_prevention",
    "no_unsupported_investment_advice",
}


def _load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_chat_runtime_eval_manifest_covers_release_matrix() -> None:
    manifest = _load_manifest()
    scenarios = manifest["scenarios"]

    qa_ids = {scenario["qa_id"] for scenario in scenarios}
    assert qa_ids == EXPECTED_QA_IDS

    covered_workstreams = {
        bucket
        for scenario in scenarios
        for bucket in scenario["buckets"]
        if bucket.startswith("workstream_")
    }
    assert covered_workstreams == EXPECTED_WORKSTREAMS


def test_chat_runtime_eval_manifest_has_judge_and_hard_checks() -> None:
    manifest = _load_manifest()
    scenario_ids: set[str] = set()

    for scenario in manifest["scenarios"]:
        assert scenario["id"] not in scenario_ids
        scenario_ids.add(scenario["id"])
        assert scenario["priority"] in VALID_PRIORITIES
        assert scenario["purpose"]
        assert len(scenario["natural_prompt_variants"]) >= 3
        assert scenario["conversation_steps"]
        assert scenario["artifact_checks"]
        assert scenario["action_checks"]
        assert scenario["reload_checks"]
        assert scenario["forbidden_outcomes"]
        assert scenario["judge_rubric"]

        for step in scenario["conversation_steps"]:
            assert step["semantic_target"]
            assert step["hard_checks"]


def test_result_action_eval_manifest_matches_current_and_stale_action_contracts() -> None:
    manifest = _load_manifest()
    scenarios = {scenario["qa_id"]: scenario for scenario in manifest["scenarios"]}

    qa_8 = scenarios["QA 8"]
    assert qa_8["action_checks"] == [
        "show_breakdown and refine_strategy use the latest run id"
    ]

    qa_9 = scenarios["QA 9"]
    visible_actions = [
        step["action_type"]
        for step in qa_9["conversation_steps"]
        if step["actor"] == "action"
    ]
    assert visible_actions == ["show_breakdown", "refine_strategy"]

    stale_actions = [
        step
        for step in qa_9["conversation_steps"]
        if step["actor"] == "stale_action"
    ]
    assert stale_actions == [
        {
            "actor": "stale_action",
            "action_type": "save_strategy",
            "semantic_target": "return_non_mutating_legacy_save_continuity",
            "hard_checks": [
                "reports that the legacy save surface is retired",
                "keeps the completed run reachable in conversation and Recents",
                "does not create or mutate Strategy records",
            ],
        }
    ]

    assert not any(
        step.get("action_type") == "save_strategy" and step["actor"] == "action"
        for scenario in manifest["scenarios"]
        for step in scenario["conversation_steps"]
    )


def test_chat_runtime_eval_manifest_separates_hard_checks_from_llm_judgment() -> None:
    manifest = _load_manifest()
    assert manifest["scoring"]["must_pass"].startswith("Hard runtime")

    must_pass = [
        scenario
        for scenario in manifest["scenarios"]
        if scenario["priority"] == "must_pass"
    ]
    assert len(must_pass) >= 10

    for scenario in must_pass:
        hard_check_text = " ".join(
            check
            for step in scenario["conversation_steps"]
            for check in step["hard_checks"]
        )
        assert "judge" not in hard_check_text.lower()
        assert "rubric" not in hard_check_text.lower()


def test_chat_runtime_eval_layer_tracks_semantic_groundedness_and_receipts() -> None:
    manifest = _load_manifest()
    layer = manifest["production_readiness_eval_layer"]

    assert layer["assertion_style"] == "semantic_contracts_not_exact_wording"
    assert set(layer["exact_strings_reserved_for"]) == {
        "protocol",
        "static_ui",
        "safety_fallback",
    }
    assert set(layer["categories"]) == EXPECTED_EVAL_CATEGORIES
    assert set(layer["capability_context_source"]) == {
        "build_default_capability_contract",
        "EXECUTABLE_INDICATORS",
        "strategy_contract validators",
    }
    assert set(layer["receipt_fields"]) >= {
        "task",
        "tier",
        "model",
        "fallback_model",
        "latency_ms",
        "outcome",
        "failure_mode",
        "token_usage",
        "context_packet_ids",
    }


def test_chat_runtime_eval_manifest_covers_conditional_buy_sell_regression() -> None:
    manifest = _load_manifest()
    prompts = {
        prompt
        for scenario in manifest["scenarios"]
        for prompt in scenario["natural_prompt_variants"]
    }
    hard_checks = {
        check
        for scenario in manifest["scenarios"]
        for step in scenario["conversation_steps"]
        for check in step["hard_checks"]
    }

    assert "buy and sell when it goes up" in prompts
    assert (
        "does not collapse conditional buy/sell language into buy-and-hold" in hard_checks
    )


def test_eval_harness_builds_judge_payload_from_runtime_capabilities() -> None:
    context = capability_context_payload()

    assert context["contract_version"] == "1.0"
    assert "strategy_drafting" in context["supported_intents"]
    assert {"rsi", "sma", "ema", "macd", "bbands"}.issubset(
        {item["key"] for item in context["executable_indicators"]}
    )
    assert (
        "asset resolution and provider availability"
        in context["deterministic_boundaries"]
    )

    cases = iter_eval_cases(priority="must_pass")
    case = next(item for item in cases if item.prompt == "buy and sell when it goes up")
    messages = build_semantic_judge_messages(
        case=case,
        assistant_response="I need a specific executable rule before I can run that.",
        final_payload={"stage_outcome": "await_user_reply"},
        route_receipts=[
            {
                "task": "interpretation",
                "tier": "structured",
                "model": "test/model",
                "fallback_model": "test/fallback",
                "latency_ms": 123,
                "outcome": "succeeded",
                "failure_mode": None,
                "token_usage": None,
                "context_packet_ids": [],
            }
        ],
        capability_context=context,
    )

    assert messages[0]["role"] == "system"
    assert "Do not require exact wording" in messages[0]["content"]
    payload = json.loads(messages[1]["content"])
    assert payload["case"]["prompt"] == "buy and sell when it goes up"
    assert payload["case"]["semantic_target"] == case.semantic_target
    assert payload["case"]["hard_checks"] == list(case.hard_checks)
    assert payload["case"]["semantic_steps"] == [
        {
            "step_id": case.steps[0].step_id,
            "semantic_target": case.semantic_target,
            "hard_checks": list(case.hard_checks),
        }
    ]
    assert payload["capability_context"]["executable_indicators"]
    assert payload["runtime_output"]["route_receipts"][0]["task"] == "interpretation"


def test_eval_cases_preserve_every_conversation_step() -> None:
    case = next(
        item
        for item in iter_eval_cases(priority="must_pass")
        if item.scenario_id == "qa_02_draft_continuity"
        and item.prompt == "Test buying and holding Apple over the past year."
    )

    assert [step.semantic_target for step in case.steps] == [
        "create_buy_hold_aapl_last_year",
        "patch_active_artifact_asset_only",
        "patch_active_artifact_period_only",
        "answer_from_visible_confirmation_artifact",
    ]
    assert case.steps[1].prompt_variants == (
        "Actually make it Nvidia.",
        "switch the asset to NVDA",
        "same thing but Nvidia",
    )


def test_judge_payload_includes_every_sanitized_semantic_step_in_order() -> None:
    case = next(
        item
        for item in iter_eval_cases(priority="must_pass")
        if item.scenario_id == "qa_02_draft_continuity"
        and item.prompt == "Test buying and holding Apple over the past year."
    )

    messages = build_semantic_judge_messages(
        case=case,
        assistant_response="Sanitized assistant result.",
        final_payload={"stage_outcome": "ready_for_confirmation"},
        route_receipts=[],
        capability_context={"contract_version": "test"},
    )
    payload = json.loads(messages[1]["content"])
    semantic_steps = payload["case"]["semantic_steps"]

    assert semantic_steps == [
        {
            "step_id": step.step_id,
            "semantic_target": step.semantic_target,
            "hard_checks": list(step.hard_checks),
        }
        for step in case.steps
    ]
    assert payload["case"]["semantic_target"] == case.steps[0].semantic_target
    assert payload["case"]["hard_checks"] == list(case.steps[0].hard_checks)
    assert all(
        set(step_payload) == {"step_id", "semantic_target", "hard_checks"}
        for step_payload in semantic_steps
    )

    serialized_case = json.dumps(payload["case"], sort_keys=True)
    for step in case.steps[1:]:
        assert all(prompt not in serialized_case for prompt in step.prompt_variants)


def test_eval_case_iteration_emits_no_product_event(monkeypatch) -> None:
    # Eval tooling never writes into the product analytics stream (SPEC 0, 0C-1).
    posts: list[object] = []
    monkeypatch.setenv("POSTHOG_PROJECT_TOKEN", "phc_test")
    monkeypatch.setenv("POSTHOG_REGION", "us")
    monkeypatch.setattr(
        "argus.observability.envelope.httpx.post",
        lambda *args, **kwargs: posts.append((args, kwargs)),
    )

    cases = iter_eval_cases(priority="must_pass")

    assert cases
    assert posts == []
    assert not hasattr(chat_runtime_eval_harness, "capture_product_event")


def test_eval_harness_parses_canonical_sse_frames() -> None:
    events = parse_sse_events(
        "\n".join(
            [
                'data: {"type":"stage_start","stage":"interpret"}',
                'data: {"type":"token","content":"hello"}',
                'data: {"type":"final","payload":{"stage_outcome":"ready_to_respond"}}',
                "data: [DONE]",
            ]
        )
    )

    assert [event["type"] for event in events] == [
        "stage_start",
        "token",
        "final",
    ]


def test_eval_harness_persists_judge_cost_ledger_entries() -> None:
    from argus.llm.openrouter import OpenRouterRouteReceipt

    class FakeGateway:
        def __init__(self) -> None:
            self.entries: list[dict[str, Any]] = []

        def create_cost_ledger_entry(self, *, entry: dict[str, Any]) -> dict[str, Any]:
            self.entries.append(entry)
            return {"id": "ledger-1", **entry}

    gateway = FakeGateway()
    persist_eval_harness_cost_ledger_entries(
        gateway=gateway,
        receipts=[
            OpenRouterRouteReceipt(
                task="capability_conflict",
                tier="context",
                model="judge/model",
                fallback_model="judge/fallback",
                mode="json_schema",
                schema_name="SemanticEvalJudge",
                latency_ms=250,
                outcome="succeeded",
                token_usage={"prompt_tokens": 50, "completion_tokens": 10},
                usage_cost_usd=0.001,
            )
        ],
        eval_suite_id="private-alpha-next",
        eval_case_id="qa-1",
    )

    assert len(gateway.entries) == 1
    assert gateway.entries[0]["source"] == "eval_harness"
    assert gateway.entries[0]["feature_area"] == "eval_readiness"
    assert gateway.entries[0]["correlation_id"] == "eval:private-alpha-next:qa-1"
    assert gateway.entries[0]["cost_amount"] == 0.001
