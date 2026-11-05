from __future__ import annotations

import hashlib
from typing import Any, Literal, cast
from uuid import uuid4

from loguru import logger

from argus.observability.envelope import (
    ArgusEventEnvelope,
    EventAction,
    EventCaptureResult,
    EventType,
    FeatureArea,
    build_event_envelope,
    capture_event,
)

# Retired from PostHog (SPEC 0, 0C-1): the sink refuses these envelopes, so
# nothing below reaches PostHog. Only the kinds a later wave 1 package renames
# are left, each at the call site that package replaces with its analytics
# event: ``decision_capture`` becomes ``card_saved`` (0C-4),
# ``account_registration_completed`` becomes ``signed_in`` (0C-4), and
# ``receipt_created`` becomes ``receipt_shared`` (0C-8).
ProductEventKind = Literal[
    "decision_capture",
    "receipt_created",
    "account_registration_completed",
]

_PRODUCT_EVENT_MAP: dict[ProductEventKind, tuple[EventType, EventAction, FeatureArea]] = {
    "decision_capture": ("decision_saved", "completed", "decision_capture"),
    "receipt_created": ("storage", "completed", "evidence_capture"),
    "account_registration_completed": ("storage", "completed", "guest_acquisition"),
}


def build_product_event(
    kind: ProductEventKind | str,
    *,
    user_id: str | None,
    conversation_id: str | None = None,
    turn_id: str | None = None,
    message_id: str | None = None,
    job_id: str | None = None,
    backtest_run_id: str | None = None,
    status: str | None = None,
    latency_ms: int | None = None,
    error_category: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> ArgusEventEnvelope:
    product_event_kind = cast(ProductEventKind, kind)
    event_type, event_action, feature_area = _PRODUCT_EVENT_MAP[product_event_kind]
    event_attributes = {**(attributes or {}), "product_event": product_event_kind}
    return build_event_envelope(
        event_type=event_type,
        event_action=event_action,
        feature_area=feature_area,
        actor_hash=actor_hash_for_user(user_id),
        conversation_id=conversation_id,
        turn_id=turn_id,
        message_id=message_id,
        job_id=job_id,
        backtest_run_id=backtest_run_id,
        status=status,
        latency_ms=latency_ms,
        error_category=error_category,
        attributes=event_attributes,
    )


def capture_product_event(
    kind: ProductEventKind | str,
    *,
    user_id: str | None,
    conversation_id: str | None = None,
    turn_id: str | None = None,
    message_id: str | None = None,
    job_id: str | None = None,
    backtest_run_id: str | None = None,
    status: str | None = None,
    latency_ms: int | None = None,
    error_category: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> EventCaptureResult:
    try:
        envelope = build_product_event(
            kind,
            user_id=user_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            message_id=message_id,
            job_id=job_id,
            backtest_run_id=backtest_run_id,
            status=status,
            latency_ms=latency_ms,
            error_category=error_category,
            attributes=attributes,
        )
    except KeyError:
        logger.warning(
            "Unknown product event kind",
            product_event=kind,
        )
        return EventCaptureResult(
            status="failed",
            reason="unknown_product_event_kind",
            event_id=str(uuid4()),
            destination=None,
        )
    return capture_event(envelope)


def actor_hash_for_user(user_id: str | None) -> str | None:
    if user_id is None or not str(user_id).strip():
        return None
    digest = hashlib.sha256(f"argus:actor:{user_id.strip()}".encode("utf-8")).hexdigest()
    return f"argus_actor_{digest[:32]}"
