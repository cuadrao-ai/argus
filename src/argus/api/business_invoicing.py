"""Whether Facturación is offered: one answer for the workspace read and every
invoicing route."""

from __future__ import annotations

from fastapi import Request

from argus.api.fiscal_operations import fiscal_service
from argus.domain.business.invoicing.config import Settings


def invoicing_available(request: Request) -> bool:
    """True only while ``CUADRAO_BUSINESS_INVOICING_ENABLED`` is on and the
    fiscal provider is wired in this process, so a missing credential offers
    nothing rather than a broken screen."""
    return Settings().enabled and fiscal_service(request) is not None
