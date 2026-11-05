"""Guard coverage of the two readout composers without widening other APIs."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from argus.agent_runtime.business.interpretation import business_interpretation_prompt
from argus.domain.business.tools.declarations import get_business_declarations

from tests.interpreter_prompt_surface import (
    BUSINESS_ACCEPTANCE_STEP_IDS,
    BUSINESS_DECLARATION_OWNER,
    BUSINESS_MODEL_FACING_OWNERS,
    DOCUMENT_EXTRACTION_OWNERS,
    fingerprint_surface,
    model_facing_surface,
    require_document_extraction_measurement,
    surface_drift,
    validate_business_measurement,
    validate_document_extraction_measurement,
)


def _write(root: Path, name: str, source: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def test_document_prompt_is_covered_only_at_its_exact_owner(tmp_path: Path) -> None:
    owner = "src/argus/domain/ingestion/documents/extractor.py"
    source = '_PROMPT = "Extract printed evidence."\nERROR = "Private failure."'
    _write(tmp_path, owner, source)
    _write(tmp_path, "src/argus/domain/ingestion/unrelated.py", source)
    first = model_facing_surface(tmp_path)
    assert set(first) == {owner}
    assert first[owner]["entries"] == 1
    _write(tmp_path, owner, source.replace("printed evidence", "visible evidence"))
    assert model_facing_surface(tmp_path)[owner] != first[owner]
    _write(tmp_path, owner, source.replace("Private failure", "Internal error"))
    assert model_facing_surface(tmp_path) == first


@pytest.mark.parametrize(
    "text",
    [
        "Unverified RNC",
        "Unverified NCF",
        "Unverified e-CF",
        "Unverified ITBIS",
        "Printed line total",
        "alongside receipt details",
    ],
)
def test_all_document_schema_instructions_change_the_surface(
    tmp_path: Path, text: str
) -> None:
    owner = "src/argus/domain/ingestion/documents/models.py"
    source = (Path(__file__).resolve().parents[1] / owner).read_text()
    assert source.count(text) == 1
    _write(tmp_path, owner, source)
    first = model_facing_surface(tmp_path)
    assert first[owner]["entries"] == 6
    _write(tmp_path, owner, source.replace(text, "Changed instruction"))
    assert model_facing_surface(tmp_path)[owner] != first[owner]


def _document_measurement_fixture() -> tuple[dict, dict]:
    surface = {
        owner: {"entries": 1, "chars": 10, "sha256": "a" * 64}
        for owner in DOCUMENT_EXTRACTION_OWNERS
    }
    scope = {
        "owners": sorted(DOCUMENT_EXTRACTION_OWNERS),
        "status": "MEASURED",
        "surface": surface,
        "last_measured": {
            "commit": "b" * 40,
            "model": "test/vision",
            "scorecard": "docs/reports/evidence/document-test/live.json",
        },
    }
    scorecard = {
        "scope": "document_extraction",
        "status": "passed",
        "candidate_sha": "b" * 40,
        "model": "test/vision",
        "surface": deepcopy(surface),
        "totals": {"passed": 2, "failed": 0, "unavailable": 0},
    }
    return scope, scorecard


def _empty_business_scope() -> dict:
    return {
        "owners": sorted(BUSINESS_MODEL_FACING_OWNERS),
        "surface": {},
        "last_measured": None,
    }


def _unmeasured_document_scope() -> dict:
    return {
        "owners": sorted(DOCUMENT_EXTRACTION_OWNERS),
        "status": "UNMEASURED",
        "surface": {},
        "last_measured": None,
    }


def _document_fingerprint(scope: dict) -> dict:
    return {
        "surface": {"legacy": {"entries": 1, "chars": 7, "sha256": "c" * 64}},
        "last_measured": {"passed": 70, "failed": 3},
        "scoped_measurements": {
            "document_extraction": scope,
            "business": _empty_business_scope(),
        },
    }


def test_document_union_keeps_legacy_evidence_and_detects_legacy_drift() -> None:
    scope, scorecard = _document_measurement_fixture()
    fingerprint = _document_fingerprint(scope)
    original = deepcopy(fingerprint)
    validate_document_extraction_measurement(scope, scorecard)
    combined = fingerprint_surface(fingerprint)
    assert combined == fingerprint["surface"] | scope["surface"]
    assert fingerprint == original
    observed = deepcopy(combined)
    observed["legacy"]["sha256"] = "d" * 64
    assert surface_drift(combined, observed) == (["legacy"], [], [])
    observed["unknown_owner"] = observed.pop("legacy")
    assert surface_drift(combined, observed) == ([], ["unknown_owner"], ["legacy"])


@pytest.mark.parametrize(
    "invalid",
    [
        "missing_scope",
        "unknown_scope",
        "unknown_owner",
        "duplicate_owner",
        "overlap",
        "partial_surface",
        "invalid_status",
        "unmeasured_surface",
    ],
)
def test_document_scope_rejects_missing_partial_or_overlapping_owners(
    invalid: str,
) -> None:
    scope, _ = _document_measurement_fixture()
    fingerprint = _document_fingerprint(scope)
    owner = sorted(DOCUMENT_EXTRACTION_OWNERS)[0]
    if invalid == "missing_scope":
        fingerprint.pop("scoped_measurements")
    elif invalid == "unknown_scope":
        fingerprint["scoped_measurements"]["other"] = scope
    elif invalid == "unknown_owner":
        scope["owners"][0] = "src/argus/domain/other.py"
    elif invalid == "duplicate_owner":
        scope["owners"].append(owner)
    elif invalid == "overlap":
        fingerprint["surface"][owner] = scope["surface"][owner]
    elif invalid == "partial_surface":
        scope["surface"].pop(owner)
    elif invalid == "invalid_status":
        scope["status"] = "passed"
    else:
        scope["status"] = "UNMEASURED"
        scope["last_measured"] = None
    with pytest.raises(AssertionError):
        fingerprint_surface(fingerprint)


@pytest.mark.parametrize(
    "invalid",
    [
        "missing",
        "partial_surface",
        "unknown_owner",
        "wrong_scope",
        "failed_status",
        "wrong_commit",
        "wrong_model",
        "missing_totals",
        "zero_passed",
        "unavailable",
        "failed_case",
        "boolean_count",
        "malformed_digest",
        "missing_binding",
    ],
)
def test_document_measurement_rejects_missing_partial_unavailable_evidence(
    invalid: str,
) -> None:
    scope, scorecard = _document_measurement_fixture()
    owner = sorted(DOCUMENT_EXTRACTION_OWNERS)[0]
    if invalid == "missing":
        scorecard = None
    elif invalid == "partial_surface":
        scorecard["surface"].pop(owner)
    elif invalid == "unknown_owner":
        scorecard["surface"]["unknown"] = scorecard["surface"].pop(owner)
    elif invalid == "wrong_scope":
        scorecard["scope"] = "business"
    elif invalid == "failed_status":
        scorecard["status"] = "unavailable"
    elif invalid == "wrong_commit":
        scorecard["candidate_sha"] = "d" * 40
    elif invalid == "wrong_model":
        scorecard["model"] = "other/vision"
    elif invalid == "missing_totals":
        scorecard.pop("totals")
    elif invalid == "zero_passed":
        scorecard["totals"]["passed"] = 0
    elif invalid == "unavailable":
        scorecard["totals"]["unavailable"] = 1
    elif invalid == "failed_case":
        scorecard["totals"]["failed"] = 1
    elif invalid == "boolean_count":
        scorecard["totals"]["passed"] = True
    elif invalid == "malformed_digest":
        scope["surface"][owner]["sha256"] = "invalid"
        scorecard["surface"] = deepcopy(scope["surface"])
    else:
        scope["last_measured"].pop("commit")
    with pytest.raises(AssertionError):
        validate_document_extraction_measurement(scope, scorecard)


@pytest.mark.parametrize(
    "state", ["missing_file", "escaped_file", "unmeasured", "passed"]
)
def test_document_scorecard_must_exist_with_bound_evidence(
    tmp_path: Path, state: str
) -> None:
    scope, scorecard = _document_measurement_fixture()
    fingerprint = _document_fingerprint(scope)
    path = scope["last_measured"]["scorecard"]
    if state == "unmeasured":
        scope.update(status="UNMEASURED", surface={}, last_measured=None)
        assert fingerprint_surface(fingerprint) == fingerprint["surface"]
    elif state == "escaped_file":
        scope["last_measured"]["scorecard"] = "private.json"
        _write(tmp_path, "private.json", json.dumps(scorecard))
    elif state == "passed":
        _write(tmp_path, path, json.dumps(scorecard))
    if state == "passed":
        require_document_extraction_measurement(tmp_path, fingerprint)
    else:
        with pytest.raises(AssertionError):
            require_document_extraction_measurement(tmp_path, fingerprint)


def test_inline_readout_system_prompt_changes_its_fingerprint(tmp_path: Path) -> None:
    owner = "src/argus/agent_runtime/stages/explain.py"
    source = 'messages = [{"role": "system", "content": "Explain the ride."}]'
    _write(tmp_path, owner, source)
    first = model_facing_surface(tmp_path)
    assert owner in first
    _write(tmp_path, owner, source.replace("ride", "drawdown"))
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
    case_ids = list(BUSINESS_ACCEPTANCE_STEP_IDS)
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
        human_only = case_id == "en_revoked_accountant_read"
        cases.append(
            {
                "schema_version": "business_e1_scorecard_v1",
                "case_id": case_id,
                "status": "passed",
                "failed_checks": [],
                "hidden_state_assertions": [
                    {"step": step, "failed_checks": []}
                    for step in BUSINESS_ACCEPTANCE_STEP_IDS[case_id]
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
        "scoped_measurements": {
            "business": scope,
            "document_extraction": _unmeasured_document_scope(),
        },
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
        "scoped_measurements": {
            "business": scope,
            "document_extraction": _unmeasured_document_scope(),
        },
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
    fingerprint = {
        "surface": {},
        "scoped_measurements": {
            "business": scope,
            "document_extraction": _unmeasured_document_scope(),
        },
    }
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


@pytest.mark.parametrize(
    "invalid",
    [
        "redistribute_all_steps",
        "redistribute_one_step",
        "omit_step",
        "duplicate_step_id",
        "unexpected_step_id",
        "boolean_step_id",
        "unknown_case_id",
        "reordered_steps",
    ],
)
def test_business_measurement_requires_each_cases_exact_step_coverage(
    invalid: str,
) -> None:
    scope, scorecard = _scoped_measurement_fixture()
    first = scorecard["cases"][0]["hidden_state_assertions"]
    second = scorecard["cases"][1]["hidden_state_assertions"]
    if invalid == "redistribute_all_steps":
        second.extend(first)
        first.clear()
    elif invalid == "redistribute_one_step":
        second.append(first.pop())
    elif invalid == "omit_step":
        first.pop()
    elif invalid == "duplicate_step_id":
        first[-1] = deepcopy(first[0])
    elif invalid == "unexpected_step_id":
        first[-1]["step"] = 99
    elif invalid == "boolean_step_id":
        first[0]["step"] = False
    elif invalid == "unknown_case_id":
        scope["last_measured"]["case_ids"][0] = "unknown_case"
        scorecard["case_ids"][0] = "unknown_case"
        scorecard["cases"][0]["case_id"] = "unknown_case"
    else:
        first.reverse()
    with pytest.raises(AssertionError):
        validate_business_measurement(scope, scorecard)


def test_business_model_prompt_uses_capabilities_without_execution_schema():
    prompt = business_interpretation_prompt({})[0]["content"]
    assert all(item.description in prompt for item in get_business_declarations())
    for internal in (
        '"from_action"',
        '"base_version"',
        '"answers_question_id"',
        '"source_ids"',
        '"TurnPlan"',
    ):
        assert internal not in prompt


def test_sparse_fact_policy_distinguishes_absence_from_explicit_uncertainty():
    from argus.agent_runtime.business.interpretation import BusinessRecordIntent

    description = BusinessRecordIntent.model_json_schema()["properties"]["facts"][
        "description"
    ]
    assert "omit absent fields" in description
    assert "explicit unknown" in description
    prompt = business_interpretation_prompt({})[0]["content"]
    assert "Include only facts stated or corrected by this message" in prompt
    assert "Do not fill absent facts with unknown" in prompt
    assert "Leave unnamed currency omitted" in prompt


def test_activity_kind_policy_does_not_infer_debt_from_a_payment_instrument():
    prompt = business_interpretation_prompt({})[0]["content"]
    assert "A card mention alone does not establish later payment or a payable" in prompt
    assert "Preserve explicit income, credit, loan and uncertain debt semantics" in prompt


@pytest.mark.parametrize(
    "currency",
    [
        None,
        {"state": "unknown"},
        {"state": "owner_does_not_know"},
        {"state": "known", "value": "USD"},
    ],
)
def test_semantic_sparse_currency_preserves_canonical_default_and_explicit_states(
    currency,
):
    from uuid import uuid4

    from argus.agent_runtime.business.binding import (
        capture_business_snapshot,
        compile_business_plan,
    )
    from argus.agent_runtime.business.interpretation import BusinessInterpretation
    from argus.domain.business.actions.facts import patched_facts

    source_id = uuid4()
    facts = {
        "kind": {"state": "known", "value": "expense"},
        "amount": {"state": "known", "value": "37"},
    }
    if currency is not None:
        facts["currency"] = currency
    interpretation = BusinessInterpretation.model_validate(
        {"records": [{"facts": facts}]}
    )
    plan = compile_business_plan(
        interpretation,
        snapshot=capture_business_snapshot({"drafts": [], "questions": []}),
        source_id=source_id,
    )
    after = patched_facts(
        None, plan.actions[0].facts, plan.actions[0].source_ids, origin="owner_stated"
    )
    if currency is None:
        assert after.currency.value == "DOP"
        assert after.currency.origin == "default"
        assert after.currency.source_ids == ()
    else:
        assert after.currency.state == currency["state"]
        assert after.currency.value == currency.get("value")
        assert after.currency.origin == "owner_stated"
        assert after.currency.source_ids == (source_id,)
    assert after.currency.verified is False
    assert after.occurred_on.origin is None
    assert after.occurred_on.source_ids == ()


def test_omitted_currency_and_date_retain_prior_sources_during_a_correction():
    from uuid import uuid4

    from argus.domain.business.actions.facts import patched_facts
    from argus.domain.business.contracts.facts import BusinessFactPatch

    first_source, correction_source = uuid4(), uuid4()
    before = patched_facts(
        None,
        BusinessFactPatch(
            currency={"state": "known", "value": "USD"},
            occurred_on={"state": "known", "value": "2026-10-08"},
            amount={"state": "known", "value": "37"},
        ),
        (first_source,),
        origin="owner_stated",
    )
    after = patched_facts(
        before,
        BusinessFactPatch(amount={"state": "known", "value": "29"}),
        (correction_source,),
        origin="owner_stated",
    )
    assert after.currency == before.currency
    assert after.occurred_on == before.occurred_on
    assert after.amount.value == "29"
    assert after.amount.source_ids == (correction_source,)


def test_question_policy_qualifies_funding_priority_and_preserves_uncertainty():
    prompt = business_interpretation_prompt({})[0]["content"]
    assert "with an absent amount, ask for the amount first" in prompt
    assert (
        "Once the amount is known, ask about unknown funding before other missing facts"
        in prompt
    )
    assert (
        "After a known answer, propose at most one useful still-required owner fact as a question to persist with Ask"
        in prompt
    )
    assert (
        "An owner_does_not_know answer moves its existing question to the accountant; do not duplicate or reask it"
        in prompt
    )
    assert "Do not require confirmation of facts already supplied" in prompt


def test_allocation_guidance_sources_both_fields_from_the_current_message():
    from argus.agent_runtime.business.interpretation import BusinessRecordIntent

    properties = BusinessRecordIntent.model_json_schema()["properties"]
    description = properties["allocation"]["description"]
    assert "both funding and business share" in description
    assert "this message" in description
    assert "single changed field in sparse facts" in description
    prompt = business_interpretation_prompt({})[0]["content"]
    assert "Never copy stored funding or share to complete an allocation" in prompt
    assert (
        "Explicit unknown and owner_does_not_know still represent sourced changes"
        in prompt
    )


def test_question_guidance_uses_projected_requirements_without_banning_requested_questions():
    from argus.agent_runtime.business.interpretation import BusinessRecordIntent

    description = BusinessRecordIntent.model_json_schema()["properties"]["question"][
        "description"
    ]
    assert "canonical required_fact_fields and current blockers" in description
    prompt = business_interpretation_prompt({})[0]["content"]
    assert "current blockers describe facts before this proposal" in prompt
    assert (
        "Consider facts supplied in this message when deciding what remains required"
        in prompt
    )
    assert "Optional unknown facts can remain for accountant review" in prompt
    assert "Preserve an explicitly requested factual question" in prompt
