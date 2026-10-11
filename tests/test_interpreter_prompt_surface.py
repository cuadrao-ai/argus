import json
from copy import deepcopy
from pathlib import Path

import pytest
from argus.agent_runtime.business.interpretation import business_interpretation_prompt
from argus.domain.business.tools.declarations import get_business_declarations

from tests.interpreter_prompt_surface import (
    BUSINESS_DECLARATION_OWNER,
    BUSINESS_MODEL_FACING_OWNERS,
    fingerprint_surface,
    model_facing_surface,
    surface_drift,
    validate_business_measurement,
)


def _write(root: Path, name: str, source: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def test_inline_readout_system_prompt_changes_its_fingerprint(tmp_path: Path) -> None:
    owner = "src/argus/agent_runtime/stages/explain.py"
    source = 'messages = [{"role": "system", "content": "Explain the ride."}]'
    _write(tmp_path, owner, source)
    first = model_facing_surface(tmp_path)
    assert owner in first
    _write(tmp_path, owner, source.replace("ride", "drawdown"))
    assert model_facing_surface(tmp_path)[owner] != first[owner]


def test_breakdown_prompt_and_schema_are_covered_without_other_api_prose(
    tmp_path: Path,
) -> None:
    owner = "src/argus/api/chat/breakdown.py"
    source = """
def messages():
    return [{"role": "system", "content": "Explain the stored result."}]
class Draft:
    text = Field(description="Complete grounded explanation.")
"""
    _write(tmp_path, owner, source)
    _write(tmp_path, "src/argus/api/chat/unrelated.py", source)
    first = model_facing_surface(tmp_path)
    assert set(first) == {owner}
    assert first[owner]["entries"] == 2
    _write(tmp_path, owner, source.replace("Complete grounded", "Concise grounded"))
    assert model_facing_surface(tmp_path)[owner] != first[owner]


def test_unrelated_inline_runtime_dictionary_does_not_expand_fingerprint(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "src/argus/agent_runtime/unrelated.py",
        'data = {"role": "system", "content": "Not a readout owner."}',
    )
    assert model_facing_surface(tmp_path) == {}


def test_shared_readout_instruction_constant_is_fingerprinted(tmp_path: Path) -> None:
    owner = "src/argus/domain/result_readout_grounding.py"
    source = 'READOUT_GROUNDING_INSTRUCTIONS = "Use stored figures only."'
    _write(tmp_path, owner, source)
    first = model_facing_surface(tmp_path)
    assert owner in first
    _write(tmp_path, owner, source.replace("stored figures", "supplied numbers"))
    assert model_facing_surface(tmp_path)[owner] != first[owner]


@pytest.mark.parametrize(
    "owner,name",
    [
        (
            "src/argus/domain/result_readout_grounding.py",
            "READOUT_RUN_GROUNDING_INSTRUCTIONS",
        ),
        (
            "src/argus/domain/result_readout_grounding.py",
            "READOUT_GROUNDING_INSTRUCTIONS",
        ),
        ("src/argus/domain/result_readout_sources.py", "BREAKDOWN_SOURCE_INSTRUCTIONS"),
    ],
)
def test_each_readout_instruction_fragment_remains_measured(
    tmp_path: Path, owner: str, name: str
) -> None:
    source = f'{name} = SHARED_TEXT + "Keep run and source figures separate."'
    _write(tmp_path, owner, source)
    first = model_facing_surface(tmp_path)
    assert owner in first
    _write(tmp_path, owner, source.replace("separate", "distinct"))
    assert model_facing_surface(tmp_path)[owner] != first[owner]


@pytest.mark.parametrize(
    "owner",
    [
        "src/argus/domain/result_readout_fact_sheet.py",
        "src/argus/domain/result_readout_fact_definitions.py",
    ],
)
def test_readout_fact_meanings_are_measured_but_docstrings_are_not(
    tmp_path: Path, owner: str
) -> None:
    source = '''"""Internal implementation notes."""
FACT_DEFINITIONS = {"executed_fills": ("count", "Executed fills, not closed trades.")}
def build():
    """Implementation detail."""
    return {"meaning": "Annualized volatility."}
'''
    _write(tmp_path, owner, source)
    first = model_facing_surface(tmp_path)
    assert owner in first
    _write(tmp_path, owner, source.replace("Annualized volatility", "Daily volatility"))
    assert model_facing_surface(tmp_path)[owner] != first[owner]
    _write(tmp_path, owner, source.replace("Implementation detail", "Private helper"))
    assert model_facing_surface(tmp_path)[owner] == first[owner]


def _business_declaration_source() -> str:
    root = Path(__file__).resolve().parents[1]
    return (root / BUSINESS_DECLARATION_OWNER).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "description",
    [declaration.description for declaration in get_business_declarations()],
)
def test_each_business_tool_description_changes_its_fingerprint(
    tmp_path: Path, description: str
) -> None:
    source = _business_declaration_source()
    literal = json.dumps(description)
    assert source.count(literal) == 1
    _write(tmp_path, BUSINESS_DECLARATION_OWNER, source)
    first = model_facing_surface(tmp_path)
    assert first[BUSINESS_DECLARATION_OWNER]["entries"] == 7
    changed = source.replace(literal, json.dumps(description + " Changed wording."))
    _write(tmp_path, BUSINESS_DECLARATION_OWNER, changed)
    assert (
        model_facing_surface(tmp_path)[BUSINESS_DECLARATION_OWNER]
        != first[BUSINESS_DECLARATION_OWNER]
    )


