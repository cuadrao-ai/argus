"""Validate the archived Business measurement against its fixtures and surviving owners."""

from __future__ import annotations

import hashlib
from typing import Any

from tests.evals.business_eval import (
    APPROVED_JUDGE_MODELS,
    RUNTIME_CANDIDATES,
    fixture_digest,
)
from tests.evals.business_variety import VARIETY_DIR, load_variety_cases
from tests.interpreter_prompt_surface import (
    BUSINESS_ACCEPTANCE_STEP_IDS,
    HISTORICAL_BUSINESS_OWNERS,
    validate_business_scorecard_surface,
)

SCHEMA_VERSION = "business_invariant_acceptance_v1"
MEASUREMENT_KIND = "invariant_measurement"


def _variety_digest() -> str:
    digest = hashlib.sha256()
    for path in sorted(VARIETY_DIR.glob("case_*.yaml")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def validate_business_invariant_measurement(scorecard: dict[str, Any]) -> None:
    """Assert a passed invariant measurement is complete and bound to its inputs."""

    assert scorecard["schema_version"] == SCHEMA_VERSION
    assert scorecard["measurement_kind"] == MEASUREMENT_KIND
    assert scorecard["scope"] == "business"
    assert scorecard["status"] == "passed"
    assert scorecard["judge_model"] in APPROVED_JUDGE_MODELS
    assert scorecard["runtime_model"] in RUNTIME_CANDIDATES
    assert set(scorecard["surface"]) == HISTORICAL_BUSINESS_OWNERS
    assert scorecard["calibration"]["status"] == "passed"
    assert scorecard["calibration"]["judge_model"] == scorecard["judge_model"]
    assert scorecard["frozen_fixture_sha256"] == fixture_digest()
    assert scorecard["variety_fixture_sha256"] == _variety_digest()
    frozen_ids = list(BUSINESS_ACCEPTANCE_STEP_IDS)
    varied_ids = [c["id"] for c in load_variety_cases()]
    assert scorecard["case_ids"] == {"frozen": frozen_ids, "varied": varied_ids}
    cases = scorecard["cases"]
    assert [c["case_id"] for c in cases] == frozen_ids + varied_ids
    assert {c["kind"] for c in cases[: len(frozen_ids)]} == {"frozen"}
    assert {c["kind"] for c in cases[len(frozen_ids) :]} == {"varied"}
    assert all(c["status"] == "passed" and not c["failed_checks"] for c in cases)
    assert scorecard["totals"] == {"passed": len(cases), "failed": 0, "unavailable": 0}
    for case in cases:
        if case["case_id"] == "en_revoked_accountant_read":
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
    """Every surviving Business owner must match its complete historical measurement."""

    measured = scope.get("last_measured")
    assert isinstance(measured, dict), "Business live measurement is still missing"
    validate_business_invariant_measurement(scorecard)
    assert measured["measurement_kind"] == MEASUREMENT_KIND
    validate_business_scorecard_surface(scope, scorecard)
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
