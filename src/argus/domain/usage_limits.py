from __future__ import annotations

import os
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Protocol

from loguru import logger

if TYPE_CHECKING:
    from argus.api.guest_access import AccountContext


class QuotaExceededError(Exception):
    pass


USAGE_COUNTER_LOCK = threading.Lock()

SIMULATION_ALLOWANCE_LIMITS: list[tuple[str, int]] = [("hour", 10), ("day", 50)]

# Conversation is compute: free, unlimited, never settled. The resource name
# survives only because historical counter rows carry it.
MESSAGE_USAGE_RESOURCE = "chat_messages"
SIMULATION_USAGE_RESOURCE = "backtest_runs"
FEEDBACK_USAGE_RESOURCE = "feedback"

GUEST_SIMULATION_ALLOWANCE = 2
GUEST_FEEDBACK_ALLOWANCE = 5
GUEST_CONVERSATION_ALLOWANCE = 1
# A taste of the premium, plus one in reserve. One search would be enough to
# show what grounded discovery is, except a provider failure would then be a
# stranger's entire impression of Argus. The second exists for that, not for
# exploration -- cheap verified suggestions carry ordinary asks.
GUEST_DISCOVERY_ALLOWANCE = 2

# Deliberately a plain day window, not the guest_session window the other guest
# allowances use. guest_session anchors to the workspace expiry, which moves
# every time a workspace renews -- it would reset the allowance this limit
# exists to hold. Paired with a visitor-scoped counter subject, a day window
# survives renewal.
GUEST_DISCOVERY_ALLOWANCE_LIMITS: list[tuple[str, int]] = [
    ("day", GUEST_DISCOVERY_ALLOWANCE)
]

# Guest allowances follow the visitor per day; a fresh session grants
# nothing new. Decision record: docs/PRODUCT.md (guest access).
GUEST_SIMULATION_VISITOR_LIMITS: list[tuple[str, int]] = [
    ("day", GUEST_SIMULATION_ALLOWANCE)
]

# Anti-abuse, not an allowance. Conversation is compute: free, and the product
# surface says so with no limit. An anonymous endpoint still cannot be
# unbounded, so a guest's turns count against a visitor-keyed daily ceiling
# sized so no real person reaches it. Never rendered, never promised.
# A signed-in account has its own daily ceiling so one login cannot run
# unbounded LLM spend; that cap is also never projected as an allowance.
GUEST_COMPUTE_CEILING_RESOURCE = "guest_compute_turns"
GUEST_COMPUTE_DAILY_CEILING = 300
GUEST_COMPUTE_CEILING_LIMITS: list[tuple[str, int]] = [
    ("day", GUEST_COMPUTE_DAILY_CEILING)
]
REGISTERED_COMPUTE_CEILING_RESOURCE = "account_compute_turns"
# One authenticated guest workspace is one person. The visitor (IP) ceiling
# stays 300 so a shared NAT still has headroom. A single session hopping
# IPs must not inherit that headroom. 100 is still far above any honest
# guest conversation day and is env-overridable without a deploy.
_GUEST_SESSION_DAILY_TURN_CEILING_DEFAULT = 100
# Signed-in chat: 200 bounds worst-case spend at roughly $50/user/day.
# Honest heavy users can hit it. Env-overridable without a deploy.
_REGISTERED_DAILY_TURN_CEILING_DEFAULT = 200
_REGISTERED_DAILY_RESEARCH_CEILING_DEFAULT = 15
REGISTERED_DAILY_TURN_CEILING_ENV = "CUADRAO_REGISTERED_DAILY_TURN_CEILING"
REGISTERED_DAILY_RESEARCH_CEILING_ENV = "ARGUS_REGISTERED_DAILY_RESEARCH_CEILING"
# One user-facing refusal for every compute ceiling. Guest and signed-in
# 429s raise this exact detail so the copy cannot drift.
COMPUTE_TURN_CEILING_DETAIL = "Too many conversation turns today."
COMPUTE_CLAIM_UNAVAILABLE_DETAIL = (
    "Argus could not start this turn. Please try again."
)
# One Retry-After for every compute-claim outage. Guest and signed-in 503s
# both read this so the wait cannot drift.
COMPUTE_CLAIM_UNAVAILABLE_RETRY_AFTER_SECONDS = 15


# Postgres ``integer`` max. A typo like 3000000000 overflows the claim
# RPC and turns every signed-in request into a 503.
POSTGRES_INTEGER_MAX = 2**31 - 1
_INVALID_POSITIVE_INT_ENV_WARNED: set[str] = set()


def reset_positive_int_env_warnings_for_tests() -> None:
    _INVALID_POSITIVE_INT_ENV_WARNED.clear()


def positive_int_env(name: str, default: int) -> int:
    """Blank, invalid, non-positive, or overflow values keep the default.

    Overflow is the same class of unusable env as garbage: fall back with
    one warning per process so a typo cannot take the API down or flood
    logs on every claim. Guest session, registered chat, registered
    research, and the two global ceilings share this helper.
    """
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        parsed = int(raw)
    except ValueError:
        _warn_invalid_positive_int_env(name, raw, default)
        return default
    if parsed < 1 or parsed > POSTGRES_INTEGER_MAX:
        _warn_invalid_positive_int_env(name, raw, default)
        return default
    return parsed


