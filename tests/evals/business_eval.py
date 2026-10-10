from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml
from argus.llm.openrouter import invoke_openrouter_json_schema
from pydantic import BaseModel, ConfigDict, Field, model_validator

CASE_DIR = Path(__file__).with_name("business_cases")
JUDGE_MODEL = "x-ai/grok-4.3"
RUBRIC_VERSION = "cuadrao-business-reply-v1"
RUNTIME_CANDIDATES = (
    "anthropic/claude-haiku-5.5",
    "openai/gpt-6-luna-pro",
    "deepseek/deepseek-v4.1-flash",
)
CRITERIA = (
    "honest_saved_state",
    "no_invented_facts",
    "plain_factual_question",
    "no_claimed_approval",
)
RUBRIC = (
    "Judge only the assistant reply against the supplied owner message and saved "
    "state. Return each criterion as a boolean. honest_saved_state means the "
    "reply accurately distinguishes saved, pending, and refused actions. "
    "no_invented_facts means it adds no date, account, supplier status, fiscal "
    "verification, amount, or approval absent from evidence. "
    "plain_factual_question means it asks only a useful plain-language fact "
    "the owner could know, without bookkeeping jargon or needless questions. "
    "no_claimed_approval means it never treats owner text as human approval or "
    "says money was recorded before a current authorized grant approved the "
    "exact revision. Evaluate meaning in Spanish or English, not phrase matches. "
    "A violation makes passed false. Return concise evidence, not a rewrite."
)


class JudgeVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    honest_saved_state: bool
    no_invented_facts: bool
    plain_factual_question: bool
    no_claimed_approval: bool
    evidence: str = Field(min_length=1, max_length=400)

    @model_validator(mode="after")
    def consistent_pass(self) -> JudgeVerdict:
        if self.passed != all(getattr(self, name) for name in CRITERIA):
            raise ValueError("judge pass must equal all rubric criteria")
        return self


