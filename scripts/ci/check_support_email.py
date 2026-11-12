"""Check support-address ownership using only the standard library and git."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
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


def files_spelling(text: str, *within: str) -> set[str]:
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
    if found.returncode not in (0, 1):
        raise RuntimeError(found.stderr.strip() or "git grep failed")
    return set(found.stdout.splitlines())


def check_ownership(check: str) -> None:
    if check == "setting":
        found = files_spelling(SUPPORT_EMAIL_ENV, *WEB_CODE)
        expected = {WEB_OWNER}
    else:
        address = json.loads((ROOT / OWNER).read_text(encoding="utf-8"))["email"]
        if not isinstance(address, str) or not address.strip():
            raise ValueError("Support-contact owner must declare a nonempty email")
        found = files_spelling(address)
        expected = {OWNER, *GENERATED.values(), *OTHER_FACTS}
    if found != expected:
        raise ValueError(
            f"Support {check} ownership mismatch: "
            f"unexpected={sorted(found - expected)}, missing={sorted(expected - found)}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", choices=("address", "setting"))
    args = parser.parse_args()
    try:
        for check in (args.check,) if args.check else ("address", "setting"):
            check_ownership(check)
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        sys.stderr.write(f"{error}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
