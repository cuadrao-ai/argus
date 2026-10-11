from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from psycopg import Error as PostgresError
from psycopg_pool import PoolTimeout
from pydantic import BeforeValidator

from argus.api.business import BusinessPerson, require_business_person
from argus.api.business_drafts import DraftContext, action_problem, require_drafts
from argus.api.business_spaces import space_missing_problem
from argus.api.dependencies import problem
from argus.api.documents import NO_STORE, require_saved_documents
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.export import ExportLimit, ExportPeriod, export_package
from argus.domain.business.scope import resolve_business_scope
from argus.domain.ingestion.documents.service import DocumentsService


class ExportRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def no_store(request: Request):
            try:
                response = await handler(request)
            except RequestValidationError as error:
                validation = request.app.exception_handlers.get(
                    RequestValidationError, request_validation_exception_handler
                )
                response = await validation(request, error)
            except HTTPException as error:
                error.headers = {**(error.headers or {}), **NO_STORE}
                raise
            response.headers.update(NO_STORE)
            return response

        return no_store


router = APIRouter(prefix="/business/exports", tags=["business"], route_class=ExportRoute)


def _calendar_date(value):
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError("Use YYYY-MM-DD")
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("Use YYYY-MM-DD")
    return parsed


CalendarDate = Annotated[date, BeforeValidator(_calendar_date)]


@router.get(
    "",
    response_class=Response,
    responses={
        200: {
            "content": {
                "application/zip": {"schema": {"type": "string", "format": "binary"}}
            }
        },
        403: {"description": "The live grant does not permit reading this Business."},
        404: {"description": "The Business or canonical draft anchor is unavailable."},
        413: {
            "description": "A bounded export collection, cell or archive limit was exceeded."
        },
    },
)
def download_export(
    request: Request,
    start: Annotated[CalendarDate, Query()],
    end: Annotated[CalendarDate, Query()],
    context: Annotated[DraftContext, Depends(require_drafts)],
    person: Annotated[BusinessPerson, Depends(require_business_person)],
    documents: Annotated[DocumentsService, Depends(require_saved_documents)],
    draft_id: Annotated[UUID | None, Query()] = None,
):
    if any(
        key not in {"start", "end", "draft_id"}
        or len(request.query_params.getlist(key)) != 1
        for key in request.query_params
    ):
        raise problem(
            request,
            status_code=422,
            code="validation_error",
            title="Validation Error",
            detail="Only start, end and an optional draft_id are accepted.",
            headers=NO_STORE,
        )
    try:
        period = ExportPeriod(start, end)
    except ValueError as error:
        raise problem(
            request,
            status_code=422,
            code=str(error),
            title="Invalid export period",
            detail=str(error),
            headers=NO_STORE,
        ) from None
    try:
        if draft_id is not None:
            actor = context.service.context_for_draft(context.actor_id, draft_id)
        else:
            scope = resolve_business_scope(person.spaces, person.person_id)
            if scope is None:
                raise space_missing_problem(request)
            actor = context.service.resolve_actor(
                TrustedActor(
                    actor_id=context.actor_id,
                    actor_kind="member",
                    space_id=scope.owner.space_id,
                )
            )
        objects = getattr(documents.store, "objects", None)
        if objects is None:
            raise problem(
                request,
                status_code=503,
                code="business_export_unavailable",
                title="Export unavailable",
                detail="Original source storage is unavailable.",
                headers=NO_STORE,
            )
        content = export_package(context.service.authority, actor, period, objects)
    except ActionError as error:
        raise action_problem(request, error.result) from None
    except ExportLimit as error:
        raise problem(
            request,
            status_code=413,
            code=str(error),
            title="Export limit exceeded",
            detail=str(error),
            headers=NO_STORE,
        ) from None
    except (PostgresError, PoolTimeout):
        raise problem(
            request,
            status_code=503,
            code="business_export_unavailable",
            title="Export unavailable",
            detail="The authorized export snapshot is unavailable.",
            headers=NO_STORE,
        ) from None
    return Response(
        content,
        media_type="application/zip",
        headers={
            **NO_STORE,
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'attachment; filename="business-export-{start}-{end}.zip"',
        },
    )
