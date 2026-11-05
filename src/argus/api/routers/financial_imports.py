"""Import review queue: inspect, resolve, merge, dismiss and record imports.

Thin transport over ``ReconciliationService``. Nothing here writes financial
activity except ``accept``, which records the person's reviewed request
through the existing money service.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, TypeVar

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from argus.api.dependencies import problem
from argus.api.financial_accounts import domain_problem
from argus.api.financial_imports_schemas import (
    AcceptBatchBody,
    AcceptBatchResponse,
    AcceptBody,
    ImportAcceptResponse,
    ImportEventListResponse,
    ImportEventResponse,
    ImportPreviewResponse,
    LinkActivityBody,
    MergeBody,
    PreviewBody,
    ResolveBody,
    VersionBody,
)
from argus.api.ingestion import IngestionContext, require_ingestion_context
from argus.domain.ingestion.reconcile.model import (
    EventNotFound,
    ReconcileError,
    StaleEvent,
)
from argus.domain.ingestion.reconcile.service import ReconciliationService
from argus.domain.owner_scope import PERSONAL

router = APIRouter(prefix="/financial-imports", tags=["financial-imports"])
T = TypeVar("T")
_CONFLICTS = frozenset(
    {
        "import_already_accepted",
        "import_accept_in_progress",
        "import_merge_two_records",
        "import_merge_same_source",
        "activity_already_linked",
    }
)
_STATES = {
    "open": ("open", "accepting"),
    "accepted": ("accepted",),
    "dismissed": ("dismissed",),
}


def _service(request: Request, context: IngestionContext) -> ReconciliationService:
    sink = context.hub.sink
    if not isinstance(sink, ReconciliationService):
        raise problem(
            request,
            status_code=404,
            code="financial_connections_unavailable",
            title="Not Found",
            detail="Financial connections are not available.",
        )
    return sink


def _call(request: Request, action: Callable[[], T]) -> T:
    try:
        return action()
    except Exception as error:
        raise _problem(request, error) from None


def _problem(request: Request, error: Exception) -> HTTPException:
    if isinstance(error, EventNotFound):
        return problem(
            request,
            status_code=404,
            code="financial_import_not_found",
            title="Not Found",
            detail="No such import.",
        )
    if isinstance(error, StaleEvent):
        return problem(
            request,
            status_code=409,
            code="stale_version",
            title="Stale Version",
            detail="This import changed since you last read it. Reload and try again.",
        )
    if isinstance(error, ReconcileError):
        return problem(
            request,
            status_code=409 if error.code in _CONFLICTS else 422,
            code=error.code,
            title=error.code.replace("_", " ").capitalize(),
            detail=error.detail,
        )
    return domain_problem(request, error)


@router.get("", response_model=ImportEventListResponse)
def list_imports(
    request: Request,
    state: Literal["open", "accepted", "dismissed"] = "open",
    context: IngestionContext = Depends(require_ingestion_context),  # noqa: B008
) -> dict[str, Any]:
    service = _service(request, context)
    return {
        "items": service.list(
            user_id=context.user_id, states=_STATES[state], scope=PERSONAL
        )
    }


@router.post("/accept-batch", response_model=AcceptBatchResponse)
def accept_import_batch(
    request: Request,
    body: AcceptBatchBody,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: IngestionContext = Depends(require_ingestion_context),  # noqa: B008
) -> dict[str, Any]:
    """Record the reviewed batch; anything with an open question is returned
    as ``needs_review`` and left untouched."""

    from argus.api.routers.financial_accounts import _required_idempotency_key

    service = _service(request, context)
    key = _required_idempotency_key(request, idempotency_key)
    items = [(item.event_id, item.version) for item in body.items]
    return _call(
        request,
        lambda: {
            "items": service.accept_batch(
                user_id=context.user_id, items=items, idempotency_key=key, scope=PERSONAL
            )
        },
    )


@router.get("/{event_id}", response_model=ImportEventResponse)
def get_import(
    request: Request,
    event_id: str,
    context: IngestionContext = Depends(require_ingestion_context),  # noqa: B008
) -> dict[str, Any]:
    service = _service(request, context)
    return _call(
        request,
        lambda: service.detail(
            user_id=context.user_id, event_id=event_id, scope=PERSONAL
        ),
    )


@router.patch("/{event_id}", response_model=ImportEventResponse)
def resolve_import(
    request: Request,
    event_id: str,
    body: ResolveBody,
    context: IngestionContext = Depends(require_ingestion_context),  # noqa: B008
) -> dict[str, Any]:
    service = _service(request, context)
    return _call(
        request,
        lambda: service.resolve(
            user_id=context.user_id,
            event_id=event_id,
            version=body.version,
            changes=body.changes,
            scope=PERSONAL,
        ),
    )


@router.post("/{event_id}/merge", response_model=ImportEventResponse)
def merge_import(
    request: Request,
    event_id: str,
    body: MergeBody,
    context: IngestionContext = Depends(require_ingestion_context),  # noqa: B008
) -> dict[str, Any]:
    service = _service(request, context)
    return _call(
        request,
        lambda: service.merge(
            user_id=context.user_id,
            event_id=event_id,
            into_event_id=body.into_event_id,
            version=body.version,
            into_version=body.into_version,
            scope=PERSONAL,
        ),
    )


@router.post("/{event_id}/link-activity", response_model=ImportEventResponse)
def link_import(
    request: Request,
    event_id: str,
    body: LinkActivityBody,
    context: IngestionContext = Depends(require_ingestion_context),  # noqa: B008
) -> dict[str, Any]:
    service = _service(request, context)
    return _call(
        request,
        lambda: service.link_activity(
            user_id=context.user_id,
            event_id=event_id,
            activity_id=body.activity_id,
            version=body.version,
            scope=PERSONAL,
        ),
    )


@router.post("/{event_id}/preview", response_model=ImportPreviewResponse)
def preview_import(
    request: Request,
    event_id: str,
    body: PreviewBody,
    context: IngestionContext = Depends(require_ingestion_context),  # noqa: B008
) -> dict[str, Any]:
    service = _service(request, context)
    return _call(
        request,
        lambda: service.preview(
            user_id=context.user_id,
            event_id=event_id,
            overrides=body.overrides,
            scope=PERSONAL,
        ),
    )


@router.post("/{event_id}/accept", response_model=ImportAcceptResponse)
def accept_import(
    request: Request,
    event_id: str,
    body: AcceptBody,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: IngestionContext = Depends(require_ingestion_context),  # noqa: B008
) -> dict[str, Any]:
    from argus.api.routers.financial_accounts import _required_idempotency_key

    service = _service(request, context)
    key = _required_idempotency_key(request, idempotency_key)
    return _call(
        request,
        lambda: service.accept(
            user_id=context.user_id,
            event_id=event_id,
            idempotency_key=key,
            version=body.version,
            request=body.request,
            scope=PERSONAL,
        ),
    )


# Registered last: the generic action path must not shadow the named ones.
@router.post("/{event_id}/{action}", response_model=ImportEventResponse)
def change_import(
    request: Request,
    event_id: str,
    action: Literal["dismiss", "reopen", "acknowledge"],
    body: VersionBody,
    context: IngestionContext = Depends(require_ingestion_context),  # noqa: B008
) -> dict[str, Any]:
    service = _service(request, context)
    method = getattr(service, action)
    return _call(
        request,
        lambda: method(
            user_id=context.user_id,
            event_id=event_id,
            version=body.version,
            scope=PERSONAL,
        ),
    )
