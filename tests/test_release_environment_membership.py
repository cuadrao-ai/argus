import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def contract(tmp_path: Path) -> tuple[Path, Path]:
    directory = tmp_path / ".github"
    directory.mkdir()
    for name in (
        "argus-env.sh",
        "private-alpha-release-profile.py",
        "private-alpha-release-profile.json",
    ):
        shutil.copy(ROOT / ".github" / name, directory / name)
    return directory / "argus-env.sh", directory / "private-alpha-release-profile.json"


def test_api_environment_membership_follows_the_release_profile(
    contract: tuple[Path, Path], tmp_path: Path
) -> None:
    script, profile_path = contract
    profile = json.loads(profile_path.read_text())
    profile["services"]["api"]["env"]["ARGUS_TEST_RELEASE_FLAG"] = "false"
    profile_path.write_text(json.dumps(profile))

    result = subprocess.run(
        [
            "bash",
            "-euc",
            'source "$1"; printf "%s\\n" "${ARGUS_RENDER_API_ENV[@]}"',
            "bash",
            str(script),
        ],
        cwd=tmp_path.parent,
        capture_output=True,
        text=True,
        check=True,
    )

    assert "ARGUS_TEST_RELEASE_FLAG" in result.stdout.splitlines()


def test_api_environment_membership_rejects_an_invalid_release_profile(
    contract: tuple[Path, Path], tmp_path: Path
) -> None:
    script, profile_path = contract
    profile_path.write_text("{")

    result = subprocess.run(
        ["bash", "-c", 'source "$1"', "bash", str(script)],
        cwd=tmp_path.parent,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "cannot load release profile" in result.stderr
