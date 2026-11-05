"""A member's Business search memory routes. Mounted from the Business router.

Recents and opens belong to the signed-in member in the Business their live
grant names; another member, in this Business or another, never sees them.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from argus.api.business import BusinessContext, require_business
from argus.api.business_schemas import (
    OpenSearchResult,
    RecentSearch,
    RecentSearches,
    RememberSearch,
)
from argus.api.business_spaces import business_search_memory
from argus.api.dependencies import problem
from argus.api.documents import NO_STORE
from argus.domain.business.search_memory import SearchMemory

router = APIRouter(prefix="/search", tags=["business"])


def _memory(request: Request) -> SearchMemory:
    memory = business_search_memory()
    if memory is None:
        raise problem(
            request,
            status_code=503,
            code="business_unavailable",
            title="Service Unavailable",
            detail="Business search memory is not available.",
            headers=NO_STORE,
        )
    return memory


def _member(context: BusinessContext) -> tuple[str, str]:
    return (
        context.scope.owner.space_id,
        context.scope.actor_id or context.scope.person_id,
    )


@router.get("/recents", response_model=RecentSearches)
def recents(
    request: Request,
    context: Annotated[BusinessContext, Depends(require_business)],
) -> dict:
    return {
        "items": [asdict(item) for item in _memory(request).recents(*_member(context))]
    }


@router.post("/recents", response_model=RecentSearch, status_code=201)
def remember(
    request: Request,
    body: RememberSearch,
    context: Annotated[BusinessContext, Depends(require_business)],
) -> dict:
    return asdict(_memory(request).remember(*_member(context), body.q))


@router.delete("/recents/{recent_id}", status_code=204)
def forget(
    request: Request,
    recent_id: UUID,
    context: Annotated[BusinessContext, Depends(require_business)],
) -> Response:
    if not _memory(request).forget(*_member(context), str(recent_id)):
        raise problem(
            request,
            status_code=404,
            code="business_search_recent_not_found",
            title="Not Found",
            detail="This search is not in your recents.",
            headers=NO_STORE,
        )
    return Response(status_code=204, headers=NO_STORE)


@router.delete("/recents", status_code=204)
def forget_all(
    request: Request,
    context: Annotated[BusinessContext, Depends(require_business)],
) -> Response:
    _memory(request).forget_all(*_member(context))
    return Response(status_code=204, headers=NO_STORE)


@router.post("/opens", status_code=204)
def opened(
    request: Request,
    body: OpenSearchResult,
    context: Annotated[BusinessContext, Depends(require_business)],
) -> Response:
    _memory(request).open(*_member(context), body.kind, str(body.id))
    return Response(status_code=204, headers=NO_STORE)
