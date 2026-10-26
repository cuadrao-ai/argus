"""Registros queries, complete answer exports, and private saved recipes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response
from psycopg import Error as PostgresError
from psycopg_pool import PoolTimeout

from argus.api.business import (
    BusinessPerson,
    MembershipRoute,
    require_business_person,
    require_business_surface,
)
from argus.api.business_drafts import DraftContext, action_problem, require_drafts
from argus.api.business_reporting_schemas import DeleteReportView, ExportReport
from argus.api.dependencies import problem
from argus.api.documents import NO_STORE
from argus.api.routers.business_export import ExportRoute
from argus.domain.business.authority import ActionError
from argus.domain.business.reporting_export import export_report
from argus.domain.business.reporting_preferences import ReportInput
from argus.domain.business.reporting_query import ReportAnswer
from argus.domain.business.reporting_store import read_report
from argus.domain.business.reporting_views import (
    CreateView,
    SavedView,
    UpdateView,
    delete_view,
    list_views,
    save_view,
)


class ReportingRoute(ExportRoute, MembershipRoute):
    """Existing private response and membership error boundaries."""


router = APIRouter(
    route_class=ReportingRoute, dependencies=[Depends(require_business_surface)]
)
Context = Annotated[DraftContext, Depends(require_drafts)]
Person = Annotated[BusinessPerson, Depends(require_business_person)]
Key = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)]
T = TypeVar("T")


def _run(request: Request, response: Response, operation: Callable[[], T]) -> T:
    response.headers.update(NO_STORE)
    if request.query_params:
        raise problem(
            request,
            status_code=422,
            code="validation_error",
            title="Validation Error",
            detail="No query parameters are accepted.",
            headers=NO_STORE,
        )
    try:
        return operation()
    except ActionError as error:
        raise action_problem(request, error.result) from None
    except (PostgresError, PoolTimeout):
        raise problem(
            request,
            status_code=503,
            code="business_reports_unavailable",
            title="Reports unavailable",
            detail="The authorized report is unavailable.",
            headers=NO_STORE,
        ) from None


@router.post("/reports/query", response_model=ReportAnswer)
def query_report(
    request: Request,
    response: Response,
    body: ReportInput,
    context: Context,
    person: Person,
) -> ReportAnswer:
    return _run(
        request,
        response,
        lambda: read_report(
            context.service.authority, context.for_space(request, person.spaces), body
        ),
    )


@router.post(
    "/reports/export",
    response_class=Response,
    responses={
        200: {
            "content": {"application/zip": {}},
            "description": "Complete filtered records, CSV, XLSX and scope manifest; originals excluded.",
        },
        409: {
            "description": "business_report_changed; explicitly refresh the query before retrying."
        },
    },
)
def download_report(
    request: Request,
    response: Response,
    body: ExportReport,
    context: Context,
    person: Person,
) -> Response:
    data = _run(
        request,
        response,
        lambda: export_report(
            context.service.authority,
            context.for_space(request, person.spaces),
            body.report,
            body.expected_fingerprint,
        ),
    )
    return Response(
        data,
        media_type="application/zip",
        headers={
            **NO_STORE,
            "Content-Disposition": 'attachment; filename="business-records.zip"',
        },
    )


@router.get("/report-views", response_model=tuple[SavedView, ...])
def get_views(
    request: Request, response: Response, context: Context, person: Person
) -> tuple[SavedView, ...]:
    return _run(
        request,
        response,
        lambda: list_views(
            context.service.authority, context.for_space(request, person.spaces)
        ),
    )


@router.post("/report-views", response_model=SavedView, status_code=201)
def create_view(
    request: Request,
    response: Response,
    body: CreateView,
    context: Context,
    person: Person,
    key: Key,
) -> SavedView:
    return _run(
        request,
        response,
        lambda: save_view(
            context.service.authority,
            context.for_space(request, person.spaces),
            body,
            key,
        ),
    )


@router.patch("/report-views/{view_id}", response_model=SavedView)
def update_view(
    request: Request,
    response: Response,
    view_id: UUID,
    body: UpdateView,
    context: Context,
    person: Person,
    key: Key,
) -> SavedView:
    return _run(
        request,
        response,
        lambda: save_view(
            context.service.authority,
            context.for_space(request, person.spaces),
            body,
            key,
            view_id,
        ),
    )


@router.delete("/report-views/{view_id}", status_code=204)
def remove_view(
    request: Request,
    response: Response,
    view_id: UUID,
    body: DeleteReportView,
    context: Context,
    person: Person,
    key: Key,
) -> Response:
    _run(
        request,
        response,
        lambda: delete_view(
            context.service.authority,
            context.for_space(request, person.spaces),
            view_id,
            body.expected_version,
            key,
        ),
    )
    return Response(status_code=204, headers=NO_STORE)
