from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.evals import measurement_eval_scorecard as scorecards


def _environment_sources(tmp_path: Path) -> Path:
    """A checkout tracking a template, a symlink out of it and a folder symlink,
    with a gitignored .env, and outside links and hard links that reach tracked
    entries."""

    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
    settings = "ARGUS_TURN_CALL_ALLOWANCE=3\n"
    outside = tmp_path / "live-eval.env"
    outside.write_text(settings, encoding="utf-8")
    (tmp_path / "outside-link.env").symlink_to(outside)
    (tmp_path / "envdir").mkdir()
    (tmp_path / "envdir" / "live.env").write_text(settings, encoding="utf-8")
    (repository / ".gitignore").write_text(".env\n", encoding="utf-8")
    (repository / ".env.example").write_text(settings, encoding="utf-8")
    (repository / ".env.link").symlink_to(outside)
    (repository / "envs").symlink_to(tmp_path / "envdir")
    subprocess.run(
        ["git", "add", ".gitignore", ".env.example", ".env.link", "envs"],
        cwd=repository,
        check=True,
    )
    (repository / ".env").write_text(settings, encoding="utf-8")
    os.link(repository / ".env.example", tmp_path / "hard-link.env")
    os.link(
        repository / ".env.link",
        tmp_path / "symlink-hard-link.env",
        follow_symlinks=False,
    )
    (tmp_path / "via").symlink_to(repository)
    (tmp_path / "hop").symlink_to(repository / "envs")
    return repository


@pytest.mark.parametrize(
    ("env_file", "refused"),
    [
        pytest.param("repository/.env.example", True, id="tracked-template"),
        pytest.param("repository/.env.link", True, id="tracked-symlink"),
        pytest.param(
            "repository/envs/live.env", True, id="tracked-folder-symlink-on-the-way"
        ),
        pytest.param("via/.env.example", True, id="link-to-a-tracked-file"),
        pytest.param("hop/live.env", True, id="link-through-a-tracked-symlink"),
        pytest.param("hard-link.env", True, id="hard-link-to-a-tracked-file"),
        pytest.param(
            "symlink-hard-link.env", True, id="hard-link-to-a-tracked-symlink"
        ),
        pytest.param("repository/.env", False, id="gitignored-file-in-the-checkout"),
        pytest.param("live-eval.env", False, id="file-outside-the-checkout"),
        pytest.param("outside-link.env", False, id="link-to-an-untracked-file"),
    ],
)
def test_eval_env_file_may_not_be_fed_by_a_tracked_file(
    tmp_path: Path, env_file: str, refused: bool
) -> None:
    """Evidence identity compares the tree, never the eval's environment, so no
    tracked file may feed that environment, whatever path or link reaches it."""

    repository = _environment_sources(tmp_path)
    outcome = (
        pytest.raises(RuntimeError, match="scorecard_provenance:eval_env_file_tracked")
        if refused
        else nullcontext()
    )

    with outcome:
        scorecards.assert_eval_env_file_untracked(
            tmp_path / env_file, repository_root=repository
        )


