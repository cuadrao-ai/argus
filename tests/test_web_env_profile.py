from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def web_contract(tmp_path: Path) -> Path:
    target = tmp_path / "checkout with spaces" / ".github"
    target.mkdir(parents=True)
    for name in (
        "argus-env.sh",
        "private-alpha-release-profile.py",
        "private-alpha-release-profile.json",
    ):
        shutil.copy2(ROOT / ".github" / name, target / name)
    return target


def source_contract(contract: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; printf "%s\\n" "${ARGUS_RENDER_WEB_ENV[@]}"; echo CONTRACT_LOADED',
            "bash",
            str(contract / "argus-env.sh"),
        ],
        cwd=contract.parent.parent,
        env={
            key: value
            for key, value in os.environ.items()
            if key not in ("BASH_ENV", "ENV")
        },
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("category", ["env", "required_present", "optional"])
def test_web_contract_derives_each_profile_key_category(
    web_contract: Path, category: str
) -> None:
    path = web_contract / "private-alpha-release-profile.json"
    profile = json.loads(path.read_text())
    key = "ARGUS_SYNTHETIC_PROFILE_KEY"
    web = profile["services"]["web"]
    if category == "env":
        web[category][key] = "fixture"
    else:
        web[category].append(key)
    path.write_text(json.dumps(profile))
    result = source_contract(web_contract)
    assert result.returncode == 0, result.stderr
    assert set(result.stdout.splitlines()) == set(web["env"]) | set(
        web["required_present"]
    ) | set(web["optional"]) | {"CONTRACT_LOADED"}


@pytest.mark.parametrize(
    "failure",
    [
        "missing-tool",
        "missing-profile",
        "invalid-profile",
        "empty-success",
        "partial-error",
    ],
)
def test_web_contract_stops_before_using_failed_profile(
    web_contract: Path, failure: str
) -> None:
    tool = web_contract / "private-alpha-release-profile.py"
    profile = web_contract / "private-alpha-release-profile.json"
    if failure == "missing-tool":
        tool.unlink()
    elif failure == "missing-profile":
        profile.unlink()
    elif failure == "invalid-profile":
        profile.write_text("{}")
    elif failure == "empty-success":
        tool.write_text("")
    else:
        tool.write_text('print("ARGUS_PARTIAL_KEY")\nraise SystemExit(7)\n')
    result = source_contract(web_contract)
    assert result.returncode != 0
    assert "CONTRACT_LOADED" not in result.stdout
    assert "ARGUS_PARTIAL_KEY" not in result.stdout
