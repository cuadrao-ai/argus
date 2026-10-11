from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from argus.llm.openrouter import (
    begin_openrouter_route_receipt_capture,
    end_openrouter_route_receipt_capture,
    openrouter_request_guard,
)

from tests.evals.business_eval import (
    APPROVED_JUDGE_MODELS,
    CRITERIA,
    RUBRIC_VERSION,
    RUNTIME_CANDIDATES,
    JudgeVerdict,
    check_calibration,
    fixture_digest,
    judge_reply,
    load_calibration,
    load_cases,
    score_runtime_capture,
)
from tests.evals.business_runtime_capture import CaseCapture, capture_case
from tests.interpreter_prompt_surface import model_facing_surface

BUSINESS_OWNERS = (
    "src/argus/agent_runtime/business/interpretation.py",
    "src/argus/domain/business/tools/declarations.py",
)
CASE_IDS = (
    "es_owner_funds_no_receipt",
    "en_funding_correction",
    "es_owner_does_not_know_amount",
    "es_cross_client_approval_injection",
    "en_amount_not_supplied",
    "en_replay_stale_and_current_grant",
    "en_revoked_accountant_read",
)
CASE_STEP_COUNTS = (4, 3, 2, 1, 1, 6, 3)
HUMAN_ONLY_CASE = "en_revoked_accountant_read"
SCRIPTED_FOREIGN_READ_CASE = "es_cross_client_approval_injection"


def _git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(("git", *args), cwd=root, stderr=subprocess.DEVNULL)


def _committed_head(root: Path, candidate_sha: str) -> None:
    if _git(root, "rev-parse", "HEAD").decode().strip() != candidate_sha:
        raise ValueError("Business acceptance candidate does not match executed HEAD")
    if _git(root, "status", "--porcelain"):
        raise ValueError("Business acceptance requires a clean executed worktree")


def _validate_case_manifest(cases: list[dict[str, Any]]) -> None:
    if tuple((case["id"], len(case["steps"])) for case in cases) != tuple(
        zip(CASE_IDS, CASE_STEP_COUNTS, strict=True)
    ):
        raise ValueError(
            "Business acceptance requires the frozen seven-case step manifest"
        )


def _calibration(root: Path, path: Path | None, judge_model: str) -> dict[str, Any]:
    unavailable = {"status": "unavailable", "judge_model": judge_model, "report": None}
    if path is None:
        return unavailable
    try:
        relative = path.resolve().relative_to(root.resolve())
        if relative.parts[:3] != ("docs", "reports", "evidence"):
            return unavailable
        committed = _git(root, "show", f"HEAD:{relative.as_posix()}")
        if path.read_bytes() != committed:
            return unavailable
        report = json.loads(committed)
        examples = load_calibration()
        verdicts = {
            name: JudgeVerdict.model_validate(value)
            for name, value in report["verdicts"].items()
        }
        receipts = report["call_receipts"]
        settings = report["request_settings"]
        calibration_sha = hashlib.sha256(
            Path(__file__)
            .with_name("business_cases")
            .joinpath("rubric_calibration.yaml")
            .read_bytes()
        ).hexdigest()
        if (
            report["schema_version"] != "business_e1_judge_calibration_v1"
            or report["status"] != "passed"
            or report["judge_model"] != judge_model
            or report["rubric_version"] != RUBRIC_VERSION
            or report["fixture_sha256"] != calibration_sha
            or set(verdicts) != {example["id"] for example in examples}
            or check_calibration(examples, verdicts)
            or len(receipts) != len(examples)
            or any(
                receipt.get("task") != "chat_composer"
                or receipt.get("schema_name") != "BusinessE1JudgeVerdict"
                or receipt.get("mode") != "json_schema"
                or receipt.get("model") != judge_model
                or receipt.get("outcome") != "succeeded"
                or not isinstance(receipt.get("latency_ms"), int)
                or not isinstance(receipt.get("usage_cost_usd"), (int, float))
                for receipt in receipts
            )
            or len(settings) != len(examples)
            or any(
                setting.get("task") != "chat_composer"
                or setting.get("model") != judge_model
                or setting.get("schema_name") != "BusinessE1JudgeVerdict"
                or not isinstance(setting.get("parameters"), dict)
                or not setting["parameters"]
                for setting in settings
            )
            or not isinstance(report["total_cost_usd"], (int, float))
            or not isinstance(report["total_latency_ms"], int)
        ):
            return unavailable
    except (KeyError, TypeError, ValueError, OSError, subprocess.CalledProcessError):
        return unavailable
    return {
        "status": "passed",
        "judge_model": judge_model,
        "report": relative.as_posix(),
        "rubric_version": RUBRIC_VERSION,
        "fixture_sha256": calibration_sha,
    }


