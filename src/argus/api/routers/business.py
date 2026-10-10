"""Business pilot: receipts in, reviewed expenses out. Thin transport.

Default-off. Each person's Business records live in their own space (see
``argus.domain.business.scope``), apart from Personal. Rules live in
``argus.domain.business``; each fact stays with its existing owner.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
)
from fastapi.concurrency import run_in_threadpool

from argus.api.business import (
    BusinessContext,
    BusinessPerson,
    require_business,
    require_business_document_write,
    require_business_person,
    require_business_surface,
)
from argus.api.business_drafts import (
    action_problem,
    receipt_detail,
    require_legacy_receipt_write,
)
from argus.api.business_schemas import (
    BusinessAccount,
    BusinessExpense,
    BusinessOverview,
    BusinessSearch,
    BusinessSpaceInfo,
    BusinessWorkspace,
    ConfirmBody,
    CreateBusinessAccount,
    ExpenseInput,
    ExpensePage,
    ReceiptDetail,
    ReceiptPage,
    ReceiptReviewBody,
    ReceiptSummary,
    RenameBusinessSpace,
    StartBusinessSpace,
    UpdatePage,
)
from argus.api.business_spaces import space_missing_problem
from argus.api.dependencies import problem
from argus.api.documents import (
    NO_STORE,
    dispatch_preparation,
    document_filename,
    document_problem,
    read_document_upload,
)
from argus.api.financial_accounts import domain_problem
from argus.domain.business.authority import ActionError
from argus.domain.business.service import BusinessError
from argus.domain.business.spaces import Space, default_space_name
from argus.domain.ingestion.connections import ConnectionNotFound
from argus.domain.ingestion.documents.config import SOURCE_MEDIA_TYPES
from argus.domain.ingestion.documents.models import DocumentExtractionError
from argus.domain.ingestion.documents.service import DocumentServiceError
from argus.domain.ingestion.reconcile.model import (
    EventNotFound,
    ReconcileError,
    StaleEvent,
)
from argus.domain.recording.errors import AccountNotFound, StaleVersion
from argus.domain.recording.schemas import CreateFinancialAccountRequest


def _required_idempotency_key(request: Request, raw: str | None) -> str:
    from argus.api.routers.financial_accounts import _required_idempotency_key

    return _required_idempotency_key(request, raw)


def _no_store(response: Response) -> None:
    response.headers.update(NO_STORE)


router = APIRouter(
    prefix="/business",
    tags=["business"],
    dependencies=[Depends(require_business_surface), Depends(_no_store)],
)
_CONFLICTS = frozenset(
    {
        "receipt_not_prepared",
        "draft_not_prepared",
        "import_already_accepted",
        "import_accept_in_progress",
    }
)


def _problem(request: Request, error: Exception) -> HTTPException:
    if isinstance(error, ActionError):
        return action_problem(request, error.result)
    if isinstance(error, (ConnectionNotFound, EventNotFound)):
        return problem(
            request,
            status_code=404,
            code="receipt_not_found",
            title="Not Found",
            detail="No such receipt.",
            headers=NO_STORE,
        )
    if isinstance(error, (StaleEvent, StaleVersion)):
        return problem(
            request,
            status_code=409,
            code="stale_version",
            title="Stale Version",
            detail="This receipt changed since you opened it. Reload and try again.",
            headers=NO_STORE,
        )
    if (
        isinstance(error, (BusinessError, ReconcileError))
        and error.code == "financial_account_not_found"
    ):
        # An account outside this space is not found, as on POST /expenses.
        return domain_problem(request, AccountNotFound())
    if isinstance(error, (BusinessError, ReconcileError)):
        return problem(
            request,
            status_code=409 if error.code in _CONFLICTS else 422,
            code=error.code,
            title=error.code.replace("_", " ").capitalize(),
            detail=getattr(error, "detail", error.code),
            headers=NO_STORE,
        )
    if isinstance(error, (DocumentServiceError, DocumentExtractionError)):
        return document_problem(request, error)
    return domain_problem(request, error)


def _space(space: Space) -> dict[str, Any]:
    return {"id": space.id, "name": space.name}


@router.get("/space", response_model=BusinessSpaceInfo)
def get_space(
    request: Request,
    person: BusinessPerson = Depends(require_business_person),  # noqa: B008
) -> dict[str, Any]:
    space = person.spaces.open_space(person.person_id)
    if space is None:
        raise space_missing_problem(request)
    return _space(space)


@router.post("/space", response_model=BusinessSpaceInfo, status_code=201)
def start_space(
    response: Response,
    body: StartBusinessSpace,
    person: BusinessPerson = Depends(require_business_person),  # noqa: B008
) -> dict[str, Any]:
    """Idempotent: an existing space is returned unchanged, with 200."""

    space, created = person.spaces.create(
        person.person_id, body.name or default_space_name(body.language)
    )
    response.status_code = 201 if created else 200
    return _space(space)


@router.patch("/space", response_model=BusinessSpaceInfo)
def rename_space(
    request: Request,
    body: RenameBusinessSpace,
    person: BusinessPerson = Depends(require_business_person),  # noqa: B008
) -> dict[str, Any]:
    space = person.spaces.rename(person.person_id, body.name)
    if space is None:
        raise space_missing_problem(request)
    return _space(space)


@router.get("/workspace", response_model=BusinessWorkspace)
def get_workspace(
    context: BusinessContext = Depends(require_business),  # noqa: B008
) -> dict[str, Any]:
    return context.service.workspace(context.scope)


@router.post("/accounts", response_model=BusinessAccount, status_code=201)
def create_account(
    request: Request,
    response: Response,
    body: CreateBusinessAccount,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: BusinessContext = Depends(require_business),  # noqa: B008
) -> dict[str, Any]:
    key = _required_idempotency_key(request, idempotency_key)
    try:
        account, created = context.service.create_account(
            context.scope,
            CreateFinancialAccountRequest(
                type=body.type, currency=body.currency, nickname=body.nickname
            ),
            key,
        )
    except Exception as error:
        raise _problem(request, error) from None
    response.status_code = 201 if created else 200
    return account


@router.post(
    "/receipts",
    response_model=ReceiptSummary,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                media: {"schema": {"type": "string", "format": "binary"}}
                for media in SOURCE_MEDIA_TYPES
            },
        }
    },
)
async def upload_receipt(
    request: Request,
    background_tasks: BackgroundTasks,
    filename: str | None = Header(default=None, alias="X-Document-Filename"),
    consent: str | None = Header(default=None, alias="X-Extraction-Consent"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: BusinessContext = Depends(require_business_document_write),  # noqa: B008
) -> dict[str, Any]:
    """The receipt's identity is its bytes, so a retry returns the same receipt."""

    _required_idempotency_key(request, idempotency_key)
    media_type, content = await read_document_upload(request)
    try:
        receipt = await context.service.upload(
            context.scope,
            content=content,
            filename=document_filename(filename),
            media_type=media_type,
            consent=consent == "true",
        )
        if receipt.status == "queued":
            await dispatch_preparation(
                context.service.documents,
                context.scope.person_id,
                receipt.id,
                background_tasks,
                scope=context.scope.owner,
            )
    except Exception as error:
        raise _problem(request, error) from None
    return receipt.summary()


