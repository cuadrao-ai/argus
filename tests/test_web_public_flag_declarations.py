from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from tests.test_staging_default_off_flags import APPROVED_STAGING_OVERRIDES

ROOT = Path(__file__).resolve().parents[1]

# Surfaces that already leave a web flag to its code default. A new
# process.env.NEXT_PUBLIC_* read in web/lib/private-alpha-flags.ts fails
# until the flag is declared in each hosted file, or this map records the
# surface that still leaves it unset.
UNSET_WEB_FLAG_SURFACES = {
    "NEXT_PUBLIC_GUEST_ACCESS_ENABLED": {"render.yaml", "manifest production", "manifest staging"},
    "NEXT_PUBLIC_OMNISEARCH_ENABLED": {"render.yaml", "manifest staging"},
    "NEXT_PUBLIC_RESEARCH_RAIL_ENABLED": {"render.yaml", "manifest staging"},
    "NEXT_PUBLIC_EVIDENCE_RECEIPT_SHARING_ENABLED": {"render.yaml", "manifest staging"},
    "NEXT_PUBLIC_BUSINESS_PILOT_ENABLED": {".env.example"},
    # Fallback alias read after NEXT_PUBLIC_CUADRAO_BUSINESS_BANK_MATCHING_ENABLED;
    # the hosted files declare only the Cuadrao name.
    "NEXT_PUBLIC_BUSINESS_BANK_MATCHING_ENABLED": {
        "render.yaml",
        "manifest production",
        "manifest staging",
    },
}
HOSTED_FLAG_SURFACES = (".env.example", "render.yaml", "manifest production", "manifest staging")
BUSINESS_DEFAULT_OFF_FLAGS = (
    "NEXT_PUBLIC_CUADRAO_BUSINESS_BANK_MATCHING_ENABLED",
    "NEXT_PUBLIC_CUADRAO_BUSINESS_LIFECYCLE_CONTROLS_ENABLED",
)
# The server's `invoicing_available` on GET /business/workspace is the one
# switch for Facturación; the web switch and its readers are gone.
RETIRED_WEB_SWITCH = ("NEXT_PUBLIC_CUADRAO_BUSINESS_INVOICING_ENABLED", "businessInvoicingEnabled")
RETIRED_WEB_SWITCH_SCOPE = ("web", "scripts", ".github", ".env.example", "render.yaml")


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _hosted_flag_declarations() -> dict[str, set[str]]:
    env_assignments = set(re.findall(r"^(NEXT_PUBLIC_[A-Z0-9_]+)=", _text(".env.example"), re.M))
    manifest = json.loads(_text("scripts/ops/staging_env_manifest.json"))
    web = manifest["services"]["web"]["entries"]
    render_config = yaml.safe_load(_text("render.yaml"))
    render_keys = {
        item["key"]
        for service in render_config["services"]
        for item in service.get("envVars", [])
    }
    return {
        ".env.example": env_assignments,
        "render.yaml": render_keys,
        "manifest production": {e["name"] for e in web if "not_set" not in e["production"]},
        "manifest staging": {e["name"] for e in web if not e.get("production_only")},
    }


def test_private_alpha_web_flags_are_declared_for_hosted_settings() -> None:
    names = re.findall(
        r"process\.env\.(NEXT_PUBLIC_[A-Z0-9_]+)",
        _text("web/lib/private-alpha-flags.ts"),
    )
    assert names
    assert len(names) == len(set(names))
    declared = _hosted_flag_declarations()
    problems: list[str] = []
    for name in names:
        unset = UNSET_WEB_FLAG_SURFACES.get(name, set())
        assert unset <= set(HOSTED_FLAG_SURFACES)
        for surface in HOSTED_FLAG_SURFACES:
            present = name in declared[surface]
            if surface in unset and present:
                problems.append(f"declared but listed unset {surface}:{name}")
            elif surface not in unset and not present:
                problems.append(f"missing {surface}:{name}")
    assert problems == []

    env_example = _text(".env.example")
    manifest_entries = {
        entry["name"]: entry
        for entry in json.loads(_text("scripts/ops/staging_env_manifest.json"))["services"]["web"]["entries"]
    }
    render_web = {
        service["name"]: {item["key"]: item for item in service["envVars"]}
        for service in yaml.safe_load(_text("render.yaml"))["services"]
        if service["name"] == "cuadrao-web-staging"
    }
    for name in BUSINESS_DEFAULT_OFF_FLAGS:
        assert re.search(rf"^{name}=false$", env_example, re.M)
        assert manifest_entries[name]["production"] == {"value": "false"}
        staging_value = "true" if APPROVED_STAGING_OVERRIDES.get(name, "").strip() else "false"
        assert manifest_entries[name]["value"] == staging_value
        for service_env in render_web.values():
            assert service_env[name]["value"] == staging_value


def test_web_invoicing_switch_is_gone() -> None:
    skipped = {"node_modules", ".next", "__pycache__"}
    found: list[str] = []
    for scope in RETIRED_WEB_SWITCH_SCOPE:
        root = ROOT / scope
        paths = [root] if root.is_file() else [path for path in root.rglob("*") if path.is_file()]
        for path in paths:
            if skipped & set(path.relative_to(ROOT).parts):
                continue
            if path == ROOT / "tests" / Path(__file__).name:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            found.extend(f"{path.relative_to(ROOT)}:{name}" for name in RETIRED_WEB_SWITCH if name in text)
    assert found == []


def test_whatsapp_preferences_have_no_independent_web_switch() -> None:
    name = "NEXT_PUBLIC_BUSINESS_WHATSAPP_PREFERENCES_ENABLED"
    assert name not in APPROVED_STAGING_OVERRIDES
    for surface, declared in _hosted_flag_declarations().items():
        assert name not in declared, surface
    for folder in ("web/lib", "web/components"):
        for path in (ROOT / folder).rglob("*"):
            if path.suffix in {".ts", ".tsx"}:
                text = path.read_text(encoding="utf-8")
                assert name not in text, path.relative_to(ROOT)
                assert "businessWhatsAppPreferencesEnabled" not in text, path.relative_to(ROOT)
