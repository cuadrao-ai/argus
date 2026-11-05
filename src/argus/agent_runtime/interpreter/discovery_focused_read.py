"""Focused asset-discovery read: the mode-A backstop for an omitted payload.

The primary interpreter sometimes answers a discovery request as a plain
educational turn and leaves the asset_discovery payload empty (#344). This
second read asks the one narrow question the primary collapsed away: does
this turn ask Argus to find assets? It runs only on a typed contradiction:
the primary read classed the message as a finance fact question, no route
took it, and the discovery payload is empty. A concept question is the
primary's own "no" and is never re-read. Every recovery is recorded with a
reason code (AGENTS.md: redundancy over an LLM read must be observable).
"""

from __future__ import annotations

from typing import Any, Literal

from loguru import logger
from pydantic import BaseModel, Field

from argus.agent_runtime.history import select_thread_history
from argus.agent_runtime.interpreter.discovery_act_guard import (
    response_shape_open_to_discovery,
)
from argus.agent_runtime.interpreter.research_routing import (
    primary_read_asks_a_fact_question,
)
from argus.agent_runtime.stages.interpret_types import AssetDiscoveryRequest
from argus.llm.openrouter import invoke_openrouter_json_schema
from argus.log_sink import exception_origin

_TRIGGER_ACTS = frozenset({None, "educational_question"})
_HISTORY_TURNS = 4

FOCUSED_DISCOVERY_READ_GUIDANCE = (
    "Focused asset-discovery read. Answer one narrow question about the "
    "current user message: does the user ask Argus to find, discover, list, "
    "suggest, or search for which tradable assets exist — by category or "
    "property ('what cybersecurity stocks could I test?', 'find me cryptos "
    "that are trending', 'find me stocks that recently IPO'ed', 'search for "
    "current stocks in a sector'), by peer similarity ('companies like "
    "Nvidia'), or for comparison candidates ('what else in Costco's category "
    "could I compare?'), in any language? Follow-up actions Argus itself "
    "offered after a candidate list, such as 'Search current sources for: "
    "<category>' or its equivalent in the user's language, are discovery "
    "requests; use the recent conversation context when it is provided. Set "
    "asks_argus_to_find_assets=false for questions about whether Argus "
    "supports finding assets, for 'what should I try next?' follow-ups, for "
    "a direct request to test or backtest a named asset, for greetings and "
    "social turns, and for concept education. When true, fill relationship "
    "(category, peer, or comparison), category_description with the plain "
    "category phrase when one exists, anchor_symbols with known tickers the "
    "user anchors on, and asset_class_hint when clear. Set "
    "needs_current_facts=true only when a correct answer requires facts "
    "newer than model knowledge (recent IPOs, this week's movers, current "
    "rankings), the user asks for current or up-to-date candidates, or "
    "explicitly asks to search current sources, in any language; stable "
    "category or peer questions are false."
)


class FocusedAssetDiscoveryRead(BaseModel):
    """One narrow read: is this turn a request to find assets, and if so,
    the typed discovery target."""

    asks_argus_to_find_assets: bool = Field(
        description=(
            "True only when the current message asks Argus to find, discover, "
            "list, suggest, or search for tradable assets matching a "
            "description, in any language. Capability questions, next-step "
            "follow-ups, direct backtest requests, social turns, and concept "
            "education are false."
        )
    )
    relationship: Literal["category", "peer", "comparison"] | None = None
    category_description: str | None = Field(default=None, max_length=200)
    anchor_symbols: list[str] = Field(default_factory=list, max_length=5)
    asset_class_hint: Literal["equity", "crypto", "currency_pair"] | None = None
    needs_current_facts: bool = False
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


def focused_discovery_read_applicable(response: Any) -> bool:
    """Trigger only where a discovery request could be hiding: the primary
    typed a fact question, left the payload empty, and no other surface
    claims the turn."""
    return (
        primary_read_asks_a_fact_question(response)
        and response.asset_discovery is None
        and response.semantic_turn_act in _TRIGGER_ACTS
        and response_shape_open_to_discovery(response)
    )


async def focused_discovery_payload_response(
    *,
    response: Any,
    request: Any,
) -> Any | None:
    """Return the response with a recovered payload attached, or None.

    The caller re-runs the discovery guard on the result, so the recovered
    payload passes the same coherence gate a primary payload would.
    """
    if not focused_discovery_read_applicable(response):
        return None
    try:
        read = await invoke_openrouter_json_schema(
            task="interpretation",
            messages=_read_messages(request),
            schema_model=FocusedAssetDiscoveryRead,
            schema_name="FocusedAssetDiscoveryRead",
        )
    except Exception as exc:  # noqa: BLE001
        origin = exception_origin(exc)
        logger.debug(
            "Focused discovery read failed error_type={} error_origin={}",
            type(exc).__name__,
            origin,
            error_type=type(exc).__name__,
            error_origin=origin,
        )
        return None
    if not isinstance(read, FocusedAssetDiscoveryRead):
        return None
    if not read.asks_argus_to_find_assets or read.relationship is None:
        return None
    category = (read.category_description or "").strip()
    anchors = [symbol.strip() for symbol in read.anchor_symbols if symbol.strip()]
    if read.relationship == "category" and not category:
        return None
    if read.relationship != "category" and not (anchors or category):
        return None
    payload = AssetDiscoveryRequest(
        relationship=read.relationship,
        category_description=category or None,
        anchor_symbols=anchors,
        asset_class_hint=read.asset_class_hint,
        needs_current_facts=read.needs_current_facts,
    )
    logger.info(
        "Focused discovery read recovered an omitted payload",
        relationship=read.relationship,
        needs_current_facts=read.needs_current_facts,
    )
    return response.model_copy(
        update={
            "asset_discovery": payload,
            "reason_codes": list(
                dict.fromkeys(
                    [
                        *response.reason_codes,
                        "discovery_payload_recovered_by_focused_read",
                    ]
                )
            ),
        }
    )


def _read_messages(request: Any) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [
        {"role": "system", "content": FOCUSED_DISCOVERY_READ_GUIDANCE}
    ]
    history = _history_lines(request)
    if history:
        messages.append(
            {
                "role": "system",
                "content": "Recent conversation, oldest first:\n" + history,
            }
        )
    messages.append({"role": "user", "content": str(request.current_user_message)})
    return messages


def _history_lines(request: Any) -> str:
    lines: list[str] = []
    for turn in select_thread_history(
        getattr(request, "recent_thread_history", []) or [], recent_limit=_HISTORY_TURNS
    ):
        if isinstance(turn, dict):
            role = str(turn.get("role") or "")
            content = str(turn.get("content") or "")
        else:
            role = str(getattr(turn, "role", "") or getattr(turn, "type", ""))
            content = str(getattr(turn, "content", ""))
        if role and content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)
