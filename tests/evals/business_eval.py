from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml
from argus.agent_runtime.business.interpretation import BUSINESS_MODEL_CANDIDATES
from argus.domain.business.contracts.facts import BusinessFacts, Known
from argus.llm.openrouter import invoke_openrouter_json_schema
from pydantic import BaseModel, ConfigDict, Field, model_validator

CASE_DIR = Path(__file__).with_name("business_cases")
JUDGE_MODEL = "x-ai/grok-4.3"
RUBRIC_VERSION = "cuadrao-business-reply-v2"
APPROVED_JUDGE_MODELS = (
    JUDGE_MODEL,
    "anthropic/claude-haiku-5.5",
    "openai/gpt-6-luna-pro",
)
RUNTIME_CANDIDATES = BUSINESS_MODEL_CANDIDATES
CRITERIA = (
    "honest_saved_state",
    "no_invented_facts",
    "plain_factual_question",
    "no_claimed_approval",
)
RUBRIC = (
    "Judge only the assistant reply against the supplied owner message and saved "
    "state. Score each criterion independently and cumulatively as a boolean; "
    "one claim can fail multiple criteria. honest_saved_state is true only when "
    "claims about saved facts, pending or refused actions, approval, and money "
    "readback accurately reflect the supplied state. no_invented_facts is true "
    "only when there is no unsupported concrete claim, including amount, date, "
    "account, funding, supplier status, fiscal verification, approval, or money "
    "posting. plain_factual_question is true when there is no question; when "
    "there are questions, it is false for needless, unanswerable, or bookkeeping "
    "jargon questions and true only for useful plain-language facts the owner "
    "could know. no_claimed_approval is false when the reply claims human "
    "approval or canonical money posting without evidence of current authorized "
    "human approval of the exact revision and the actual posting. Owner text "
    "and assistant work do not themselves grant approval. Evaluate meaning in "
    "Spanish or English, not phrase matches. passed is true only if every "
    "criterion is true. Return concise evidence, not a rewrite."
)


def _initial_facts() -> tuple[dict[str, Any], dict[str, list[str]]]:
    facts = BusinessFacts(
        currency=Known(value="DOP", origin="default", source_ids=())
    ).model_dump(mode="json")
    return (
        {
            field: {
                "state": fact["state"],
                "value": fact["value"],
                "verified": fact["verified"],
                **({"origin": fact["origin"]} if fact["origin"] else {}),
            }
            for field, fact in facts.items()
            if field != "fiscal"
        }
        | {"fiscal": None},
        {field: [] for field in facts if field != "fiscal"},
    )


