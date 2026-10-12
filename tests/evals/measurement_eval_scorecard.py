from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable

import yaml  # type: ignore[import-untyped]

from tests.promotion_evidence_configuration import measured_release_configuration

FIXTURE_DIR = Path(__file__).with_name("measurement_cases")
SCORECARD_DIR = Path("temp/argus_eval_scorecards")
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

_LIVE_PROBE_SYMBOL = "SPY"
_LIVE_PROBE_REQUESTED_DATE_RANGE = {
    "start": "2024-01-01",
    "end": "2024-01-10",
}
_LIVE_PROBE_EFFECTIVE_DATE_RANGE = {
    "start": "2024-01-02",
    "end": "2024-01-10",
}
_FULL_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class LiveMarketDataProbe:
    symbol: str
    requested_date_range: dict[str, str]
    effective_date_range: dict[str, str]
    adjustment_reason: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "requested_date_range": dict(self.requested_date_range),
            "effective_date_range": dict(self.effective_date_range),
            "adjustment_reason": self.adjustment_reason,
        }


@dataclass(frozen=True)
class EvalScorecardProvenance:
    evaluation_mode: str
    market_data_provider_mode: str
    asset_provider_mode: str
    candidate_sha: str
    python_version: str
    fixture_sha256: str
    fixture_case_ids: tuple[str, ...]
    worktree_clean: bool
    release_configuration: dict[str, str | None]
    live_market_data_probe: LiveMarketDataProbe | None = None


@dataclass(frozen=True)
class MeasurementFixtureIdentity:
    sha256: str
    case_ids: tuple[str, ...]


def measurement_fixture_paths(path: Path = FIXTURE_DIR) -> tuple[Path, ...]:
    fixture_paths = tuple(sorted(path.glob("*.yaml")))
    if not fixture_paths:
        raise ValueError("scorecard_provenance:fixture_set_empty")
    return fixture_paths


def measurement_fixture_sha256(path: Path = FIXTURE_DIR) -> str:
    return measurement_fixture_identity(path).sha256


def measurement_fixture_identity(path: Path = FIXTURE_DIR) -> MeasurementFixtureIdentity:
    entries = tuple(
        (fixture_path.relative_to(path).as_posix(), fixture_path.read_bytes())
        for fixture_path in measurement_fixture_paths(path)
    )
    return _measurement_fixture_identity_from_entries(entries)


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


def measurement_fixture_documents(
    path: Path = FIXTURE_DIR,
) -> tuple[tuple[Path, dict[str, Any]], ...]:
    documents: list[tuple[Path, dict[str, Any]]] = []
    for fixture_path in measurement_fixture_paths(path):
        payload = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
            raise ValueError("scorecard_provenance:fixture_cases_invalid")
        documents.append((fixture_path, payload))
    return tuple(documents)


def measurement_fixture_case_ids(path: Path = FIXTURE_DIR) -> tuple[str, ...]:
    return measurement_fixture_identity(path).case_ids


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


def build_scorecard_provenance(
    *,
    evaluation_mode: str,
    fixture_dir: Path = FIXTURE_DIR,
    repository_root: Path = REPOSITORY_ROOT,
) -> EvalScorecardProvenance:
    if evaluation_mode not in {"live", "mocked"}:
        raise ValueError("scorecard_provenance:evaluation_mode")
    market_data_provider_mode = _resolved_provider_mode(
        "ARGUS_MARKET_DATA_PROVIDER_MODE"
    )
    asset_provider_mode = _resolved_provider_mode("ARGUS_ASSET_PROVIDER_MODE")
    candidate_sha = _candidate_sha(repository_root)
    python_version = platform.python_version()
    fixture_identity = measurement_fixture_identity(fixture_dir)
    worktree_clean = _worktree_is_clean(repository_root)
    if not worktree_clean:
        raise ValueError("scorecard_provenance:worktree_clean")
    live_probe = None
    if evaluation_mode == "live":
        if os.getenv("ARGUS_RUN_LIVE_EVALS") != "1":
            raise RuntimeError("live_eval_requires_ARGUS_RUN_LIVE_EVALS")
        live_probe = verify_live_market_data_environment()
    provenance = EvalScorecardProvenance(
        evaluation_mode=evaluation_mode,
        market_data_provider_mode=market_data_provider_mode,
        asset_provider_mode=asset_provider_mode,
        candidate_sha=candidate_sha,
        python_version=python_version,
        fixture_sha256=fixture_identity.sha256,
        fixture_case_ids=fixture_identity.case_ids,
        worktree_clean=worktree_clean,
        release_configuration=measured_release_configuration(
            candidate_sha, repository_root=repository_root
        ),
        live_market_data_probe=live_probe,
    )
    validated_provenance_payload(provenance)
    return provenance


