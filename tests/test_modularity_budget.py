import json
from pathlib import Path

from scripts.check_modularity_budget import (
    SourceFileSize,
    collect_budgets,
    collect_source_sizes,
    format_report,
)


def test_modularity_budget_current_baselines_are_within_threshold() -> None:
    budgets = collect_budgets()

    assert budgets
    assert [budget for budget in budgets if budget.overage > 0] == []


def test_modularity_budget_reports_scanned_top_offenders_and_watched_status() -> None:
    budgets = collect_budgets()
    watched = budgets[0].path
    report = format_report(
        budgets,
        top_count=2,
        source_sizes=[
            SourceFileSize(Path("web/components/new-large-file.tsx"), 9999),
            SourceFileSize(watched, 5279),
        ],
    )

    assert "Top scanned files by current line count" in report
    assert "web/components/new-large-file.tsx: 9999 lines" in report
    assert f"{watched.as_posix()}: 5279 lines (watched)" in report
    assert "Watched-file budget status" in report
    assert "Budget violations:\n- none" in report


def test_modularity_budget_scans_production_sources_without_surprise_failures(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "src"
    test_root = tmp_path / "web" / "__tests__"
    source_root.mkdir()
    test_root.mkdir(parents=True)
    production_file = source_root / "large.py"
    excluded_test_file = test_root / "large.test.ts"
    production_file.write_text("line\n" * 4, encoding="utf-8")
    excluded_test_file.write_text("line\n" * 99, encoding="utf-8")
    config = tmp_path / ".agent" / "modularity_budget.json"
    config.parent.mkdir()
    config.write_text(
        """
        {
          "scan_roots": ["src", "web"],
          "scan_extensions": [".py", ".ts"],
          "scan_exclude_globs": ["web/__tests__/**"],
          "watched_files": {}
        }
        """,
        encoding="utf-8",
    )

    sizes = collect_source_sizes(config)

    assert sizes == [SourceFileSize(Path("src/large.py"), 4)]


def test_modularity_budget_config_watches_large_test_files() -> None:
    config_path = Path(".agent/modularity_budget.json")
    config = json.loads(config_path.read_text(encoding="utf-8"))

    assert "tests" in config["scan_roots"]
    assert "web/__tests__/**" not in config["scan_exclude_globs"]
    assert "web/e2e/**" not in config["scan_exclude_globs"]

    watched_files = set(config["watched_files"])
    baseline_capture_minimum_lines = config["baseline_capture_minimum_lines"]
    large_test_files = [
        source_file.path.as_posix()
        for source_file in collect_source_sizes(config_path)
        if source_file.path.as_posix().startswith(("tests/", "web/__tests__/", "web/e2e/"))
        and source_file.lines >= baseline_capture_minimum_lines
    ]

    assert large_test_files
    assert set(large_test_files).issubset(watched_files)


def test_modularity_budget_fails_only_past_allowed_growth(tmp_path: Path) -> None:
    watched_file = tmp_path / "large.py"
    watched_file.write_text("line\n" * 4, encoding="utf-8")
    config = tmp_path / "budget.json"
    config.write_text(
        '{"allowed_growth_lines": 2, "watched_files": {"'
        + str(watched_file)
        + '": 1}}',
        encoding="utf-8",
    )

    [budget] = collect_budgets(config)

    assert budget.baseline_lines == 1
    assert budget.current_lines == 4
    assert budget.limit == 3
    assert budget.overage == 1


def test_modularity_budget_applies_per_file_growth_overrides(tmp_path: Path) -> None:
    default_file = tmp_path / "default.py"
    strict_file = tmp_path / "strict.py"
    default_file.write_text("line\n" * 2, encoding="utf-8")
    strict_file.write_text("line\n" * 2, encoding="utf-8")
    config = tmp_path / "budget.json"
    config.write_text(
        json.dumps(
            {
                "allowed_growth_lines": 2,
                "allowed_growth_lines_by_file": {str(strict_file): 0},
                "watched_files": {
                    str(default_file): 1,
                    str(strict_file): 1,
                },
            }
        ),
        encoding="utf-8",
    )

    budgets_by_name = {budget.path.name: budget for budget in collect_budgets(config)}

    assert budgets_by_name["default.py"].allowed_growth_lines == 2
    assert budgets_by_name["default.py"].overage == 0
    assert budgets_by_name["strict.py"].allowed_growth_lines == 0
    assert budgets_by_name["strict.py"].limit == 1
    assert budgets_by_name["strict.py"].overage == 1


def test_modularity_budget_resolves_repo_relative_paths_from_config_location(
    tmp_path: Path,
) -> None:
    watched_file = tmp_path / "src" / "large.py"
    watched_file.parent.mkdir()
    watched_file.write_text("line\n" * 2, encoding="utf-8")
    config = tmp_path / ".agent" / "modularity_budget.json"
    config.parent.mkdir()
    config.write_text(
        '{"allowed_growth_lines": 2, "watched_files": {"src/large.py": 2}}',
        encoding="utf-8",
    )

    [budget] = collect_budgets(config)

    assert budget.path == Path("src/large.py")
    assert budget.current_lines == 2
    assert budget.overage == 0


def test_modularity_budget_skips_missing_watched_files(tmp_path: Path) -> None:
    config = tmp_path / "budget.json"
    config.write_text(
        '{"allowed_growth_lines": 2, "watched_files": {"missing.py": 1}}',
        encoding="utf-8",
    )

    assert collect_budgets(config) == []