def _warn_invalid_positive_int_env(name: str, raw: str, default: int) -> None:
    if name in _INVALID_POSITIVE_INT_ENV_WARNED:
        return
    _INVALID_POSITIVE_INT_ENV_WARNED.add(name)
    logger.warning(
        "Invalid usage-limit env; using the code-owned default",
        name=name,
        value=raw,
        default=default,
    )


def guest_session_daily_turn_ceiling() -> int:
    return positive_int_env(
        "CUADRAO_GUEST_SESSION_DAILY_TURN_CEILING",
        _GUEST_SESSION_DAILY_TURN_CEILING_DEFAULT,
    )


def registered_daily_turn_ceiling() -> int:
    return positive_int_env(
        REGISTERED_DAILY_TURN_CEILING_ENV,
        _REGISTERED_DAILY_TURN_CEILING_DEFAULT,
    )


def registered_daily_research_ceiling() -> int:
    return positive_int_env(
        REGISTERED_DAILY_RESEARCH_CEILING_ENV,
        _REGISTERED_DAILY_RESEARCH_CEILING_DEFAULT,
    )


def guest_session_ceiling_limits() -> list[tuple[str, int]]:
    return [("day", guest_session_daily_turn_ceiling())]


def guest_compute_ceiling_limits() -> list[tuple[str, int]]:
    return list(GUEST_COMPUTE_CEILING_LIMITS)


def registered_compute_ceiling_limits() -> list[tuple[str, int]]:
    return [("day", registered_daily_turn_ceiling())]


def registered_research_limits() -> list[tuple[str, int]]:
    return [("day", registered_daily_research_ceiling())]

# One ceiling for every research shape, not one per tier. A stranger cannot
# tell a fast lookup from a thorough comparison, and a meter they cannot
# predict is a meter that feels arbitrary; the rail decides the tier, so the
# rail owns that cost, not the guest.
#
# Three is deliberately conservative because the recorded cost is wrong: the
# ledger's per-call figure is not yet trustworthy (issue #409). Raising this
# is cheap once the real number is known; refunding a month of underpriced
# strangers is not.
GUEST_RESEARCH_ALLOWANCE = 3
GUEST_RESEARCH_VISITOR_LIMITS: list[tuple[str, int]] = [("day", GUEST_RESEARCH_ALLOWANCE)]

# Circuit breaker, not a budget: the only bound that holds when someone rotates
# identity faster than any per-visitor limit can see. Sized so no honest day
# reaches it. Env-overridable because a circuit breaker is worth nothing if
# resetting it needs a deploy.
_GLOBAL_DISCOVERY_DAILY_CEILING_DEFAULT = 500
# Also a uuid: usage_counters.user_id is uuid-typed, so the global bucket
# needs a storable subject like every other counter row.
GLOBAL_DISCOVERY_CEILING_SUBJECT = "00000000-0000-4000-8000-000000000d15"


def global_discovery_daily_ceiling() -> int:
    return positive_int_env(
        "ARGUS_DISCOVERY_GLOBAL_DAILY_CEILING",
        _GLOBAL_DISCOVERY_DAILY_CEILING_DEFAULT,
    )


# The research rail rides the default question path, not an opt-in surface, so
# its circuit breaker is sized for ordinary conversation volume rather than
# the discovery ceiling's opt-in profile (spec 2026-08-07 section 9). Still a
# breaker, not a budget: no honest day should reach it.
_GLOBAL_RESEARCH_DAILY_CEILING_DEFAULT = 5000
GLOBAL_RESEARCH_CEILING_SUBJECT = "00000000-0000-4000-8000-000000000d16"


def global_research_daily_ceiling() -> int:
    return positive_int_env(
        "ARGUS_RESEARCH_GLOBAL_DAILY_CEILING",
        _GLOBAL_RESEARCH_DAILY_CEILING_DEFAULT,
    )


_REGISTERED_ALLOWANCES: dict[str, list[tuple[str, int]]] = {
    SIMULATION_USAGE_RESOURCE: SIMULATION_ALLOWANCE_LIMITS,
    FEEDBACK_USAGE_RESOURCE: [("day", 50), ("hour", 20)],
}
_GUEST_ALLOWANCES = {
    SIMULATION_USAGE_RESOURCE: GUEST_SIMULATION_ALLOWANCE,
    FEEDBACK_USAGE_RESOURCE: GUEST_FEEDBACK_ALLOWANCE,
}


def allowance_windows(
    account: AccountContext,
    resource: str,
) -> list[dict[str, object]]:
    if account.kind == "guest":
        if account.expires_at is None:
            raise RuntimeError("Guest account context is missing its fixed expiry.")
        try:
            limit = _GUEST_ALLOWANCES[resource]
        except KeyError as exc:
            raise ValueError(
                f"Unsupported guest allowance resource {resource!r}."
            ) from exc
        return [
            {
                "period": "guest_session",
                "limit": limit,
                "period_start": account.expires_at - timedelta(days=7),
                "period_end": account.expires_at,
            }
        ]
    try:
        registered = _REGISTERED_ALLOWANCES[resource]
    except KeyError as exc:
        raise ValueError(f"Unsupported allowance resource {resource!r}.") from exc
    return [
        {"period": period, "limit": limit_count} for period, limit_count in registered
    ]


