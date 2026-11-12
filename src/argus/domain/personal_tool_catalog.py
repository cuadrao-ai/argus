from __future__ import annotations

from argus.domain.calculations import get_calculation_declarations
from argus.domain.tool_declaration import ToolCatalog


def personal_tool_catalog(*, include_unavailable: bool = False) -> ToolCatalog:
    del include_unavailable
    return ToolCatalog(
        tuple(
            declaration
            for declaration in get_calculation_declarations()
            if "personal" in declaration.surfaces
        )
    )
