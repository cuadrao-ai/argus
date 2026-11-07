from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "scripts" / "ops" / "staging_env_manifest.json"
RENDER_PATH = ROOT / "render.yaml"

_LAUNCH_DAY_ONE = (
    "Staging keeps in-development features on. Production day one is staging's "
    "features with email and WhatsApp off (launch plan 2026-11-04)."
)

APPROVED_STAGING_OVERRIDES: dict[str, str] = {
    "CUADRAO_BETA_INVITES_ENABLED": (
        "Staging tests the invite flow end to end (7-day invite expiry from "
        "#1228; invite email under #1226/#1267). Prod stays false."
    ),
    "CUADRAO_HOUSEHOLDS_ENABLED": (
        "The Consumer staging proof uses households ahead of the iOS beta "
        "build. Prod stays false."
    ),
    "CUADRAO_BUSINESS_BANK_MATCHING_ENABLED": (
        "Lucas approved bank matching on staging 2026-10-28 (demo loop approval "
        "2). Prod stays false."
    ),
    "CUADRAO_BUSINESS_EMAIL_CAPTURE_ENABLED": _LAUNCH_DAY_ONE,
    "CUADRAO_BUSINESS_EMAIL_INTAKE_ENABLED": _LAUNCH_DAY_ONE,
    "CUADRAO_WHATSAPP_INTAKE_ENABLED": _LAUNCH_DAY_ONE,
    "CUADRAO_WHATSAPP_OUTBOUND_ENABLED": _LAUNCH_DAY_ONE,
    "CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED": (
        "Staging is internal and stays open. Production is invite only "
        "(launch plan 2026-11-04): only allowlist rows may sign in."
    ),
}


def production_values(manifest: dict) -> dict:
    """The manifest's fixed production values, shaped {services: {label: {env}}}."""
    return {
        "services": {
            label: {
                "env": {
                    entry["name"]: entry["production"]["value"]
                    for entry in service["entries"]
                    if not entry.get("local_only") and "value" in entry["production"]
                }
            }
            for label, service in manifest["services"].items()
        }
    }


def _is_feature_flag(name: str) -> bool:
    return name.endswith("_ENABLED") or name.startswith("ENABLE_") or "_ENABLE_" in name


def turned_on_default_off_flags(
    production: dict,
    manifest: dict,
    overrides: Mapping[str, str],
) -> list[str]:
    default_off = [
        name
        for service in production["services"].values()
        for name, value in service["env"].items()
        if value == "false" and _is_feature_flag(name)
    ]
    declared: dict[str, list[str]] = {}
    for service in manifest["services"].values():
        for entry in service.get("entries", []):
            if "value" not in entry:
                continue
            declared.setdefault(entry["name"], []).append(entry["value"])
    exempt = {name for name, reason in overrides.items() if reason.strip()}
    return sorted(
        {
            name
            for name in default_off
            if name not in exempt
            and any(value != "false" for value in declared.get(name, []))
        }
    )


def test_temp_manifest_true_flag_fails_and_a_reasoned_override_passes() -> None:
    profile = {
        "services": {
            "api": {
                "env": {
                    "SAMPLE_FLAG_ENABLED": "false",
                    "CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED": "true",
                    "ARGUS_DEV_MEMORY_FALLBACK": "false",
                }
            }
        }
    }
    turned_on = {
        "services": {
            "api": {
                "entries": [
                    {"name": "SAMPLE_FLAG_ENABLED", "value": "true"},
                    {
                        "name": "CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED",
                        "value": "true",
                    },
                ]
            }
        }
    }
    assert turned_on_default_off_flags(profile, turned_on, {}) == [
        "SAMPLE_FLAG_ENABLED"
    ]
    assert turned_on_default_off_flags(
        profile,
        turned_on,
        {"SAMPLE_FLAG_ENABLED": "staging sample is approved"},
    ) == []
    assert turned_on_default_off_flags(
        profile,
        turned_on,
        {"SAMPLE_FLAG_ENABLED": "  "},
    ) == ["SAMPLE_FLAG_ENABLED"]
    false_value = {
        "services": {
            "api": {
                "entries": [
                    {"name": "SAMPLE_FLAG_ENABLED", "value": "false"},
                ]
            }
        }
    }
    assert turned_on_default_off_flags(profile, false_value, {}) == []
    absent = {"services": {"api": {"entries": []}}}
    assert turned_on_default_off_flags(profile, absent, {}) == []


