from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.evals import measurement_eval_scorecard as scorecards
from tests.promotion_evidence_repository import commit_files


def test_committed_fixture_identity_binds_filename_and_contents(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    original = "tests/evals/measurement_cases/original.yaml"
    renamed = "tests/evals/measurement_cases/renamed.yaml"
    contents = "cases: [{id: example}]\n"
    first = commit_files(tmp_path, {original: contents})
    second = commit_files(tmp_path, {original: None, renamed: contents})
    third = commit_files(tmp_path, {renamed: contents + "\n"})
    commit_files(tmp_path, {renamed: None})

    identities = [
        scorecards.measurement_fixture_identity_at_git_sha(
            candidate_sha=sha, repository_root=tmp_path
        )
        for sha in (first, second, third)
    ]
    assert all(identity.case_ids == ("example",) for identity in identities)
    assert len({identity.sha256 for identity in identities}) == 3


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