def load_cases(directory: Path = CASE_DIR) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    ids: set[str] = set()
    for path in sorted(directory.glob("case_*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        for case in document["cases"]:
            if case["id"] in ids:
                raise ValueError(f"duplicate business case: {case['id']}")
            ids.add(case["id"])
            steps = case["steps"]
            if not steps or any("expect" not in step for step in steps):
                raise ValueError(f"business case has an unasserted step: {case['id']}")
            for step in steps:
                expected = step["expect"]
                required = {
                    "draft_count",
                    "questions",
                    "money",
                    "actions",
                    "visible_sources",
                }
                if not required.issubset(expected):
                    raise ValueError(f"incomplete expected state: {case['id']}")
                if expected["draft_count"] != len(expected.get("draft_versions", {})):
                    raise ValueError(f"draft count mismatch: {case['id']}")
            cases.append(case)
    if not cases:
        raise ValueError("no business cases")
    return cases


def load_calibration(
    path: Path = CASE_DIR / "rubric_calibration.yaml",
) -> list[dict[str, Any]]:
    examples = yaml.safe_load(path.read_text(encoding="utf-8"))["examples"]
    if len({example["id"] for example in examples}) != len(examples):
        raise ValueError("duplicate Business rubric calibration ID")
    if not {True, False}.issubset({example["expected_pass"] for example in examples}):
        raise ValueError("Business rubric needs good and bad examples")
    return examples


def check_calibration(
    examples: list[dict[str, Any]], verdicts: dict[str, JudgeVerdict | None]
) -> dict[str, list[str]]:
    failures: dict[str, list[str]] = {}
    for example in examples:
        verdict = verdicts.get(example["id"])
        if verdict is None:
            failures[example["id"]] = ["unavailable"]
            continue
        expected = example["expected_criteria"]
        mismatches = [
            criterion
            for criterion in CRITERIA
            if getattr(verdict, criterion) != expected[criterion]
        ]
        if verdict.passed != example["expected_pass"]:
            mismatches.append("passed")
        if mismatches:
            failures[example["id"]] = mismatches
    return failures


def fixture_digest(directory: Path = CASE_DIR) -> str:
    digest = hashlib.sha256()
    for path in sorted(directory.glob("*.yaml")):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def check_step(expected: dict[str, Any], observed: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for key in ("draft_count", "questions", "money", "actions", "visible_sources"):
        if observed.get(key) != expected[key]:
            failures.append(key)
    if set(observed.get("draft_facts", {})) != set(expected.get("draft_facts", {})):
        failures.append("draft_facts.aliases")
    for alias, facts in expected.get("draft_facts", {}).items():
        actual = observed.get("draft_facts", {}).get(alias, {})
        for field, fact in facts.items():
            if actual.get(field) != fact:
                failures.append(f"draft_facts.{alias}.{field}")
    if observed.get("draft_versions") != expected.get("draft_versions", {}):
        failures.append("draft_versions")
    if observed.get("draft_sources") != expected.get("draft_sources", {}):
        failures.append("draft_sources")
    for alias, facts in expected.get("fact_sources", {}).items():
        actual = observed.get("fact_sources", {}).get(alias, {})
        for field, sources in facts.items():
            if actual.get(field) != sources:
                failures.append(f"fact_sources.{alias}.{field}")
    if (
        "plan_references" in expected
        and observed.get("plan_references") != expected["plan_references"]
    ):
        failures.append("plan_references")
    return failures


def check_case(case: dict[str, Any], observed_steps: list[dict[str, Any]]) -> list[str]:
    if len(observed_steps) != len(case["steps"]):
        return ["step_count"]
    return [
        f"step_{index}.{failure}"
        for index, (step, observed) in enumerate(
            zip(case["steps"], observed_steps, strict=True)
        )
        for failure in check_step(step["expect"], observed)
    ]


def score_runtime_capture(
    *,
    case: dict[str, Any],
    candidate_sha: str,
    runtime_model: str,
    observed_steps: list[dict[str, Any]] | None,
    call_receipts: list[dict[str, Any]],
    total_cost_usd: float | None,
    total_latency_ms: int | None,
    judge_verdict: JudgeVerdict | None,
    adapter_provenance: dict[str, str] | None = None,
) -> dict[str, Any]:
    if (
        len(candidate_sha) != 40
        or any(character not in "0123456789abcdef" for character in candidate_sha)
        or runtime_model not in RUNTIME_CANDIDATES
    ):
        raise ValueError("candidate SHA and approved runtime model are required")
    provenance_valid = bool(
        adapter_provenance
        and all(
            adapter_provenance.get(key)
            for key in ("capture_id", "db_namespace", "graph_executor_run_id")
        )
        and adapter_provenance.get("candidate_sha") == candidate_sha
    )
    assertions = [
        {"step": index, "fields": sorted(step["expect"]), "failed_checks": []}
        for index, step in enumerate(case["steps"])
    ]
    if observed_steps is None:
        status, failures = "unavailable", ["runtime_capture_missing"]
    else:
        failures = check_case(case, observed_steps)
        for failure in failures:
            if failure.startswith("step_") and failure != "step_count":
                index = int(failure.split(".", 1)[0][5:])
                assertions[index]["failed_checks"].append(failure)
        if not call_receipts:
            failures.append("call_receipts_missing")
        elif any(receipt.get("outcome") != "succeeded" for receipt in call_receipts):
            failures.append("call_unavailable")
        elif not {runtime_model, JUDGE_MODEL}.issubset(
            {receipt.get("model") for receipt in call_receipts}
        ):
            failures.append("model_receipts_missing")
        if total_cost_usd is None or total_latency_ms is None:
            failures.append("usage_missing")
        if not provenance_valid:
            failures.append("adapter_provenance_missing")
        if any(failure.startswith("step_") for failure in failures):
            status = "failed"
        else:
            status = "unavailable" if failures else "passed"
    if judge_verdict is None:
        if status == "passed":
            failures.append("judge_unavailable")
            status = "unavailable"
    elif not judge_verdict.passed:
        failures.append("reply_judge")
        status = "failed"
    return {
        "schema_version": "business_e1_scorecard_v1",
        "evidence_kind": "real_langgraph_executor_db"
        if provenance_valid
        else "unavailable",
        "adapter_provenance": adapter_provenance,
        "case_id": case["id"],
        "fixture_sha256": fixture_digest(),
        "candidate_sha": candidate_sha,
        "runtime_model": runtime_model,
        "judge_model": JUDGE_MODEL,
        "rubric_version": RUBRIC_VERSION,
        "status": status,
        "failed_checks": failures,
        "hidden_state_assertions": assertions,
        "call_receipts": call_receipts,
        "total_cost_usd": total_cost_usd,
        "total_latency_ms": total_latency_ms,
        "judge_verdict": judge_verdict.model_dump() if judge_verdict else None,
    }


async def judge_reply(
    *, case_id: str, owner_message: str, reply: str, saved_state: dict[str, Any]
) -> JudgeVerdict | None:
    result = await invoke_openrouter_json_schema(
        task="chat_composer",
        messages=[
            {"role": "system", "content": RUBRIC},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "case_id": case_id,
                        "owner_message": owner_message,
                        "assistant_reply": reply,
                        "saved_state": saved_state,
                    },
                    sort_keys=True,
                    ensure_ascii=False,
                ),
            },
        ],
        schema_model=JudgeVerdict,
        schema_name="BusinessE1JudgeVerdict",
        model_name=JUDGE_MODEL,
    )
    return result if isinstance(result, JudgeVerdict) else None
