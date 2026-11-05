"""Chat-side durable admission flow.

A capacity rejection triggers one bounded blocker-reconciliation pass and
exactly one admission retry. Rejections are typed outcomes; they never fall
through to free in-process execution.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from argus.api.chat.backtest_job_envelopes import admission_failure_reason
from argus.domain.backtest_admission import CHAT_RUN_SCOPE, validate_idempotency_key
from argus.domain.usage_limits import (
    GUEST_SIMULATION_VISITOR_LIMITS,
    SIMULATION_USAGE_RESOURCE,
)
from argus.domain.visitor_usage import (
    settle_visitor_usage,
    visitor_within_limits,
)

BACKPRESSURE_RECONCILE_SCAN_LIMIT = 16


@dataclass(frozen=True)
class ChatAdmissionResult:
    decision: str
    job: dict[str, Any] | None = None


def _record_rejection(
    *,
    gateway: Any,
    context: Any,
    decision: str,
    identity_hash: str,
    payload_digest: str,
    launch_payload: dict[str, Any],
    execution_metadata: dict[str, Any],
) -> ChatAdmissionResult:
    log_fields = {
        "reason": decision,
        "user_id": context.user_id,
        "conversation_id": context.conversation_id,
        "request_id": context.request_id,
    }
    logger.warning(
        "Chat backtest admission rejected {}",
        json.dumps(log_fields, sort_keys=True),
        **log_fields,
    )
    reason = admission_failure_reason(decision)
    job = gateway.record_backtest_job_rejection(
        user_id=context.user_id,
        operation_scope=CHAT_RUN_SCOPE,
        rejected_idempotency_key=context.idempotency_key,
        identity_hash=identity_hash,
        payload_hash=payload_digest,
        launch_payload=launch_payload,
        conversation_id=context.conversation_id,
        request_message_id=context.request_message_id,
        confirmation_message_id=context.confirmation_message_id,
        failure_code=reason.failure_code,
        failure_detail=reason.failure_detail,
        retryable=reason.retryable,
        execution_metadata={
            **execution_metadata,
            "admission_decision": decision,
            "rejected_idempotency_key": context.idempotency_key,
            "refused_before_dispatch": True,
        },
    )
    return ChatAdmissionResult(decision=decision, job=job)


def admit_durable_chat_job(
    *,
    gateway: Any,
    context: Any,
    identity_hash: str,
    payload_digest: str,
    launch_payload: dict[str, Any],
    reconcile_blockers: Callable[..., bool],
) -> ChatAdmissionResult:
    # #229 grammar, never normalized: the reservation key is the accepted
    # header bytes exactly.
    key_state, idempotency_key = validate_idempotency_key(context.idempotency_key)
    if key_state != "ok" or idempotency_key is None:
        logger.warning(
            "Chat run action reached admission without a valid idempotency key",
            user_id=context.user_id,
            conversation_id=context.conversation_id,
            key_state=key_state,
        )
        return ChatAdmissionResult(decision="missing_key")

    execution_metadata = {
        "shadow_mode": True,
        "source": "api_chat",
        "request_id": context.request_id,
        "payload_hash": payload_digest,
        "openrouter_traffic_class": context.account_kind,
    }

    visitor_key = getattr(context, "visitor_key", None)
    if visitor_key:
        # Replay resolves before allowance: a retry of an admitted run must
        # return its existing job, never a conversion wall.
        existing_reservation = gateway.get_backtest_job_reservation(
            user_id=context.user_id,
            operation_scope=CHAT_RUN_SCOPE,
            idempotency_key=idempotency_key,
        )
        if existing_reservation is None:
            now = datetime.now(timezone.utc)
            if not visitor_within_limits(
                gateway.client,
                visitor_key=visitor_key,
                resource=SIMULATION_USAGE_RESOURCE,
                limits=list(GUEST_SIMULATION_VISITOR_LIMITS),
                now=now,
            ):
                return _record_rejection(
                    gateway=gateway,
                    context=context,
                    decision="conversion_required",
                    identity_hash=identity_hash,
                    payload_digest=payload_digest,
                    launch_payload=launch_payload,
                    execution_metadata=execution_metadata,
                )

    for attempt in (1, 2):
        outcome = gateway.admit_backtest_job(
            user_id=context.user_id,
            operation_scope=CHAT_RUN_SCOPE,
            idempotency_key=idempotency_key,
            identity_hash=identity_hash,
            payload_hash=payload_digest,
            launch_payload=launch_payload,
            initial_status="queued",
            conversation_id=context.conversation_id,
            request_message_id=context.request_message_id,
            confirmation_message_id=context.confirmation_message_id,
            execution_metadata=execution_metadata,
            allowance_limits=context.allowance_limits,
        )
        decision = str(outcome.get("decision") or "")
        if decision in ("admitted", "replay"):
            job = outcome.get("job")
            if decision == "admitted" and visitor_key:
                # Best-effort: the check above is the enforcement point.
                try:
                    settle_visitor_usage(
                        gateway.client,
                        visitor_key=visitor_key,
                        resource=SIMULATION_USAGE_RESOURCE,
                        limits=list(GUEST_SIMULATION_VISITOR_LIMITS),
                    )
                except Exception as exc:
                    logger.warning(
                        "Visitor simulation settlement failed",
                        error=str(exc),
                        failure_classification="telemetry_only",
                    )
            return ChatAdmissionResult(
                decision=decision,
                job=dict(job) if isinstance(job, dict) else None,
            )
        if decision in ("per_user_capacity", "global_capacity"):
            if attempt == 1 and reconcile_blockers(
                gateway=gateway,
                fallback_user_id=context.user_id,
                status="queued" if decision == "global_capacity" else "running",
                user_id=(context.user_id if decision == "per_user_capacity" else None),
                limit=BACKPRESSURE_RECONCILE_SCAN_LIMIT,
            ):
                continue
            return _record_rejection(
                gateway=gateway,
                context=context,
                decision=decision,
                identity_hash=identity_hash,
                payload_digest=payload_digest,
                launch_payload=launch_payload,
                execution_metadata=execution_metadata,
            )
        if decision in ("conflict", "allowance_exhausted", "conversion_required"):
            return _record_rejection(
                gateway=gateway,
                context=context,
                decision=decision,
                identity_hash=identity_hash,
                payload_digest=payload_digest,
                launch_payload=launch_payload,
                execution_metadata=execution_metadata,
            )
        raise RuntimeError(f"Backtest admission returned unknown decision {decision!r}.")
    return ChatAdmissionResult(decision="per_user_capacity")
