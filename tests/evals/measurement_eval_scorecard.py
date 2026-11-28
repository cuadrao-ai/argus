"""Recover the fixture identity of the commit named in promotion evidence."""

from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml  # type: ignore[import-untyped]

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_FULL_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class MeasurementFixtureIdentity:
    sha256: str
    case_ids: tuple[str, ...]


def measurement_fixture_identity_at_git_sha(
    *,
    candidate_sha: str,
    repository_root: Path = REPOSITORY_ROOT,
) -> MeasurementFixtureIdentity:
    if not _FULL_SHA_PATTERN.fullmatch(candidate_sha):
        raise ValueError("scorecard_provenance:candidate_sha")
    fixture_prefix = "tests/evals/measurement_cases"
    try:
        verified_commit = subprocess.run(
            [
                "git",
                "--no-replace-objects",
                "rev-parse",
                "--verify",
                f"{candidate_sha}^{{commit}}",
            ],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(
            "scorecard_provenance:candidate_commit_unavailable"
        ) from exc
    if verified_commit != candidate_sha:
        raise RuntimeError("scorecard_provenance:candidate_commit_unavailable")
    try:
        listed = subprocess.run(
            [
                "git",
                "--no-replace-objects",
                "ls-tree",
                "-r",
                "--name-only",
                candidate_sha,
                "--",
                fixture_prefix,
            ],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        fixture_paths = tuple(
            sorted(
                git_path
                for git_path in listed.stdout.splitlines()
                if Path(git_path).parent.as_posix() == fixture_prefix
                and git_path.endswith(".yaml")
            )
        )
        entries = []
        for git_path in fixture_paths:
            shown = subprocess.run(
                [
                    "git",
                    "--no-replace-objects",
                    "show",
                    f"{candidate_sha}:{git_path}",
                ],
                cwd=repository_root,
                check=True,
                capture_output=True,
                timeout=10,
            )
            entries.append((Path(git_path).name, shown.stdout))
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(
            "scorecard_provenance:candidate_fixture_identity_unavailable"
        ) from exc
    return _measurement_fixture_identity_from_entries(tuple(entries))


def _measurement_fixture_identity_from_entries(
    entries: tuple[tuple[str, bytes], ...],
) -> MeasurementFixtureIdentity:
    if not entries:
        raise ValueError("scorecard_provenance:fixture_set_empty")
    digest = hashlib.sha256()
    case_ids: list[str] = []
    for relative_name_text, contents in sorted(entries):
        relative_name = relative_name_text.encode("utf-8")
        digest.update(len(relative_name).to_bytes(8, "big"))
        digest.update(relative_name)
        digest.update(len(contents).to_bytes(8, "big"))
        digest.update(contents)
        payload = yaml.safe_load(contents)
        if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
            raise ValueError("scorecard_provenance:fixture_cases_invalid")
        for raw_case in payload["cases"]:
            raw_case_id = raw_case.get("id") if isinstance(raw_case, dict) else None
            case_id = str(raw_case_id or "").strip()
            if not case_id:
                raise ValueError("scorecard_provenance:fixture_case_id_missing")
            case_ids.append(case_id)
    if not case_ids or len(case_ids) != len(set(case_ids)):
        raise ValueError("scorecard_provenance:fixture_case_ids")
    return MeasurementFixtureIdentity(
        sha256=digest.hexdigest(),
        case_ids=tuple(case_ids),
    )


def _candidate_sha(repository_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "--no-replace-objects", "rev-parse", "--verify", "HEAD"],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("scorecard_provenance:candidate_sha_unavailable") from exc
    candidate_sha = completed.stdout.strip().lower()
    if not _FULL_SHA_PATTERN.fullmatch(candidate_sha):
        raise RuntimeError("scorecard_provenance:candidate_sha_unavailable")
    return candidate_sha