def verify_live_market_data_environment(
    *,
    prepare_market_data_func: Callable[[dict[str, Any]], Any] | None = None,
) -> LiveMarketDataProbe:
    provider_mode = _resolved_provider_mode("ARGUS_MARKET_DATA_PROVIDER_MODE")
    if provider_mode != "live_provider":
        raise RuntimeError(
            "live_eval_requires_explicit_live_provider:"
            f"ARGUS_MARKET_DATA_PROVIDER_MODE={provider_mode}"
        )
    if prepare_market_data_func is None:
        from argus.domain.backtesting.coverage import prepare_market_data

        prepare_market_data_func = prepare_market_data

    config = {
        "asset_class": "equity",
        "symbols": [_LIVE_PROBE_SYMBOL],
        "timeframe": "1D",
        "start_date": _LIVE_PROBE_REQUESTED_DATE_RANGE["start"],
        "end_date": _LIVE_PROBE_REQUESTED_DATE_RANGE["end"],
        "requested_date_range": dict(_LIVE_PROBE_REQUESTED_DATE_RANGE),
        "benchmark_symbol": _LIVE_PROBE_SYMBOL,
    }
    try:
        prepared = prepare_market_data_func(config)
        effective_date_range = prepared.effective_date_range.model_dump()
        adjustment_reason = prepared.adjustment_reason
    except Exception as exc:
        raise RuntimeError("live_eval_market_data_probe_failed:provider_error") from exc

    probe = LiveMarketDataProbe(
        symbol=_LIVE_PROBE_SYMBOL,
        requested_date_range=dict(_LIVE_PROBE_REQUESTED_DATE_RANGE),
        effective_date_range={
            "start": str(effective_date_range.get("start") or ""),
            "end": str(effective_date_range.get("end") or ""),
        },
        adjustment_reason=(
            str(adjustment_reason) if adjustment_reason is not None else None
        ),
    )
    if (
        probe.effective_date_range != _LIVE_PROBE_EFFECTIVE_DATE_RANGE
        or probe.adjustment_reason != "calendar_alignment"
    ):
        raise RuntimeError(
            "live_eval_market_data_probe_failed:"
            "expected_2024-01-02_calendar_alignment"
        )
    return probe


def scorecard_for_results(
    results: list[dict[str, Any]],
    *,
    provenance: EvalScorecardProvenance,
) -> dict[str, Any]:
    provenance_payload = validated_provenance_payload(provenance)
    _assert_complete_live_result_set(results, provenance=provenance)
    by_category: dict[str, dict[str, int | float | None]] = {}
    for result in results:
        category = str(result["category"])
        bucket = by_category.setdefault(
            category,
            {
                "passed": 0,
                "failed": 0,
                "expected_failed": 0,
                "unexpected_pass": 0,
                "skipped": 0,
                "infrastructure_error": 0,
                "pass_rate": 0.0,
            },
        )
        status = str(result["status"])
        if status not in bucket:
            status = "failed"
        bucket[status] = int(bucket[status]) + 1

    for bucket in by_category.values():
        denominator = sum(
            int(bucket[status])
            for status in ("passed", "failed", "expected_failed", "unexpected_pass")
        )
        bucket["pass_rate"] = (
            None if denominator == 0 else round(int(bucket["passed"]) / denominator, 4)
        )

    return {
        "schema_version": 3,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provenance": provenance_payload,
        "provider_usage": _provider_usage(results),
        "category_pass_rates": by_category,
        "totals": {
            status: sum(int(item[status]) for item in by_category.values())
            for status in (
                "passed",
                "failed",
                "expected_failed",
                "unexpected_pass",
                "skipped",
                "infrastructure_error",
            )
        },
        "results": results,
    }


