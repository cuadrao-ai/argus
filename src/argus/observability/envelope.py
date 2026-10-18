from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

import httpx
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

PrivacyMode = Literal["raw_alpha", "redacted_default", "metadata_only", "disabled"]
EventAction = Literal[
    "started",
    "completed",
    "failed",
    "suppressed",
    "redacted",
    "sampled",
    "reconciled",
]
EventType = Literal[
    "user_message",
    "ai_interpretation",
    "ai_response",
    "tool_call",
    "tool_result",
    "research",
    "stt",
    "storage",
    "system",
    "recovery",
    "decision_saved",
    "revisit_opened",
    "compare_started",
    "memory_candidate_proposed",
    "memory_candidate_suppressed",
    "cost_ledger_entry",
    "eval_case_run",
    "eval_suite_run",
    "broker_handoff_prep",
    "analytics",
]
FeatureArea = Literal[
    "chat_interpretation",
    "continuity",
    "evidence_capture",
    "decision_capture",
    "guest_acquisition",
    "recall",
    "result_explanation",
    "memory_candidate_proposal",
    "research_light",
    "research_deep",
    "freshness_check",
    "stt",
    "storage",
    "broker_handoff_prep",
    "product_analytics",
]

EVENT_ACTIONS: tuple[str, ...] = (
    "started",
    "completed",
    "failed",
    "suppressed",
    "redacted",
    "sampled",
    "reconciled",
)
EVENT_TYPES: tuple[str, ...] = (
    "user_message",
    "ai_interpretation",
    "ai_response",
    "tool_call",
    "tool_result",
    "research",
    "stt",
    "storage",
    "system",
    "recovery",
    "decision_saved",
    "revisit_opened",
    "compare_started",
    "memory_candidate_proposed",
    "memory_candidate_suppressed",
    "cost_ledger_entry",
    "eval_case_run",
    "eval_suite_run",
    "broker_handoff_prep",
    "analytics",
)
FEATURE_AREAS: tuple[str, ...] = (
    "chat_interpretation",
    "continuity",
    "evidence_capture",
    "decision_capture",
    "guest_acquisition",
    "recall",
    "result_explanation",
    "memory_candidate_proposal",
    "research_light",
    "research_deep",
    "freshness_check",
    "stt",
    "storage",
    "broker_handoff_prep",
    "product_analytics",
)

_BLOCKED_KEY_PARTS = (
    "account_balance",
    "api_key",
    "assistant_prose",
    "auth_material",
    "auth_token",
    "authorization",
    "broker_credentials",
    "capital",
    "cookie",
    "context_packets",
    "date_",
    "display_name",
    "email",
    "exact_date",
    "full_audio",
    "header",
    "holdings",
    "ip_address",
    "message_history",
    "model",
    "model_metadata",
    "password",
    "payment_identifier",
    "preview",
    "prompt",
    "provider",
    "provider_metadata",
    "raw_payload",
    "route_receipt",
    "secret",
    "_date",
    "title",
    "token",
    "transcript",
    "url",
)
_BLOCKED_EXACT_KEYS = {"date"}
_POSTHOG_US_HOST = "https://us.i.posthog.com"
_POSTHOG_EU_HOST = "https://eu.i.posthog.com"
_POSTHOG_CAPTURE_PATH = "/i/v0/e/"
_POSTHOG_DEFAULT_TIMEOUT_SECONDS = 0.75


def _clean_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    stripped = value.strip().strip("\"'")
    return stripped or None


def _default_environment() -> str:
    return (
        _clean_env("APP_ENV")
        or _clean_env("ARGUS_ENV")
        or _clean_env("ARGUS_APP_ENV")
        or _clean_env("ENVIRONMENT")
        or "local"
    )


class ArgusEventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "argus_observability_event/v1"
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    environment: str = Field(default_factory=_default_environment)
    privacy_mode: PrivacyMode = "metadata_only"
    event_type: EventType
    event_action: EventAction
    feature_area: FeatureArea
    actor_hash: str | None = None
    session_id: str | None = None
    conversation_id: str | None = None
    turn_id: str | None = None
    message_id: str | None = None
    job_id: str | None = None
    backtest_run_id: str | None = None
    route_receipt_id: str | None = None
    provider: str | None = None
    model: str | None = None
    provider_request_id: str | None = None
    upstream_id: str | None = None
    status: str | None = None
    latency_ms: int | None = None
    usage: dict[str, Any] | None = None
    cost: dict[str, Any] | None = None
    error_category: str | None = None
    sampling_rate: float | None = None
    retention_class: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class EventCaptureResult(BaseModel):
    status: Literal["captured", "suppressed", "failed"]
    reason: str | None = None
    event_id: str
    destination: Literal["posthog"] | None = None


def build_event_envelope(
    *,
    event_type: EventType,
    event_action: EventAction,
    feature_area: FeatureArea,
    attributes: dict[str, Any] | None = None,
    **kwargs: Any,
) -> ArgusEventEnvelope:
    return ArgusEventEnvelope(
        event_type=event_type,
        event_action=event_action,
        feature_area=feature_area,
        attributes=sanitize_observability_attributes(attributes or {}),
        **kwargs,
    )


def live_analytics_sink_enabled() -> bool:
    return (
        _posthog_project_token() is not None
        and _posthog_ingestion_host() is not None
    )


def posthog_project_token_configured() -> bool:
    """False means this server sends no PostHog events: capture_event
    suppresses every one as posthog_not_configured."""
    return _posthog_project_token() is not None


