import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_auth_email_secrets_remain_held_until_staging_activation() -> None:
    manifest = json.loads((ROOT / "scripts/ops/staging_env_manifest.json").read_text())
    web = manifest["services"]["web"]
    secrets = {"CUADRAO_AUTH_EMAIL_HOOK_SECRET", "CUADRAO_AUTH_EMAIL_RESEND_API_KEY"}
    assert secrets <= {entry["name"] for entry in web["hold"]}
    assert secrets.isdisjoint(entry["name"] for entry in web["entries"])


def test_staging_auth_email_hook_stays_disabled_by_default() -> None:
    manifest = json.loads((ROOT / "scripts/ops/staging_env_manifest.json").read_text())
    entries = manifest["services"]["web"]["entries"]
    assert (
        next(
            entry["value"]
            for entry in entries
            if entry["name"] == "CUADRAO_AUTH_EMAIL_HOOK_ENABLED"
        )
        == "false"
    )