@pytest.mark.parametrize(
    "unmeasured", ["business_context_required", "business.action", "business_action"]
)
def test_business_handler_and_card_text_do_not_change_prompt_fingerprint(
    tmp_path: Path, unmeasured: str
) -> None:
    source = _business_declaration_source()
    literal = json.dumps(unmeasured)
    assert literal in source
    _write(tmp_path, BUSINESS_DECLARATION_OWNER, source)
    first = model_facing_surface(tmp_path)
    _write(
        tmp_path,
        BUSINESS_DECLARATION_OWNER,
        source.replace(literal, json.dumps(unmeasured + "_changed")),
    )
    assert model_facing_surface(tmp_path) == first


def test_measured_business_descriptions_reach_the_actual_prompt(tmp_path: Path) -> None:
    declarations = get_business_declarations()
    assert len(declarations) == 7
    prompt = business_interpretation_prompt({})[0]["content"]
    assert all(declaration.description in prompt for declaration in declarations)
    _write(tmp_path, BUSINESS_DECLARATION_OWNER, _business_declaration_source())
    assert model_facing_surface(tmp_path)[BUSINESS_DECLARATION_OWNER]["entries"] == len(
        declarations
    )


def _scoped_measurement_fixture() -> tuple[dict, dict]:
    digest = {"entries": 1, "chars": 1, "sha256": "a" * 64}
    surface = {owner: dict(digest) for owner in BUSINESS_MODEL_FACING_OWNERS}
    case_ids = [f"unit_owner_{index}" for index in range(6)] + [
        "en_revoked_accountant_read"
    ]
    measured = {
        "commit": "1" * 40,
        "scorecard": "unit-only-scorecard.json",
        "fixture_sha256": "2" * 64,
        "case_ids": case_ids,
        "runtime_model": "deepseek/deepseek-v4.1-flash",
        "judge_model": "x-ai/grok-4.3",
        "passed": 7,
        "failed": 0,
        "unavailable": 0,
    }
    cases = []
    for index, case_id in enumerate(case_ids):
        human_only = index == 6
        cases.append(
            {
                "schema_version": "business_e1_scorecard_v1",
                "case_id": case_id,
                "status": "passed",
                "failed_checks": [],
                "hidden_state_assertions": [
                    {"step": step, "failed_checks": []}
                    for step in range(2 if human_only else 3)
                ],
                "candidate_sha": measured["commit"],
                "fixture_sha256": measured["fixture_sha256"],
                "runtime_model": None if human_only else measured["runtime_model"],
                "judge_model": None if human_only else measured["judge_model"],
                "adapter_provenance": {
                    "candidate_sha": measured["commit"],
                    "capture_id": f"unit-capture-{index}",
                    "db_namespace": "unit-db",
                    **({} if human_only else {"graph_run_id": f"unit-graph-{index}"}),
                },
                "evidence_kind": "real_business_db_human_command"
                if human_only
                else "real_langgraph_executor_db",
                "no_model_calls_required": human_only,
                "call_receipts": []
                if human_only
                else [
                    {
                        "task": task,
                        "schema_name": schema,
                        "model": model,
                        "mode": "json_schema",
                        "outcome": "succeeded",
                    }
                    for task, schema, model in (
                        (
                            "interpretation",
                            "BusinessInterpretation",
                            measured["runtime_model"],
                        ),
                        ("interpretation", "BusinessReply", measured["runtime_model"]),
                        (
                            "chat_composer",
                            "BusinessE1JudgeVerdict",
                            measured["judge_model"],
                        ),
                    )
                ],
                "total_cost_usd": 0 if human_only else 0.01,
                "total_latency_ms": 0 if human_only else 100,
                "judge_verdict": None
                if human_only
                else {
                    "passed": True,
                    "honest_saved_state": True,
                    "no_invented_facts": True,
                    "plain_factual_question": True,
                    "no_claimed_approval": True,
                },
            }
        )
    scope = {
        "owners": sorted(BUSINESS_MODEL_FACING_OWNERS),
        "surface": surface,
        "last_measured": measured,
    }
    scorecard = {
        "schema_version": "business_acceptance_v1",
        "scope": "business",
        "status": "passed",
        "measurement_kind": "initial_measurement",
        "surface": deepcopy(surface),
        "candidate_sha": measured["commit"],
        "fixture_sha256": measured["fixture_sha256"],
        "runtime_model": measured["runtime_model"],
        "judge_model": measured["judge_model"],
        "case_ids": case_ids,
        "step_count": 20,
        "cases": cases,
        "totals": {"passed": 7, "failed": 0, "unavailable": 0},
        "calibration": {
            "status": "passed",
            "judge_model": measured["judge_model"],
            "report": "unit-only-calibration.json",
        },
    }
    return scope, scorecard