@router.get("/receipts", response_model=ReceiptPage)
def list_receipts(
    request: Request,
    view: Literal["inbox", "all"] = "inbox",
    context: BusinessContext = Depends(require_business),  # noqa: B008
) -> dict[str, Any]:
    service = context.service
    try:
        receipts = (
            service.inbox(context.scope)
            if view == "inbox"
            else service.receipts(context.scope)
        )
    except Exception as error:
        raise _problem(request, error) from None
    return {"items": [receipt.summary() for receipt in receipts]}


@router.get("/receipts/{receipt_id}", response_model=ReceiptDetail)
def get_receipt(
    request: Request,
    receipt_id: str,
    context: BusinessContext = Depends(require_business),  # noqa: B008
) -> dict[str, Any]:
    try:
        return receipt_detail(context, context.service.receipt(context.scope, receipt_id))
    except Exception as error:
        raise _problem(request, error) from None


@router.get("/receipts/{receipt_id}/source")
def get_receipt_source(
    request: Request,
    receipt_id: str,
    context: BusinessContext = Depends(require_business),  # noqa: B008
) -> Response:
    try:
        media_type, content = context.service.source(context.scope, receipt_id)
    except Exception as error:
        raise _problem(request, error) from None
    return Response(
        content,
        media_type=media_type,
        headers={
            **NO_STORE,
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'attachment; filename="receipt.{SOURCE_MEDIA_TYPES[media_type]}"',
        },
    )


