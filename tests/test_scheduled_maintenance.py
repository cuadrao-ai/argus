from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from scripts.ops import scheduled_maintenance
from scripts.ops.scheduled_maintenance import (
    MaintenanceJob,
    main,
    maintenance_jobs,
    run_maintenance,
    summarize,
)

ROOT = Path(__file__).resolve().parents[1]


def _jobs() -> tuple[MaintenanceJob, ...]:
    return maintenance_jobs(guest_limit=25, stale_limit=100)


def test_scheduled_pass_invokes_every_registered_ops_job() -> None:
    jobs = _jobs()

    assert [job.name for job in jobs] == [
        "guest_workspace_retention",
        "stale_backtest_jobs",
        "expired_access_welcome_claims",
        "account_deletion_resume",
    ]
    assert jobs[0].argv[0] == "scripts/ops/cleanup_expired_guest_workspaces.py"
    assert jobs[1].argv[0] == "scripts/ops/stale_backtest_jobs.py"
    assert jobs[2].argv == ("scripts/ops/release_expired_access_welcome_claims.py",)
    assert jobs[3].argv[0] == "scripts/ops/resume_account_deletions.py"
    for job in jobs:
        assert (ROOT / job.argv[0]).is_file()


def test_bounded_batch_arguments_reach_each_job() -> None:
    jobs = maintenance_jobs(guest_limit=40, stale_limit=7)

    assert jobs[0].argv == (
        "scripts/ops/cleanup_expired_guest_workspaces.py",
        "--limit",
        "40",
    )
    assert jobs[1].argv == (
        "scripts/ops/stale_backtest_jobs.py",
        "--json",
        "--limit",
        "7",
    )
    assert jobs[3].argv[1:] == ("--limit", "25")
    tuned = maintenance_jobs(guest_limit=40, stale_limit=7, deletion_limit=3)
    assert tuned[0].argv[-1] == "40" and tuned[3].argv[1:] == ("--limit", "3")


def test_deletion_limit_is_its_own_bounded_flag() -> None:
    from scripts.ops.scheduled_maintenance import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["--guest-limit", "40", "--deletion-limit", "9"])
    assert (args.guest_limit, args.deletion_limit) == (40, 9)
    for bad in ("0", "101"):
        with pytest.raises(SystemExit):
            parser.parse_args(["--deletion-limit", bad])


def test_a_failed_retention_purge_does_not_hide_the_reconciler() -> None:
    invoked: list[str] = []

    def runner(job: MaintenanceJob) -> int:
        invoked.append(job.name)
        return 1 if job.name == "guest_workspace_retention" else 0

    outcomes = run_maintenance(_jobs(), runner=runner)
    summary = summarize(outcomes)

    assert invoked == [
        "guest_workspace_retention",
        "stale_backtest_jobs",
        "expired_access_welcome_claims",
        "account_deletion_resume",
    ]
    assert summary["status"] == "degraded"
    assert summary["failed_count"] == 1
    assert summary["failed_jobs"] == ["guest_workspace_retention"]


def test_a_failed_reconciliation_is_counted_and_named() -> None:
    outcomes = run_maintenance(
        _jobs(),
        runner=lambda job: 1 if job.name == "stale_backtest_jobs" else 0,
    )
    summary = summarize(outcomes)

    assert summary["status"] == "degraded"
    assert summary["failed_jobs"] == ["stale_backtest_jobs"]


def test_a_job_that_cannot_start_is_a_counted_failure_not_a_crash() -> None:
    def runner(job: MaintenanceJob) -> int:
        raise OSError("interpreter is gone")

    outcomes = run_maintenance(_jobs(), runner=runner)
    summary = summarize(outcomes)

    assert summary["failed_count"] == 4
    assert all(outcome.error == "interpreter is gone" for outcome in outcomes)


def test_a_clean_pass_reports_ready_and_no_failures() -> None:
    summary = summarize(run_maintenance(_jobs(), runner=lambda job: 0))

    assert summary["status"] == "ready"
    assert summary["failed_count"] == 0
    assert summary["failed_jobs"] == []
    assert summary["job_count"] == 4


def test_scheduler_carries_no_state_so_a_retry_repeats_the_same_pass() -> None:
    invocations: list[tuple[str, ...]] = []

    def runner(job: MaintenanceJob) -> int:
        invocations.append(job.argv)
        return 0

    first = summarize(run_maintenance(_jobs(), runner=runner))
    halfway = len(invocations)
    second = summarize(run_maintenance(_jobs(), runner=runner))

    assert invocations[:halfway] == invocations[halfway:]
    assert first == second


def test_main_exits_nonzero_and_prints_a_machine_readable_summary(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(
        scheduled_maintenance,
        "run_job",
        lambda job: 1 if job.name == "stale_backtest_jobs" else 0,
    )

    exit_code = main([])
    summary = json.loads(capsys.readouterr().out.strip().splitlines()[-1])

    assert exit_code == 1
    assert summary["status"] == "degraded"
    assert summary["failed_jobs"] == ["stale_backtest_jobs"]
    assert summary["job_count"] == 4


def test_main_exits_zero_only_when_every_job_succeeded(monkeypatch, capsys) -> None:
    monkeypatch.setattr(scheduled_maintenance, "run_job", lambda job: 0)

    exit_code = main([])
    summary = json.loads(capsys.readouterr().out.strip().splitlines()[-1])

    assert exit_code == 0
    assert summary["status"] == "ready"


def test_each_job_runs_as_its_own_child_from_the_repo_root(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    class _Completed:
        returncode = 0

    def fake_run(argv, **kwargs):
        calls.append({"argv": list(argv), **kwargs})
        return _Completed()

    monkeypatch.setattr(scheduled_maintenance.subprocess, "run", fake_run)
    scheduled_maintenance.run_job(_jobs()[0])

    assert calls[0]["argv"][0] == sys.executable
    assert calls[0]["argv"][1] == "scripts/ops/cleanup_expired_guest_workspaces.py"
    assert calls[0]["cwd"] == str(ROOT)
    assert calls[0]["check"] is False


def test_runbook_keeps_operator_entry_point_outside_render_contract() -> None:
    blueprint = (ROOT / "render.yaml").read_text(encoding="utf-8")
    runbook = (ROOT / "docs" / "PRIVATE_LAUNCH_RUNBOOK.md").read_text(encoding="utf-8")
    entry_point = "poetry run python scripts/ops/scheduled_maintenance.py"

    assert f"startCommand: {entry_point}" not in blueprint
    assert entry_point in runbook
