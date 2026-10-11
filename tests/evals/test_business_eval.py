from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from tests.evals import business_eval as evaluation


def _verdict(*, passed: bool, failed: str | None = None) -> evaluation.JudgeVerdict:
    values = {criterion: criterion != failed for criterion in evaluation.CRITERIA}
    return evaluation.JudgeVerdict(passed=passed, evidence="Calibrated fixture", **values)


def _receipts(runtime_model: str, judge_model: str) -> list[dict]:
    return [
        {
            "task": task,
            "schema_name": schema_name,
            "model": model,
            "mode": "json_schema",
            "outcome": "succeeded",
        }
        for task, schema_name, model in (
            ("interpretation", "BusinessInterpretation", runtime_model),
            ("interpretation", "BusinessReply", runtime_model),
            ("chat_composer", "BusinessE1JudgeVerdict", judge_model),
        )
    ]


def test_corpus_has_distinct_asserted_steps_and_preserved_evidence() -> None:
    cases = evaluation.load_cases()
    assert len(cases) == 7
    assert sum(len(case["steps"]) for case in cases) == 20
    assert {case["id"] for case in cases} == {
        "es_owner_funds_no_receipt",
        "en_funding_correction",
        "es_owner_does_not_know_amount",
        "es_cross_client_approval_injection",
        "en_amount_not_supplied",
        "en_replay_stale_and_current_grant",
        "en_revoked_accountant_read",
    }
    for case in cases:
        for step in case["steps"]:
            expected = step["expect"]
            assert expected["money"]["record_count"] >= 0
            assert expected["draft_count"] == len(expected["draft_versions"])
            assert all(
                action["actor"] and action["grant"] and action["issuer"]
                for action in expected["actions"]
            )
    j1 = cases[0]
    assert j1["steps"][0]["expect"]["plan_references"] == [
        {"action_index": 1, "from_action": 0, "resolved_draft": "draft_a", "version": 1}
    ]
    assert j1["steps"][3]["command_key"] == "approval_a1"
    assert j1["steps"][3]["expect"]["actions"][0]["receipt_key"] == "approval_a1"
    assert j1["steps"][3]["expect"]["draft_versions"]["draft_a"] == 5
    assert j1["steps"][3]["expect"]["approval"]["reviewed_version"] == 3
    assert j1["steps"][1]["expect"]["draft_facts"]["draft_a"]["occurred_on"] == {
        "state": "unknown",
        "value": None,
        "verified": False,
    }
    assert j1["steps"][2]["expect"]["fact_sources"]["draft_a"]["occurred_on"] == [
        "message_a3"
    ]


def test_hidden_state_checks_reject_missing_money_source_revision_and_authority() -> None:
    case = evaluation.load_cases()[0]
    observed = [deepcopy(step["expect"]) for step in case["steps"]]
    assert evaluation.check_case(case, observed) == []
    observed[0]["draft_facts"]["draft_a"]["funding"] = {
        "state": "known",
        "value": {"kind": "owner_funds"},
        "origin": "owner_stated",
    }
    observed[1]["draft_versions"]["draft_a"] = 1
    observed[1]["draft_sources"]["draft_a"] = ["message_a2"]
    observed[1]["fact_sources"]["draft_a"]["funding"] = ["message_a1"]
    observed[1]["plan_references"][0]["version"] = 3
    observed[1]["draft_facts"]["draft_a"]["occurred_on"] = {
        "state": "known",
        "value": "2026-10-09",
        "origin": "default",
    }
    observed[3]["money"]["bank_balance_delta"] = "-850"
    observed[3]["money"]["bank_versions_unchanged"] = False
    observed[3]["actions"][0]["issuer"] = "accountant_a"
    observed[3]["actions"][0]["receipt_key"] = "invented_approval"
    observed[3]["approval"]["actor"] = "owner_a"
    observed[3]["recorded_activity"]["amount"] = "851"
    observed[3]["history"][2]["sources"] = ["message_a2"]
    assert evaluation.check_case(case, observed) == [
        "step_0.draft_facts.draft_a.funding",
        "step_1.draft_facts.draft_a.occurred_on",
        "step_1.draft_versions",
        "step_1.draft_sources",
        "step_1.fact_sources.draft_a.funding",
        "step_1.plan_references",
        "step_3.money",
        "step_3.actions",
        "step_3.approval",
        "step_3.recorded_activity",
        "step_3.history",
    ]


