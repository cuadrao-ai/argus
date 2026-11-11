from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_FILES = (
    ".github/argus-env.sh",
    "scripts/ops/staging_env.py",
    "scripts/ops/staging_env_manifest.json",
)


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    root = tmp_path / "checkout with spaces"
    for name in CONTRACT_FILES:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    return root


def source_contract(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; printf "%s\\n" "${ARGUS_RENDER_WEB_ENV[@]}"; echo CONTRACT_LOADED',
            "bash",
            str(root / ".github" / "argus-env.sh"),
        ],
        cwd=root.parent,
        env={
            key: value
            for key, value in os.environ.items()
            if key not in ("BASH_ENV", "ENV")
        },
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    ("rule", "listed"),
    [
        ({"value": "fixture"}, True),
        ({"enter": "fixture source"}, True),
        ({"enter": "fixture source", "optional": True}, True),
        ({"copy_from": "ARGUS_SYNTHETIC_LEGACY_KEY"}, True),
        ({"not_set": True}, False),
    ],
)
def test_web_contract_lists_every_name_production_may_hold(
    checkout: Path, rule: dict, listed: bool
) -> None:
    path = checkout / "scripts/ops/staging_env_manifest.json"
    manifest = json.loads(path.read_text())
    key = "ARGUS_SYNTHETIC_PROFILE_KEY"
    web = manifest["services"]["web"]["entries"]
    expected = {e["name"] for e in web if not e.get("local_only") and "not_set" not in e["production"]}
    web.append({"name": key, "kind": "plain", "production_only": True, "production": rule})
    path.write_text(json.dumps(manifest))

    result = source_contract(checkout)

    assert result.returncode == 0, result.stderr
    assert set(result.stdout.splitlines()) == expected | {"CONTRACT_LOADED"} | (
        {key} if listed else set()
    )


@pytest.mark.parametrize(
    "failure",
    [
        "missing-tool",
        "missing-manifest",
        "invalid-manifest",
        "empty-success",
        "partial-error",
    ],
)
def test_web_contract_stops_before_using_a_failed_manifest(
    checkout: Path, failure: str
) -> None:
    tool = checkout / "scripts/ops/staging_env.py"
    manifest = checkout / "scripts/ops/staging_env_manifest.json"
    if failure == "missing-tool":
        tool.unlink()
    elif failure == "missing-manifest":
        manifest.unlink()
    elif failure == "invalid-manifest":
        manifest.write_text("{}")
    elif failure == "empty-success":
        tool.write_text("")
    else:
        tool.write_text('print("ARGUS_PARTIAL_KEY")\nraise SystemExit(7)\n')
    result = source_contract(checkout)
    assert result.returncode != 0
    assert "CONTRACT_LOADED" not in result.stdout
    assert "ARGUS_PARTIAL_KEY" not in result.stdout
