"""The support address has one owner: argus_display_contract/support_contact.json."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from argus.domain.resend_email import SUPPORT_EMAIL_ADDRESS
from faker import Faker

ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "web"
SUPPORT_EMAIL_ENV = "NEXT_PUBLIC_CUADRAO_SUPPORT_EMAIL"
WEB_OWNER = "web/lib/support-email.ts"
CODE_SUFFIXES = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs")
fake = Faker()


def _web_support_email(configured: str | None) -> str:
    env = {key: value for key, value in os.environ.items() if key != SUPPORT_EMAIL_ENV}
    if configured is not None:
        env[SUPPORT_EMAIL_ENV] = configured
    evaluated = subprocess.run(
        [
            "bun",
            "--no-env-file",
            "--eval",
            f'import {{ supportEmail }} from "{(ROOT / WEB_OWNER).as_posix()}";'
            " console.log(JSON.stringify(supportEmail));",
        ],
        cwd=WEB_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert evaluated.returncode == 0, evaluated.stderr
    return json.loads(evaluated.stdout)


def _app_code_containing(text: str, *roots: str) -> list[str]:
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "--", *roots],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    return sorted(
        name
        for name in listed
        if name.endswith(CODE_SUFFIXES)
        and not name.startswith(("web/__tests__/", "web/e2e/"))
        and (ROOT / name).is_file()
        and text in (ROOT / name).read_text(encoding="utf-8")
    )


@pytest.mark.parametrize("configured", [None, "", "   "])
def test_web_falls_back_to_the_api_support_address(configured: str | None) -> None:
    assert _web_support_email(configured) == SUPPORT_EMAIL_ADDRESS


def test_web_uses_the_configured_support_address() -> None:
    configured = fake.email()
    assert _web_support_email(configured) == configured


def test_release_profile_pins_the_api_support_address() -> None:
    # render.yaml is held to this profile by test_private_alpha_release_profile.py.
    profile_path = ROOT / ".github" / "private-alpha-release-profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    assert profile["services"]["web"]["env"][SUPPORT_EMAIL_ENV] == SUPPORT_EMAIL_ADDRESS


def test_only_the_web_owner_reads_the_support_address_setting() -> None:
    # Next inlines only the literal process.env name, so every working reader spells it.
    assert _app_code_containing(SUPPORT_EMAIL_ENV, "web") == [WEB_OWNER]


def test_no_app_code_spells_the_support_address() -> None:
    # Both runtimes derive the address from the contract file instead of repeating it.
    assert _app_code_containing(SUPPORT_EMAIL_ADDRESS, "src", "web") == []
