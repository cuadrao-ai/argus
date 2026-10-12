"""Canonical capability registry: the single source of derived capability truth.

The typed *data* lives in its existing homes — `strategy_capabilities.STRATEGY_CAPABILITIES`
(strategies, each carrying a typed `status`) and `indicators.EXECUTABLE_INDICATORS`
(indicator execution specs). This module is the one place every other allow-list derives
from, so the same truth feeds the runtime contract, the engine config, the API schema,
the save passthrough, discovery, and capability answers.

Spine guardrail: everything here is typed structured data and set membership over enums
the LLM emits (`strategy_type`, `indicator.key`). Nothing scans prose or LLM free-text.
See `docs/specs/private-alpha-next-p2.1a-capability-registry-impl.md`.
"""

from __future__ import annotations

from argus.domain.strategy_capabilities import STRATEGY_CAPABILITIES
from argus.domain.strategy_template_contract import (  # noqa: F401
    RegisteredStrategyTemplate,
)
from argus.domain.tool_declaration import ToolCatalog

# --- Strategy derivations -------------------------------------------------------------

# Every named strategy Argus recognizes, including draft-only templates. This is a
# derived view of STRATEGY_CAPABILITIES, not a second capability registry.
REGISTERED_STRATEGY_TEMPLATES: frozenset[str] = frozenset(STRATEGY_CAPABILITIES)


# User-facing templates that are reachable end-to-end (status == executable).
EXECUTABLE_TEMPLATES: frozenset[str] = frozenset(
    template
    for template, capability in STRATEGY_CAPABILITIES.items()
    if capability.status == "executable"
)

# Execution strategy types accepted by the runtime contract / confirm gate. Derived from
# the executable strategies' execution types (e.g. buy_the_dip + rsi_mean_reversion both
# map to indicator_threshold; moving_average_crossover maps to signal_strategy).
SUPPORTED_STRATEGY_TYPES: frozenset[str] = frozenset(
    capability.execution_strategy_type
    for capability in STRATEGY_CAPABILITIES.values()
    if capability.status == "executable" and capability.execution_strategy_type
)

# Templates accepted by engine config validation: the executable user-facing templates
# plus the generic `signal_strategy` execution template (an execution type the launch
# path uses directly, not a user-facing capability key).
ALLOWED_TEMPLATES: frozenset[str] = EXECUTABLE_TEMPLATES | {"signal_strategy"}


# --- Indicator derivations ------------------------------------------------------------

# Explicit, hand-maintained map of which supported, user-facing template consumes each
# executable indicator end-to-end. It is NOT auto-derived: RSI is consumed by
# rsi_mean_reversion's rsi-only `indicator` parameter, and SMA by moving_average_crossover
# (hardcoded in backtesting/signals.py). test_reachability_map_is_internally_consistent
# ties the RSI entry back to the rsi_mean_reversion parameter so the map cannot silently
# drift from the strategy definition. EMA/MACD/Bollinger compute but no named template
# consumes them (they remain usable inside a generic signal_strategy rule), so they stay
# draft — not executable — until a dedicated template exposes them.
INDICATOR_TEMPLATE_REACHABILITY: dict[str, str] = {
    "rsi": "rsi_mean_reversion",
    "sma": "moving_average_crossover",
}


def indicator_template(key: str) -> str | None:
    """The named supported template that consumes this indicator, if any (else None)."""
    return INDICATOR_TEMPLATE_REACHABILITY.get(key)


def get_tool_catalog(
    *, include_unavailable: bool = False, surface: str = "personal"
) -> ToolCatalog:
    """Assemble real declarations only when a catalog consumer asks for them.

    Each declaration lives beside its typed callable and card presenter. This
    is the sole catalog assembly point: schemas, execution, discovery and
    capability answers consume the same immutable declarations. Completion and
    receipt readers may resolve an already admitted binding with
    ``include_unavailable``; new calls always use the effective catalog.
    """
    if surface == "business":
        from argus.domain.business.tools import get_business_declarations

        return ToolCatalog(
            tuple(
                declaration
                for declaration in get_business_declarations()
                if surface in declaration.surfaces
            )
        )
    if surface != "personal":
        raise ValueError("Unknown tool surface")

    from argus.agent_runtime.research_tools import get_research_declarations
    from argus.agent_runtime.tools.registered_backtest import get_backtest_declaration
    from argus.domain.calculations import get_calculation_declarations
    from argus.domain.research.config import research_rail_enabled

    research = (
        get_research_declarations()
        if include_unavailable or research_rail_enabled()
        else ()
    )
    return ToolCatalog(
        tuple(
            declaration
            for declaration in (
                get_backtest_declaration(),
                *get_calculation_declarations(),
                *research,
            )
            if surface in declaration.surfaces
        )
    )
