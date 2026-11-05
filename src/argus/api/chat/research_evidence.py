"""Research rail metering: one flat meter for users, rich classes underneath.

Retrieval is the grounding operation class: metered per retrieval, never per
turn. A signed-in account has a daily research ceiling keyed to
``user:<account id>``. A guest carries a small research allowance keyed
to the visitor (spec section 9b). What this module owns:

- the shared global daily ceiling, atomically claimed immediately before a
  cache miss enters provider work;
- the guest's own daily research allowance, claimed in that same transaction,
  so concurrent turns can never spend one remaining slot twice;
- capability-class instrumentation per research turn (fast_quote,
  balanced_lookup, thorough_research, screening, peer_expansion), recorded on
  the cost ledger whether or not a provider call happened, because the class
  mix is what makes natural tiers visible later.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from argus.api import state as api_state
from argus.api.chat.discovery_evidence import discovery_meter
from argus.domain.research.admission import ResearchAttemptAdmission
from argus.domain.research.config import research_rail_enabled
from argus.domain.research.contracts import ResearchUsage
from argus.domain.usage_limits import (
    GLOBAL_RESEARCH_CEILING_SUBJECT,
    GUEST_RESEARCH_VISITOR_LIMITS,
    UsageMeter,
    align_usage_period,
    global_research_daily_ceiling,
    read_memory_usage,
    registered_research_limits,
    settle_memory_usage,
)
from argus.domain.visitor_usage import (
    is_registered_account_usage_key,
    memory_visitor_within_limits,
    registered_account_usage_key,
    settle_memory_visitor_usage,
    visitor_key_for,
)

RESEARCH_USAGE_RESOURCE = "research_searches"
# Charged against the visitor table when Supabase is live for the same reason
# as discovery: usage_counters.user_id FKs to profiles, so a synthetic global
# subject there would fail to insert and the ceiling would silently never trip.
GLOBAL_CEILING_KEY = "global:research"
_MEMORY_CLAIM_LOCK = threading.Lock()


def _ceiling_limits() -> list[tuple[str, int]]:
    return [("day", global_research_daily_ceiling())]


def research_meter(*, is_guest: bool) -> UsageMeter:
    """The per-account research counter ``GET /me/usage`` may project.

    Guests keep the visitor day window. Signed-in accounts have a daily
    claim ceiling, but this meter stays empty so the usage panel does not
    invent an allowance window the product surface does not promise.
    """
    return UsageMeter(
        resource=RESEARCH_USAGE_RESOURCE,
        limits=list(GUEST_RESEARCH_VISITOR_LIMITS) if is_guest else [],
    )


def research_account_limits(*, account_key: str | None) -> list[tuple[str, int]]:
    """Limits the optional per-account research row is claimed against."""
    if account_key is None:
        return []
    if is_registered_account_usage_key(account_key):
        return list(registered_research_limits())
    return list(GUEST_RESEARCH_VISITOR_LIMITS)


def grounding_meter(*, is_guest: bool) -> UsageMeter:
    """Which meter grounds a retrieval: the one the live rail charges, so the
    allowance projection can never name a counter the charge does not."""
    if research_rail_enabled():
        return research_meter(is_guest=is_guest)
    return discovery_meter(is_guest=is_guest)


def guest_research_visitor_key(
    *,
    is_guest: bool,
    client_identity: str | None,
    user_id: str | None = None,
) -> str | None:
    """The subject a research claim charges against.

    Guests key on the visitor digest. Signed-in accounts key on
    ``user:<account id>``. Computed once at the request edge so everything
    downstream carries the opaque subject, including the job row a
    background run settles from long after the request is gone.
    """
    if is_guest:
        return visitor_key_for(client_identity)
    return registered_account_usage_key(user_id)


def claim_research_provider_attempt(
    *,
    guest_visitor_key: str | None = None,
) -> ResearchAttemptAdmission:
    """Atomically claim capacity immediately before billable provider work.

    Two bounds are owned here: the shared global circuit breaker, and the
    optional per-account daily row. Guests use the visitor key and the
    three-question allowance. Signed-in accounts use ``user:<id>`` and the
    registered daily research ceiling.

    Flag-off short-circuits to available. Fails closed: without writable truth,
    no research spend is allowed, and
    the turn still answers through the honest exhausted path.
    """
    if not research_rail_enabled():
        return ResearchAttemptAdmission(available=True)
    now = datetime.now(timezone.utc)
    account_limits = research_account_limits(account_key=guest_visitor_key)
    account_limit = dict(account_limits)["day"] if account_limits else 1
    try:
        if api_state.supabase_gateway is not None:
            client = api_state.supabase_gateway.client
            result = client.rpc(
                "claim_research_usage",
                {
                    "p_guest_visitor_key": guest_visitor_key,
                    "p_resource": RESEARCH_USAGE_RESOURCE,
                    "p_global_visitor_key": GLOBAL_CEILING_KEY,
                    "p_global_limit": global_research_daily_ceiling(),
                    "p_guest_limit": account_limit,
                },
            ).execute()
            payload = getattr(result, "data", None)
            if not isinstance(payload, dict):
                raise TypeError("Research usage claim returned no object")
            account_exhausted = payload.get("guest_exhausted") is True
            registered = is_registered_account_usage_key(guest_visitor_key)
            return ResearchAttemptAdmission(
                available=payload.get("available") is True,
                guest_exhausted=account_exhausted and not registered,
                registered_exhausted=account_exhausted and registered,
                period_start=payload.get("period_start") or None,
            )
        return _claim_memory_research_usage(
            guest_visitor_key=guest_visitor_key,
            account_limits=account_limits,
            now=now,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Research allowance claim failed; treating capacity as exhausted",
            error=str(exc),
        )
        return ResearchAttemptAdmission(available=False)


def release_research_provider_claim(
    admission: ResearchAttemptAdmission,
    *,
    guest_visitor_key: str | None,
) -> bool:
    """Give the account back the research question a failed provider call cost.

    Only the per-account row for the period the claim charged is returned. The
    shared ceiling keeps the attempt: it bounds provider work, and the work was
    attempted. Guests and signed-in accounts both get that row back when
    provider work failed with no usable response.
    Returns whether the charge went back; anything short of a confirmed release
    leaves the charge standing. This never raises."""
    if (
        guest_visitor_key is None
        or not admission.available
        or admission.period_start is None
        or not research_rail_enabled()
    ):
        return False
    try:
        if api_state.supabase_gateway is not None:
            result = api_state.supabase_gateway.client.rpc(
                "release_research_usage",
                {
                    "p_guest_visitor_key": guest_visitor_key,
                    "p_resource": RESEARCH_USAGE_RESOURCE,
                    "p_global_visitor_key": GLOBAL_CEILING_KEY,
                    "p_period_start": admission.period_start,
                },
            ).execute()
            payload = getattr(result, "data", None)
            released = isinstance(payload, dict) and payload.get("released") is True
        else:
            released = _release_memory_research_usage(
                guest_visitor_key=guest_visitor_key,
                resource=RESEARCH_USAGE_RESOURCE,
                period_start=datetime.fromisoformat(admission.period_start),
            )
    except Exception as exc:  # noqa: BLE001
        # The deployed log sink drops structured extras; the error rides the text.
        logger.warning(
            f"Research guest claim release failed; the charge stands error={exc}"
        )
        return False
    if not released:
        logger.warning(
            "Research guest claim release matched no charge; the charge stands"
        )
    return released


def _release_memory_research_usage(
    *,
    guest_visitor_key: str,
    resource: str,
    period_start: datetime,
) -> bool:
    """Process-local twin of the release_research_usage function."""

    with _MEMORY_CLAIM_LOCK:
        row = api_state.store.visitor_usage_counters.get(
            (guest_visitor_key, resource, "day")
        )
        if (
            row is None
            or row.get("period_start") != period_start
            or int(row.get("used_count", 0)) <= 0
        ):
            return False
        row["used_count"] = int(row["used_count"]) - 1
        return True


def _claim_memory_research_usage(
    *,
    guest_visitor_key: str | None,
    account_limits: list[tuple[str, int]],
    now: datetime,
) -> ResearchAttemptAdmission:
    """Process-local twin of the database transaction used in tests/dev."""

    registered = is_registered_account_usage_key(guest_visitor_key)
    with _MEMORY_CLAIM_LOCK:
        if guest_visitor_key is not None:
            account_within = memory_visitor_within_limits(
                api_state.store.visitor_usage_counters,
                visitor_key=guest_visitor_key,
                resource=RESEARCH_USAGE_RESOURCE,
                limits=list(account_limits),
                now=now,
            )
            if not account_within:
                return ResearchAttemptAdmission(
                    available=False,
                    guest_exhausted=not registered,
                    registered_exhausted=registered,
                )
        if not _memory_ceiling_available(now=now):
            return ResearchAttemptAdmission(available=False)
        settle_memory_usage(
            api_state.store.usage_counters,
            user_id=GLOBAL_RESEARCH_CEILING_SUBJECT,
            resource=RESEARCH_USAGE_RESOURCE,
            limits=_ceiling_limits(),
            at=now,
        )
        if guest_visitor_key is not None:
            settle_memory_visitor_usage(
                api_state.store.visitor_usage_counters,
                visitor_key=guest_visitor_key,
                resource=RESEARCH_USAGE_RESOURCE,
                limits=list(account_limits),
                now=now,
            )
        charged, _ = align_usage_period(now, "day")
        return ResearchAttemptAdmission(available=True, period_start=charged.isoformat())


def _memory_ceiling_available(*, now: datetime) -> bool:
    for period, limit_count in _ceiling_limits():
        start, _ = align_usage_period(now, period)
        row = read_memory_usage(
            api_state.store.usage_counters,
            user_id=GLOBAL_RESEARCH_CEILING_SUBJECT,
            resource=RESEARCH_USAGE_RESOURCE,
            period=period,
        )
        if (
            row is not None
            and row.get("period_start") == start
            and int(row.get("used_count", 0)) >= limit_count
        ):
            return False
    return True


def settle_research_turn(
    runtime_result: dict[str, Any],
    *,
    user_id: str,
    conversation_id: str | None,
    message_id: str | None,
    request_id: str | None,
    tool_call_id: str | None = None,
) -> None:
    """Post-terminal evidence for a turn that may carry a research sidecar."""
    research = runtime_result.get("research")
    if not isinstance(research, dict):
        return
    record_research_turn_evidence(
        research=research,
        user_id=user_id,
        conversation_id=conversation_id,
        message_id=message_id,
        request_id=request_id,
        tool_call_id=tool_call_id,
    )


def record_research_turn_evidence(
    *,
    research: Any,
    user_id: str,
    conversation_id: str | None,
    message_id: str | None,
    request_id: str | None,
    tool_call_id: str | None = None,
) -> None:
    """Append one capability-classed ledger row for every research turn."""
    if not isinstance(research, dict):
        return
    usage = research.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    _append_ledger_row(
        research=research,
        usage=usage,
        user_id=user_id,
        conversation_id=conversation_id,
        message_id=message_id,
        request_id=request_id,
        tool_call_id=tool_call_id,
    )


def record_result_breakdown_spend(
    *,
    usage: ResearchUsage | None,
    failure_mode: str | None,
    user_id: str,
    conversation_id: str | None,
    request_id: str | None,
) -> None:
    """The received invoice counts even when the readout falls back entirely.

    The shared Agent client separately sends unpriceable invoices to the existing
    unpriced-spend recorder. This row owns the action's spend, never its prose.
    """
    if usage is None:
        return
    _append_ledger_row(
        research={
            "capability_class": "result_breakdown",
            "shape": "balanced",
            "degraded": {"code": failure_mode} if failure_mode else None,
        },
        usage=usage.model_dump(mode="json"),
        user_id=user_id,
        conversation_id=conversation_id,
        message_id=None,
        request_id=request_id,
        feature_area="result_readout",
    )


def _append_ledger_row(
    *,
    research: dict[str, Any],
    usage: dict[str, Any],
    user_id: str,
    conversation_id: str | None,
    message_id: str | None,
    request_id: str | None,
    tool_call_id: str | None = None,
    feature_area: str = "research_rail",
) -> None:
    gateway = api_state.supabase_gateway
    if gateway is None:
        return
    capability_class = str(research.get("capability_class") or "unknown")
    paid = cache_status_of(usage) == "miss"
    correlation_id = request_id or message_id or conversation_id or user_id
    if tool_call_id is not None:
        correlation_id = f"{correlation_id}:{tool_call_id}"
    degraded = research.get("degraded")
    entry = {
        "source": "research",
        "service": "perplexity_agent",
        "provider": "perplexity_agent",
        "feature_area": feature_area,
        "model": usage.get("model"),
        "input_tokens": usage.get("input_tokens") if paid else None,
        "output_tokens": usage.get("output_tokens") if paid else None,
        "task": capability_class,
        "user_id": user_id,
        "conversation_id": conversation_id,
        "message_id": message_id,
        "request_id": request_id,
        "correlation_id": f"research:{correlation_id}",
        "usage_metadata": {
            "capability_class": capability_class,
            "shape": research.get("shape"),
            "cache_status": cache_status_of(usage),
            "invocations": usage.get("invocations"),
            **{
                key: usage[key]
                for key in (
                    "web_search_invocations",
                    "fetch_url_invocations",
                    "finance_search_invocations",
                    "cache_creation_input_tokens",
                    "cache_read_input_tokens",
                )
                if key in usage
            },
            **({"tool_call_id": tool_call_id} if tool_call_id is not None else {}),
            # A provider failure's HTTP status rides beside its degraded code,
            # so outages can be counted by kind.
            **(
                {
                    f"degraded_{key}": degraded[key]
                    for key in ("code", "status")
                    if degraded.get(key) is not None
                }
                if isinstance(degraded, dict) and degraded.get("code")
                else {}
            ),
        },
        "billable_unit": "request",
        "billable_quantity": 1 if paid else 0,
        # What this turn paid, not what the answer cost whoever retrieved it. A
        # cache hit serves a record with an invoice on it and spends nothing, so
        # its cost and latency belong to the miss that stored the record and are
        # already on that row; repeating them here would let any report that
        # sums the column charge one retrieval twice.
        "cost_amount": usage.get("cost_usd") if paid else None,
        "cost_source": (
            "provider_reported"
            if paid and usage.get("cost_usd") is not None
            else "unavailable"
        ),
        "latency_ms": usage.get("latency_ms") if paid else None,
    }
    try:
        gateway.create_cost_ledger_entry(entry=entry)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Research cost ledger persistence failed",
            error=str(exc),
            failure_classification="telemetry_only",
        )


def cache_status_of(usage: dict[str, Any]) -> str:
    return str(usage.get("cache_status") or "miss")