def prod_values_other_than_false(
    production: dict,
    render_config: dict,
    overrides: Mapping[str, str],
) -> list[str]:
    bad: list[str] = []
    for name, reason in overrides.items():
        if not reason.strip():
            continue
        profile_values = [
            service["env"][name]
            for service in production["services"].values()
            if name in service.get("env", {})
        ]
        render_values = [
            item.get("value")
            for service in render_config.get("services", [])
            if service.get("name") not in ("cuadrao-api-staging", "cuadrao-web-staging")
            for item in service.get("envVars", [])
            if item.get("key") == name
        ]
        if any(value != "false" for value in profile_values):
            bad.append(name)
        if any(value != "false" for value in render_values):
            bad.append(name)
    return sorted(set(bad))


def test_override_true_in_prod_fails() -> None:
    overrides = {"SAMPLE_FLAG_ENABLED": "staging sample is approved"}
    profile_true = {
        "services": {"api": {"env": {"SAMPLE_FLAG_ENABLED": "true"}}}
    }
    render_false = {
        "services": [
            {"envVars": [{"key": "SAMPLE_FLAG_ENABLED", "value": "false"}]}
        ]
    }
    assert prod_values_other_than_false(profile_true, render_false, overrides) == [
        "SAMPLE_FLAG_ENABLED"
    ]
    profile_false = {
        "services": {"api": {"env": {"SAMPLE_FLAG_ENABLED": "false"}}}
    }
    render_true = {
        "services": [
            {"envVars": [{"key": "SAMPLE_FLAG_ENABLED", "value": "true"}]}
        ]
    }
    assert prod_values_other_than_false(profile_false, render_true, overrides) == [
        "SAMPLE_FLAG_ENABLED"
    ]
    assert (
        prod_values_other_than_false(profile_false, render_false, overrides) == []
    )


def test_approved_staging_overrides_record_a_reason() -> None:
    assert [
        name
        for name, reason in APPROVED_STAGING_OVERRIDES.items()
        if not reason.strip()
    ] == []


def test_staging_overrides_stay_false_in_prod() -> None:
    profile = production_values(json.loads(MANIFEST_PATH.read_text(encoding="utf-8")))
    render_config = yaml.safe_load(RENDER_PATH.read_text(encoding="utf-8"))
    assert (
        prod_values_other_than_false(
            profile, render_config, APPROVED_STAGING_OVERRIDES
        )
        == []
    )


def test_production_off_flags_are_not_turned_on_in_staging() -> None:
    profile = production_values(json.loads(MANIFEST_PATH.read_text(encoding="utf-8")))
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert (
        turned_on_default_off_flags(profile, manifest, APPROVED_STAGING_OVERRIDES)
        == []
    )


@pytest.mark.parametrize("surface", ["profile", "render", "unknown", "unnamed"])
def test_staging_exception_cannot_hide_other_true_values(surface: str) -> None:
    profile = production_values(json.loads(MANIFEST_PATH.read_text(encoding="utf-8")))
    render_config = yaml.safe_load(RENDER_PATH.read_text(encoding="utf-8"))
    name = "CUADRAO_BUSINESS_BANK_MATCHING_ENABLED"
    if surface == "profile":
        profile["services"]["web"]["env"][name] = "true"
    elif surface == "render":
        production = next(
            service
            for service in render_config["services"]
            if service["name"] == "cuadrao-web"
        )
        production.setdefault("envVars", []).append({"key": name, "value": "true"})
    else:
        service = {"envVars": [{"key": name, "value": "true"}]}
        if surface == "unknown":
            service["name"] = "cuadrao-web-preview-staging"
        render_config["services"].append(service)
    assert prod_values_other_than_false(
        profile, render_config, APPROVED_STAGING_OVERRIDES
    ) == [name]


def test_another_staging_flag_still_needs_its_own_approval() -> None:
    profile = production_values(json.loads(MANIFEST_PATH.read_text(encoding="utf-8")))
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    name = "NEXT_PUBLIC_CUADRAO_BUSINESS_BANK_MATCHING_ENABLED"
    entry = next(
        entry for entry in manifest["services"]["web"]["entries"] if entry["name"] == name
    )
    entry["value"] = "true"
    assert turned_on_default_off_flags(profile, manifest, APPROVED_STAGING_OVERRIDES) == [
        name
    ]


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("NEXT_PUBLIC_CUADRAO_BUSINESS_BANK_MATCHING_ENABLED", "false"),
    ],
)
def test_staging_web_flags_match_the_20261029_decision(
    name: str,
    expected: str,
) -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    render_config = yaml.safe_load(RENDER_PATH.read_text(encoding="utf-8"))
    stage = next(
        service
        for service in render_config["services"]
        if service["name"] == "cuadrao-web-staging"
    )
    assert next(entry for entry in stage["envVars"] if entry["key"] == name)[
        "value"
    ] == expected
    assert next(
        entry
        for entry in manifest["services"]["web"]["entries"]
        if entry["name"] == name
    )["value"] == expected
