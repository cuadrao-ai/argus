from __future__ import annotations

from argus.agent_runtime.research_tools import get_research_declarations
from argus.agent_runtime.tools.registered_backtest import get_backtest_declaration
from argus.domain.calculations import get_calculation_declarations
from argus.domain.research.config import research_rail_enabled
from argus.domain.tool_declaration import ToolCatalog


def personal_tool_catalog(*, include_unavailable: bool = False) -> ToolCatalog:
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
            if "personal" in declaration.surfaces
        )
    )