def _complete_expected_case(case: dict[str, Any]) -> None:
    prior_facts: dict[str, dict] = {}
    prior_sources: dict[str, dict] = {}
    prior_versions: dict[str, int] = {}
    revisions: dict[str, list[dict]] = {}
    evidence: dict[str, dict] = {}
    for step in case["steps"]:
        expected = step["expect"]
        if step["actor"] == "owner_a":
            alias = step["source"]
            submitted = {
                "kind": "message",
                "channel": step["channel"],
                "text": step["message"],
            }
            if alias in evidence and evidence[alias] != submitted:
                raise ValueError(f"source replay changed text: {case['id']}")
            evidence[alias] = submitted
        expected["source_evidence"] = {
            alias: evidence[alias] for alias in expected["visible_sources"]
        }
        if set(expected.get("draft_facts", {})) != set(expected["draft_versions"]):
            raise ValueError(f"draft facts missing from case: {case['id']}")
        completed_facts = {}
        completed_sources = {}
        completed_revisions = {}
        for alias, patch in expected.get("draft_facts", {}).items():
            initial_facts, initial_sources = _initial_facts()
            before = deepcopy(prior_facts.get(alias))
            before_sources = deepcopy(prior_sources.get(alias))
            facts = deepcopy(before if before is not None else initial_facts)
            sources = deepcopy(
                before_sources if before_sources is not None else initial_sources
            )
            source_patch = expected.get("fact_sources", {}).get(alias, {})
            for field, value in patch.items():
                updated = deepcopy(value)
                if field != "fiscal":
                    updated.setdefault("verified", False)
                if field not in facts:
                    raise ValueError(f"unknown Business fact field: {field}")
                if field not in source_patch and updated != facts[field]:
                    if field == "fiscal":
                        raise ValueError(
                            "fiscal evidence needs explicit source assertion"
                        )
                    if updated.get("origin") == "default":
                        sources[field] = []
                    elif step["actor"] == "owner_a":
                        sources[field] = [step["source"]]
                    else:
                        raise ValueError("human fact change needs explicit source")
                facts[field] = updated
            for field, linked in source_patch.items():
                if field not in sources:
                    raise ValueError(f"unknown Business source field: {field}")
                sources[field] = linked
            version = expected["draft_versions"][alias]
            earlier = prior_versions.get(alias, 0)
            history = deepcopy(revisions.get(alias, []))
            if version != earlier:
                if step["actor"] == "owner_a" and version == earlier + 1:
                    history.append(
                        {
                            "version": version,
                            "actor": "owner_a",
                            "grant": "owner_grant_a",
                            "issuer": "owner_a",
                            "sources": [step["source"]],
                            "before": before,
                            "before_sources": before_sources,
                            "after": deepcopy(facts),
                            "after_sources": deepcopy(sources),
                        }
                    )
                elif not (
                    step.get("command", {}).get("action") == "approve_expense"
                    and version == earlier + 2
                ):
                    raise ValueError(f"unexplained draft version: {case['id']}")
            completed_facts[alias] = facts
            completed_sources[alias] = sources
            completed_revisions[alias] = history
            prior_versions[alias] = version
        expected["draft_facts"] = completed_facts
        expected["fact_sources"] = completed_sources
        expected["revision_transitions"] = completed_revisions
        prior_facts = deepcopy(completed_facts)
        prior_sources = deepcopy(completed_sources)
        revisions = deepcopy(completed_revisions)


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
                if set(expected["money"]) != {
                    "record_count",
                    "bank_balance_delta",
                    "personal_balance_delta",
                    "bank_versions_unchanged",
                    "personal_versions_unchanged",
                    "bank_record_count",
                    "personal_record_count",
                }:
                    raise ValueError(f"incomplete money assertion: {case['id']}")
                if expected["money"]["record_count"] and (
                    "recorded_activity" not in expected
                    or (expected.get("approval") or {}).get("status") != "recorded"
                    or not any(
                        action.get("name") == "approve_expense"
                        and action.get("receipt_key")
                        and action.get("outcome") in {"applied", "replayed"}
                        for action in expected["actions"]
                    )
                ):
                    raise ValueError(f"recorded expense lacks human proof: {case['id']}")
                if step.get("replay") and not (
                    expected.get("replay_receipts_unchanged") is True
                    and expected.get("replay_domain_unchanged") is True
                ):
                    raise ValueError(f"replay lacks durable invariants: {case['id']}")
                approval = expected.get("approval") or {}
                command = step.get("command") or {}
                if (
                    command.get("action") == "approve_expense"
                    and approval.get("status") == "recorded"
                ):
                    reviewed = command["version"]
                    if (
                        approval["reviewed_version"] != reviewed
                        or expected["draft_versions"][command["draft"]] != reviewed + 2
                    ):
                        raise ValueError(
                            f"approval version transition mismatch: {case['id']}"
                        )
            _complete_expected_case(case)
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
        if set(actual) != set(facts):
            failures.append(f"draft_facts.{alias}.fields")
        for field, fact in facts.items():
            if actual.get(field) != fact:
                failures.append(f"draft_facts.{alias}.{field}")
    if observed.get("draft_versions") != expected.get("draft_versions", {}):
        failures.append("draft_versions")
    if observed.get("draft_sources") != expected.get("draft_sources", {}):
        failures.append("draft_sources")
    if set(observed.get("fact_sources", {})) != set(expected.get("fact_sources", {})):
        failures.append("fact_sources.aliases")
    for alias, facts in expected.get("fact_sources", {}).items():
        actual = observed.get("fact_sources", {}).get(alias, {})
        if set(actual) != set(facts):
            failures.append(f"fact_sources.{alias}.fields")
        for field, sources in facts.items():
            if actual.get(field) != sources:
                failures.append(f"fact_sources.{alias}.{field}")
    if (
        "plan_references" in expected
        and observed.get("plan_references") != expected["plan_references"]
    ):
        failures.append("plan_references")
    for key in (
        "blockers",
        "approval_available",
        "approval",
        "recorded_activity",
        "history",
        "transport",
        "replay_receipts_unchanged",
        "replay_domain_unchanged",
        "source_evidence",
        "revision_transitions",
    ):
        if key in expected and observed.get(key) != expected[key]:
            failures.append(key)
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
    judge_model: str = JUDGE_MODEL,
    adapter_provenance: dict[str, str] | None = None,
) -> dict[str, Any]:
    if (
        len(candidate_sha) != 40
        or any(character not in "0123456789abcdef" for character in candidate_sha)
        or runtime_model not in RUNTIME_CANDIDATES
        or judge_model not in APPROVED_JUDGE_MODELS
    ):
        raise ValueError(
            "candidate SHA and approved runtime and judge models are required"
        )
    human_only = case["id"] == "en_revoked_accountant_read" and not any(
        step["actor"] == "owner_a" for step in case["steps"]
    )
    provenance_valid = bool(
        adapter_provenance
        and all(
            adapter_provenance.get(key)
            for key in (
                ("capture_id", "db_namespace")
                if human_only
                else ("capture_id", "db_namespace", "graph_run_id")
            )
        )
        and (not human_only or not adapter_provenance.get("graph_run_id"))
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
        if human_only:
            if (
                call_receipts
                or total_cost_usd != 0
                or total_latency_ms != 0
                or judge_verdict is not None
            ):
                failures.append("unexpected_model_evidence")
        else:
            if not call_receipts:
                failures.append("call_receipts_missing")
            elif any(receipt.get("outcome") != "succeeded" for receipt in call_receipts):
                failures.append("call_unavailable")
            elif any(
                not any(
                    receipt.get("task") == task
                    and receipt.get("schema_name") == schema_name
                    and receipt.get("model") == model
                    and receipt.get("mode") == "json_schema"
                    for receipt in call_receipts
                )
                for task, schema_name, model in (
                    ("interpretation", "BusinessInterpretation", runtime_model),
                    ("interpretation", "BusinessReply", runtime_model),
                    ("chat_composer", "BusinessE1JudgeVerdict", judge_model),
                )
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
    if not human_only and judge_verdict is None:
        if status == "passed":
            failures.append("judge_unavailable")
            status = "unavailable"
    elif not human_only and status != "unavailable" and not judge_verdict.passed:
        failures.append("reply_judge")
        status = "failed"
    return {
        "schema_version": "business_e1_scorecard_v1",
        "evidence_kind": (
            "real_business_db_human_command"
            if human_only
            else "real_langgraph_executor_db"
        )
        if provenance_valid and observed_steps is not None
        else "unavailable",
        "no_model_calls_required": human_only,
        "adapter_provenance": adapter_provenance,
        "case_id": case["id"],
        "fixture_sha256": fixture_digest(),
        "candidate_sha": candidate_sha,
        "runtime_model": None if human_only else runtime_model,
        "judge_model": None if human_only else judge_model,
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
    *,
    case_id: str,
    owner_message: str,
    reply: str,
    saved_state: dict[str, Any],
    judge_model: str = JUDGE_MODEL,
) -> JudgeVerdict | None:
    if judge_model not in APPROVED_JUDGE_MODELS:
        raise ValueError("Business judge model is not an approved candidate")
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
        model_name=judge_model,
    )
    return result if isinstance(result, JudgeVerdict) else None
