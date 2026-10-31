from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from tests.evals import measurement_eval_scorecard as scorecards


def _valid_scorecard_provenance(
    *fixture_case_ids: str,
) -> Any:
    return scorecards.EvalScorecardProvenance(
        evaluation_mode="live",
        market_data_provider_mode="live_provider",
        asset_provider_mode="live_provider",
        candidate_sha="a" * 40,
        python_version="3.10.20",
        fixture_sha256="b" * 64,
        fixture_case_ids=fixture_case_ids or ("case-a",),
        worktree_clean=True,
        release_configuration={"CUADRAO_CHAT_MODEL": "test/model"},
        live_market_data_probe=scorecards.LiveMarketDataProbe(
            symbol="SPY",
            requested_date_range={"start": "2024-01-01", "end": "2024-01-10"},
            effective_date_range={"start": "2024-01-02", "end": "2024-01-10"},
            adjustment_reason="calendar_alignment",
        ),
    )


def test_scorecard_reports_per_category_pass_rates() -> None:
    results = [
        {"id": "case-a", "category": "messy_english", "status": "passed"},
        {"id": "case-b", "category": "messy_english", "status": "failed"},
        {
            "id": "case-c",
            "category": "messy_spanish",
            "status": "expected_failed",
        },
        {
            "id": "case-d",
            "category": "messy_spanish",
            "status": "unexpected_pass",
        },
    ]

    scorecard = scorecards.scorecard_for_results(
        results,
        provenance=_valid_scorecard_provenance(
            "case-a",
            "case-b",
            "case-c",
            "case-d",
        ),
    )

    assert scorecard["category_pass_rates"]["messy_english"] == {
        "passed": 1,
        "failed": 1,
        "expected_failed": 0,
        "unexpected_pass": 0,
        "skipped": 0,
        "infrastructure_error": 0,
        "pass_rate": 0.5,
    }
    assert scorecard["category_pass_rates"]["messy_spanish"] == {
        "passed": 0,
        "failed": 0,
        "expected_failed": 1,
        "unexpected_pass": 1,
        "skipped": 0,
        "infrastructure_error": 0,
        "pass_rate": 0.0,
    }
    assert scorecard["totals"]["unexpected_pass"] == 1


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("market_data_provider_mode", ""),
        ("asset_provider_mode", ""),
        ("candidate_sha", "not-a-sha"),
        ("python_version", ""),
        ("fixture_sha256", "not-a-hash"),
        ("fixture_case_ids", ()),
    ],
)
def test_scorecard_refuses_missing_or_malformed_provenance(
    field_name: str,
    invalid_value: Any,
) -> None:
    provenance = replace(
        _valid_scorecard_provenance(),
        **{field_name: invalid_value},
    )

    with pytest.raises(ValueError, match=f"scorecard_provenance:{field_name}"):
        scorecards.scorecard_for_results([], provenance=provenance)


def test_live_scorecard_refuses_non_live_market_data_provenance() -> None:
    provenance = replace(
        _valid_scorecard_provenance(),
        market_data_provider_mode="synthetic_unit_fixture",
    )

    with pytest.raises(
        ValueError,
        match="scorecard_provenance:live_market_data_provider_mode",
    ):
        scorecards.scorecard_for_results([], provenance=provenance)


def test_live_scorecard_refuses_missing_calendar_probe() -> None:
    provenance = replace(
        _valid_scorecard_provenance(),
        live_market_data_probe=None,
    )

    with pytest.raises(
        ValueError,
        match="scorecard_provenance:live_market_data_probe",
    ):
        scorecards.scorecard_for_results([], provenance=provenance)


def test_scorecard_refuses_dirty_worktree_provenance() -> None:
    provenance = replace(_valid_scorecard_provenance(), worktree_clean=False)

    with pytest.raises(ValueError, match="scorecard_provenance:worktree_clean"):
        scorecards.scorecard_for_results([], provenance=provenance)


def test_scorecard_records_provenance_and_provider_cost() -> None:
    results = [
        {
            "id": "costed-case",
            "category": "messy_english",
            "status": "passed",
            "route_receipts": [
                {"usage_cost_usd": 0.125},
                {"usage_cost_usd": 0.25},
                {"usage_cost_usd": None},
            ],
        }
    ]

    scorecard = scorecards.scorecard_for_results(
        results,
        provenance=_valid_scorecard_provenance("costed-case"),
    )

    assert scorecard["schema_version"] == 3
    assert scorecard["provenance"] == {
        "evaluation_mode": "live",
        "market_data_provider_mode": "live_provider",
        "asset_provider_mode": "live_provider",
        "candidate_sha": "a" * 40,
        "python_version": "3.10.20",
        "fixture_sha256": "b" * 64,
        "fixture_case_ids": ["costed-case"],
        "worktree_clean": True,
        "release_configuration": {"CUADRAO_CHAT_MODEL": "test/model"},
        "live_market_data_probe": {
            "symbol": "SPY",
            "requested_date_range": {
                "start": "2024-01-01",
                "end": "2024-01-10",
            },
            "effective_date_range": {
                "start": "2024-01-02",
                "end": "2024-01-10",
            },
            "adjustment_reason": "calendar_alignment",
        },
    }
    assert scorecard["provider_usage"] == {
        "route_receipt_count": 3,
        "reported_cost_receipt_count": 2,
        "unreported_cost_receipt_count": 1,
        "reported_cost_usd": 0.375,
    }


