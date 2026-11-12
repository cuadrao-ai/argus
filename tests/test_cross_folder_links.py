"""The cross-folder boundary works without installing either deployable."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_cross_folder_links.py"
spec = importlib.util.spec_from_file_location("cross_folder_links", SCRIPT)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


@pytest.mark.parametrize(
    "source",
    [
        'import layout from "../../marketing/lib/email/layout";',
        'require("../../marketing/lib/email/layout")',
        'readFileSync("marketing/lib/email/layout.ts")',
        'ROOT / "marketing" / "lib" / "email" / "layout.ts"',
        'join(root, "marketing", "lib", "email", "layout.ts")',
    ],
)
def test_literal_read_and_import_shapes(source):
    paths = guard.references("web/server/mail.ts", source, {})
    assert any(path.startswith("marketing/lib/email/layout") for path in paths)


def test_packaged_resource_uses_metadata_owner():
    paths = guard.references(
        "src/argus/mail.py",
        'files("contract").joinpath("support.json")',
        {"contract": "web/contract"},
    )
    assert paths == {"web/contract/support.json"}


def test_tracked_only_and_shared_is_allowed(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "pyproject.toml").write_text(
        '[tool.poetry]\npackages = [{include = "contract", from = "web"}]'
    )
    (tmp_path / "web").mkdir()
    (tmp_path / "web/tracked.ts").write_text('import data from "../shared/data.json";')
    (tmp_path / "web/untracked.ts").write_text(
        'import data from "../marketing/data.json";'
    )
    subprocess.run(
        ["git", "add", "pyproject.toml", "web/tracked.ts"], cwd=tmp_path, check=True
    )
    assert guard.discover(tmp_path) == {("pyproject.toml", "web/contract")}


def test_new_and_stale_link_messages(tmp_path, monkeypatch, capsys):
    (tmp_path / "scripts").mkdir()
    entry = {"consumer": "web/read.ts", "owner": "marketing/old.ts"}
    (tmp_path / guard.LIST).write_text(json.dumps([entry]))
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    monkeypatch.setattr(
        guard, "discover", lambda _: {("web/read.ts", "marketing/new.ts")}
    )
    assert guard.main() == 1
    output = capsys.readouterr().out
    assert (
        "new cross-folder link web/read.ts -> marketing/new.ts: put the fact in shared/ or in its one owner (see AGENTS.md)"
        in output
    )
    assert (
        "listed link no longer exists: remove it from scripts/cross_folder_links.json"
        in output
    )


def test_python_cross_package_import():
    assert "marketing/brand.py" in guard.references(
        "src/argus/code.py", "from marketing.brand import name", {}
    )


def test_multideployable_generator_is_not_unowned(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "pyproject.toml").write_text("[tool.poetry]")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/generate_new.py").write_text(
        'read("web/value.json"); write("src/argus/value.json")'
    )
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    assert guard.discover(tmp_path) == {
        ("scripts/generate_new.py", "web/value.json"),
        ("scripts/generate_new.py", "src/argus/value.json"),
    }