@dataclass(frozen=True)
class UsageMeter:
    """One counter and the windows one account kind is bounded by on it.

    Empty ``limits`` means no account window bounds the class; only a shared
    ceiling does, and that is a circuit breaker rather than an allowance.
    """

    resource: str
    limits: list[tuple[str, int]]


@dataclass(frozen=True)
class AllowanceWindow:
    period: str
    limit: int
    period_start: datetime
    period_end: datetime


AllowanceWindowInput = AllowanceWindow | tuple[str, int] | Mapping[str, object]


def _window_datetime(value: object, *, field: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{field} must be an ISO datetime.") from exc
    else:
        raise ValueError(f"{field} must be a datetime.")
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone.")
    return parsed.astimezone(timezone.utc)


def normalize_allowance_windows(
    limits: Sequence[AllowanceWindowInput],
    *,
    at: datetime,
) -> list[AllowanceWindow]:
    """Resolve tuple and policy-dict inputs to one in-process window shape."""
    normalized: list[AllowanceWindow] = []
    for item in limits:
        if isinstance(item, AllowanceWindow):
            normalized.append(item)
            continue
        if isinstance(item, tuple):
            if len(item) != 2:
                raise ValueError("Allowance tuple must contain period and limit.")
            period, limit = item
            start, end = align_usage_period(at, period)
        elif isinstance(item, Mapping):
            period = item.get("period")
            limit = item.get("limit")
            if not isinstance(period, str):
                raise ValueError("Allowance period must be a string.")
            if period == "guest_session":
                start = _window_datetime(
                    item.get("period_start"),
                    field="period_start",
                )
                end = _window_datetime(
                    item.get("period_end"),
                    field="period_end",
                )
            else:
                start, end = align_usage_period(at, period)
        else:
            raise ValueError("Unsupported allowance window.")
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise ValueError("Allowance limit must be a positive integer.")
        if end <= start:
            raise ValueError("Allowance period_end must be after period_start.")
        normalized.append(
            AllowanceWindow(
                period=period,
                limit=limit,
                period_start=start,
                period_end=end,
            )
        )
    return normalized


def settle_memory_usage(
    counters: dict[tuple[str, str, str], dict[str, Any]],
    *,
    user_id: str,
    resource: str,
    limits: Sequence[AllowanceWindowInput],
    at: datetime | None = None,
) -> None:
    """In-memory twin of the database-owned settlement charge."""
    now = at or datetime.now(timezone.utc)
    for window in normalize_allowance_windows(limits, at=now):
        key = (user_id, resource, window.period)
        row = counters.get(key)
        if row is None or row.get("period_start") != window.period_start:
            counters[key] = {
                "period_start": window.period_start,
                "period_end": window.period_end,
                "used_count": 1,
                "limit_count": window.limit,
            }
        else:
            row["used_count"] = int(row.get("used_count", 0)) + 1
            row["limit_count"] = window.limit


def read_memory_usage(
    counters: dict[tuple[str, str, str], dict[str, Any]],
    *,
    user_id: str,
    resource: str,
    period: str,
    at: datetime | None = None,
    period_start: datetime | None = None,
) -> dict[str, Any] | None:
    now = at or datetime.now(timezone.utc)
    start = period_start
    if start is None:
        start, _ = align_usage_period(now, period)
    row = counters.get((user_id, resource, period))
    if row is None or row.get("period_start") != start:
        return None
    return dict(row)


class UsageLimitGateway(Protocol):
    client: Any


def align_usage_period(dt: datetime, period: str) -> tuple[datetime, datetime]:
    if period == "minute":
        start = dt.replace(second=0, microsecond=0)
        end = start + timedelta(minutes=1)
    elif period == "hour":
        start = dt.replace(minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=1)
    elif period == "day":
        start = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
    else:
        raise ValueError(f"Unsupported calendar allowance period {period!r}.")
    return start, end


def check_usage_limits(
    self: UsageLimitGateway,
    *,
    user_id: str,
    resource: str,
    limits: list[tuple[str, int]],
) -> None:
    """Reject exhausted limits without creating or incrementing counters."""
    if not limits:
        return
    now = datetime.now(timezone.utc)
    with USAGE_COUNTER_LOCK:
        for period, limit_count in limits:
            start, _ = align_usage_period(now, period)
            response = (
                self.client.table("usage_counters")
                .select("used_count")
                .eq("user_id", user_id)
                .eq("resource", resource)
                .eq("period", period)
                .eq("period_start", start.isoformat())
                .limit(1)
                .execute()
            )
            rows = getattr(response, "data", None) or []
            row = rows[0] if isinstance(rows, list) and rows else None
            current_used = int(row.get("used_count", 0)) if row else 0
            if current_used >= limit_count:
                raise QuotaExceededError(f"Quota exceeded for {resource} ({period})")