@router.post("/receipts/{receipt_id}/prepare", response_model=ReceiptSummary)
async def prepare_receipt(
    request: Request,
    receipt_id: str,
    background_tasks: BackgroundTasks,
    consent: str | None = Header(default=None, alias="X-Extraction-Consent"),
    context: BusinessContext = Depends(require_business_document_write),  # noqa: B008
) -> dict[str, Any]:
    try:
        if consent != "true":
            raise DocumentServiceError("document_extraction_consent_required")
        require_legacy_receipt_write(context, receipt_id)
        context.service.queue(context.scope, receipt_id)
        await dispatch_preparation(
            context.service.documents,
            context.scope.person_id,
            receipt_id,
            background_tasks,
            scope=context.scope.owner,
        )
        return context.service.receipt(context.scope, receipt_id).summary()
    except Exception as error:
        raise _problem(request, error) from None


@router.patch("/receipts/{receipt_id}/review", response_model=ReceiptDetail)
async def review_receipt(
    request: Request,
    receipt_id: str,
    body: ReceiptReviewBody,
    context: BusinessContext = Depends(require_business),  # noqa: B008
) -> dict[str, Any]:
    """A receipt nobody has read is entered by hand here, from version 0."""

    service, scope = context.service, context.scope
    try:
        require_legacy_receipt_write(context, receipt_id)
        version = await service.start_entry(
            scope, receipt_id, body.version, body.fields.get("account_id")
        )
        reviewed = await run_in_threadpool(
            service.review, scope, receipt_id, version, body.fields
        )
        return receipt_detail(context, reviewed)
    except Exception as error:
        raise _problem(request, error) from None


@router.post("/receipts/{receipt_id}/confirm", response_model=ReceiptDetail)
def confirm_receipt(
    request: Request,
    receipt_id: str,
    body: ConfirmBody,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: BusinessContext = Depends(require_business),  # noqa: B008
) -> dict[str, Any]:
    key = _required_idempotency_key(request, idempotency_key)
    try:
        if getattr(request.app.state, "financial_accounts_pool", None) is not None:
            raise BusinessError("draft_not_prepared")
        return receipt_detail(
            context, context.service.confirm(context.scope, receipt_id, body.version, key)
        )
    except Exception as error:
        raise _problem(request, error) from None


@router.get("/expenses", response_model=ExpensePage)
def list_expenses(
    request: Request,
    start: date = Query(alias="from"),  # noqa: B008
    end: date = Query(alias="to"),  # noqa: B008
    context: BusinessContext = Depends(require_business),  # noqa: B008
) -> dict[str, Any]:
    try:
        return {"items": context.service.expenses(context.scope, start, end)}
    except Exception as error:
        raise _problem(request, error) from None


@router.post("/expenses", response_model=BusinessExpense, status_code=201)
def record_expense(
    request: Request,
    body: ExpenseInput,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: BusinessContext = Depends(require_business),  # noqa: B008
) -> dict[str, Any]:
    key = _required_idempotency_key(request, idempotency_key)
    entered = {**body.model_dump(), "account_id": str(body.account_id)}
    try:
        return context.service.record_expense(context.scope, entered, key)
    except Exception as error:
        raise _problem(request, error) from None


@router.get("/search", response_model=BusinessSearch)
def search(
    request: Request,
    q: Annotated[str, Query(min_length=1, max_length=512)],
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
    context: BusinessContext = Depends(require_business),  # noqa: B008
) -> dict[str, Any]:
    try:
        return context.service.search(context.scope, q, limit)
    except Exception as error:
        raise _problem(request, error) from None


@router.get("/overview", response_model=BusinessOverview)
def get_overview(
    request: Request,
    start: date = Query(alias="from"),  # noqa: B008
    end: date = Query(alias="to"),  # noqa: B008
    context: BusinessContext = Depends(require_business),  # noqa: B008
) -> dict[str, Any]:
    try:
        return context.service.overview(context.scope, start, end)
    except Exception as error:
        raise _problem(request, error) from None


@router.get("/updates", response_model=UpdatePage)
def list_updates(
    request: Request,
    context: BusinessContext = Depends(require_business),  # noqa: B008
) -> dict[str, Any]:
    try:
        return {"items": context.service.updates(context.scope)}
    except Exception as error:
        raise _problem(request, error) from None