def _registered_payload(
    envelope: ArgusEventEnvelope,
) -> tuple[str, dict[str, Any]] | None:
    # Imported here because the registry builds envelopes and imports this
    # module; the registry, not a field on the envelope, decides what is sent.
    from argus.observability.analytics_events import registered_payload

    return registered_payload(envelope)


def capture_event(envelope: ArgusEventEnvelope) -> EventCaptureResult:
    if _registered_payload(envelope) is None:
        # The clean break (SPEC 0, 0C-1): only an event the closed analytics
        # registry built and re-validates reaches PostHog. Anything else,
        # including an envelope that merely names an event, stops here.
        return EventCaptureResult(
            status="suppressed",
            reason="not_an_analytics_event",
            event_id=envelope.event_id,
            destination=None,
        )
    if envelope.privacy_mode == "disabled":
        return EventCaptureResult(
            status="suppressed",
            reason="privacy_mode_disabled",
            event_id=envelope.event_id,
            destination=None,
        )
    api_key = _posthog_project_token()
    if api_key is None:
        return EventCaptureResult(
            status="suppressed",
            reason="posthog_not_configured",
            event_id=envelope.event_id,
            destination=None,
        )
    capture_url = _posthog_capture_url()
    if capture_url is None:
        return EventCaptureResult(
            status="suppressed",
            reason="posthog_region_not_configured",
            event_id=envelope.event_id,
            destination=None,
        )
    try:
        payload = posthog_event_payload(envelope, api_key=api_key)
        response = httpx.post(
            capture_url,
            json=payload,
            timeout=_posthog_timeout_seconds(),
        )
        response.raise_for_status()
    except Exception as exc:
        logger.warning(
            "PostHog product event capture failed",
            error=str(exc),
            event_id=envelope.event_id,
            analytics_event=getattr(
                getattr(envelope, "analytics_event", None), "event_name", None
            ),
        )
        return EventCaptureResult(
            status="failed",
            reason="posthog_capture_failed",
            event_id=envelope.event_id,
            destination="posthog",
        )
    return EventCaptureResult(
        status="captured",
        reason=None,
        event_id=envelope.event_id,
        destination="posthog",
    )


def posthog_event_payload(
    envelope: ArgusEventEnvelope,
    *,
    api_key: str,
) -> dict[str, Any]:
    """The PostHog capture body for an analytics event, under its own name.

    Properties are the fixed technical set plus the event model's validated
    fields, nothing else: no hashed conversation or message ids, status,
    latency, or nested attributes.
    """
    registered = _registered_payload(envelope)
    if registered is None:
        raise ValueError("only registry-built analytics events have a PostHog payload")
    event_name, event_properties = registered
    return {
        "api_key": api_key,
        "event": event_name,
        "distinct_id": envelope.actor_hash,
        "timestamp": envelope.occurred_at.isoformat(),
        "properties": {
            **event_properties,
            "$process_person_profile": False,
            "schema_version": envelope.schema_version,
            "event_id": envelope.event_id,
            "environment": envelope.environment,
            # Present and a bool: ``_registered_payload()`` checked it.
            "internal_account": envelope.internal_account,  # type: ignore[attr-defined]
        },
    }


def sanitize_observability_attributes(value: dict[str, Any]) -> dict[str, Any]:
    sanitized = _sanitize_value(value)
    return sanitized if isinstance(sanitized, dict) else {}


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, raw in value.items():
            if not isinstance(key, str) or _blocked_key(key):
                continue
            sanitized = _sanitize_value(raw)
            if sanitized is not None:
                safe[key] = sanitized
        return safe
    if isinstance(value, list):
        return [
            sanitized
            for item in value
            if (sanitized := _sanitize_value(item)) is not None
        ]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        return stripped[:500]
    if isinstance(value, int | float | bool) or value is None:
        return value
    return str(value)[:500]


def _blocked_key(key: str) -> bool:
    normalized = key.strip().lower()
    return normalized in _BLOCKED_EXACT_KEYS or any(
        part in normalized for part in _BLOCKED_KEY_PARTS
    )


def _posthog_project_token() -> str | None:
    return _clean_env("POSTHOG_PROJECT_TOKEN")


def _posthog_capture_url() -> str | None:
    host = _posthog_ingestion_host()
    if host is None:
        return None
    return f"{host.rstrip('/')}{_POSTHOG_CAPTURE_PATH}"


def _posthog_ingestion_host() -> str | None:
    explicit_host = _clean_env("POSTHOG_HOST")
    if explicit_host is not None:
        normalized = explicit_host.rstrip("/")
        if normalized == "https://us.posthog.com":
            return _POSTHOG_US_HOST
        if normalized == "https://eu.posthog.com":
            return _POSTHOG_EU_HOST
        return normalized
    raw_region = _clean_env("POSTHOG_REGION")
    if raw_region is None:
        return None
    region = raw_region.lower().replace("_", "-").replace(" ", "-")
    if region in {"us", "us-cloud", "us-cloud-hosted"}:
        return _POSTHOG_US_HOST
    if region in {"eu", "eu-cloud", "eu-cloud-hosted"}:
        return _POSTHOG_EU_HOST
    logger.warning(
        "Unrecognized POSTHOG_REGION; product-event capture disabled. "
        "Set POSTHOG_REGION to a us/eu synonym or POSTHOG_HOST explicitly.",
        posthog_region=raw_region,
    )
    return None


def _posthog_timeout_seconds() -> float:
    raw = _clean_env("ARGUS_POSTHOG_TIMEOUT_SECONDS")
    if raw is None:
        return _POSTHOG_DEFAULT_TIMEOUT_SECONDS
    try:
        return max(0.1, float(raw))
    except ValueError:
        return _POSTHOG_DEFAULT_TIMEOUT_SECONDS
