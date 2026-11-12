"""The support address has one owner: argus_display_contract/support_contact.json."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from argus.domain.resend_email import SUPPORT_EMAIL_ADDRESS
from faker import Faker

from scripts.ci.check_support_email import (
    GENERATED,
    INQUIRY_INBOX_SETTING,
    SUPPORT_EMAIL_ENV,
    WEB_OWNER,
)

ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "web"
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


def _check_support_ownership(check: str) -> None:
    checked = subprocess.run(
        [sys.executable, str(ROOT / "scripts/ci/check_support_email.py"), "--check", check],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert checked.returncode == 0, checked.stderr


@pytest.mark.parametrize("configured", [None, "", "   "])
def test_web_falls_back_to_the_api_support_address(configured: str | None) -> None:
    assert _web_support_email(configured) == SUPPORT_EMAIL_ADDRESS


def test_web_uses_the_configured_support_address() -> None:
    configured = fake.email()
    assert _web_support_email(configured) == configured


def test_hosted_settings_leave_the_address_to_the_contract_file() -> None:
    # Unset, the web reads support_contact.json, so no hosted setting repeats it.
    manifest_path = ROOT / "scripts" / "ops" / "staging_env_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = next(
        e
        for e in manifest["services"]["web"]["entries"]
        if e["name"] == SUPPORT_EMAIL_ENV
    )
    assert entry["production"] == {"not_set": True}
    assert entry["production_only"] is True
    assert SUPPORT_EMAIL_ENV not in (ROOT / "render.yaml").read_text(encoding="utf-8")
    holding_the_address = {
        setting["name"]
        for service in manifest["services"].values()
        for setting in service["entries"]
        if SUPPORT_EMAIL_ADDRESS in json.dumps(setting)
    }
    assert holding_the_address <= {INQUIRY_INBOX_SETTING}


def test_only_the_web_owner_reads_the_support_address_setting() -> None:
    # Next inlines only the literal process.env name, so every working reader spells it.
    _check_support_ownership("setting")


def test_only_the_owner_and_its_generated_files_spell_the_support_address() -> None:
    _check_support_ownership("address")


@pytest.mark.parametrize("generator", sorted(GENERATED))
def test_generated_files_match_the_owner(generator: str) -> None:
    checked = subprocess.run(
        ["bun", "--no-env-file", generator, "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert checked.returncode == 0, checked.stderr
