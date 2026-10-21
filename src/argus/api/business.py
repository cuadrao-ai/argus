from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request

from argus.api.business_spaces import (
    business_access,
    business_spaces,
    space_missing_problem,
)
from argus.api.dependencies import problem
from argus.api.documents import (
    NO_STORE,
    DocumentContext,
    require_document_context,
    require_saved_documents,
)
from argus.api.ingestion import IngestionContext, require_ingestion_context
from argus.api.whatsapp import whatsapp_runtime
from argus.domain.business.config import business_pilot_enabled
from argus.domain.business.contracts.dossier import RecordContext
from argus.domain.business.scope import BusinessScope, resolve_business_scope
from argus.domain.business.service import BusinessService
from argus.domain.business.spaces import SpaceStore
from argus.domain.ingestion.documents.service import DocumentsService
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.ingestion.reconcile.service import ReconciliationService
from argus.domain.owner_scope import BusinessSpace

#: The caller's choice among their own grants. The server takes the Business
#: from that grant row, after proving on every request that it is the
#: caller's and live; no header means the caller's own Business.
GRANT_HEADER = "X-Business-Grant"


def unavailable_problem(request: Request) -> HTTPException:
    return problem(
        request,
        status_code=404,
        code="business_unavailable",
        title="Not Found",
        detail="Business is not available.",
        headers=NO_STORE,
    )


def require_business_surface(
    request: Request,
    grant: Annotated[
        str | None,
        Header(
            alias=GRANT_HEADER,
            description="The caller's own live grant on the Business to work in; absent for the own Business. A missing, foreign, revoked or expired grant answers 403 business_grant_not_live.",
        ),
    ] = None,
) -> None:
    # The header is read where the scope is resolved (chosen_scope); declared
    # here so every Business route documents it.
    del grant
    if not business_pilot_enabled():
        raise unavailable_problem(request)


def grant_not_live_problem(request: Request) -> HTTPException:
    return problem(
        request,
        status_code=403,
        code="business_grant_not_live",
        title="Forbidden",
        detail="This access is no longer live.",
        headers=NO_STORE,
    )


def chosen_scope(request: Request, user_id: str) -> BusinessScope | None:
    """The Business named by the caller's chosen grant, or None without one.
    A grant that is not the caller's, revoked or expired is refused the same
    way, so the header reveals nothing about any Business."""

    grant_id = (request.headers.get(GRANT_HEADER) or "").strip()
    if not grant_id:
        return None
    access = business_access()
    if access is None:
        raise unavailable_problem(request)
    found = access.granted(user_id, grant_id)
    if found is None:
        raise grant_not_live_problem(request)
    spaces = business_spaces()
    space = spaces.get(found.space_id) if spaces is not None else None
    if space is None:
        raise space_missing_problem(request)
    return BusinessScope(
        person_id=found.owner_id,
        owner=BusinessSpace(found.space_id),
        actor_id=user_id,
        grant_id=found.grant_id,
        role=found.role,  # type: ignore[arg-type]
        country=space.country,
        currency=space.currency,
    )


def owner_required_problem(request: Request) -> HTTPException:
    return problem(
        request,
        status_code=403,
        code="business_permission_denied",
        title="Forbidden",
        detail="Only the Business owner can do this.",
        headers=NO_STORE,
    )


def owner_only(request: Request, context: BusinessContext) -> None:
    """A route that only the Business owner may call; a grantee is told so."""

    if not context.scope.acting_as_owner:
        raise owner_required_problem(request)


def own_business_only(request: Request, user_id: str) -> None:
    """A route about the caller's own Business: under a chosen client grant it
    is refused (a dead grant is refused first, the same way as everywhere)."""

    scope = chosen_scope(request, user_id)
    if scope is not None and not scope.acting_as_owner:
        raise owner_required_problem(request)


def working_scope(
    request: Request, spaces: SpaceStore, user_id: str
) -> BusinessScope | None:
    """The Business the caller is working in: the chosen grant's, else their own."""

    return chosen_scope(request, user_id) or resolve_business_scope(spaces, user_id)


@dataclass(frozen=True)
class BusinessPerson:
    person_id: str
    spaces: SpaceStore


def require_business_person(
    request: Request,
    _surface: None = Depends(require_business_surface),  # noqa: B008
    documents: DocumentsService = Depends(require_saved_documents),  # noqa: B008
    context: IngestionContext = Depends(require_ingestion_context),  # noqa: B008
) -> BusinessPerson:
    """The signed-in person and the space store, for the space routes."""

    spaces = business_spaces()
    if spaces is None or documents.hub is not context.hub:
        raise unavailable_problem(request)
    return BusinessPerson(context.user_id, spaces)


@dataclass(frozen=True)
class BusinessContext:
    scope: BusinessScope
    service: BusinessService
    record_context: RecordContext | None = None


def _captured(person_id: str) -> frozenset[str]:
    runtime = whatsapp_runtime()
    if runtime is None:
        return frozenset()
    return runtime.intake.store.captured_connections(destination_owner_id=person_id)


def _context(
    request: Request, documents: DocumentsService, hub: IngestionHub, user_id: str
) -> BusinessContext:
    spaces = business_spaces()
    if (
        not isinstance(hub.sink, ReconciliationService)
        or spaces is None
        or documents.hub is not hub
    ):
        raise unavailable_problem(request)
    # With no header the own Business is the only one in scope: a person with no
    # own Business and no chosen grant has nothing in scope, record ids included.
    scope = working_scope(request, spaces, user_id)
    if scope is None:
        raise space_missing_problem(request)
    from argus.api.business_drafts import scoped_legacy

    return scoped_legacy(request, documents, hub, user_id, scope)


def require_business(
    request: Request,
    _surface: None = Depends(require_business_surface),  # noqa: B008
    documents: DocumentsService = Depends(require_saved_documents),  # noqa: B008
    context: IngestionContext = Depends(require_ingestion_context),  # noqa: B008
) -> BusinessContext:
    return _context(request, documents, context.hub, context.user_id)


def require_business_workspace(
    request: Request,
    person: Annotated[BusinessPerson, Depends(require_business_person)],
    documents: Annotated[DocumentsService, Depends(require_saved_documents)],
    context: Annotated[IngestionContext, Depends(require_ingestion_context)],
) -> BusinessContext:
    if not isinstance(context.hub.sink, ReconciliationService):
        raise unavailable_problem(request)
    scope = working_scope(request, person.spaces, person.person_id)
    if scope is None:
        raise space_missing_problem(request)
    return BusinessContext(scope, BusinessService(documents, context.hub.sink, _captured))


def require_business_document_write(
    request: Request,
    _surface: None = Depends(require_business_surface),  # noqa: B008
    context: DocumentContext = Depends(require_document_context),  # noqa: B008
) -> BusinessContext:
    return _context(request, context.service, context.service.hub, context.user_id)