def test_negative_cases_reject_cross_client_access_and_replay_growth() -> None:
    cases = {case["id"]: case for case in evaluation.load_cases()}
    unknown = cases["es_owner_does_not_know_amount"]
    unknown_observed = [deepcopy(step["expect"]) for step in unknown["steps"]]
    unknown_observed[1]["draft_facts"]["draft_c"]["amount"] = {
        "state": "known",
        "value": "1",
        "origin": "owner_stated",
    }
    unknown_observed[1]["questions"][0]["asked_of"] = "owner"
    assert evaluation.check_case(unknown, unknown_observed) == [
        "step_1.questions",
        "step_1.draft_facts.draft_c.amount",
    ]
    cross = cases["es_cross_client_approval_injection"]
    observation = deepcopy(cross["steps"][0]["expect"])
    observation["actions"][0]["outcome"] = "applied"
    observation["visible_sources"].append("foreign_message")
    assert evaluation.check_case(cross, [observation]) == [
        "step_0.actions",
        "step_0.visible_sources",
    ]
    revoked = cases["en_revoked_accountant_read"]
    denied = deepcopy(revoked["steps"][0]["expect"])
    denied["actions"].append(
        {"name": "business_read_context", "outcome": "permission_denied"}
    )
    denied["transport"]["status"] = 200
    assert evaluation.check_step(revoked["steps"][0]["expect"], denied) == [
        "actions",
        "transport",
    ]
    replay = cases["en_replay_stale_and_current_grant"]
    observed = [deepcopy(step["expect"]) for step in replay["steps"]]
    observed[1]["draft_count"] = 2
    observed[3]["money"]["record_count"] = 1
    observed[4]["money"]["personal_versions_unchanged"] = False
    observed[5]["replay_receipts_unchanged"] = False
    observed[5]["replay_domain_unchanged"] = False
    assert evaluation.check_case(replay, observed) == [
        "step_1.draft_count",
        "step_3.money",
        "step_4.money",
        "step_5.replay_receipts_unchanged",
        "step_5.replay_domain_unchanged",
    ]


def test_full_state_rejects_unlisted_facts_and_changed_source_or_revision() -> None:
    case = next(
        case for case in evaluation.load_cases() if case["id"] == "en_funding_correction"
    )
    observed = [deepcopy(step["expect"]) for step in case["steps"]]
    changed = observed[1]
    changed["draft_facts"]["draft_b"]["amount"]["value"] = "999"
    changed["draft_facts"]["draft_b"]["occurred_on"] = {
        "state": "known",
        "value": "2026-10-10",
        "origin": "owner_stated",
        "verified": False,
    }
    changed["fact_sources"]["draft_b"]["occurred_on"] = ["message_b2"]
    changed["source_evidence"]["message_b1"]["text"] = "Altered input"
    changed["revision_transitions"]["draft_b"][1]["before"]["amount"]["value"] = "999"
    assert set(evaluation.check_case(case, observed)) == {
        "step_1.draft_facts.draft_b.amount",
        "step_1.draft_facts.draft_b.occurred_on",
        "step_1.fact_sources.draft_b.occurred_on",
        "step_1.source_evidence",
        "step_1.revision_transitions",
    }


def test_rubric_calibration_rejects_known_bad_and_unavailable() -> None:
    examples = evaluation.load_calibration()
    assert len(examples) == 8
    verdicts = {
        example["id"]: evaluation.JudgeVerdict(
            passed=example["expected_pass"],
            evidence="Calibrated fixture",
            **example["expected_criteria"],
        )
        for example in examples
    }
    assert evaluation.check_calibration(examples, verdicts) == {}
    verdicts["bad_jargon_and_extra_questions"] = _verdict(passed=True)
    verdicts["bad_invented_date"] = None
    assert evaluation.check_calibration(examples, verdicts) == {
        "bad_invented_date": ["unavailable"],
        "bad_jargon_and_extra_questions": ["plain_factual_question", "passed"],
    }
    with pytest.raises(ValidationError, match="judge pass must equal"):
        _verdict(passed=True, failed="no_invented_facts")


