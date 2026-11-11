"""Release-owned API model and flag identity for eval evidence.

This checks measurement/configuration mistakes, not deliberate evidence tampering.
The settings manifest's production rules own the selected keys. A commit whose
release profile still holds an API env predates them and reads that env.
Historical spelling equivalence is limited to the approved environment rename
identities below.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Mapping

RELEASE_PROFILE = ".github/private-alpha-release-profile.json"
SETTINGS_MANIFEST = "scripts/ops/staging_env_manifest.json"

_APPROVED_ENV_RENAMES = {
    key: key.replace("ARGUS_", "CUADRAO_", 1)
    for key in (
        "ARGUS_ACCOUNT_DELETION_ENABLED",
        "ARGUS_API_BASE_URL",
        "ARGUS_APPLE_BUNDLE_ID",
        "ARGUS_APPLE_REVOCATION_CAPTURE_ENABLED",
        "ARGUS_APPLE_SIGN_IN_KEY_ID",
        "ARGUS_APPLE_SIGN_IN_PRIVATE_KEY",
        "ARGUS_APPLE_TEAM_ID",
        "ARGUS_APPROVAL_EMAIL_SMTP_PASSWORD",
        "ARGUS_BETA_INVITES_ENABLED",
        "ARGUS_BETA_INVITE_GATE_ENABLED",
        "ARGUS_CAPABILITY_REASONING_EFFORT",
        "ARGUS_CHAT_FALLBACK_MODEL",
        "ARGUS_CHAT_MODEL",
        "ARGUS_CHECKPOINTER_MODE",
        "ARGUS_CLIENT_IP_ECHO_ENABLED",
        "ARGUS_CONTEXT_FALLBACK_MODEL",
        "ARGUS_CONTEXT_MODEL",
        "ARGUS_CORS_ALLOW_ORIGINS",
        "ARGUS_CROSS_CURRENCY_TRANSFERS_ENABLED",
        "ARGUS_EVIDENCE_RECEIPT_SHARING_ENABLED",
        "ARGUS_GUEST_ACCESS_ENABLED",
        "ARGUS_GUEST_ACCESS_OPENROUTER_API_KEY",
        "ARGUS_GUEST_SESSION_DAILY_TURN_CEILING",
        "ARGUS_HOUSEHOLDS_ENABLED",
        "ARGUS_INVITE_CODE_SECRET",
        "ARGUS_INVITE_CODE_SECRET_PREVIOUS",
        "ARGUS_INVITE_FOUNDER_USER_ID",
        "ARGUS_INVITE_UNIVERSAL_LINK_ENABLED",
        "ARGUS_MOCK_AUTH",
        "ARGUS_OPENROUTER_ASSET_MENTION_PREFLIGHT_TIMEOUT_SECONDS",
        "ARGUS_OPENROUTER_CAPABILITY_CONFLICT_TIMEOUT_SECONDS",
        "ARGUS_OPENROUTER_CHAT_COMPOSER_TIMEOUT_SECONDS",
        "ARGUS_OPENROUTER_CLARIFICATION_TIMEOUT_SECONDS",
        "ARGUS_OPENROUTER_DOCUMENT_EXTRACTION_TIMEOUT_SECONDS",
        "ARGUS_OPENROUTER_FIELD_FIDELITY_TIMEOUT_SECONDS",
        "ARGUS_OPENROUTER_INTERPRETATION_REPAIR_TIMEOUT_SECONDS",
        "ARGUS_OPENROUTER_INTERPRETATION_TIMEOUT_SECONDS",
        "ARGUS_OPENROUTER_KNOWLEDGE_ROUTE_TIMEOUT_SECONDS",
        "ARGUS_OPENROUTER_KNOWLEDGE_VOICING_TIMEOUT_SECONDS",
        "ARGUS_OPENROUTER_NAME_SUGGESTION_TIMEOUT_SECONDS",
        "ARGUS_OPENROUTER_RESULT_SUMMARY_TIMEOUT_SECONDS",
        "ARGUS_OPS_TOKEN",
        "ARGUS_PERSISTENCE_MODE",
        "ARGUS_POSTHOG_TIMEOUT_SECONDS",
        "ARGUS_PROD_OPENROUTER_API_KEY",
        "ARGUS_PUBLIC_ACCOUNT_ACCESS_ENABLED",
        "ARGUS_READOUT_FALLBACK_MODEL",
        "ARGUS_READOUT_MODEL",
        "ARGUS_REGISTERED_DAILY_TURN_CEILING",
        "ARGUS_RUNTIME_EVENT_KEEPALIVE_SECONDS",
        "ARGUS_RUNTIME_EVENT_TIMEOUT_SECONDS",
        "ARGUS_RUNTIME_STREAM_WORKER",
        "ARGUS_RUNTIME_STREAM_WORKERS",
        "ARGUS_STRUCTURED_FALLBACK_MODEL",
        "ARGUS_STRUCTURED_MODEL",
        "ARGUS_STRUCTURED_REASONING_EFFORT",
        "ARGUS_TESTFLIGHT_PUBLIC_URL",
        "ARGUS_TURN_CALL_ALLOWANCE",
        "ARGUS_TURN_DEADLINE_SECONDS",
        "ARGUS_UTILITY_FALLBACK_MODEL",
        "ARGUS_UTILITY_MODEL",
        "ARGUS_VISITOR_KEY_SECRET",
        "ARGUS_WAITLIST_URL",
    )
}

# These already shipped before configuration was recorded. Keep their evidence
# bytes unchanged; every new manifest needs measured configuration on every side.
MANIFESTS_BEFORE_CONFIGURATION = frozenset(
    {
        "2026-08-13-main-production-promotion.md",
        "2026-08-13-api-domain-promotion.md",
        "2026-08-13-guest-signup-hotfix-promotion.md",
        "2026-08-16-main-production-promotion.md",
        "2026-08-21-main-production-promotion.md",
        "2026-08-27-main-production-promotion.md",
        "2026-09-03-main-production-promotion.md",
        "2026-09-05-main-production-promotion.md",
        "2026-09-12-main-production-promotion.md",
    }
)


def _file_at_commit(sha: str, path: str, *, repository_root: Path) -> str | None:
    shown = subprocess.run(
        ["git", "--no-replace-objects", "show", f"{sha}:{path}"],
        cwd=repository_root,
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )
    return shown.stdout if shown.returncode == 0 else None


def _production_api_values(manifest_source: str | None) -> dict[str, str] | None:
    if manifest_source is None:
        return None
    entries = json.loads(manifest_source)["services"]["api"]["entries"]
    if not any("production" in entry for entry in entries):
        return None
    return {
        entry["name"]: entry["production"]["value"]
        for entry in entries
        if not entry.get("local_only") and "value" in entry["production"]
    }


def release_configuration_at_commit(sha: str, *, repository_root: Path) -> dict[str, str]:
    """Only API model IDs and explicit on/off flags from the named commit."""
    assert re.fullmatch(r"[0-9a-f]{40}", sha), "release_configuration: full SHA required"
    profile = _file_at_commit(sha, RELEASE_PROFILE, repository_root=repository_root)
    legacy = json.loads(profile or "{}").get("services", {}).get("api", {}).get("env")
    environment = legacy if legacy is not None else _production_api_values(
        _file_at_commit(sha, SETTINGS_MANIFEST, repository_root=repository_root)
    )
    assert environment is not None, f"release_configuration: no settings at {sha[:8]}"
    return {
        key: value
        for key, value in environment.items()
        if key.endswith("_MODEL") or value in ("true", "false")
    }


def measured_release_configuration(
    sha: str, *, repository_root: Path
) -> dict[str, str | None]:
    """Read only contract-selected keys, from the eval's process environment."""
    from argus.llm.memory_embedding import resolve_memory_embedding_model
    from argus.llm.openrouter import _env_model_value

    values: dict[str, str | None] = {}
    for key in release_configuration_at_commit(sha, repository_root=repository_root):
        if key == "ARGUS_MEMORY_EMBEDDING_MODEL":
            values[key] = resolve_memory_embedding_model()
        elif key.endswith("_MODEL"):
            # The same per-key resolution used by OpenRouter's ordered candidates.
            # Keep primary/fallback slots even when they resolve to the same ID.
            values[key] = _env_model_value(key)
        else:
            raw = os.getenv(key)
            value = raw.strip().lower() if raw is not None else None
            # Flag parsers differ in their accepted aliases. Require the contract's
            # explicit true/false spelling rather than inventing shared semantics.
            # Missing is unknown, never filled from the contract's desired value.
            values[key] = value
    return values


