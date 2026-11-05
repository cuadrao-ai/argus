from __future__ import annotations

from copy import deepcopy

import pytest
from argus.agent_runtime.business.interpretation import BUSINESS_MODEL_CANDIDATES

from tests.evals.business_acceptance import CASE_IDS, HUMAN_ONLY_CASE
from tests.evals.business_eval import APPROVED_JUDGE_MODELS, fixture_digest, load_cases
from tests.evals.business_invariants import (
    MEASUREMENT_KIND,
    SCHEMA_VERSION,
    _variety_digest,
    check_invariants,
    validate_business_invariant_measurement,
    validate_business_invariant_scope,
)
from tests.evals.business_variety import load_variety_cases

BUSINESS_OWNERS = (
    "src/argus/agent_runtime/business/interpretation.py",
    "src/argus/domain/business/tools/declarations.py",
)


def frozen(case_id: str) -> dict:
    return next(c for c in load_cases() if c["id"] == case_id)


def observed(**changes: object) -> dict:
    state = {
        "money": {"record_count": 0},
        "approval": None,
        "questions": [],
        "foreign_scope_unchanged": True,
    }
    state.update(changes)
    return state


def test_a_quiet_run_holds_every_invariant() -> None:
    case = frozen("es_owner_funds_no_receipt")
    steps = [observed() for _ in case["steps"][:-1]] + [
        observed(money={"record_count": 1}, approval={"status": "recorded"})
    ]
    assert check_invariants(case, steps) == []


def test_owner_words_never_move_money_or_approve() -> None:
    case = frozen("es_owner_funds_no_receipt")
    steps = [observed() for _ in case["steps"]]
    for step in steps:
        step["money"] = {"record_count": 1}
    assert check_invariants(case, steps)[0] == (
        "step0:owner_words_changed_money_or_approval"
    )
    steps = [observed() for _ in case["steps"]]
    steps[1]["approval"] = {"status": "recorded"}
    assert "step1:owner_words_changed_money_or_approval" in check_invariants(case, steps)


def test_a_replay_must_change_nothing() -> None:
    case = frozen("en_replay_stale_and_current_grant")
    index = next(i for i, s in enumerate(case["steps"]) if s.get("replay"))
    steps = [observed() for _ in case["steps"]]
    for step in steps:
        step["replay_receipts_unchanged"] = step["replay_domain_unchanged"] = True
    assert check_invariants(case, steps) == []
    steps[index]["replay_domain_unchanged"] = False
    assert check_invariants(case, steps) == [f"step{index}:replay_changed_domain"]


def test_the_foreign_scope_must_stay_untouched() -> None:
    case = frozen("es_cross_client_approval_injection")
    assert check_invariants(case, [observed(foreign_scope_unchanged=False)]) == [
        "step0:foreign_scope_changed"
    ]


def test_one_open_owner_question_at_most() -> None:
    case = frozen("en_amount_not_supplied")
    questions = [{"asked_of": "owner", "state": "open"}] * 2
    assert check_invariants(case, [observed(questions=questions)]) == [
        "step0:more_than_one_open_owner_question"
    ]


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
            "judge_receipts": [] if case_id == HUMAN_ONLY_CASE else [receipt],
        }
        for kind, ids in (("frozen", list(CASE_IDS)), ("varied", varied))
        for case_id in ids
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "measurement_kind": MEASUREMENT_KIND,
        "scope": "business",
        "status": "passed",
        "judge_model": judge,
        "runtime_model": BUSINESS_MODEL_CANDIDATES[0],
        "surface": {owner: {"sha256": "x"} for owner in BUSINESS_OWNERS},
        "calibration": {"status": "passed", "judge_model": judge},
        "frozen_fixture_sha256": fixture_digest(),
        "variety_fixture_sha256": _variety_digest(),
        "case_ids": {"frozen": list(CASE_IDS), "varied": varied},
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
        "surface": deepcopy(scorecard["surface"]),
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


def test_the_fingerprint_scope_must_record_exactly_the_scorecard() -> None:
    scope, scorecard = scoped()
    validate_business_invariant_scope(scope, scorecard)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda scope, card: scope["last_measured"].update(commit="b" * 40),
        lambda scope, card: scope["last_measured"].update(judge_model="other"),
        lambda scope, card: scope["last_measured"].update(passed=1),
        lambda scope, card: scope["surface"].popitem(),
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


def test_a_rerun_replaces_only_an_unavailable_case_and_keeps_both_attempts() -> None:
    from tests.evals.business_invariants import compose_with_rerun

    base = passing_scorecard()
    base.update(candidate_sha="a" * 40)
    case_id = base["cases"][0]["case_id"]
    base["cases"][0].update(status="unavailable", failed_checks=["capture_error:X"])
    base["totals"] = {"passed": len(base["cases"]) - 1, "failed": 0, "unavailable": 1}
    base["status"] = "unavailable"
    rerun = {
        k: base[k] for k in ("candidate_sha", "runtime_model", "judge_model", "surface")
    }
    rerun["cases"] = [{**passing_scorecard()["cases"][0]}]
    composed = compose_with_rerun(base, rerun, case_id)
    assert composed["status"] == "passed"
    assert composed["totals"]["passed"] == len(composed["cases"])
    assert composed["cases"][0]["earlier_attempts"][0]["status"] == "unavailable"
    passed_case = base["cases"][1]["case_id"]
    with pytest.raises(AssertionError):
        compose_with_rerun(
            base,
            {**rerun, "cases": [{**rerun["cases"][0], "case_id": passed_case}]},
            passed_case,
        )