def test_live_scorecard_refuses_incomplete_fixture_result_set() -> None:
    provenance = _valid_scorecard_provenance("case-a", "case-b")

    with pytest.raises(
        ValueError,
        match="scorecard_results:incomplete_fixture_result_set",
    ):
        scorecards.scorecard_for_results(
            [{"id": "case-a", "category": "messy_english", "status": "passed"}],
            provenance=provenance,
        )


def test_measurement_fixture_identity_binds_filenames_and_contents(
    tmp_path: Path,
) -> None:
    fixture_dir = tmp_path / "fixtures"
    fixture_dir.mkdir()
    first = fixture_dir / "first.yaml"
    second = fixture_dir / "second.yaml"
    first.write_text("category: first\ncases: [{id: first}]\n", encoding="utf-8")
    second.write_text("category: second\ncases: [{id: second}]\n", encoding="utf-8")

    original = scorecards.measurement_fixture_sha256(fixture_dir)
    second.rename(fixture_dir / "renamed.yaml")
    renamed = scorecards.measurement_fixture_sha256(fixture_dir)
    (fixture_dir / "renamed.yaml").write_text(
        "category: renamed\ncases: [{id: renamed}]\n",
        encoding="utf-8",
    )
    changed = scorecards.measurement_fixture_sha256(fixture_dir)

    assert len(original) == 64
    assert original != renamed
    assert renamed != changed


def test_candidate_fixture_identity_rejects_non_commit_git_object(
    tmp_path: Path,
) -> None:
    fixture_dir = tmp_path / "tests" / "evals" / "measurement_cases"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "messy_english.yaml").write_text(
        "category: messy_english\ncases: [{id: case-a}]\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "init", "--quiet"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "add", "tests/evals/measurement_cases"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    tree_sha = subprocess.run(
        ["git", "write-tree"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    with pytest.raises(
        RuntimeError,
        match="scorecard_provenance:candidate_commit_unavailable",
    ):
        scorecards.measurement_fixture_identity_at_git_sha(
            candidate_sha=tree_sha,
            repository_root=tmp_path,
        )


def test_candidate_fixture_identity_ignores_git_replacement_refs(
    tmp_path: Path,
) -> None:
    fixture_dir = tmp_path / "tests" / "evals" / "measurement_cases"
    fixture_dir.mkdir(parents=True)
    subprocess.run(
        ["git", "init", "--quiet"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    def commit_fixture(case_id: str) -> str:
        (fixture_dir / "messy_english.yaml").write_text(
            f"category: messy_english\ncases: [{{id: {case_id}}}]\n",
            encoding="utf-8",
        )
        subprocess.run(
            ["git", "add", "tests/evals/measurement_cases"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Argus Eval Test",
                "-c",
                "user.email=argus-eval@example.invalid",
                "-c",
                "commit.gpgsign=false",
                "commit",
                "--quiet",
                "-m",
                case_id,
            ],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    candidate_sha = commit_fixture("case-a")
    expected = scorecards.measurement_fixture_identity_at_git_sha(
        candidate_sha=candidate_sha,
        repository_root=tmp_path,
    )
    replacement_sha = commit_fixture("case-b")
    subprocess.run(
        ["git", "replace", candidate_sha, replacement_sha],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    observed = scorecards.measurement_fixture_identity_at_git_sha(
        candidate_sha=candidate_sha,
        repository_root=tmp_path,
    )

    assert observed == expected


def test_write_scorecard_requires_provenance(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        scorecards.write_scorecard([], output_dir=tmp_path)


def test_write_scorecard_rejects_provenance_that_no_longer_matches_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("ARGUS_MARKET_DATA_PROVIDER_MODE", "synthetic_unit_fixture")
    monkeypatch.setenv("ARGUS_ASSET_PROVIDER_MODE", "synthetic_unit_fixture")
    monkeypatch.setattr(scorecards, "_worktree_is_clean", lambda _root: True)
    provenance = scorecards.build_scorecard_provenance(evaluation_mode="mocked")
    stale = replace(provenance, candidate_sha="a" * 40)

    with pytest.raises(ValueError, match="scorecard_provenance:candidate_sha_mismatch"):
        scorecards.write_scorecard([], provenance=stale, output_dir=tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_write_scorecard_emits_validated_provenance(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("ARGUS_MARKET_DATA_PROVIDER_MODE", "synthetic_unit_fixture")
    monkeypatch.setenv("ARGUS_ASSET_PROVIDER_MODE", "synthetic_unit_fixture")
    monkeypatch.setattr(scorecards, "_worktree_is_clean", lambda _root: True)
    provenance = scorecards.build_scorecard_provenance(evaluation_mode="mocked")

    scorecard_path = scorecards.write_scorecard(
        [],
        provenance=provenance,
        output_dir=tmp_path,
    )

    scorecard = json.loads(scorecard_path.read_text(encoding="utf-8"))
    assert scorecard["provenance"]["candidate_sha"] == provenance.candidate_sha
    assert scorecard["provenance"]["worktree_clean"] is True