def test_live_eval_refuses_a_tracked_env_file_before_loading_it() -> None:
    process_env = os.environ.copy()
    process_env.update(
        {
            "ARGUS_EVAL_ENV_FILE": str(scorecards.REPOSITORY_ROOT / ".env.example"),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )

    completed = subprocess.run(
        [sys.executable, "-c", "import tests.evals.test_measurement_eval_live"],
        cwd=scorecards.REPOSITORY_ROOT,
        env=process_env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "scorecard_provenance:eval_env_file_tracked" in completed.stderr


def test_live_eval_env_preloads_calendar_aware_confirmation(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    (project / "src" / "argus").mkdir(parents=True)
    (project / "pyproject.toml").write_text(
        '[tool.poetry]\nname = "argus-live-eval-regression"\n',
        encoding="utf-8",
    )
    (project / ".env").write_text(
        "ARGUS_MARKET_DATA_PROVIDER_MODE=synthetic_unit_fixture\n",
        encoding="utf-8",
    )
    eval_env = tmp_path / "live-eval.env"
    eval_env.write_text(
        "ARGUS_MARKET_DATA_PROVIDER_MODE=live_provider\n",
        encoding="utf-8",
    )
    process_env = os.environ.copy()
    process_env.pop("ARGUS_MARKET_DATA_PROVIDER_MODE", None)
    process_env.update(
        {
            "ARGUS_EVAL_ENV_FILE": str(eval_env),
            "ARGUS_RUN_LIVE_EVALS": "1",
            "ARGUS_TEST_PROJECT_ROOT": str(project),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    probe = textwrap.dedent(
        """
        import json
        import os
        from datetime import date, datetime
        from pathlib import Path

        import pandas as pd

        import argus.env as argus_env

        argus_env.__file__ = str(
            Path(os.environ["ARGUS_TEST_PROJECT_ROOT"])
            / "src"
            / "argus"
            / "env.py"
        )
        import tests.evals.test_measurement_eval_live  # noqa: F401
        from argus.domain.backtesting.coverage import prepare_market_data
        from argus.domain.market_data.capabilities import EquityMarketSession

        provider_mode = os.environ["ARGUS_MARKET_DATA_PROVIDER_MODE"]
        if provider_mode == "synthetic_unit_fixture":
            observed_days = pd.date_range(
                start="2024-01-01",
                end="2024-12-31",
                freq="1D",
                tz="UTC",
            )
        else:
            observed_days = pd.bdate_range(
                start="2024-01-02",
                end="2024-12-31",
                tz="UTC",
            )

        def fetch_bars(**_kwargs):
            close = pd.Series(
                range(100, 100 + len(observed_days)),
                index=observed_days,
                dtype=float,
            )
            return pd.DataFrame(
                {
                    "open": close,
                    "high": close + 1.0,
                    "low": close - 1.0,
                    "close": close,
                    "volume": 1_000.0,
                },
                index=observed_days,
            )

        def fetch_calendar(*, start_date: date, end_date: date):
            return tuple(
                EquityMarketSession(
                    provider="calendar-fixture",
                    session_date=timestamp.date(),
                    opens_at=datetime.fromisoformat(
                        f"{timestamp.date().isoformat()}T09:30:00-05:00"
                    ),
                    closes_at=datetime.fromisoformat(
                        f"{timestamp.date().isoformat()}T16:00:00-05:00"
                    ),
                )
                for timestamp in observed_days
                if start_date <= timestamp.date() <= end_date
            )

        prepared = prepare_market_data(
            {
                "asset_class": "equity",
                "symbols": ["AAPL"],
                "timeframe": "1D",
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "requested_date_range": {
                    "start": "2024-01-01",
                    "end": "2024-12-31",
                },
                "benchmark_symbol": "SPY",
            },
            fetch_ohlcv_func=fetch_bars,
            fetch_market_calendar_func=fetch_calendar,
        )
        print(
            json.dumps(
                {
                    "provider_mode": provider_mode,
                    "effective_date_range": (
                        prepared.effective_date_range.model_dump()
                    ),
                    "adjustment_reason": prepared.adjustment_reason,
                },
                sort_keys=True,
            )
        )
        """
    )

    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=Path(__file__).parents[2],
        env=process_env,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    result = json.loads(completed.stdout.strip().splitlines()[-1])

    assert result == {
        "provider_mode": "live_provider",
        "effective_date_range": {
            "start": "2024-01-02",
            "end": "2024-12-31",
        },
        "adjustment_reason": "calendar_alignment",
    }


def _prepared_market_data(
    *,
    effective_start: str,
    adjustment_reason: str | None,
) -> SimpleNamespace:
    return SimpleNamespace(
        effective_date_range=SimpleNamespace(
            model_dump=lambda: {
                "start": effective_start,
                "end": "2024-01-10",
            }
        ),
        adjustment_reason=adjustment_reason,
    )


def test_live_environment_probe_accepts_calendar_aligned_provider_behavior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARGUS_MARKET_DATA_PROVIDER_MODE", "live_provider")

    probe = scorecards.verify_live_market_data_environment(
        prepare_market_data_func=lambda _config: _prepared_market_data(
            effective_start="2024-01-02",
            adjustment_reason="calendar_alignment",
        )
    )

    assert probe.effective_date_range == {
        "start": "2024-01-02",
        "end": "2024-01-10",
    }
    assert probe.adjustment_reason == "calendar_alignment"


def test_live_environment_probe_rejects_synthetic_calendar_behavior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARGUS_MARKET_DATA_PROVIDER_MODE", "live_provider")

    with pytest.raises(
        RuntimeError,
        match="live_eval_market_data_probe_failed",
    ):
        scorecards.verify_live_market_data_environment(
            prepare_market_data_func=lambda _config: _prepared_market_data(
                effective_start="2024-01-01",
                adjustment_reason=None,
            )
        )


def test_live_environment_probe_rejects_non_live_provider_before_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "ARGUS_MARKET_DATA_PROVIDER_MODE",
        "synthetic_unit_fixture",
    )
    fetch_started = False

    def prepare_market_data(_config: dict[str, object]) -> SimpleNamespace:
        nonlocal fetch_started
        fetch_started = True
        return _prepared_market_data(
            effective_start="2024-01-01",
            adjustment_reason=None,
        )

    with pytest.raises(
        RuntimeError,
        match="live_eval_requires_explicit_live_provider",
    ):
        scorecards.verify_live_market_data_environment(
            prepare_market_data_func=prepare_market_data,
        )

    assert fetch_started is False


def test_live_provenance_rejects_dirty_worktree_before_provider_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARGUS_RUN_LIVE_EVALS", "1")
    monkeypatch.setenv("ARGUS_MARKET_DATA_PROVIDER_MODE", "live_provider")
    monkeypatch.setenv("ARGUS_ASSET_PROVIDER_MODE", "live_provider")
    monkeypatch.setattr(scorecards, "_worktree_is_clean", lambda _root: False)
    probe_started = False

    def verify_live_market_data_environment() -> scorecards.LiveMarketDataProbe:
        nonlocal probe_started
        probe_started = True
        raise AssertionError("provider probe should not start")

    monkeypatch.setattr(
        scorecards,
        "verify_live_market_data_environment",
        verify_live_market_data_environment,
    )

    with pytest.raises(ValueError, match="scorecard_provenance:worktree_clean"):
        scorecards.build_scorecard_provenance(evaluation_mode="live")

    assert probe_started is False


def test_live_suite_runs_environment_probe_before_any_eval_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.evals import test_measurement_eval_live as live_suite

    monkeypatch.setenv("ARGUS_RUN_LIVE_EVALS", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "fixture-openrouter-key")
    monkeypatch.setenv(
        "ARGUS_ASSET_PROVIDER_MODE",
        "recorded_provider_fixture",
    )
    monkeypatch.setattr(live_suite, "clear_asset_cache", lambda: None)
    case_iteration_started = False

    def load_eval_cases() -> list[object]:
        nonlocal case_iteration_started
        case_iteration_started = True
        return []

    monkeypatch.setattr(live_suite, "load_eval_cases", load_eval_cases)
    monkeypatch.setattr(
        live_suite,
        "build_scorecard_provenance",
        lambda **_kwargs: (_ for _ in ()).throw(
            RuntimeError("live_eval_market_data_probe_failed")
        ),
    )

    with pytest.raises(RuntimeError, match="live_eval_market_data_probe_failed"):
        live_suite.test_measurement_live_eval_suite_writes_scorecard(monkeypatch)

    assert case_iteration_started is False


def test_explicit_live_suite_fails_when_openrouter_key_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.evals import test_measurement_eval_live as live_suite

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(
        RuntimeError,
        match="OPENROUTER_API_KEY is required for requested live evals",
    ):
        live_suite._assert_requested_live_eval_credentials()
