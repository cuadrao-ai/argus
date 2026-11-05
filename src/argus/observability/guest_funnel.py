from __future__ import annotations

from typing import Literal, cast

from argus.observability.envelope import (
    ArgusEventEnvelope,
    EventAction,
    EventCaptureResult,
    EventType,
    build_event_envelope,
    capture_event,
)
from argus.observability.product_events import actor_hash_for_user

# Retired from PostHog (SPEC 0, 0C-1): the sink refuses these envelopes, so
# nothing below reaches PostHog. Only the kinds a later wave 1 package renames
# are left, at the call sites that package replaces:
# ``first_useful_assistant_response_completed`` becomes ``first_answer_shown``
# (0C-3), and the two account completions become ``signed_in`` (0C-4). The
# milestone claim stays; 0C-3 reuses it for ``first_answer_shown``.
GuestFunnelEventKind = Literal[
    "first_useful_assistant_response_completed",
    "account_creation_completed",
    "existing_account_sign_in_completed",
]
GuestFunnelLanguage = Literal["en", "es-419"]
GuestFunnelSurface = Literal[
    "guest_entry",
    "starter_actions",
    "chat",
    "confirmation",
    "backtest",
    "conversion_modal",
    "account_conversion",
    "feedback",
    "cleanup",
]
GuestFunnelStrategyCategory = Literal[
    "buy_and_hold",
    "buy_the_dip",
    "dca_accumulation",
    "moving_average_crossover",
    "rsi_mean_reversion",
]
# Product activity, not the research work kind carried by capability_class.
GuestFunnelProductCapability = Literal[
    "chat",
    "simulation",
    "decision",
    "history",
    "account",
    "feedback",
]
GuestFunnelTerminalOutcome = Literal[
    "started",
    "selected",
    "completed",
    "admitted",
    "shown",
    "claimed",
    "limit_reached",
    "expired",
]
GuestFunnelConversionReason = Literal[
    "simulation_limit",
    "message_limit",
    "save_decision",
    "new_conversation",
    "keep_history",
    "discovery_searches",
]

# Milestone-class kinds are recorded at most once per subject, ever: the kinds
# whose own name asserts a first-time semantic, plus the conversion completions
# the funnel counts once per visitor. Every other kind stays repeatable volume
# or step data, which a guest reaches as many times as they actually do.
MILESTONE_EVENT_KINDS: frozenset[GuestFunnelEventKind] = frozenset(
    {
        "first_useful_assistant_response_completed",
        "account_creation_completed",
        "existing_account_sign_in_completed",
    }
)

GUEST_FUNNEL_EVENT_MAP: dict[
    GuestFunnelEventKind,
    tuple[EventType, EventAction],
] = {
    "first_useful_assistant_response_completed": ("ai_response", "completed"),
    "account_creation_completed": ("storage", "completed"),
    "existing_account_sign_in_completed": ("system", "completed"),
}


def build_guest_funnel_event(
    kind: GuestFunnelEventKind | str,
    *,
    user_id: str | None,
    conversation_id: str | None = None,
    message_id: str | None = None,
    job_id: str | None = None,
    backtest_run_id: str | None = None,
    language: GuestFunnelLanguage | None = None,
    surface: GuestFunnelSurface | None = None,
    strategy_category: GuestFunnelStrategyCategory | None = None,
    product_capability: GuestFunnelProductCapability | None = None,
    conversion_reason: GuestFunnelConversionReason | None = None,
    terminal_outcome: GuestFunnelTerminalOutcome | None = None,
) -> ArgusEventEnvelope:
    event_kind = cast(GuestFunnelEventKind, kind)
    event_type, event_action = GUEST_FUNNEL_EVENT_MAP[event_kind]
    attributes = {
        "product_event": event_kind,
        "language": language,
        "surface": surface,
        "strategy_category": strategy_category,
        "product_capability": product_capability,
        "conversion_reason": conversion_reason,
        "terminal_outcome": terminal_outcome,
    }
    return build_event_envelope(
        event_type=event_type,
        event_action=event_action,
        feature_area="guest_acquisition",
        actor_hash=actor_hash_for_user(user_id),
        conversation_id=conversation_id,
        message_id=message_id,
        job_id=job_id,
        backtest_run_id=backtest_run_id,
        status=terminal_outcome,
        attributes={key: value for key, value in attributes.items() if value is not None},
    )


def is_milestone_event(kind: GuestFunnelEventKind | str) -> bool:
    return kind in MILESTONE_EVENT_KINDS


def milestone_subject(*, visitor_key: str | None, user_id: str | None) -> str | None:
    """The durable identity a milestone is claimed against.

    Prefers the visitor key so a workspace renewal, which mints a fresh user
    id, does not re-emit a milestone the visitor already reached. Falls back to
    the pseudonymous actor when no visitor key is bound, which still bars a
    replay within one workspace, and returns None when neither exists rather
    than claiming every anonymous emission against one shared subject.
    """
    key = (visitor_key or "").strip()
    if key:
        return key
    actor_hash = actor_hash_for_user(user_id)
    return f"actor:{actor_hash}" if actor_hash else None


def capture_guest_funnel_event(
    kind: GuestFunnelEventKind | str,
    **kwargs: object,
) -> EventCaptureResult:
    return capture_event(build_guest_funnel_event(kind, **kwargs))