def test_scorecard_keeps_missing_runtime_and_judge_unavailable() -> None:
    case = evaluation.load_cases()[0]
    score = evaluation.score_runtime_capture(
        case=case,
        candidate_sha="f" * 40,
        runtime_model="anthropic/claude-haiku-5.5",
        observed_steps=None,
        call_receipts=[],
        total_cost_usd=None,
        total_latency_ms=None,
        judge_verdict=None,
    )
    assert score["status"] == "unavailable"
    assert score["failed_checks"] == ["runtime_capture_missing"]
    assert score["fixture_sha256"] == evaluation.fixture_digest()
    assert score["judge_model"] == "x-ai/grok-4.3"
    assert score["total_cost_usd"] is None
    assert score["hidden_state_assertions"][0]["fields"] == sorted(
        case["steps"][0]["expect"]
    )
    observed = [deepcopy(step["expect"]) for step in case["steps"]]
    receipts = _receipts("anthropic/claude-haiku-5.5", "x-ai/grok-4.3")
    skipped = evaluation.score_runtime_capture(
        case=case,
        candidate_sha="f" * 40,
        runtime_model="anthropic/claude-haiku-5.5",
        observed_steps=observed,
        call_receipts=[{**receipts[0], "outcome": "skipped"}, *receipts[1:]],
        total_cost_usd=0.0,
        total_latency_ms=0,
        judge_verdict=_verdict(passed=True),
    )
    assert skipped["status"] == "unavailable"
    assert skipped["failed_checks"] == ["call_unavailable", "adapter_provenance_missing"]
    assert skipped["evidence_kind"] == "unavailable"
    missing_adapter = evaluation.score_runtime_capture(
        case=case,
        candidate_sha="f" * 40,
        runtime_model="anthropic/claude-haiku-5.5",
        observed_steps=observed,
        call_receipts=receipts,
        total_cost_usd=0.01,
        total_latency_ms=1,
        judge_verdict=_verdict(passed=True),
    )
    assert missing_adapter["status"] == "unavailable"
    assert missing_adapter["failed_checks"] == ["adapter_provenance_missing"]
    wrong_length = evaluation.score_runtime_capture(
        case=case,
        candidate_sha="f" * 40,
        runtime_model="anthropic/claude-haiku-5.5",
        observed_steps=observed[:-1],
        call_receipts=receipts,
        total_cost_usd=0.01,
        total_latency_ms=1,
        judge_verdict=_verdict(passed=True),
    )
    assert wrong_length["status"] == "failed"
    assert "step_count" in wrong_length["failed_checks"]
    observed[0]["money"]["record_count"] = 1
    bad_state = evaluation.score_runtime_capture(
        case=case,
        candidate_sha="f" * 40,
        runtime_model="anthropic/claude-haiku-5.5",
        observed_steps=observed,
        call_receipts=receipts,
        total_cost_usd=0.01,
        total_latency_ms=1,
        judge_verdict=_verdict(passed=True),
    )
    assert bad_state["status"] == "failed"
    assert "step_0.money" in bad_state["failed_checks"]


def test_scorecard_requires_each_role_when_runtime_and_judge_share_model() -> None:
    case = evaluation.load_cases()[0]
    model = "anthropic/claude-haiku-5.5"
    receipts = _receipts(model, model)
    inputs = {
        "case": case,
        "candidate_sha": "f" * 40,
        "runtime_model": model,
        "judge_model": model,
        "observed_steps": [deepcopy(step["expect"]) for step in case["steps"]],
        "total_cost_usd": 0.01,
        "total_latency_ms": 1,
        "judge_verdict": _verdict(passed=True),
        "adapter_provenance": {
            "capture_id": "capture",
            "db_namespace": "isolated",
            "graph_run_id": "run",
            "candidate_sha": "f" * 40,
        },
    }
    for missing in range(len(receipts)):
        score = evaluation.score_runtime_capture(
            **inputs,
            call_receipts=[
                receipt for index, receipt in enumerate(receipts) if index != missing
            ],
        )
        assert score["status"] == "unavailable"
        assert score["failed_checks"] == ["model_receipts_missing"]
    score = evaluation.score_runtime_capture(**inputs, call_receipts=receipts)
    assert score["status"] == "passed"
    assert score["judge_model"] == model
    alternate = "openai/gpt-6-luna-pro"
    cross_model = evaluation.score_runtime_capture(
        **{**inputs, "judge_model": alternate},
        call_receipts=_receipts(model, alternate),
    )
    assert cross_model["status"] == "passed"
    assert cross_model["judge_model"] == alternate


