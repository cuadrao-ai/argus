import json
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
def contract(tmp_path: Path) -> tuple[Path, Path]:
    for name in CONTRACT_FILES:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / name, target)
    return tmp_path / CONTRACT_FILES[0], tmp_path / CONTRACT_FILES[2]


def _api_names(script: Path, cwd: Path) -> list[str]:
    return subprocess.run(
        [
            "bash",
            "-euc",
            'source "$1"; printf "%s\\n" "${ARGUS_RENDER_API_ENV[@]}"',
            "bash",
            str(script),
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()


def test_api_environment_membership_follows_the_manifest_production_rules(
    contract: tuple[Path, Path], tmp_path: Path
) -> None:
    script, manifest_path = contract
    manifest = json.loads(manifest_path.read_text())
    manifest["services"]["api"]["entries"] += [
        {
            "name": "ARGUS_TEST_RELEASE_FLAG",
            "kind": "plain",
            "production_only": True,
            "production": {"value": "false"},
        },
        {
            "name": "ARGUS_TEST_UNSET_FLAG",
            "kind": "plain",
            "production_only": True,
            "production": {"not_set": True},
        },
    ]
    manifest_path.write_text(json.dumps(manifest))

    names = _api_names(script, tmp_path.parent)

    assert "ARGUS_TEST_RELEASE_FLAG" in names
    assert "ARGUS_TEST_UNSET_FLAG" not in names


def test_api_environment_membership_rejects_an_invalid_manifest(
    contract: tuple[Path, Path], tmp_path: Path
) -> None:
    script, manifest_path = contract
    manifest_path.write_text("{")

    result = subprocess.run(
        ["bash", "-c", 'source "$1"', "bash", str(script)],
        cwd=tmp_path.parent,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "cannot load the settings manifest" in result.stderr
