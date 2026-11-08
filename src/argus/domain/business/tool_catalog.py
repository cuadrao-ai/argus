"""Business WhatsApp tool catalog assembly without the shared capability registry."""

from __future__ import annotations

from argus.domain.business.tools import get_business_declarations
from argus.domain.tool_declaration import ToolCatalog


def get_business_tool_catalog() -> ToolCatalog:
    return ToolCatalog(
        tuple(
            declaration
            for declaration in get_business_declarations()
            if "business" in declaration.surfaces
        )
    )
