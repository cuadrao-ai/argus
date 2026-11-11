"""Production dependency removals include parent packages and deferred imports."""

from pathlib import Path

import pytest

from scripts.check_production_dependencies import audit, import_graph, import_paths


def test_production_imports_have_declared_packages() -> None:
    _, failures = audit()
    assert failures == []


@pytest.mark.parametrize(
    "statement",
    (
        "import dateparser",
        "from dateparser.date import DateDataParser",
        "def parse():\n    import dateparser",
        "from importlib import import_module as load\nload('dateparser')",
    ),
)
def test_graph_reports_imports_in_parent_packages(tmp_path: Path, statement: str) -> None:
    package = tmp_path / "src" / "example"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(statement)
    (package / "app.py").write_text("from . import helper\n")
    (package / "helper.py").write_text("")
    graph, uses = import_graph(tmp_path)
    paths = import_paths(graph, "example.app")
    assert paths["example"] == ["example.app", "example"]
    assert "example.helper" in paths
    assert any(use.target.startswith("dateparser") for use in uses)


def test_graph_skips_type_only_imports_but_keeps_else(tmp_path: Path) -> None:
    package = tmp_path / "src" / "example"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n    import vectorbt\n"
        "else:\n    import dateparser\n"
    )
    _, uses = import_graph(tmp_path)
    assert "vectorbt" not in {use.target for use in uses}
    assert "dateparser" in {use.target for use in uses}


def test_graph_reports_computed_dynamic_imports(tmp_path: Path) -> None:
    package = tmp_path / "src" / "example"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("__import__(configured_name)\n")
    _, uses = import_graph(tmp_path)
    assert [(use.target, use.line) for use in uses] == [("<dynamic>", 1)]


def test_production_and_smoke_entry_points_import_without_optional_stack() -> None:
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import argus.api.main; import workflows.document_worker; "
            "import workflows.document_job; import argus.api.chat.backtest_jobs",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_lock_audit_discovers_removed_transitive_packages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.check_production_dependencies import removed_packages

    manifest = "[tool.poetry.dependencies]\nkept = '1.0'\n"
    lock = '[[package]]\nname = "kept"\ngroups = ["main"]\n'
    (tmp_path / "pyproject.toml").write_text(manifest)
    (tmp_path / "poetry.lock").write_text(lock)
    previous = {
        "base:pyproject.toml": manifest + "removed = '1.0'\n",
        "base:poetry.lock": lock
        + '[[package]]\nname = "transitive-only"\ngroups = ["main"]\n'
        + '[[package]]\nname = "dev-only"\ngroups = ["dev"]\n',
    }
    monkeypatch.setattr(
        "scripts.check_production_dependencies.subprocess.check_output",
        lambda command, **kwargs: previous[command[-1]],
    )
    assert removed_packages(tmp_path, "base") == {"removed", "transitive-only"}
