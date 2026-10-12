"""Guard coverage of the two readout composers without widening other APIs."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from tests.interpreter_prompt_surface import (
    DOCUMENT_EXTRACTION_OWNERS,
    fingerprint_surface,
    model_facing_surface,
    require_document_extraction_measurement,
    surface_drift,
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


def _document_fingerprint(scope: dict) -> dict:
    return {
        "surface": {"legacy": {"entries": 1, "chars": 7, "sha256": "c" * 64}},
        "last_measured": {"passed": 70, "failed": 3},
        "scoped_measurements": {"document_extraction": scope},
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
