"""Whether Facturación is offered: one answer for the workspace read and every
invoicing route."""

from __future__ import annotations

from fastapi import HTTPException, Request, Response

from argus.api.documents import NO_STORE
from argus.api.fiscal_operations import fiscal_service
from argus.domain.business.invoicing.config import Settings


def invoicing_available(request: Request) -> bool:
    """True only while ``CUADRAO_BUSINESS_INVOICING_ENABLED`` is on and the
    fiscal provider is wired in this process, so a missing credential offers
    nothing rather than a broken screen."""
    return Settings().enabled and fiscal_service(request) is not None


def require_invoicing(request: Request, response: Response) -> None:
    """The one refusal every invoicing route, and every fiscal route on an
    invoice's operation, answers while Facturación is off."""
    response.headers.update(NO_STORE)
    if not invoicing_available(request):
        raise HTTPException(
            404, detail="business_invoicing_unavailable", headers=NO_STORE
        )