def write_scorecard(
    results: list[dict[str, Any]],
    *,
    provenance: EvalScorecardProvenance,
    output_dir: Path = SCORECARD_DIR,
) -> Path:
    assert_provenance_matches_current_run(provenance)
    scorecard = scorecard_for_results(results, provenance=provenance)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"argus-eval-scorecard-{stamp}.json"
    path.write_text(json.dumps(scorecard, indent=2, sort_keys=True), encoding="utf-8")
    return path


def validated_provenance_payload(
    provenance: EvalScorecardProvenance,
) -> dict[str, Any]:
    if provenance.evaluation_mode not in {"live", "mocked"}:
        raise ValueError("scorecard_provenance:evaluation_mode")
    for field_name in (
        "market_data_provider_mode",
        "asset_provider_mode",
        "python_version",
    ):
        if not str(getattr(provenance, field_name) or "").strip():
            raise ValueError(f"scorecard_provenance:{field_name}")
    if not _FULL_SHA_PATTERN.fullmatch(provenance.candidate_sha):
        raise ValueError("scorecard_provenance:candidate_sha")
    if not _SHA256_PATTERN.fullmatch(provenance.fixture_sha256):
        raise ValueError("scorecard_provenance:fixture_sha256")
    if (
        not provenance.fixture_case_ids
        or any(not case_id.strip() for case_id in provenance.fixture_case_ids)
        or len(provenance.fixture_case_ids) != len(set(provenance.fixture_case_ids))
    ):
        raise ValueError("scorecard_provenance:fixture_case_ids")
    if provenance.worktree_clean is not True:
        raise ValueError("scorecard_provenance:worktree_clean")

    live_probe_payload = None
    if provenance.live_market_data_probe is not None:
        live_probe_payload = provenance.live_market_data_probe.as_dict()
    if provenance.evaluation_mode == "live":
        if provenance.market_data_provider_mode != "live_provider":
            raise ValueError(
                "scorecard_provenance:live_market_data_provider_mode"
            )
        if (
            live_probe_payload is None
            or live_probe_payload["symbol"] != _LIVE_PROBE_SYMBOL
            or live_probe_payload["requested_date_range"]
            != _LIVE_PROBE_REQUESTED_DATE_RANGE
            or live_probe_payload["effective_date_range"]
            != _LIVE_PROBE_EFFECTIVE_DATE_RANGE
            or live_probe_payload["adjustment_reason"] != "calendar_alignment"
        ):
            raise ValueError("scorecard_provenance:live_market_data_probe")

    return {
        "evaluation_mode": provenance.evaluation_mode,
        "market_data_provider_mode": provenance.market_data_provider_mode,
        "asset_provider_mode": provenance.asset_provider_mode,
        "candidate_sha": provenance.candidate_sha,
        "python_version": provenance.python_version,
        "fixture_sha256": provenance.fixture_sha256,
        "fixture_case_ids": list(provenance.fixture_case_ids),
        "worktree_clean": provenance.worktree_clean,
        "release_configuration": dict(provenance.release_configuration),
        "live_market_data_probe": live_probe_payload,
    }


def assert_provenance_matches_current_run(
    provenance: EvalScorecardProvenance,
) -> None:
    validated_provenance_payload(provenance)
    fixture_identity = measurement_fixture_identity(FIXTURE_DIR)
    expected_values = {
        "market_data_provider_mode": _resolved_provider_mode(
            "ARGUS_MARKET_DATA_PROVIDER_MODE"
        ),
        "asset_provider_mode": _resolved_provider_mode("ARGUS_ASSET_PROVIDER_MODE"),
        "candidate_sha": _candidate_sha(REPOSITORY_ROOT),
        "python_version": platform.python_version(),
        "fixture_sha256": fixture_identity.sha256,
        "fixture_case_ids": fixture_identity.case_ids,
        "worktree_clean": _worktree_is_clean(REPOSITORY_ROOT),
        "release_configuration": measured_release_configuration(
            _candidate_sha(REPOSITORY_ROOT), repository_root=REPOSITORY_ROOT
        ),
    }
    for field_name, expected in expected_values.items():
        if getattr(provenance, field_name) != expected:
            raise ValueError(f"scorecard_provenance:{field_name}_mismatch")


def _assert_complete_live_result_set(
    results: list[dict[str, Any]],
    *,
    provenance: EvalScorecardProvenance,
) -> None:
    if provenance.evaluation_mode != "live":
        return
    result_case_ids = tuple(str(result.get("id") or "") for result in results)
    if result_case_ids != provenance.fixture_case_ids:
        raise ValueError("scorecard_results:incomplete_fixture_result_set")


