"""The rail's find operation: asset discovery as an operation, not a sibling.

Spec section 11b. The router dispatches discovery-shaped questions here; the
composer pipeline in ``agent_runtime.discovery`` stays the implementation
engine for extraction, resolver validation, and voicing, while this module
supplies what made discovery a parallel system: the shared research cache in
front of the provider, the research meter underneath, and the typed research
sidecar so one settlement path and one transcript contract cover every
question shape. The discovery sidecar and its typed action rows are
unchanged; the user-visible experience is the same or better.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from argus.agent_runtime import research_grounded as grounded
from argus.agent_runtime.stages.interpret_types import (
    AssetDiscoveryRequest,
    InterpretDecision,
    StageResult,
    StructuredInterpretation,
)
from argus.agent_runtime.state.models import RunState, UserState
from argus.domain.research.admission import claim_current_research_attempt
from argus.domain.research.cache import SearchPacketCache
from argus.domain.research.contracts import CapabilityClass


def _public_anchor_search(request: AssetDiscoveryRequest) -> bool:
    """Share only anchors the asset catalog has already validated.

    Discovery turns leave the strategy draft empty, so decision and state
    provenance are not proof. Each anchor is resolved through the same
    catalog check a strategy symbol uses. A category, a private description,
    an unresolved symbol, or a class that conflicts with the request stays
    uncached. This does not search.
    """
    if request.relationship == "category" or (request.category_description or "").strip():
        return False
    anchors = [symbol.strip() for symbol in request.anchor_symbols if symbol.strip()]
    if not anchors:
        return False
    expected_class = request.asset_class_hint or "equity"
    from argus.agent_runtime.resolution import resolve_asset_candidate

    for index, anchor in enumerate(anchors):
        resolution = resolve_asset_candidate(
            anchor,
            field=f"asset_discovery.anchor_symbols[{index}]",
            source="llm_extraction",
            asset_class_hint=expected_class,
        )
        asset = resolution.asset
        if (
            resolution.status != "resolved"
            or asset is None
            or resolution.provenance.validated_by != "provider_catalog"
            or asset.asset_class != expected_class
        ):
            return False
    return True


async def find_assets_stage_result(
    *,
    request: AssetDiscoveryRequest | None,
    interpretation: StructuredInterpretation,
    decision: InterpretDecision | None,
    state: RunState,
    user: UserState,
) -> StageResult | None:
    """Run the find operation and attach the rail's typed instrumentation."""
    from argus.agent_runtime.discovery.composer import discovery_operation_result

    capability_class: CapabilityClass = (
        "peer_expansion"
        if request is not None and request.anchor_symbols
        else "screening"
    )
    language = (
        getattr(interpretation, "detected_user_language", None)
        or user.language_preference
        or "en"
    )
    effective_decision = decision or grounded.research_decision(
        interpretation, user, f"research_answer_{capability_class}"
    )
    packet_cache = None
    if request is not None and request.needs_current_facts:
        # Sync catalog lookups: off the loop, or one anchor stalls every stream.
        if await asyncio.to_thread(_public_anchor_search, request):
            packet_cache = SearchPacketCache
    result = await discovery_operation_result(
        decision=effective_decision,
        request=request,
        current_user_message=state.current_user_message,
        language=language,
        packet_cache=packet_cache,
        provider_admission=claim_current_research_attempt,
    )
    if result is None:
        return None
    result.stage_patch["research"] = grounded.build_research_sidecar(
        **_research_sidecar_inputs_for_find(
            stage_patch=result.stage_patch,
            request=request,
            capability_class=capability_class,
        )
    )
    return result


def _research_sidecar_inputs_for_find(
    *,
    stage_patch: dict[str, Any],
    request: AssetDiscoveryRequest | None,
    capability_class: CapabilityClass,
) -> dict[str, Any]:
    """One settlement contract: the find op meters like every other shape.

    The discovery sidecar keeps owning sources and candidate rows; this
    sidecar carries the capability class, the cache status, and the verified
    candidates as peers so a later confirmation card can offer them through
    the same transcript contract research answers use."""
    discovery = stage_patch.get("discovery")
    discovery = discovery if isinstance(discovery, dict) else {}
    usage = stage_patch.get("discovery_usage")
    usage = usage if isinstance(usage, dict) else {}
    candidates = [c for c in discovery.get("candidates") or [] if isinstance(c, dict)]
    peers = [
        {
            "symbol": str(c.get("symbol") or ""),
            "name": str(c.get("name") or c.get("symbol") or ""),
            "asset_class": str(c.get("asset_class") or "equity"),
        }
        for c in candidates
        if c.get("symbol")
    ]
    attempted = usage.get("search_attempted") is True
    cache_status = str(usage.get("cache_status") or ("miss" if attempted else "bypass"))
    subjects = (
        [
            {"symbol": symbol.strip().upper(), "name": symbol.strip().upper()}
            for symbol in request.anchor_symbols
            if symbol.strip()
        ]
        if request is not None
        else []
    )
    fallback_code = usage.get("fallback_code")
    return {
        "capability_class": capability_class,
        "shape": "find",
        # The discovery sidecar owns the rich source list; duplicating it
        # here would create a second rendering surface.
        "sources": [],
        "retrieved_at": str(
            discovery.get("retrieved_at") or datetime.now(timezone.utc).isoformat()
        ),
        "subjects": subjects,
        "peers": peers,
        "usage": {
            "invocations": 1 if attempted else 0,
            "latency_ms": usage.get("latency_ms"),
            "cost_usd": usage.get("cost_usd"),
            "cache_status": cache_status,
        },
        "period_of_interest": None,
        "category": request.category_description if request else None,
        "degraded_code": str(fallback_code) if fallback_code else None,
    }
