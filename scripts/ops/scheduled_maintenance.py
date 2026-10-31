"""Run every recurring Argus maintenance job in one scheduled pass."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class MaintenanceJob:
    name: str
    argv: tuple[str, ...]


@dataclass(frozen=True)
class JobOutcome:
    name: str
    exit_code: int
    error: str | None = None

    @property
    def failed(self) -> bool:
        return self.exit_code != 0

    def as_dict(self) -> dict[str, object]:
        return {"name": self.name, "exit_code": self.exit_code, "error": self.error}


def maintenance_jobs(
    *, guest_limit: int, deletion_limit: int = 25
) -> tuple[MaintenanceJob, ...]:
    """Retention first: it has a documented deadline."""
    return (
        MaintenanceJob(
            name="guest_workspace_retention",
            argv=(
                "scripts/ops/cleanup_expired_guest_workspaces.py",
                "--limit",
                str(guest_limit),
            ),
        ),
        MaintenanceJob(
            name="expired_access_welcome_claims",
            argv=("scripts/ops/release_expired_access_welcome_claims.py",),
        ),
        MaintenanceJob(
            name="account_deletion_resume",
            argv=(
                "scripts/ops/resume_account_deletions.py",
                "--limit",
                str(deletion_limit),
            ),
        ),
    )


def run_job(job: MaintenanceJob) -> int:
    # A child process per job: a job that dies hard cannot take the scheduler
    # down with it, and its own report reaches the cron log unaltered.
    completed = subprocess.run(
        [sys.executable, *job.argv],
        cwd=str(ROOT),
        check=False,
    )
    return int(completed.returncode)


def run_maintenance(
    jobs: Sequence[MaintenanceJob],
    *,
    runner: Callable[[MaintenanceJob], int] | None = None,
) -> list[JobOutcome]:
    """Every job runs even after an earlier one fails, so no failure is hidden."""
    runner = runner or run_job
    outcomes: list[JobOutcome] = []
    for job in jobs:
        print(f"scheduled maintenance: running job={job.name}", flush=True)
        try:
            exit_code = int(runner(job))
            error = None
        except Exception as exc:
            exit_code = 1
            error = str(exc)
        outcome = JobOutcome(name=job.name, exit_code=exit_code, error=error)
        outcomes.append(outcome)
        print(
            f"scheduled maintenance: job={job.name} "
            f"status={'failed' if outcome.failed else 'ok'} "
            f"exit_code={outcome.exit_code}" + (f" error={error}" if error else ""),
            flush=True,
        )
    return outcomes


def summarize(outcomes: Sequence[JobOutcome]) -> dict[str, object]:
    failed = [outcome for outcome in outcomes if outcome.failed]
    return {
        "status": "degraded" if failed else "ready",
        "job_count": len(outcomes),
        "failed_count": len(failed),
        "failed_jobs": [outcome.name for outcome in failed],
        "jobs": [outcome.as_dict() for outcome in outcomes],
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the scheduled Argus retention and reconciliation jobs.",
    )
    parser.add_argument("--guest-limit", type=int, default=25, choices=range(1, 101))
    parser.add_argument("--deletion-limit", type=int, default=25, choices=range(1, 101))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    outcomes = run_maintenance(
        maintenance_jobs(
            guest_limit=args.guest_limit,
            deletion_limit=args.deletion_limit,
        )
    )
    summary = summarize(outcomes)
    print(json.dumps(summary, sort_keys=True), flush=True)
    # A silent zero here would make the retention windows in DATA_MODEL.md look
    # enforced while nothing enforced them.
    return 1 if summary["failed_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