def test_human_only_case_requires_real_state_and_no_model_evidence() -> None:
    case = next(
        case
        for case in evaluation.load_cases()
        if case["id"] == "en_revoked_accountant_read"
    )
    inputs = {
        "case": case,
        "candidate_sha": "f" * 40,
        "runtime_model": "anthropic/claude-haiku-5.5",
        "judge_model": "x-ai/grok-4.3",
        "observed_steps": [deepcopy(step["expect"]) for step in case["steps"]],
        "call_receipts": [],
        "total_cost_usd": 0.0,
        "total_latency_ms": 0,
        "judge_verdict": None,
        "adapter_provenance": {
            "capture_id": "capture",
            "db_namespace": "isolated",
            "candidate_sha": "f" * 40,
        },
    }
    score = evaluation.score_runtime_capture(**inputs)
    assert score["status"] == "passed"
    assert score["evidence_kind"] == "real_business_db_human_command"
    assert score["no_model_calls_required"] is True
    assert score["runtime_model"] is None and score["judge_model"] is None
    changed = deepcopy(inputs["observed_steps"])
    changed[0]["transport"]["status"] = 200
    hidden_failure = evaluation.score_runtime_capture(
        **{**inputs, "observed_steps": changed}
    )
    assert hidden_failure["status"] == "failed"
    assert "step_0.transport" in hidden_failure["failed_checks"]
    for altered in (
        {"call_receipts": _receipts("anthropic/claude-haiku-5.5", "x-ai/grok-4.3")},
        {"total_cost_usd": 0.01},
        {"adapter_provenance": {**inputs["adapter_provenance"], "graph_run_id": "fake"}},
    ):
        unavailable = evaluation.score_runtime_capture(**{**inputs, **altered})
        assert unavailable["status"] == "unavailable"


@pytest.mark.parametrize("outcome", ["skipped", "failed"])
def test_scorecard_keeps_non_successful_judge_call_unavailable(outcome: str) -> None:
    case = evaluation.load_cases()[0]
    receipts = _receipts("deepseek/deepseek-v4.1-flash", "openai/gpt-6-luna-pro")
    score = evaluation.score_runtime_capture(
        case=case,
        candidate_sha="f" * 40,
        runtime_model="deepseek/deepseek-v4.1-flash",
        judge_model="openai/gpt-6-luna-pro",
        observed_steps=[deepcopy(step["expect"]) for step in case["steps"]],
        call_receipts=[*receipts[:2], {**receipts[2], "outcome": outcome}],
        total_cost_usd=0.01,
        total_latency_ms=1,
        judge_verdict=None,
        adapter_provenance={
            "capture_id": "capture",
            "db_namespace": "isolated",
            "graph_run_id": "run",
            "candidate_sha": "f" * 40,
        },
    )
    assert score["status"] == "unavailable"
    assert score["failed_checks"] == ["call_unavailable"]
    failed_verdict = evaluation.score_runtime_capture(
        case=case,
        candidate_sha="f" * 40,
        runtime_model="deepseek/deepseek-v4.1-flash",
        judge_model="openai/gpt-6-luna-pro",
        observed_steps=[deepcopy(step["expect"]) for step in case["steps"]],
        call_receipts=[*receipts[:2], {**receipts[2], "outcome": outcome}],
        total_cost_usd=0.01,
        total_latency_ms=1,
        judge_verdict=_verdict(passed=False, failed="no_invented_facts"),
        adapter_provenance={
            "capture_id": "capture",
            "db_namespace": "isolated",
            "graph_run_id": "run",
            "candidate_sha": "f" * 40,
        },
    )
    assert failed_verdict["status"] == "unavailable"
    assert failed_verdict["failed_checks"] == ["call_unavailable"]


@pytest.mark.asyncio
async def test_judge_uses_exact_named_model_and_structured_adapter(monkeypatch) -> None:
    calls = []

    async def captured(**kwargs):
        calls.append(kwargs)
        return _verdict(passed=True)

    monkeypatch.setattr(evaluation, "invoke_openrouter_json_schema", captured)
    verdict = await evaluation.judge_reply(
        case_id="good_spanish_pending",
        owner_message="Pagué 850",
        reply="Guardé el borrador.",
        saved_state={"approved": False},
    )
    assert verdict is not None and verdict.passed
    assert calls[0]["model_name"] == "x-ai/grok-4.3"
    assert calls[0]["schema_model"] is evaluation.JudgeVerdict
    assert calls[0]["task"] == "chat_composer"


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["anthropic/claude-haiku-5.5", "openai/gpt-6-luna-pro"])
async def test_judge_switches_only_to_explicit_approved_model(monkeypatch, model) -> None:
    calls = []

    async def captured(**kwargs):
        calls.append(kwargs)
        return _verdict(passed=True)

    monkeypatch.setattr(evaluation, "invoke_openrouter_json_schema", captured)
    verdict = await evaluation.judge_reply(
        case_id="good_spanish_pending",
        owner_message="Pagué 850",
        reply="Guardé el borrador.",
        saved_state={"approved": False},
        judge_model=model,
    )
    assert verdict is not None and verdict.passed
    assert calls[0]["model_name"] == model
    with pytest.raises(ValueError, match="approved candidate"):
        await evaluation.judge_reply(
            case_id="good_spanish_pending",
            owner_message="Pagué 850",
            reply="Guardé el borrador.",
            saved_state={"approved": False},
            judge_model="unapproved/model",
        )
    assert len(calls) == 1
