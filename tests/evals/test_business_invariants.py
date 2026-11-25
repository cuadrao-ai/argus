from __future__ import annotations

from copy import deepcopy

import pytest

from tests.evals.business_eval import (
    APPROVED_JUDGE_MODELS,
    RUNTIME_CANDIDATES,
    fixture_digest,
)
from tests.evals.business_invariants import (
    MEASUREMENT_KIND,
    SCHEMA_VERSION,
    _variety_digest,
    validate_business_invariant_measurement,
    validate_business_invariant_scope,
)
from tests.evals.business_variety import load_variety_cases
from tests.interpreter_prompt_surface import (
    BUSINESS_ACCEPTANCE_STEP_IDS,
    BUSINESS_DECLARATION_OWNER,
    BUSINESS_MODEL_FACING_OWNERS,
    HISTORICAL_BUSINESS_OWNERS,
)


def passing_scorecard() -> dict:
    varied = [c["id"] for c in load_variety_cases()]
    judge = APPROVED_JUDGE_MODELS[0]
    receipt = {
        "task": "chat_composer",
        "schema_name": "BusinessE1JudgeVerdict",
        "model": judge,
        "outcome": "succeeded",
    }
    cases = [
        {
            "case_id": case_id,
            "kind": kind,
            "status": "passed",
            "failed_checks": [],
            "judge_receipts": [] if case_id == "en_revoked_accountant_read" else [receipt],
        }
        for kind, ids in (("frozen", list(BUSINESS_ACCEPTANCE_STEP_IDS)), ("varied", varied))
        for case_id in ids
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "measurement_kind": MEASUREMENT_KIND,
        "scope": "business",
        "status": "passed",
        "judge_model": judge,
        "runtime_model": RUNTIME_CANDIDATES[0],
        "surface": {owner: {"sha256": "x"} for owner in HISTORICAL_BUSINESS_OWNERS},
        "calibration": {"status": "passed", "judge_model": judge},
        "frozen_fixture_sha256": fixture_digest(),
        "variety_fixture_sha256": _variety_digest(),
        "case_ids": {"frozen": list(BUSINESS_ACCEPTANCE_STEP_IDS), "varied": varied},
        "cases": cases,
        "totals": {"passed": len(cases), "failed": 0, "unavailable": 0},
    }


def test_a_complete_passing_scorecard_is_accepted() -> None:
    validate_business_invariant_measurement(passing_scorecard())


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: s["cases"].pop(),
        lambda s: s["cases"][0].update(status="failed", failed_checks=["x"]),
        lambda s: s["cases"][0].update(judge_receipts=[]),
        lambda s: s["calibration"].update(status="failed"),
        lambda s: s.update(frozen_fixture_sha256="0" * 64),
        lambda s: s.update(variety_fixture_sha256="0" * 64),
        lambda s: s.update(measurement_kind="initial_measurement"),
        lambda s: s["totals"].update(passed=1),
        lambda s: s["cases"].reverse(),
        lambda s: s.update(status="unavailable"),
    ],
)
def test_an_incomplete_or_altered_scorecard_is_refused(mutate) -> None:  # noqa: ANN001
    scorecard = deepcopy(passing_scorecard())
    mutate(scorecard)
    with pytest.raises(AssertionError):
        validate_business_invariant_measurement(scorecard)


def scoped() -> tuple[dict, dict]:
    scorecard = passing_scorecard()
    scorecard.update(
        candidate_sha="a" * 40,
        frozen_fixture_sha256=fixture_digest(),
        calibration={
            "status": "passed",
            "judge_model": scorecard["judge_model"],
            "rubric_version": "v",
            "fixture_sha256": "c" * 64,
        },
    )
    scope = {
        "surface": {
            owner: deepcopy(scorecard["surface"][owner]) for owner in BUSINESS_MODEL_FACING_OWNERS
        },
        "last_measured": {
            "measurement_kind": MEASUREMENT_KIND,
            "commit": "a" * 40,
            "runtime_model": scorecard["runtime_model"],
            "judge_model": scorecard["judge_model"],
            "frozen_fixture_sha256": scorecard["frozen_fixture_sha256"],
            "variety_fixture_sha256": scorecard["variety_fixture_sha256"],
            "rubric_version": "v",
            "calibration_fixture_sha256": "c" * 64,
            **scorecard["totals"],
        },
    }
    return scope, scorecard


def test_the_fingerprint_keeps_only_surviving_owners_from_the_historical_scorecard() -> None:
    scope, scorecard = scoped()
    assert set(scope["surface"]) == {BUSINESS_DECLARATION_OWNER}
    assert set(scope["surface"]) < set(scorecard["surface"])
    validate_business_invariant_scope(scope, scorecard)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda scope, card: scope["last_measured"].update(commit="b" * 40),
        lambda scope, card: scope["last_measured"].update(judge_model="other"),
        lambda scope, card: scope["last_measured"].update(passed=1),
        lambda scope, card: scope["surface"].pop(BUSINESS_DECLARATION_OWNER),
        lambda scope, card: scope["surface"][BUSINESS_DECLARATION_OWNER].update(
            sha256="changed"
        ),
        lambda scope, card: scope.update(last_measured=None),
        lambda scope, card: scope["last_measured"].update(
            calibration_fixture_sha256="d" * 64
        ),
    ],
)
def test_a_scope_that_drifts_from_its_scorecard_is_refused(mutate) -> None:  # noqa: ANN001
    scope, scorecard = scoped()
    mutate(scope, scorecard)
    with pytest.raises((AssertionError, KeyError)):
        validate_business_invariant_scope(scope, scorecard)