def test_scoped_measurement_keeps_legacy_evidence_and_covers_every_owner() -> None:
    scope, scorecard = _scoped_measurement_fixture()
    legacy = {"src/argus/agent_runtime/llm_interpreter.py": {"sha256": "legacy"}}
    legacy_measurement = {"commit": "old", "passed": 70, "failed": 3}
    fingerprint = {
        "surface": deepcopy(legacy),
        "last_measured": dict(legacy_measurement),
        "scoped_measurements": {"business": scope},
    }
    combined = fingerprint_surface(fingerprint)
    assert set(combined) == set(legacy) | BUSINESS_MODEL_FACING_OWNERS
    assert fingerprint["surface"] == legacy
    assert fingerprint["last_measured"] == legacy_measurement
    validate_business_measurement(scope, scorecard)


@pytest.mark.parametrize(
    "owner",
    ["src/argus/agent_runtime/llm_interpreter.py", BUSINESS_DECLARATION_OWNER],
)
def test_consumer_and_business_drift_still_fail(owner: str) -> None:
    scope, _ = _scoped_measurement_fixture()
    fingerprint = {
        "surface": {"src/argus/agent_runtime/llm_interpreter.py": {"sha256": "legacy"}},
        "scoped_measurements": {"business": scope},
    }
    recorded = fingerprint_surface(fingerprint)
    observed = deepcopy(recorded)
    observed[owner]["sha256"] = "changed"
    assert surface_drift(recorded, observed) == ([owner], [], [])
    observed = deepcopy(recorded)
    observed["src/argus/agent_runtime/new_owner.py"] = {"sha256": "new"}
    assert surface_drift(recorded, observed)[1] == [
        "src/argus/agent_runtime/new_owner.py"
    ]


@pytest.mark.parametrize("invalid", ["missing_scope", "unknown_owner", "overlap"])
def test_business_scope_cannot_exempt_unmeasured_or_shared_owners(invalid: str) -> None:
    scope, _ = _scoped_measurement_fixture()
    fingerprint = {"surface": {}, "scoped_measurements": {"business": scope}}
    if invalid == "missing_scope":
        fingerprint["scoped_measurements"] = {}
    elif invalid == "unknown_owner":
        scope["surface"]["src/argus/domain/shared.py"] = {"sha256": "unknown"}
    else:
        fingerprint["surface"][BUSINESS_DECLARATION_OWNER] = {"sha256": "shared"}
    with pytest.raises(AssertionError):
        fingerprint_surface(fingerprint)


@pytest.mark.parametrize(
    "invalid",
    [
        "missing_measurement",
        "missing_owner",
        "partial_cases",
        "duplicate_case",
        "partial_steps",
        "unavailable_aggregate",
        "unavailable",
        "failed_hidden_state",
        "missing_model_receipt",
        "unknown_model_call",
        "wrong_candidate",
        "wrong_surface",
        "missing_usage",
        "failed_judge",
        "uncalibrated_judge",
        "legacy_scorecard",
        "false_no_model_exemption",
    ],
)
def test_business_measurement_rejects_incomplete_or_wrong_scope_evidence(
    invalid: str,
) -> None:
    scope, scorecard = _scoped_measurement_fixture()
    case = scorecard["cases"][0]
    if invalid == "missing_measurement":
        scope["last_measured"] = None
    elif invalid == "missing_owner":
        scope["surface"].pop(BUSINESS_DECLARATION_OWNER)
    elif invalid == "partial_cases":
        scorecard["cases"].pop()
    elif invalid == "duplicate_case":
        scorecard["cases"][-1] = deepcopy(case)
    elif invalid == "partial_steps":
        case["hidden_state_assertions"].pop()
    elif invalid == "unavailable_aggregate":
        scorecard["status"] = "unavailable"
    elif invalid == "unavailable":
        case["status"] = "unavailable"
    elif invalid == "failed_hidden_state":
        case["hidden_state_assertions"][0]["failed_checks"] = ["wrong_amount"]
    elif invalid == "missing_model_receipt":
        case["call_receipts"].pop()
    elif invalid == "unknown_model_call":
        case["call_receipts"][0]["outcome"] = "unknown"
    elif invalid == "wrong_candidate":
        case["adapter_provenance"]["candidate_sha"] = "3" * 40
    elif invalid == "wrong_surface":
        scorecard["surface"][BUSINESS_DECLARATION_OWNER]["sha256"] = "changed"
    elif invalid == "missing_usage":
        case["total_cost_usd"] = None
    elif invalid == "failed_judge":
        case["judge_verdict"]["honest_saved_state"] = False
    elif invalid == "uncalibrated_judge":
        scorecard["calibration"]["status"] = "unavailable"
    elif invalid == "legacy_scorecard":
        scorecard["schema_version"] = "legacy_global_scorecard"
    else:
        case["no_model_calls_required"] = True
    with pytest.raises(AssertionError):
        validate_business_measurement(scope, scorecard)
