"""The settings catalog matches the names the code reads."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.ci.settings_agreement import problems

ROOT = Path(__file__).resolve().parents[1]


def _tree(tmp_path: Path, source: str, settings: list[dict[str, object]]) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text(source)
    catalog = tmp_path / "scripts" / "ops"
    catalog.mkdir(parents=True)
    payload = {"version": 1, "settings": settings}
    (catalog / "settings_catalog.generated.json").write_text(json.dumps(payload) + "\n")
    return tmp_path


def test_a_setting_the_code_reads_and_the_list_lacks_fails(tmp_path: Path) -> None:
    root = _tree(tmp_path, 'import os\nos.getenv("CUADRAO_SAMPLE_FLAG", "false")\n', [])

    assert problems(root) == ["missing CUADRAO_SAMPLE_FLAG read by src/app.py"]


def test_a_listed_setting_nothing_reads_fails(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        "import os\n",
        [{"name": "CUADRAO_UNUSED", "default": None, "owner": "src/app.py"}],
    )

    assert problems(root) == ["orphan CUADRAO_UNUSED"]


def test_the_repository_settings_list_matches_the_code() -> None:
    assert problems(ROOT) == []
