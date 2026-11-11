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
OWNER = "web/argus_display_contract/support_contact.json"
WEB_OWNER = "web/lib/support-email.ts"
WEB_CODE = tuple(f"web/*{suffix}" for suffix in (".ts", ".tsx", ".js", ".jsx", ".mjs"))
# Tests and prose quote what was rendered or decided; nothing reads the address from them.
QUOTES = (
    "tests",
    "web/__tests__",
    "web/e2e",
    "marketing/__tests__",
    "marketing/e2e",
    "docs",
    ".agent/designs",
)
# sync-layout.mjs copies the address from the owner; the other generators render emails
# through that copy. Each --check fails on a stale file.
GENERATED = {
    "scripts/emails/sync-business-closed.ts": "src/argus/domain/business/business_closed_email.generated.json",
    "scripts/emails/sync-business-invite.ts": "src/argus/domain/business/business_invite_email.generated.json",
    "scripts/emails/sync-business-transfer.ts": "src/argus/domain/business/business_transfer_email.generated.json",
    "scripts/emails/sync-existing-account.ts": "src/argus/domain/existing_account_email.generated.json",
    "scripts/emails/sync-layout.mjs": "marketing/lib/email/support-email.generated.ts",
}
INQUIRY_INBOX_SETTING = "CUADRAO_INQUIRY_TO"
LEGAL_TEXT = "published legal text, which changes only with a new legal version"
# Facts with their own owner that hold the same mailbox today. None is the support
# address, so none reads the contract file.
OTHER_FACTS = {
    "marketing/components/legal-page.tsx": "links the contact address the legal text names",
    "marketing/components/site-copy.ts": "businessContactEmail, the website's public contact address",
    "marketing/content/app-legal-en.generated.json": LEGAL_TEXT,
    "marketing/content/app-legal-es.generated.json": LEGAL_TEXT,
    "marketing/content/app-legal-source/privacidad.md": LEGAL_TEXT,
    "marketing/content/app-legal-source/terminos.md": LEGAL_TEXT,
    "marketing/content/legal-en.json": LEGAL_TEXT,
    "marketing/content/legal-es.json": LEGAL_TEXT,
    "marketing/content/legal-waitlist-source/eliminar-datos.md": LEGAL_TEXT,
    "marketing/content/legal-waitlist-source/privacidad.md": LEGAL_TEXT,
    "marketing/content/legal-waitlist-source/terminos.md": LEGAL_TEXT,
    "scripts/ops/staging_env_manifest.json": f"{INQUIRY_INBOX_SETTING}, the inbox the website's contact form delivers to",
}
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


def _files_spelling(text: str, *within: str) -> set[str]:
    found = subprocess.run(
        [
            "git",
            "grep",
            "--untracked",
            "--files-with-matches",
            "--ignore-case",
            "--fixed-strings",
            "-I",
            "-e",
            text,
            "--",
            *(within or (".",)),
            *(f":!{quoted}" for quoted in QUOTES),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert found.returncode in (0, 1), found.stderr
    return set(found.stdout.splitlines())


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
    assert _files_spelling(SUPPORT_EMAIL_ENV, *WEB_CODE) == {WEB_OWNER}


def test_only_the_owner_and_its_generated_files_spell_the_support_address() -> None:
    assert _files_spelling(SUPPORT_EMAIL_ADDRESS) == {
        OWNER,
        *GENERATED.values(),
        *OTHER_FACTS,
    }


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
