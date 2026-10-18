from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / ".github" / "private-alpha-release-profile.json"
MANIFEST_PATH = ROOT / "scripts" / "ops" / "staging_env_manifest.json"

APPROVED_STAGING_OVERRIDES: dict[str, str] = {
    "ARGUS_BETA_INVITES_ENABLED": (
        "Staging tests the invite flow end to end (7-day invite expiry from "
        "#1228; invite email under #1226/#1267). Prod stays false."
    ),
    "ARGUS_HOUSEHOLDS_ENABLED": (
        "The Consumer staging proof uses households ahead of the iOS beta "
        "build. Prod stays false."
    ),
}


def _is_feature_flag(name: str) -> bool:
    return name.endswith("_ENABLED") or name.startswith("ENABLE_") or "_ENABLE_" in name


def turned_on_default_off_flags(
    profile: dict,
    manifest: dict,
    overrides: Mapping[str, str],
) -> list[str]:
    default_off = [
        name
        for service in profile["services"].values()
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
                    "ARGUS_PUBLIC_ACCOUNT_ACCESS_ENABLED": "true",
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
                        "name": "ARGUS_PUBLIC_ACCOUNT_ACCESS_ENABLED",
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
    profile: dict,
    render_config: dict,
    overrides: Mapping[str, str],
) -> list[str]:
    return []


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


def test_approved_staging_overrides_record_a_reason() -> None:
    assert [
        name
        for name, reason in APPROVED_STAGING_OVERRIDES.items()
        if not reason.strip()
    ] == []


def test_default_off_profile_flags_are_not_turned_on_in_staging() -> None:
    profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert (
        turned_on_default_off_flags(profile, manifest, APPROVED_STAGING_OVERRIDES)
        == []
    )