def _resolved_provider_mode(env_name: str) -> str:
    mode = (os.getenv(env_name) or "").strip().lower()
    if not mode:
        raise RuntimeError(f"scorecard_provenance:{env_name.lower()}_missing")
    return mode


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


def _worktree_is_clean(repository_root: Path) -> bool:
    try:
        completed = subprocess.run(
            [
                "git",
                "--no-replace-objects",
                "status",
                "--porcelain",
                "--untracked-files=all",
            ],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("scorecard_provenance:worktree_status_unavailable") from exc
    return not completed.stdout.strip()


def assert_eval_env_file_untracked(
    env_file: Path, *, repository_root: Path = REPOSITORY_ROOT
) -> None:
    """Refuse an environment file that a tracked file feeds.

    Promotion evidence identity compares the repository's tree, never the eval's
    environment, so no tracked file may feed that environment. The file is
    refused when it, or any step on the way to it, is a tracked file or tracked
    symlink, compared by identity so whatever path or link reaches it counts. A
    gitignored file stays allowed, and an untracked file that is not ignored
    already fails the clean-worktree check. The guard catches an operator
    mistake, not a deliberate bypass.
    """

    root = repository_root.resolve()
    # The walk ends on the real file, so the visited steps cover every link on the
    # way and the target.
    identities = set()
    for path in _paths_opened(env_file):
        try:
            status = path.lstat()
        except OSError:
            continue
        identities.add((status.st_dev, status.st_ino))
    if identities & _tracked_file_identities(root):
        raise RuntimeError("scorecard_provenance:eval_env_file_tracked")


def _tracked_file_identities(root: Path) -> frozenset[tuple[int, int]]:
    """The device and inode of every file the repository tracks."""

    try:
        listed = subprocess.run(
            ["git", "--no-replace-objects", "ls-files", "-z"],
            cwd=root,
            check=True,
            capture_output=True,
            timeout=10,
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(
            "scorecard_provenance:eval_env_file_identity_unavailable"
        ) from exc
    identities = set()
    for name in listed.decode("utf-8", "surrogateescape").split("\0"):
        if not name:
            continue
        try:
            status = (root / name).lstat()
        except OSError:
            continue
        identities.add((status.st_dev, status.st_ino))
    return frozenset(identities)


# The limit the kernel applies before it reports a symlink loop.
_MAX_SYMLINK_HOPS = 40


def _paths_opened(path: Path) -> list[Path]:
    """Every absolute path visited to open `path`, expanding each symlink where
    it is met, as the operating system resolves it."""

    pending = list(path.absolute().parts)
    current = Path(pending.pop(0))
    visited = [current]
    hops = 0
    while pending:
        part = pending.pop(0)
        if part == ".":
            continue
        # Every symlink is expanded when met, so the parent here is physical.
        current = current.parent if part == ".." else current / part
        visited.append(current)
        if current.is_symlink():
            hops += 1
            if hops > _MAX_SYMLINK_HOPS:
                raise RuntimeError("scorecard_provenance:eval_env_file_link_loop")
            target = Path(os.readlink(current))
            base = target if target.is_absolute() else current.parent / target
            pending = [*base.parts, *pending]
            current = Path(pending.pop(0))
    return visited


def _provider_usage(results: list[dict[str, Any]]) -> dict[str, Any]:
    route_receipts: list[Any] = []
    for result in results:
        receipts = result.get("route_receipts")
        if isinstance(receipts, list):
            route_receipts.extend(receipts)
    reported_costs: list[Decimal] = []
    unreported_cost_receipt_count = 0
    for receipt in route_receipts:
        raw_cost = receipt.get("usage_cost_usd") if isinstance(receipt, dict) else None
        if raw_cost is None:
            unreported_cost_receipt_count += 1
            continue
        try:
            reported_costs.append(Decimal(str(raw_cost)))
        except (InvalidOperation, ValueError):
            unreported_cost_receipt_count += 1
    return {
        "route_receipt_count": len(route_receipts),
        "reported_cost_receipt_count": len(reported_costs),
        "unreported_cost_receipt_count": unreported_cost_receipt_count,
        "reported_cost_usd": float(sum(reported_costs, Decimal("0"))),
    }