def _canonical_configuration(
    configuration: Mapping[str, object], *, evidence: str
) -> dict[str, object]:
    canonical: dict[str, object] = {}
    for key, value in configuration.items():
        identity = _APPROVED_ENV_RENAMES.get(key, key)
        assert identity not in canonical, (
            f"{evidence}: duplicate release_configuration key {identity}. "
            "Legacy and renamed keys cannot both be present."
        )
        canonical[identity] = value
    return canonical


def assert_release_configuration_matches(
    measured: object, *, shipped_sha: str, repository_root: Path, evidence: str
) -> None:
    assert isinstance(measured, Mapping), (
        f"{evidence}: missing release_configuration; new promotions need "
        "configuration-bearing evidence (measurement scorecard schema v3)."
    )
    expected = _canonical_configuration(
        release_configuration_at_commit(shipped_sha, repository_root=repository_root),
        evidence=f"{evidence}: contract",
    )
    measured = _canonical_configuration(measured, evidence=f"{evidence}: measured")
    for key in sorted(expected.keys() | measured.keys()):
        actual = measured.get(key)
        contract = expected.get(key)
        assert key in measured and key in expected and actual == contract, (
            f"{evidence}: release_configuration {key}: measured={actual!r}, "
            f"contract={contract!r} at {shipped_sha[:8]}. Measure again."
        )
