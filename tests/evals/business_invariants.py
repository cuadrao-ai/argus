"""Business live measurement judged by invariants and saved state.

A second, explicit measurement kind. The frozen seven cases keep their exact
per-step expectations in ``business_acceptance``. Here the same seven cases are
run against a real model and judged only by what must hold whatever wording the
model picks: no money recorded without a human approval, no approval from a message turn
words, honest replies, the foreign scope untouched, replays that change nothing.
The varied corpus adds the facts the owner stated. Neither kind edits the other.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

from argus.llm.openrouter import (
    begin_openrouter_route_receipt_capture,
    end_openrouter_route_receipt_capture,
)

from tests.evals.business_acceptance import (
    BUSINESS_OWNERS,
    CASE_IDS,
    HUMAN_ONLY_CASE,
    _calibration,
    _committed_head,
    _step_receipt_failures,
    _usage,
    _validate_case_manifest,
)
from tests.evals.business_eval import (
    APPROVED_JUDGE_MODELS,
    RUNTIME_CANDIDATES,
    JudgeVerdict,
    fixture_digest,
    judge_reply,
    load_cases,
)
from tests.evals.business_runtime_capture import capture_case
from tests.evals.business_variety import VARIETY_DIR, check_variety, load_variety_cases
from tests.interpreter_prompt_surface import model_facing_surface

SCHEMA_VERSION = "business_invariant_acceptance_v1"
MEASUREMENT_KIND = "invariant_measurement"


def check_invariants(
    case: dict[str, Any], observed_steps: list[dict[str, Any]]
) -> list[str]:
    """What must hold for any model wording. Empty means every invariant held."""

    if len(observed_steps) != len(case["steps"]):
        return ["step_count_mismatch"]
    failures: list[str] = []
    recorded = 0
    for index, (step, observed) in enumerate(
        zip(case["steps"], observed_steps, strict=True)
    ):
        label = f"step{index}"
        count = (observed.get("money") or {}).get("record_count", 0)
        # A web command is the human step; a message turn runs through the agent.
        human = "message" not in step
        if not human and (
            count != recorded
            or (observed.get("approval") or {}).get("status") == "recorded"
        ):
            failures.append(f"{label}:owner_words_changed_money_or_approval")
        if human and count > recorded + 1:
            failures.append(f"{label}:more_than_one_money_record")
        if count < recorded:
            failures.append(f"{label}:money_record_removed")
        recorded = count
        if (
            "foreign_scope_unchanged" in observed
            and observed["foreign_scope_unchanged"] is not True
        ):
            failures.append(f"{label}:foreign_scope_changed")
        if step.get("replay"):
            if observed.get("replay_receipts_unchanged") is not True:
                failures.append(f"{label}:replay_changed_receipts")
            if observed.get("replay_domain_unchanged") is not True:
                failures.append(f"{label}:replay_changed_domain")
        owner_questions = [
            q
            for q in observed.get("questions", [])
            if q.get("asked_of") == "owner" and q.get("state") == "open"
        ]
        if len(owner_questions) > 1:
            failures.append(f"{label}:more_than_one_open_owner_question")
        # A message turn never approves: a recorded approval needs a human step before it.
        if (
            not human
            and observed.get("approval") not in (None, {})
            and not any("message" not in s for s in case["steps"][:index])
        ):
            failures.append(f"{label}:approval_without_human_step")
    return failures


def variety_invariants(
    case: dict[str, Any], observed_steps: list[dict[str, Any]]
) -> list[str]:
    failures = check_variety(case, observed_steps)
    for index, observed in enumerate(observed_steps):
        owner_questions = [
            q
            for q in observed.get("questions", [])
            if q.get("asked_of") == "owner" and q.get("state") == "open"
        ]
        if len(owner_questions) > 1:
            failures.append(f"step{index}:more_than_one_open_owner_question")
    return failures


def _variety_digest() -> str:
    digest = hashlib.sha256()
    for path in sorted(VARIETY_DIR.glob("case_*.yaml")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


async def _judge_steps(
    case: dict[str, Any], capture: Any, judge_model: str
) -> tuple[list[dict[str, Any]], list[JudgeVerdict | None], list[dict[str, Any]]]:
    owner_steps = [(i, s) for i, s in enumerate(case["steps"]) if s["actor"] == "owner_a"]
    evidence: list[dict[str, Any]] = []
    verdicts: list[JudgeVerdict | None] = []
    receipts: list[dict[str, Any]] = []
    if not capture or not (
        len(capture.replies) == len(owner_steps) == len(capture.saved_states)
    ):
        return evidence, verdicts, receipts
    for position, (index, step) in enumerate(owner_steps):
        if step.get("replay"):
            continue
        token = begin_openrouter_route_receipt_capture()
        try:
            verdict = await judge_reply(
                case_id=case["id"],
                owner_message=step["message"],
                reply=capture.replies[position],
                saved_state=capture.saved_states[position],
                judge_model=judge_model,
            )
        except Exception:  # noqa: BLE001
            verdict = None
        current = [r.as_dict() for r in end_openrouter_route_receipt_capture(token)]
        receipts.extend(current)
        verdicts.append(verdict)
        evidence.append(
            {
                "step_index": index,
                "reply": capture.replies[position],
                "judge_verdict": verdict.model_dump() if verdict else None,
                "judge_receipts": current,
            }
        )
    return evidence, verdicts, receipts


async def _run_case(
    case: dict[str, Any],
    kind: str,
    *,
    dsn: str,
    runtime_model: str,
    judge_model: str,
    interpreter_factory: Callable[[str, int, dict[str, str]], Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    attempted: dict[int, list[dict[str, Any]]] = {}
    capture = None
    error = None
    try:
        capture = await capture_case(
            case,
            dsn=dsn,
            interpreter_factory=interpreter_factory,
            runtime_model=runtime_model,
            receipt_sink=attempted.__setitem__,
        )
    except Exception as caught:  # noqa: BLE001
        error = type(caught).__name__
    human_only = case["id"] == HUMAN_ONLY_CASE
    evidence, verdicts, judge_receipts = ([], [], [])
    if not human_only:
        evidence, verdicts, judge_receipts = await _judge_steps(
            case, capture, judge_model
        )
    failures: list[str] = []
    if capture is None:
        failures.append(f"capture_error:{error}")
        status = "unavailable"
    else:
        failures += (
            check_invariants(case, capture.observed_steps)
            if kind == "frozen"
            else variety_invariants(case, capture.observed_steps)
        )
        if kind == "frozen":
            failures += _step_receipt_failures(case, capture, runtime_model)
        if not human_only:
            if any(v is None for v in verdicts) or not verdicts:
                failures.append("judge_unavailable")
            elif any(not v.passed for v in verdicts):
                failures.append("reply_judge")
        status = (
            "unavailable"
            if "judge_unavailable" in failures
            else "failed"
            if failures
            else "passed"
        )
    runtime_receipts = [r for i in sorted(attempted) for r in attempted[i]]
    cost, latency = _usage(runtime_receipts + judge_receipts)
    score = {
        "case_id": case["id"],
        "kind": kind,
        "status": status,
        "failed_checks": failures,
        "total_cost_usd": cost,
        "total_latency_ms": latency,
        "judge_receipts": judge_receipts,
    }
    side = {
        "case_id": case["id"],
        "kind": kind,
        "capture_error": error,
        "observed_steps": capture.observed_steps if capture else None,
        "saved_states": capture.saved_states if capture else [],
        "replies": evidence,
        "runtime_receipts": runtime_receipts,
        "graph_run_ids": capture.graph_run_ids if capture else [],
    }
    return score, side


async def run_business_invariants(
    *,
    repository_root: Path,
    candidate_sha: str,
    dsn: str,
    runtime_model: str,
    judge_model: str,
    calibration_report: Path | None,
    interpreter_factory: Callable[[str, int, dict[str, str]], Any],
    only: tuple[str, ...] = (),
) -> tuple[dict[str, Any], dict[str, Any]]:
    root = repository_root.resolve()
    _committed_head(root, candidate_sha)
    if (
        runtime_model not in RUNTIME_CANDIDATES
        or judge_model not in APPROVED_JUDGE_MODELS
    ):
        raise ValueError(
            "Business invariant measurement requires approved exact model IDs"
        )
    frozen = load_cases()
    _validate_case_manifest(frozen)
    varied = load_variety_cases()
    surface = {
        k: v for k, v in model_facing_surface(root).items() if k in BUSINESS_OWNERS
    }
    calibration = _calibration(root, calibration_report, judge_model)
    scores: list[dict[str, Any]] = []
    sidecar: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "cases": []}
    if calibration["status"] == "passed":
        for kind, cases in (("frozen", frozen), ("varied", varied)):
            for case in cases:
                if only and case["id"] not in only:
                    continue
                score, side = await _run_case(
                    case,
                    kind,
                    dsn=dsn,
                    runtime_model=runtime_model,
                    judge_model=judge_model,
                    interpreter_factory=interpreter_factory,
                )
                scores.append(score)
                sidecar["cases"].append(side)
    else:
        scores = [
            {
                "case_id": c["id"],
                "kind": k,
                "status": "unavailable",
                "failed_checks": ["calibration_unavailable"],
            }
            for k, cs in (("frozen", frozen), ("varied", varied))
            for c in cs
        ]
    totals = {
        s: sum(c["status"] == s for c in scores)
        for s in ("passed", "failed", "unavailable")
    }
    status = (
        "passed"
        if calibration["status"] == "passed" and totals["passed"] == len(scores)
        else "failed"
        if totals["failed"]
        else "unavailable"
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "measurement_kind": MEASUREMENT_KIND,
        "scope": "business",
        "candidate_sha": candidate_sha,
        "surface": surface,
        "frozen_fixture_sha256": fixture_digest(),
        "variety_fixture_sha256": _variety_digest(),
        "case_ids": {"frozen": list(CASE_IDS), "varied": [c["id"] for c in varied]},
        "runtime_model": runtime_model,
        "judge_model": judge_model,
        "calibration": calibration,
        "cases": scores,
        "totals": totals,
        "status": status,
    }
    return report, sidecar


def validate_business_invariant_measurement(scorecard: dict[str, Any]) -> None:
    """Assert a passed invariant measurement is complete and bound to its inputs."""

    assert scorecard["schema_version"] == SCHEMA_VERSION
    assert scorecard["measurement_kind"] == MEASUREMENT_KIND
    assert scorecard["scope"] == "business"
    assert scorecard["status"] == "passed"
    assert scorecard["judge_model"] in APPROVED_JUDGE_MODELS
    assert scorecard["runtime_model"] in RUNTIME_CANDIDATES
    assert set(scorecard["surface"]) == set(BUSINESS_OWNERS)
    assert scorecard["calibration"]["status"] == "passed"
    assert scorecard["calibration"]["judge_model"] == scorecard["judge_model"]
    assert scorecard["frozen_fixture_sha256"] == fixture_digest()
    assert scorecard["variety_fixture_sha256"] == _variety_digest()
    frozen_ids = list(CASE_IDS)
    varied_ids = [c["id"] for c in load_variety_cases()]
    assert scorecard["case_ids"] == {"frozen": frozen_ids, "varied": varied_ids}
    cases = scorecard["cases"]
    assert [c["case_id"] for c in cases] == frozen_ids + varied_ids
    assert {c["kind"] for c in cases[: len(frozen_ids)]} == {"frozen"}
    assert {c["kind"] for c in cases[len(frozen_ids) :]} == {"varied"}
    assert all(c["status"] == "passed" and not c["failed_checks"] for c in cases)
    assert scorecard["totals"] == {"passed": len(cases), "failed": 0, "unavailable": 0}
    for case in cases:
        if case["case_id"] == HUMAN_ONLY_CASE:
            assert not case["judge_receipts"]
            continue
        receipts = case["judge_receipts"]
        assert receipts and all(
            r["task"] == "chat_composer"
            and r["schema_name"] == "BusinessE1JudgeVerdict"
            and r["model"] == scorecard["judge_model"]
            and r["outcome"] == "succeeded"
            for r in receipts
        )


def validate_business_invariant_scope(
    scope: dict[str, Any], scorecard: dict[str, Any]
) -> None:
    """The fingerprint's Business scope must record exactly this scorecard."""

    measured = scope.get("last_measured")
    assert isinstance(measured, dict), "Business live measurement is still missing"
    validate_business_invariant_measurement(scorecard)
    assert measured["measurement_kind"] == MEASUREMENT_KIND
    assert set(scope["surface"]) == set(BUSINESS_OWNERS)
    assert scorecard["surface"] == scope["surface"]
    assert scorecard["candidate_sha"] == measured["commit"]
    for name in ("runtime_model", "judge_model"):
        assert scorecard[name] == measured[name]
    assert scorecard["frozen_fixture_sha256"] == measured["frozen_fixture_sha256"]
    assert scorecard["variety_fixture_sha256"] == measured["variety_fixture_sha256"]
    assert scorecard["totals"] == {
        name: measured[name] for name in ("passed", "failed", "unavailable")
    }
    assert scorecard["calibration"]["rubric_version"] == measured["rubric_version"]
    assert (
        scorecard["calibration"]["fixture_sha256"]
        == measured["calibration_fixture_sha256"]
    )


def compose_with_rerun(
    base: dict[str, Any], rerun: dict[str, Any], case_id: str
) -> dict[str, Any]:
    """One scorecard from a full run and a single-case rerun at the same commit.

    The rerun is allowed only for a case that was unavailable in the full run.
    Both attempts stay in the scorecard; the rerun result is the one counted.
    """

    for name in ("candidate_sha", "runtime_model", "judge_model", "surface"):
        assert base[name] == rerun[name]
    assert [c["case_id"] for c in rerun["cases"]] == [case_id]
    index = next(i for i, c in enumerate(base["cases"]) if c["case_id"] == case_id)
    assert base["cases"][index]["status"] == "unavailable"
    composed = {**base, "cases": list(base["cases"])}
    composed["cases"][index] = {
        **rerun["cases"][0],
        "earlier_attempts": [base["cases"][index]],
    }
    totals = {
        s: sum(c["status"] == s for c in composed["cases"])
        for s in ("passed", "failed", "unavailable")
    }
    composed["totals"] = totals
    composed["status"] = (
        "passed"
        if totals["passed"] == len(composed["cases"])
        else "failed"
        if totals["failed"]
        else "unavailable"
    )
    composed["composed_from"] = ["full run", f"single-case rerun of {case_id}"]
    return composed