def _settings(task: str, payload: dict[str, object]) -> dict[str, Any]:
    response_format = payload.get("response_format")
    schema = (
        response_format.get("json_schema", {})
        if isinstance(response_format, dict)
        else {}
    )
    return {
        "task": task,
        "model": payload.get("model"),
        "schema_name": schema.get("name") if isinstance(schema, dict) else None,
        "parameters": {
            key: payload[key]
            for key in (
                "temperature",
                "top_p",
                "seed",
                "max_tokens",
                "max_completion_tokens",
                "reasoning",
                "provider",
            )
            if key in payload
        },
        "returned_model": None,
    }


def _aggregate_verdict(verdicts: list[JudgeVerdict | None]) -> JudgeVerdict | None:
    if not verdicts or any(verdict is None for verdict in verdicts):
        return None
    criteria = {
        name: all(getattr(verdict, name) for verdict in verdicts if verdict)
        for name in CRITERIA
    }
    return JudgeVerdict(
        passed=all(criteria.values()),
        evidence="Per-reply judge evidence is retained in the Business capture sidecar.",
        **criteria,
    )


def _usage(receipts: list[dict[str, Any]]) -> tuple[float | None, int | None]:
    if not receipts:
        return None, None
    costs = [receipt.get("usage_cost_usd") for receipt in receipts]
    latencies = [receipt.get("latency_ms") for receipt in receipts]
    return (
        sum(costs) if all(isinstance(cost, (int, float)) for cost in costs) else None,
        sum(latencies)
        if all(isinstance(latency, int) for latency in latencies)
        else None,
    )


def _step_receipt_failures(
    case: dict[str, Any], capture: CaseCapture | None, runtime_model: str
) -> list[str]:
    if capture is None or len(capture.step_route_receipts) != len(case["steps"]):
        return ["step_route_receipts_missing"]
    failures = []
    if len(capture.graph_run_ids) != sum(
        step["actor"] == "owner_a" for step in case["steps"]
    ):
        failures.append("graph_run_count")
    for index, (step, receipts) in enumerate(
        zip(case["steps"], capture.step_route_receipts, strict=True)
    ):
        expected = (
            ("BusinessInterpretation", "BusinessReply")
            if step["actor"] == "owner_a" and not step.get("replay")
            else ()
        )
        if len(receipts) != len(expected) or any(
            receipt.get("task") != "interpretation"
            or receipt.get("schema_name") != schema
            or receipt.get("mode") != "json_schema"
            or receipt.get("model") != runtime_model
            or receipt.get("outcome") != "succeeded"
            for receipt, schema in zip(receipts, expected, strict=False)
        ):
            failures.append(f"step_{index}.route_receipts")
    return failures


def _apply_reachability_gate(case_id: str, score: dict[str, Any]) -> dict[str, Any]:
    if case_id == SCRIPTED_FOREIGN_READ_CASE:
        score["failed_checks"].append("foreign_target_absent_from_model_input")
        score["status"] = "unavailable"
    return score


def _report(
    *,
    candidate_sha: str,
    runtime_model: str,
    judge_model: str,
    surface: dict[str, dict[str, object]],
    calibration: dict[str, Any],
    cases: list[dict[str, Any]],
) -> dict[str, Any]:
    totals = {
        status: sum(case["status"] == status for case in cases)
        for status in ("passed", "failed", "unavailable")
    }
    status = (
        "passed"
        if calibration["status"] == "passed"
        and totals == {"passed": 7, "failed": 0, "unavailable": 0}
        else "failed"
        if totals["failed"]
        else "unavailable"
    )
    return {
        "schema_version": "business_acceptance_v1",
        "measurement_kind": "initial_measurement",
        "scope": "business",
        "candidate_sha": candidate_sha,
        "surface": surface,
        "fixture_sha256": fixture_digest(),
        "case_ids": list(CASE_IDS),
        "step_count": 20,
        "runtime_model": runtime_model,
        "judge_model": judge_model,
        "calibration": calibration,
        "cases": cases,
        "totals": totals,
        "status": status,
    }


