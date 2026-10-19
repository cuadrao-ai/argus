#!/usr/bin/env python3
"""Validate and expose the non-secret private-alpha release profile."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / ".github" / "private-alpha-release-profile.json"
LOCALES_DIR = ROOT / "web" / "public" / "locales"
SURFACES = ("api", "web", "workflow", "marketing")
AUTO_DEPLOY_TRIGGERS = ("off", "checksPass")
# The canary's fixed checks, in run order. They never follow features.
CANARY_CHECKS = (
    "services_same_commit",
    "signed_in_chat_answer",
    "backtest_completes",
    "research_answer_with_sources",
)
CANARY_PROMPTS = ("chat_prompt", "backtest_prompt", "research_prompt")
FORBIDDEN_KEY_FRAGMENTS = (
    "candidate_sha",
    "deploy_id",
    "deployment_id",
    "service_id",
    "account_id",
)
FORBIDDEN_VALUE_PATTERNS = (
    re.compile(r"\beyJ[a-zA-Z0-9_-]{20,}"),
    re.compile(r"\bsk-[a-zA-Z0-9_-]{12,}"),
    re.compile(r"\bBearer\s+", re.IGNORECASE),
)


class ProfileValidationError(ValueError):
    """Raised when the checked-in release contract is not safe or complete."""


def _load_profile() -> dict[str, Any]:
    try:
        payload = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProfileValidationError(f"cannot load release profile: {exc}") from exc
    if not isinstance(payload, dict):
        raise ProfileValidationError("release profile root must be an object")
    return payload


def _require_mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProfileValidationError(f"{field} must be an object")
    return value


def _require_strings(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ProfileValidationError(f"{field} must be a non-empty list of strings")
    return list(value)


def validate_profile(profile: dict[str, Any]) -> None:
    if profile.get("schema_version") != 1:
        raise ProfileValidationError("schema_version must be 1")
    if profile.get("release_mode") != "real-workflow":
        raise ProfileValidationError("release_mode must be real-workflow")

    serialized = json.dumps(profile, sort_keys=True)
    lower_keys = {str(key).lower() for key in _walk_keys(profile)}
    if any(fragment in key for fragment in FORBIDDEN_KEY_FRAGMENTS for key in lower_keys):
        raise ProfileValidationError("profile must not contain candidate, deployment, service, or account ids")
    if any(pattern.search(serialized) for pattern in FORBIDDEN_VALUE_PATTERNS):
        raise ProfileValidationError("profile must not contain credential-like values")

    services = _require_mapping(profile.get("services"), "services")
    if set(services) != set(SURFACES):
        raise ProfileValidationError(
            "services must define api, web, workflow, and marketing"
        )
    expected_names = {
        "api": "argus-api",
        "web": "argus-app",
        "workflow": "argus-backtests",
        "marketing": "cuadrao-web",
    }
    triggers: set[object] = set()
    for surface, expected_name in expected_names.items():
        service = _require_mapping(services.get(surface), f"services.{surface}")
        if service.get("name") != expected_name:
            raise ProfileValidationError(f"services.{surface}.name must be {expected_name}")
        if service.get("auto_deploy_trigger") not in AUTO_DEPLOY_TRIGGERS:
            raise ProfileValidationError(
                f"services.{surface}.auto_deploy_trigger must be one of "
                f"{', '.join(AUTO_DEPLOY_TRIGGERS)}"
            )
        triggers.add(service.get("auto_deploy_trigger"))
        env = _require_mapping(service.get("env"), f"services.{surface}.env")
        if not env or not all(isinstance(key, str) and isinstance(value, str) for key, value in env.items()):
            raise ProfileValidationError(f"services.{surface}.env must contain string pairs")
        required_present = _require_strings(
            service.get("required_present"),
            f"services.{surface}.required_present",
        )
        optional = service.get("optional")
        if not isinstance(optional, list) or not all(
            isinstance(item, str) and item for item in optional
        ):
            raise ProfileValidationError(f"services.{surface}.optional must be a list of strings")
        if set(env).intersection(required_present) or set(env).intersection(optional) or set(required_present).intersection(optional):
            raise ProfileValidationError(f"services.{surface} repeats environment keys")
    if len(triggers) != 1:
        raise ProfileValidationError(
            "api, web, workflow, and marketing must share one auto_deploy_trigger"
        )

    workflow = _require_mapping(profile.get("workflow"), "workflow")
    if workflow.get("proof_task") != "argus-backtests/workflow_proof":
        raise ProfileValidationError("workflow.proof_task is invalid")
    if workflow.get("real_task") != "argus-backtests/run_backtest_job":
        raise ProfileValidationError("workflow.real_task is invalid")
    if workflow.get("health_status") != "ready":
        raise ProfileValidationError("workflow.health_status must be ready")
    if workflow.get("runtime_provider_mode") != "live_provider":
        raise ProfileValidationError("workflow.runtime_provider_mode must be live_provider")

    capabilities = _require_mapping(profile.get("capabilities"), "capabilities")
    if capabilities.get("spanish") is not True or capabilities.get("omnisearch") is not True:
        raise ProfileValidationError("Spanish and Omnisearch must be enabled")
    if capabilities.get("real_workflow_execution") is not True:
        raise ProfileValidationError("real workflow execution must be enabled")

    locales = _require_mapping(profile.get("locales"), "locales")
    if locales.get("supported") != ["en", "es-419"]:
        raise ProfileValidationError("locales.supported must be [en, es-419]")
    static_keys = _require_strings(locales.get("required_static_keys"), "locales.required_static_keys")
    if "chat.confirmation.actions.run_backtest" not in static_keys:
        raise ProfileValidationError(
            "chat.confirmation.actions.run_backtest is required for the release canary"
        )

    canary = _require_mapping(profile.get("canary"), "canary")
    if canary.get("language") not in locales["supported"]:
        raise ProfileValidationError("canary.language must be a supported locale")
    for field in CANARY_PROMPTS:
        if not isinstance(canary.get(field), str) or not canary[field].strip():
            raise ProfileValidationError(f"canary.{field} must be a non-empty string")
    required_steps = _require_strings(
        canary.get("required_steps"), "canary.required_steps"
    )
    if tuple(required_steps) != CANARY_CHECKS:
        raise ProfileValidationError(
            f"canary.required_steps must be exactly {', '.join(CANARY_CHECKS)}"
        )


def _walk_keys(value: object) -> list[str]:
    if isinstance(value, dict):
        return [str(key) for key, child in value.items()] + [key for child in value.values() for key in _walk_keys(child)]
    if isinstance(value, list):
        return [key for child in value for key in _walk_keys(child)]
    return []


def profile_hash() -> str:
    return hashlib.sha256(PROFILE_PATH.read_bytes()).hexdigest()


def env_pairs(profile: dict[str, Any], surface: str) -> list[str]:
    return [
        f"{key}={value}"
        for key, value in sorted(profile["services"][surface]["env"].items())
    ]


def required_present(profile: dict[str, Any], surface: str) -> list[str]:
    return sorted(profile["services"][surface]["required_present"])


def allowed_keys(profile: dict[str, Any], surface: str) -> list[str]:
    service = profile["services"][surface]
    return sorted(
        set(service["env"]).union(service["required_present"], service["optional"])
    )


def env_value(profile: dict[str, Any], surface: str, key: str) -> str:
    try:
        return profile["services"][surface]["env"][key]
    except KeyError as exc:
        raise ProfileValidationError(
            f"services.{surface}.env does not define {key}"
        ) from exc


def auto_deploy_trigger(profile: dict[str, Any], surface: str) -> str:
    value = profile["services"][surface].get("auto_deploy_trigger")
    if not isinstance(value, str) or not value:
        raise ProfileValidationError(
            f"services.{surface}.auto_deploy_trigger must be a string"
        )
    return value


def _nested_value(payload: dict[str, Any], path: str) -> str:
    current: object = payload
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            raise ProfileValidationError(f"locale catalog does not contain {path}")
        current = current[part]
    if not isinstance(current, str) or not current:
        raise ProfileValidationError(f"locale catalog value for {path} must be a string")
    return current


def static_key_values(profile: dict[str, Any], language: str) -> dict[str, str]:
    if language not in profile["locales"]["supported"]:
        raise ProfileValidationError(f"unsupported release locale: {language}")
    locale_path = LOCALES_DIR / language / "common.json"
    try:
        catalog = json.loads(locale_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProfileValidationError(f"cannot load locale catalog for {language}: {exc}") from exc
    if not isinstance(catalog, dict):
        raise ProfileValidationError(f"locale catalog for {language} must be an object")
    return {
        key: _nested_value(catalog, key)
        for key in profile["locales"]["required_static_keys"]
    }


def canary_value(profile: dict[str, Any], field: str) -> str:
    value = profile["canary"].get(field)
    if not isinstance(value, (str, int, float, bool)):
        raise ProfileValidationError(f"canary.{field} must be a scalar value")
    return str(value).lower() if isinstance(value, bool) else str(value)


def canary_checks(profile: dict[str, Any]) -> list[str]:
    return list(profile["canary"]["required_steps"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")
    subparsers.add_parser("hash")
    env_parser = subparsers.add_parser("env-pairs")
    env_parser.add_argument("surface", choices=SURFACES)
    env_value_parser = subparsers.add_parser("env-value")
    env_value_parser.add_argument("surface", choices=SURFACES)
    env_value_parser.add_argument("key")
    autodeploy_parser = subparsers.add_parser("auto-deploy-trigger")
    autodeploy_parser.add_argument("surface", choices=SURFACES)
    present_parser = subparsers.add_parser("required-present")
    present_parser.add_argument("surface", choices=SURFACES)
    allowed_parser = subparsers.add_parser("allowed-keys")
    allowed_parser.add_argument("surface", choices=SURFACES)
    static_parser = subparsers.add_parser("static-key-values")
    static_parser.add_argument("language")
    canary_parser = subparsers.add_parser("canary-value")
    canary_parser.add_argument("field", choices=("language", *CANARY_PROMPTS))
    subparsers.add_parser("canary-checks")
    args = parser.parse_args()

    try:
        profile = _load_profile()
        validate_profile(profile)
        if args.command == "validate":
            print("profile_status=ready")
        elif args.command == "hash":
            print(profile_hash())
        elif args.command == "env-pairs":
            print("\n".join(env_pairs(profile, args.surface)))
        elif args.command == "env-value":
            print(env_value(profile, args.surface, args.key))
        elif args.command == "auto-deploy-trigger":
            print(auto_deploy_trigger(profile, args.surface))
        elif args.command == "required-present":
            print("\n".join(required_present(profile, args.surface)))
        elif args.command == "allowed-keys":
            print("\n".join(allowed_keys(profile, args.surface)))
        elif args.command == "static-key-values":
            print(json.dumps(static_key_values(profile, args.language), sort_keys=True))
        elif args.command == "canary-value":
            print(canary_value(profile, args.field))
        elif args.command == "canary-checks":
            print("\n".join(canary_checks(profile)))
    except ProfileValidationError as exc:
        print(f"release profile error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
