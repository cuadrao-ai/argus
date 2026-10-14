from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.evals import business_acceptance as acceptance
from tests.evals.business_eval import CRITERIA, JudgeVerdict, load_cases


def _receipt(schema: str, model: str) -> dict:
    return {
        "task": "interpretation",
        "schema_name": schema,
        "mode": "json_schema",
        "model": model,
        "outcome": "succeeded",
    }


def test_case_manifest_rejects_redistributed_missing_and_duplicate_steps() -> None:
    cases = load_cases()
    acceptance._validate_case_manifest(cases)
    redistributed = deepcopy(cases)
    redistributed[1]["steps"].append(redistributed[0]["steps"].pop())
    assert sum(len(case["steps"]) for case in redistributed) == 21
    with pytest.raises(ValueError, match="step manifest"):
        acceptance._validate_case_manifest(redistributed)
    omitted = deepcopy(cases)
    omitted[0]["steps"].pop()
    with pytest.raises(ValueError, match="step manifest"):
        acceptance._validate_case_manifest(omitted)
    duplicated = deepcopy(cases)
    duplicated[0]["steps"].append(deepcopy(duplicated[0]["steps"][0]))
    with pytest.raises(ValueError, match="step manifest"):
        acceptance._validate_case_manifest(duplicated)


def test_step_receipts_bind_to_fresh_turn_and_replay() -> None:
    model = "anthropic/claude-haiku-5.5"
    case = next(
        item for item in load_cases() if item["id"] == "en_replay_stale_and_current_grant"
    )
    expected = [
        [_receipt("BusinessInterpretation", model), _receipt("BusinessReply", model)]
        if "message" in step and not step.get("replay")
        else []
        for step in case["steps"]
    ]
    capture = SimpleNamespace(
        step_route_receipts=deepcopy(expected),
        graph_run_ids=["run" for step in case["steps"] if "message" in step],
    )
    assert acceptance._step_receipt_failures(case, capture, model) == []
    replay = next(index for index, step in enumerate(case["steps"]) if step.get("replay"))
    capture.step_route_receipts[replay] = [_receipt("BusinessReply", model)]
    assert acceptance._step_receipt_failures(case, capture, model) == [
        f"step_{replay}.route_receipts"
    ]
    capture.step_route_receipts = deepcopy(expected)
    capture.step_route_receipts[0][1]["model"] = "deepseek/deepseek-v4.1-flash"
    assert acceptance._step_receipt_failures(case, capture, model) == [
        "step_0.route_receipts"
    ]
    capture.step_route_receipts = deepcopy(expected)
    capture.step_route_receipts[0][1]["outcome"] = "failed"
    assert acceptance._step_receipt_failures(case, capture, model) == [
        "step_0.route_receipts"
    ]


def test_human_steps_require_zero_actual_route_receipts() -> None:
    model = "anthropic/claude-haiku-5.5"
    case = next(item for item in load_cases() if item["id"] == acceptance.HUMAN_ONLY_CASE)
    capture = SimpleNamespace(
        step_route_receipts=[[] for _ in case["steps"]], graph_run_ids=[]
    )
    assert acceptance._step_receipt_failures(case, capture, model) == []
    capture.step_route_receipts[1].append(_receipt("BusinessReply", model))
    assert acceptance._step_receipt_failures(case, capture, model) == [
        "step_1.route_receipts"
    ]


def test_aggregate_judge_requires_every_reply_and_every_criterion() -> None:
    good = JudgeVerdict(
        passed=True, evidence="A", **{criterion: True for criterion in CRITERIA}
    )
    bad_values = {criterion: criterion != "no_invented_facts" for criterion in CRITERIA}
    bad = JudgeVerdict(passed=False, evidence="B", **bad_values)
    assert acceptance._aggregate_verdict([good, None]) is None
    combined = acceptance._aggregate_verdict([good, bad])
    assert combined is not None
    assert combined.passed is False
    assert combined.no_invented_facts is False
    assert combined.honest_saved_state is True


@pytest.mark.asyncio
async def test_uncalibrated_judge_stops_before_any_capture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = Path(__file__).resolve().parents[2]
    monkeypatch.setattr(acceptance, "_committed_head", lambda *_: None)
    monkeypatch.setattr(
        acceptance,
        "model_facing_surface",
        lambda _: {
            owner: {"entries": 1, "chars": 1, "sha256": "a" * 64}
            for owner in acceptance.BUSINESS_OWNERS
        },
    )
    monkeypatch.setattr(
        acceptance,
        "capture_case",
        lambda *_args, **_kwargs: pytest.fail("uncalibrated judge reached runtime"),
    )
    report, sidecar = await acceptance.run_business_acceptance(
        repository_root=root,
        candidate_sha="a" * 40,
        dsn="postgresql://unused@127.0.0.1/unused",
        runtime_model="anthropic/claude-haiku-5.5",
        judge_model="x-ai/grok-4.3",
        calibration_report=None,
        interpreter_factory=lambda *_: pytest.fail("interpreter created"),
    )
    assert report["status"] == "unavailable"
    assert report["totals"] == {"passed": 0, "failed": 0, "unavailable": 7}
    assert report["measurement_kind"] == "initial_measurement"
    assert report["scope"] == "business"
    assert sidecar["requests"] == []
    assert sidecar["cases"] == []


@pytest.mark.asyncio
async def test_failed_capture_preserves_attempted_receipt_without_a_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = Path(__file__).resolve().parents[2]
    monkeypatch.setattr(acceptance, "_committed_head", lambda *_: None)
    monkeypatch.setattr(
        acceptance,
        "model_facing_surface",
        lambda _: {
            owner: {"entries": 1, "chars": 1, "sha256": "a" * 64}
            for owner in acceptance.BUSINESS_OWNERS
        },
    )
    monkeypatch.setattr(acceptance, "_calibration", lambda *_: {"status": "passed"})

    attempted_cases = []

    async def failed_capture(case: dict, *, receipt_sink, **_kwargs: object) -> None:
        attempted_cases.append(case["id"])
        receipt_sink(
            0,
            [
                {
                    **_receipt("BusinessInterpretation", "anthropic/claude-haiku-5.5"),
                    "latency_ms": 12,
                    "usage_cost_usd": 0.002,
                }
            ],
        )
        raise RuntimeError("structured result rejected")

    monkeypatch.setattr(acceptance, "capture_case", failed_capture)
    report, sidecar = await acceptance.run_business_acceptance(
        repository_root=root,
        candidate_sha="a" * 40,
        dsn="postgresql://unused@127.0.0.1/unused",
        runtime_model="anthropic/claude-haiku-5.5",
        judge_model="x-ai/grok-4.3",
        calibration_report=None,
        interpreter_factory=lambda *_: None,
    )
    assert report["totals"] == {"passed": 0, "failed": 0, "unavailable": 7}
    assert report["cases"][0]["call_receipts"][0]["usage_cost_usd"] == 0.002
    assert report["cases"][0]["total_cost_usd"] == 0.002
    assert sidecar["cases"][0]["capture_error"] == "RuntimeError"
    assert sidecar["cases"][0]["observed_steps"] is None
    assert attempted_cases == list(acceptance.CASE_IDS)
    foreign = next(
        item
        for item in sidecar["cases"]
        if item["case_id"] == "es_cross_client_approval_injection"
    )
    assert foreign["capture_id"] is None
    assert foreign["capture_error"] == "RuntimeError"
