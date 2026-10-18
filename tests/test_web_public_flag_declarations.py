from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

# Surfaces that already leave a web flag to its code default. A new
# process.env.NEXT_PUBLIC_* read in web/lib/private-alpha-flags.ts fails
# until the flag is declared in each hosted file, or this map records the
# surface that still leaves it unset.
UNSET_WEB_FLAG_SURFACES = {
    "NEXT_PUBLIC_GUEST_ACCESS_ENABLED": {
        "render.yaml",
        "private-alpha-release-profile.json",
        "staging_env_manifest.json",
    },
    "NEXT_PUBLIC_OMNISEARCH_ENABLED": {"render.yaml", "staging_env_manifest.json"},
    "NEXT_PUBLIC_RESEARCH_RAIL_ENABLED": {"render.yaml", "staging_env_manifest.json"},
    "NEXT_PUBLIC_EVIDENCE_RECEIPT_SHARING_ENABLED": {"render.yaml", "staging_env_manifest.json"},
    "NEXT_PUBLIC_BUSINESS_PILOT_ENABLED": {
        ".env.example",
        "private-alpha-release-profile.json",
    },
}
HOSTED_FLAG_SURFACES = (
    ".env.example",
    "render.yaml",
    "private-alpha-release-profile.json",
    "staging_env_manifest.json",
)
BUSINESS_DEFAULT_OFF_FLAGS = (
    "NEXT_PUBLIC_BUSINESS_WHATSAPP_PREFERENCES_ENABLED",
    "NEXT_PUBLIC_BUSINESS_SEARCH_ENABLED",
)


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _hosted_flag_declarations() -> dict[str, set[str]]:
    env_assignments = set(re.findall(r"^(NEXT_PUBLIC_[A-Z0-9_]+)=", _text(".env.example"), re.M))
    profile = json.loads(_text(".github/private-alpha-release-profile.json"))
    manifest = json.loads(_text("scripts/ops/staging_env_manifest.json"))
    render_config = yaml.safe_load(_text("render.yaml"))
    render_keys = {
        item["key"]
        for service in render_config["services"]
        for item in service.get("envVars", [])
    }
    return {
        ".env.example": env_assignments,
        "render.yaml": render_keys,
        "private-alpha-release-profile.json": set(profile["services"]["web"]["env"]),
        "staging_env_manifest.json": {
            entry["name"] for entry in manifest["services"]["web"]["entries"]
        },
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
    profile_env = json.loads(_text(".github/private-alpha-release-profile.json"))["services"]["web"]["env"]
    manifest_entries = {
        entry["name"]: entry
        for entry in json.loads(_text("scripts/ops/staging_env_manifest.json"))["services"]["web"]["entries"]
    }
    render_web = {
        service["name"]: {item["key"]: item for item in service["envVars"]}
        for service in yaml.safe_load(_text("render.yaml"))["services"]
        if service["name"] in {"argus-app", "cuadrao-web-staging"}
    }
    for name in BUSINESS_DEFAULT_OFF_FLAGS:
        assert re.search(rf"^{name}=false$", env_example, re.M)
        assert profile_env[name] == "false"
        assert manifest_entries[name]["value"] == "false"
        for service_env in render_web.values():
            assert service_env[name]["value"] == "false"
