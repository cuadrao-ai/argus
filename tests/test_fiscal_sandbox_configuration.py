"""Staging declares the fiscal sandbox; production keeps it off and unconfigured."""

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "CUADRAO_FISCAL_SANDBOX_"


def test_staging_fiscal_declaration_matches_manifests_and_production_stays_off():
    manifest = json.loads((ROOT / "scripts/ops/staging_env_manifest.json").read_text())
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
    assert len(entries) == 11
    assert set(entries) == set(staging)
    for name, entry in entries.items():
        if "value" in entry:
            assert staging[name]["value"] == entry["value"]
        else:
            assert entry["keep_current"] and entry["optional"]
            assert staging[name]["sync"] is False
    gates = {PREFIX + gate for gate in ("ENABLED", "CONTACT_ENABLED")}
    for name, entry in entries.items():
        if name in gates:
            assert entry["value"] == "false"
            assert entry["production"] == {"value": "false"}
        else:
            assert entry["production"] == {"not_set": True}
    production = {
        entry["key"]: entry.get("value")
        for entry in services["cuadrao-api"]["envVars"]
        if entry["key"].startswith(PREFIX)
    }
    assert production == dict.fromkeys(sorted(gates), "false")
