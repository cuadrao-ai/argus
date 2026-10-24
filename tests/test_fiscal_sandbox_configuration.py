"""Staging metadata declares fiscal settings without changing production."""

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "CUADRAO_FISCAL_SANDBOX_"


def test_staging_fiscal_declaration_matches_manifests_and_excludes_production():
    profile = json.loads(
        (ROOT / ".github/private-alpha-release-profile.json").read_text()
    )
    declaration = profile["staging_only"]["api"]
    assert declaration["manifest"] == "scripts/ops/staging_env_manifest.json"
    manifest = json.loads((ROOT / declaration["manifest"]).read_text())
    entries = {
        entry["name"]: entry
        for entry in manifest["services"]["api"]["entries"]
        if entry["name"].startswith(PREFIX)
    }
    services = {
        service["name"]: service
        for service in yaml.safe_load((ROOT / "render.yaml").read_text())["services"]
    }
    staging = {
        entry["key"]: entry
        for entry in services["cuadrao-api-staging"]["envVars"]
        if entry["key"].startswith(PREFIX)
    }
    assert len(declaration["settings"]) == len(set(declaration["settings"])) == 11
    assert set(declaration["settings"]) == set(entries) == set(staging)
    for name, entry in entries.items():
        if "value" in entry:
            assert staging[name]["value"] == entry["value"]
        else:
            assert entry["keep_current"] and entry["optional"]
            assert staging[name]["sync"] is False
    for gate in ("ENABLED", "CONTACT_ENABLED"):
        assert entries[PREFIX + gate]["value"] == "false"
    production = profile["services"]["api"]
    assert not any(name.startswith(PREFIX) for name in production["env"])
    assert not any(
        name.startswith(PREFIX)
        for field in ("required_present", "optional")
        for name in production[field]
    )
    assert not any(
        entry["key"].startswith(PREFIX) for entry in services["cuadrao-api"]["envVars"]
    )
