# ruff: noqa: E402, I001 -- live-eval env must load before Argus imports
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
import pytest

# Imports no Argus code, so it may load before the environment does.
from tests.evals.measurement_eval_scorecard import (
    assert_eval_env_file_untracked,
    build_scorecard_provenance,
    write_scorecard,
)

_EVAL_ENV_FILE = os.getenv("ARGUS_EVAL_ENV_FILE")
if _EVAL_ENV_FILE:
    # Argus imports load the shared project environment. Preload the explicit
    # live-eval environment so override=False preserves this suite's provider.
    # A tracked file is refused: evidence identity compares the tree, never the
    # eval's environment.
    assert_eval_env_file_untracked(Path(_EVAL_ENV_FILE))
    load_dotenv(Path(_EVAL_ENV_FILE), override=False)

from argus.domain.market_data.assets import clear_asset_cache
from tests.evals.measurement_eval_harness import (
    blocking_eval_results,
    expected_fail_issue_for_result,
    load_eval_cases,
    run_eval_case,
)


def _assert_requested_live_eval_credentials() -> None:
    if not (os.getenv("OPENROUTER_API_KEY") or "").strip():
        raise RuntimeError(
            "OPENROUTER_API_KEY is required for requested live evals"
        )


def test_measurement_live_eval_suite_writes_scorecard(monkeypatch) -> None:
    if os.getenv("ARGUS_RUN_LIVE_EVALS") != "1":
        pytest.skip("set ARGUS_RUN_LIVE_EVALS=1 to spend live LLM eval calls")
    _assert_requested_live_eval_credentials()

    if not (os.getenv("ARGUS_ASSET_PROVIDER_MODE") or "").strip():
        asset_provider_mode = (
            "recorded_provider_fixture"
            if (os.getenv("ARGUS_ASSET_FIXTURE_PATH") or "").strip()
            else "live_provider"
        )
        monkeypatch.setenv("ARGUS_ASSET_PROVIDER_MODE", asset_provider_mode)
    if os.getenv("ARGUS_ASSET_PROVIDER_MODE") == "live_provider" and not all(
        (os.getenv(name) or "").strip()
        for name in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY")
    ):
        pytest.fail(
            "live eval company-name grounding requires Alpaca asset-catalog keys "
            "or a recorded ARGUS_ASSET_FIXTURE_PATH"
        )
    clear_asset_cache()

    provenance = build_scorecard_provenance(evaluation_mode="live")
    results = [run_eval_case(case) for case in load_eval_cases()]
    scorecard_path = write_scorecard(results, provenance=provenance)
    failures = [
        {
            "id": result["id"],
            "category": result["category"],
            "status": result["status"],
            "expected_fail_issue": expected_fail_issue_for_result(result),
            "failed_checks": result["failed_checks"],
            "infrastructure_errors": result["infrastructure_errors"],
        }
        for result in blocking_eval_results(results)
    ]

    assert failures == [], f"Argus eval failures; scorecard: {scorecard_path}\n{failures}"