async def run_business_acceptance(
    *,
    repository_root: Path,
    candidate_sha: str,
    dsn: str,
    runtime_model: str,
    judge_model: str,
    calibration_report: Path | None,
    interpreter_factory: Callable[[str, int, dict[str, str]], Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    root = repository_root.resolve()
    _committed_head(root, candidate_sha)
    if (
        runtime_model not in RUNTIME_CANDIDATES
        or judge_model not in APPROVED_JUDGE_MODELS
    ):
        raise ValueError("Business acceptance requires approved exact model IDs")
    cases = load_cases()
    _validate_case_manifest(cases)
    measured_surface = model_facing_surface(root)
    surface = {owner: measured_surface[owner] for owner in BUSINESS_OWNERS}
    calibration = _calibration(root, calibration_report, judge_model)
    sidecar: dict[str, Any] = {
        "schema_version": "business_e1_request_settings_v1",
        "candidate_sha": candidate_sha,
        "fixture_sha256": fixture_digest(),
        "rubric_version": RUBRIC_VERSION,
        "surface": surface,
        "runtime_model": runtime_model,
        "judge_model": judge_model,
        "requests": [],
        "cases": [],
    }
    if calibration["status"] != "passed":
        unavailable = [
            score_runtime_capture(
                case=case,
                candidate_sha=candidate_sha,
                runtime_model=runtime_model,
                judge_model=judge_model,
                observed_steps=None,
                call_receipts=[],
                total_cost_usd=None,
                total_latency_ms=None,
                judge_verdict=None,
            )
            for case in cases
        ]
        return (
            _report(
                candidate_sha=candidate_sha,
                runtime_model=runtime_model,
                judge_model=judge_model,
                surface=surface,
                calibration=calibration,
                cases=unavailable,
            ),
            sidecar,
        )

    def capture_settings(task: str, payload: dict[str, object]) -> dict[str, object]:
        sidecar["requests"].append(_settings(task, payload))
        return payload

    scores = []
    with openrouter_request_guard(capture_settings):
        for case in cases:
            if case["id"] == SCRIPTED_FOREIGN_READ_CASE:
                score = score_runtime_capture(
                    case=case,
                    candidate_sha=candidate_sha,
                    runtime_model=runtime_model,
                    judge_model=judge_model,
                    observed_steps=None,
                    call_receipts=[],
                    total_cost_usd=None,
                    total_latency_ms=None,
                    judge_verdict=None,
                )
                scores.append(_apply_reachability_gate(case["id"], score))
                sidecar["cases"].append(
                    {
                        "case_id": case["id"],
                        "capture_error": "foreign_target_absent_from_model_input",
                        "capture_id": None,
                        "db_namespace": None,
                        "graph_run_ids": [],
                        "tool_records": [],
                        "saved_states": [],
                        "observed_steps": None,
                        "step_route_receipts": [],
                        "attempted_step_route_receipts": {},
                        "replies": [],
                        "runtime_receipts": [],
                    }
                )
                continue
            capture: CaseCapture | None = None
            capture_error = None
            attempted_step_receipts: dict[int, list[dict[str, Any]]] = {}
            try:
                capture = await capture_case(
                    case,
                    dsn=dsn,
                    interpreter_factory=interpreter_factory,
                    receipt_sink=attempted_step_receipts.__setitem__,
                )
            except Exception as error:
                capture_error = type(error).__name__
            step_receipts = capture.step_route_receipts if capture else []
            runtime_receipts = [
                receipt
                for index in sorted(attempted_step_receipts)
                for receipt in attempted_step_receipts[index]
            ]
            owner_steps = [
                (index, step)
                for index, step in enumerate(case["steps"])
                if step["actor"] == "owner_a"
            ]
            reply_evidence = []
            judge_receipts: list[dict[str, Any]] = []
            verdicts: list[JudgeVerdict | None] = []
            prior: dict[str, tuple[int, str, dict[str, Any], JudgeVerdict | None]] = {}
            if capture and len(capture.replies) == len(owner_steps) == len(
                capture.saved_states
            ):
                for position, (step_index, step) in enumerate(owner_steps):
                    reply = capture.replies[position]
                    saved_state = capture.saved_states[position]
                    earlier = prior.get(step["source"])
                    reused = (
                        earlier is not None
                        and step.get("replay")
                        and earlier[1] == reply
                        and earlier[2] == saved_state
                    )
                    if reused:
                        verdict = earlier[3]
                        prior_step = earlier[0]
                        current_receipts: list[dict[str, Any]] = []
                    else:
                        judge_token = begin_openrouter_route_receipt_capture()
                        try:
                            verdict = await judge_reply(
                                case_id=case["id"],
                                owner_message=step["message"],
                                reply=reply,
                                saved_state=saved_state,
                                judge_model=judge_model,
                            )
                        except Exception:
                            verdict = None
                        current_receipts = [
                            receipt.as_dict()
                            for receipt in end_openrouter_route_receipt_capture(
                                judge_token
                            )
                        ]
                        judge_receipts.extend(current_receipts)
                        prior_step = None
                    prior[step["source"]] = (step_index, reply, saved_state, verdict)
                    verdicts.append(verdict)
                    reply_evidence.append(
                        {
                            "step_index": step_index,
                            "replay": bool(step.get("replay")),
                            "reply": reply,
                            "saved_state": saved_state,
                            "judge_verdict": verdict.model_dump() if verdict else None,
                            "judge_receipts": current_receipts,
                            "reused_from_step": prior_step,
                        }
                    )
            receipts = runtime_receipts + judge_receipts
            human_only = case["id"] == HUMAN_ONLY_CASE
            cost, latency = (
                (0.0, 0)
                if human_only and capture is not None and not receipts
                else _usage(receipts)
            )
            provenance = (
                {
                    "capture_id": capture.capture_id,
                    "db_namespace": capture.db_namespace,
                    "candidate_sha": candidate_sha,
                    **(
                        {"graph_run_id": capture.graph_run_ids[0]}
                        if capture.graph_run_ids and not human_only
                        else {}
                    ),
                }
                if capture
                else None
            )
            score = score_runtime_capture(
                case=case,
                candidate_sha=candidate_sha,
                runtime_model=runtime_model,
                judge_model=judge_model,
                observed_steps=capture.observed_steps if capture else None,
                call_receipts=receipts,
                total_cost_usd=cost,
                total_latency_ms=latency,
                judge_verdict=_aggregate_verdict(verdicts) if not human_only else None,
                adapter_provenance=provenance,
            )
            receipt_failures = _step_receipt_failures(case, capture, runtime_model)
            if not human_only:
                if len(judge_receipts) != sum(
                    item["reused_from_step"] is None for item in reply_evidence
                ) or any(
                    receipt.get("task") != "chat_composer"
                    or receipt.get("schema_name") != "BusinessE1JudgeVerdict"
                    or receipt.get("mode") != "json_schema"
                    or receipt.get("model") != judge_model
                    or receipt.get("outcome") != "succeeded"
                    for receipt in judge_receipts
                ):
                    receipt_failures.append("per_reply_judge_receipts_incomplete")
            if receipt_failures:
                score["failed_checks"].extend(receipt_failures)
                if score["status"] == "passed":
                    score["status"] = "unavailable"
            scores.append(score)
            sidecar["cases"].append(
                {
                    "case_id": case["id"],
                    "capture_error": capture_error,
                    "capture_id": capture.capture_id if capture else None,
                    "db_namespace": capture.db_namespace if capture else None,
                    "graph_run_ids": capture.graph_run_ids if capture else [],
                    "tool_records": capture.tool_records if capture else [],
                    "saved_states": capture.saved_states if capture else [],
                    "observed_steps": capture.observed_steps if capture else None,
                    "step_route_receipts": step_receipts,
                    "attempted_step_route_receipts": attempted_step_receipts,
                    "replies": reply_evidence,
                    "runtime_receipts": runtime_receipts,
                }
            )
    return (
        _report(
            candidate_sha=candidate_sha,
            runtime_model=runtime_model,
            judge_model=judge_model,
            surface=surface,
            calibration=calibration,
            cases=scores,
        ),
        sidecar,
    )
