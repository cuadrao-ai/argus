"""Business pilot: receipts in, reviewed expenses out. Thin transport.

Default-off. Each person's Business records live in their own space (see
``argus.domain.business.scope``), apart from Personal. Rules live in
``argus.domain.business``; each fact stays with its existing owner.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Annotated, Any, Literal
from uuid import UUID

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
from loguru import logger

from argus.api.business import (
    BusinessContext,
    BusinessPerson,
    own_business_only,
    owner_only,
    require_business,
    require_business_document_write,
    require_business_person,
    require_business_surface,
    require_business_workspace,
)
from argus.api.business_drafts import (
    action_problem,
    expense_detail,
    expenses_with_receipts,
    overview_with_drafts,
    receipt_detail,
    receipt_summaries,
    receipt_summary,
    require_legacy_receipt_write,
    search_with_drafts,
    unread_backlog,
    updates_with_drafts,
    upload_recorder,
)
from argus.api.business_naming import require_business_name
from argus.api.business_schemas import (
    BusinessAccess,
    BusinessAccount,
    BusinessExpense,
    BusinessNamePrompt,
    BusinessNameTarget,
    BusinessNamingState,
    BusinessOverview,
    BusinessSearch,
    BusinessSpaceInfo,
    BusinessSpaces,
    BusinessWorkspace,
    ConfirmBody,
    CreateBusinessAccount,
    ExpenseDetail,
    ExpenseInput,
    ExpensePage,
    GiveBusinessAccess,
    ReceiptActivity,
    ReceiptActivityCounts,
    ReceiptDetail,
    ReceiptPage,
    ReceiptReadBody,
    ReceiptReadingBody,
    ReceiptReviewBody,
    ReceiptSummary,
    RenameBusinessSpace,
    SaveBusinessName,
    StartBusinessSpace,
    UpdatePage,
)
from argus.api.business_spaces import (
    accept_business_invites,
    business_access,
    business_spaces,
    space_missing_problem,
)
from argus.api.dependencies import problem
from argus.api.documents import (
    NO_STORE,
    dispatch_preparation,
    document_filename,
    document_problem,
    read_document_upload,
)
from argus.api.email_intake import arrived_by_email, email_receipt_flags
from argus.api.financial_accounts import domain_problem
from argus.api.ingestion import ingestion_hub
from argus.domain.business.access import AccessList, AccessStore, InvalidEmail
from argus.domain.business.actions import BusinessActions
from argus.domain.business.authority import ActionError
from argus.domain.business.service import BusinessError
from argus.domain.business.spaces import Space, default_space_name
from argus.domain.business.transactions import GrantImportStore
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
    responses={
        403: {
            "description": "`business_grant_not_live`: the chosen grant (`X-Business-Grant`) is missing, someone else's, revoked or expired; `business_permission_denied`: the live grant does not allow this."
        }
    },
)
_CONFLICTS = frozenset(
    {
        "receipt_not_prepared",
        "draft_not_prepared",
        "import_already_accepted",
        "import_accept_in_progress",
        "possible_duplicate",
    }
)


def _email_flagged(context: BusinessContext, receipts: list) -> list:  # noqa: ANN001
    """Receipts that arrived by email carry their deliveries; a grouped original
    is context for its attachment and loses prepare and enter."""

    flags = email_receipt_flags(context.scope.owner.space_id)
    if not flags:
        return receipts
    return [
        replace(
            receipt,
            channel="email"
            if arrived_by_email(receipt.draft.created_at, flags[receipt.id][2])
            else receipt.channel,
            email_delivery_ids=flags[receipt.id][0],
            email_original=flags[receipt.id][1],
        )
        if receipt.id in flags
        else receipt
        for receipt in receipts
    ]


def _refuse_email_original(
    request: Request, context: BusinessContext, receipt_id: str
) -> None:
    flags = email_receipt_flags(context.scope.owner.space_id)
    if receipt_id in flags and flags[receipt_id][1]:
        raise problem(
            request,
            status_code=409,
            code="email_original_not_a_receipt",
            title="Conflict",
            detail="This is the email itself. Its attachment is the receipt to review.",
            headers=NO_STORE,
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
    # The own Business only: a client's name comes from the listing.
    own_business_only(request, person.person_id)
    space = person.spaces.open_space(person.person_id)
    if space is None:
        raise space_missing_problem(request)
    return _space(space)


def _naming(space: Space) -> dict[str, Any]:
    return {
        **_space(space),
        "name_required": space.name_required,
        "name_prompt_seen": space.name_prompt_seen,
    }


@router.get("/space/name", response_model=BusinessNamingState)
def get_business_name(
    request: Request, person: Annotated[BusinessPerson, Depends(require_business_person)]
) -> dict[str, Any]:
    own_business_only(request, person.person_id)
    space = person.spaces.open_space(person.person_id)
    if space is None:
        raise space_missing_problem(request)
    return _naming(space)


@router.post("/space/name-prompt", response_model=BusinessNamePrompt)
def claim_business_name_prompt(
    request: Request,
    body: BusinessNameTarget,
    person: Annotated[BusinessPerson, Depends(require_business_person)],
) -> dict[str, Any]:
    own_business_only(request, person.person_id)
    space = person.spaces.open_space(person.person_id)
    if space is None or space.id != str(body.space_id):
        raise space_missing_problem(request)
    show = person.spaces.claim_naming_visit(person.person_id, str(body.space_id))
    current = person.spaces.open_space(person.person_id)
    if current is None or current.id != str(body.space_id):
        raise space_missing_problem(request)
    return {**_naming(current), "show_prompt": show and current.name_required}


@router.patch("/space/name", response_model=BusinessNamingState)
def save_business_name(
    request: Request,
    body: SaveBusinessName,
    person: Annotated[BusinessPerson, Depends(require_business_person)],
) -> dict[str, Any]:
    own_business_only(request, person.person_id)
    space = person.spaces.rename(person.person_id, body.name, str(body.space_id))
    if space is None:
        raise space_missing_problem(request)
    return _naming(space)


@router.get("/spaces", response_model=BusinessSpaces)
def list_spaces(
    request: Request,
    response: Response,
    person: BusinessPerson = Depends(require_business_person),  # noqa: B008
) -> dict[str, Any]:
    """Every Business the caller may enter through a live grant of theirs,
    their own first. Pending invites for the caller's confirmed email become
    grants first, so the read beside the first profile read already lists
    them. Names come from the spaces; the one-time access line is marked seen
    per grant, server side."""

    _no_store(response)
    access = _access_store(request)
    accept_business_invites(person.person_id)
    seen = access.seen_grants(person.person_id)
    return {
        "spaces": [
            {
                "space_id": found.space_id,
                "name": found.name
                or (person.spaces.get(found.space_id) or Space("", "")).name,
                "grant_id": found.grant_id,
                "role": found.role,
                "capabilities": list(found.capabilities),
                "access_seen": found.role == "owner" or found.grant_id in seen,
            }
            for found in access.spaces_for(person.person_id)
        ]
    }


@router.post("/spaces/{grant_id}/seen", status_code=204)
def mark_space_seen(
    request: Request,
    grant_id: str,
    person: BusinessPerson = Depends(require_business_person),  # noqa: B008
) -> Response:
    """The caller dismissed the "you now have access" line for one of their
    grants: one ledger row, once; a grant that is not theirs changes nothing."""

    _access_store(request).mark_seen(person.person_id, grant_id)
    return Response(status_code=204, headers=NO_STORE)


@router.post("/space", response_model=BusinessSpaceInfo, status_code=201)
def start_space(
    request: Request,
    response: Response,
    body: StartBusinessSpace,
    person: BusinessPerson = Depends(require_business_person),  # noqa: B008
) -> dict[str, Any]:
    """Idempotent: an existing space is returned unchanged, with 200.

    A new space is born with the owner's grant. An old space without one gets
    it here, once."""

    space, created = person.spaces.create(
        person.person_id, body.name or default_space_name(body.language)
    )
    _access_store(request).ensure_owner_grant(space.id, person.person_id)
    response.status_code = 201 if created else 200
    return _space(space)


def _access_store(request: Request) -> AccessStore:
    store = business_access()
    if store is None:
        raise problem(
            request,
            status_code=503,
            code="business_access_unavailable",
            title="Service Unavailable",
            detail="Business access is not available.",
            headers=NO_STORE,
        )
    return store


def _access(found: AccessList) -> dict[str, Any]:
    return {
        "grants": [
            {
                "id": grant.id,
                "email": grant.email,
                "display_name": grant.display_name,
                "capabilities": list(grant.capabilities),
                "created_at": grant.created_at,
                "owner": grant.owner,
            }
            for grant in found.grants
        ],
        "invites": [
            {
                "id": invite.id,
                "email": invite.email,
                "created_at": invite.created_at,
                "expires_at": invite.expires_at,
            }
            for invite in found.invites
        ],
    }


@router.get("/access", response_model=BusinessAccess)
def list_access(
    request: Request,
    response: Response,
    context: Annotated[BusinessContext, Depends(require_business_workspace)],
) -> dict[str, Any]:
    owner_only(request, context)
    """Who can act in the owner's Business: live grants and pending invites."""

    response.headers.update(NO_STORE)
    store = _access_store(request)
    store.ensure_owner_grant(context.scope.owner.space_id, context.scope.person_id)
    return _access(store.list(context.scope.owner.space_id, context.scope.person_id))


@router.post("/access", response_model=BusinessAccess, status_code=201)
def give_access(
    request: Request,
    response: Response,
    body: GiveBusinessAccess,
    context: Annotated[BusinessContext, Depends(require_business_workspace)],
) -> dict[str, Any]:
    """A read+prepare grant for a confirmed account, else a pending invite.

    The reply is the access list either way, so nothing about an unknown
    email is revealed beyond what the list shows. A replay answers 200."""
    owner_only(request, context)

    response.headers.update(NO_STORE)
    store = _access_store(request)
    space_id, owner_id = context.scope.owner.space_id, context.scope.person_id
    spaces = business_spaces()
    if spaces is None:
        raise space_missing_problem(request)
    require_business_name(request, spaces, space_id)
    store.ensure_owner_grant(space_id, owner_id)
    try:
        created, found = store.give(space_id, owner_id, body.email)
    except InvalidEmail:
        raise problem(
            request,
            status_code=422,
            code="invalid_email",
            title="Unprocessable Entity",
            detail="Enter one email address.",
            headers=NO_STORE,
        ) from None
    response.status_code = 201 if created else 200
    return _access(found)


@router.delete("/access/grants/{grant_id}", status_code=204)
def revoke_access_grant(
    grant_id: UUID,
    request: Request,
    context: Annotated[BusinessContext, Depends(require_business_workspace)],
) -> Response:
    owner_only(request, context)
    store = _access_store(request)
    result = store.revoke_grant(
        context.scope.owner.space_id, context.scope.person_id, str(grant_id)
    )
    if result == "own_grant":
        raise problem(
            request,
            status_code=409,
            code="owner_grant_required",
            title="Conflict",
            detail="The owner's own access cannot be removed.",
            headers=NO_STORE,
        )
    if result == "missing":
        raise problem(
            request,
            status_code=404,
            code="business_access_not_found",
            title="Not Found",
            detail="This access is not available.",
            headers=NO_STORE,
        )
    return Response(status_code=204, headers=NO_STORE)


@router.delete("/access/invites/{invite_id}", status_code=204)
def revoke_access_invite(
    invite_id: UUID,
    request: Request,
    context: Annotated[BusinessContext, Depends(require_business_workspace)],
) -> Response:
    owner_only(request, context)
    store = _access_store(request)
    if not store.revoke_invite(
        context.scope.owner.space_id, context.scope.person_id, str(invite_id)
    ):
        raise problem(
            request,
            status_code=404,
            code="business_access_not_found",
            title="Not Found",
            detail="This invite is not available.",
            headers=NO_STORE,
        )
    return Response(status_code=204, headers=NO_STORE)


@router.patch("/space", response_model=BusinessSpaceInfo)
def rename_space(
    request: Request,
    body: RenameBusinessSpace,
    person: BusinessPerson = Depends(require_business_person),  # noqa: B008
) -> dict[str, Any]:
    own_business_only(request, person.person_id)
    space = person.spaces.rename(person.person_id, body.name)
    if space is None:
        raise space_missing_problem(request)
    return _space(space)


@router.get("/workspace", response_model=BusinessWorkspace)
def get_workspace(
    context: Annotated[BusinessContext, Depends(require_business_workspace)],
) -> dict[str, Any]:
    # An old own space without the owner's grant gets it here, once, with one
    # ledger row; a client's Business is read as it is.
    store = business_access()
    if store is not None and context.scope.acting_as_owner:
        store.ensure_owner_grant(context.scope.owner.space_id, context.scope.person_id)
    workspace = context.service.workspace(context.scope)
    if not context.scope.acting_as_owner:
        # Business chat is the owner's: the client's shell shows no composer.
        workspace = {**workspace, "chat_available": False}
    return workspace


@router.post("/accounts", response_model=BusinessAccount, status_code=201)
def create_account(
    request: Request,
    response: Response,
    body: CreateBusinessAccount,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: BusinessContext = Depends(require_business),  # noqa: B008
) -> dict[str, Any]:
    owner_only(request, context)
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
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: BusinessContext = Depends(require_business_document_write),  # noqa: B008
) -> dict[str, Any]:
    """The receipt's identity is its bytes, so a retry returns the same receipt.
    The owner's stored receipt-reading setting decides whether it is read."""

    _required_idempotency_key(request, idempotency_key)
    media_type, content = await read_document_upload(request)
    try:
        receipt = await context.service.upload(
            context.scope,
            content=content,
            filename=document_filename(filename),
            media_type=media_type,
            consent=False,
            on_capture=upload_recorder(context, request),
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
        failure = _problem(request, error)
        # Match the existing receipt-source log path: the hosted sink keeps
        # message text. Domain codes are safe; never log source or error text.
        logger.warning(
            "receipt_upload_failed status={} code={} failure_mode={}",
            failure.status_code,
            error.code
            if isinstance(
                error,
                (
                    DocumentServiceError,
                    DocumentExtractionError,
                    BusinessError,
                    ReconcileError,
                ),
            )
            else "unknown",
            type(error).__name__,
        )
        raise failure from None
    return receipt_summary(context, receipt)


@router.get("/receipt-reading")
def receipt_reading(
    request: Request,
    language: Literal["en", "es-419"] = "en",
    context: Annotated[BusinessContext, Depends(require_business)] = None,
) -> dict:
    permission = context.service.documents.business_receipt_consent
    if permission is None:
        raise _problem(request, DocumentServiceError("business_preparation_unavailable"))
    return {
        **permission.status(
            context.scope.owner.space_id, context.scope.person_id, language
        ),
        "can_change": context.scope.acting_as_owner,
    }


@router.post("/receipt-reading")
async def set_receipt_reading(
    request: Request,
    body: ReceiptReadingBody,
    background_tasks: BackgroundTasks,
    context: Annotated[BusinessContext, Depends(require_business_document_write)] = None,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    owner_only(request, context)
    key = _required_idempotency_key(request, idempotency_key)
    permission = context.service.documents.business_receipt_consent
    if permission is None:
        raise _problem(request, DocumentServiceError("business_preparation_unavailable"))
    try:
        state = await run_in_threadpool(
            permission.set,
            context.scope.owner.space_id,
            context.scope.person_id,
            enabled=body.enabled,
            version=body.scope_version,
            disclosure_token=body.disclosure_token,
            language=body.language,
            idempotency_key=key,
        )
        if body.enabled and state["enabled"]:
            failure = None
            for receipt_id in await run_in_threadpool(unread_backlog, context):
                try:
                    await run_in_threadpool(
                        context.service.queue, context.scope, receipt_id
                    )
                    await dispatch_preparation(
                        context.service.documents,
                        context.scope.person_id,
                        receipt_id,
                        background_tasks,
                        scope=context.scope.owner,
                    )
                except DocumentServiceError as error:
                    await run_in_threadpool(
                        context.service.documents.release_queued,
                        user_id=context.scope.person_id,
                        connection_id=receipt_id,
                        scope=context.scope.owner,
                        code=error.code,
                    )
                    if error.retryable:
                        failure = error
            if failure is not None:
                raise failure
        return {**state, "can_change": True}
    except Exception as error:
        raise _problem(request, error) from None


@router.get("/receipt-activity", response_model=ReceiptActivityCounts)
def receipt_activity_counts(
    context: Annotated[BusinessContext, Depends(require_business)],
) -> dict:
    from argus.api.business_receipt_activity import counts

    return counts(context, receipt_summaries(context, "all"))


@router.post("/receipts/{receipt_id}/read", response_model=ReceiptActivity)
def mark_receipt_read(
    request: Request,
    receipt_id: str,
    body: ReceiptReadBody,
    context: Annotated[BusinessContext, Depends(require_business)] = None,
) -> dict:
    from argus.api.business_receipt_activity import project

    try:
        receipt = receipt_detail(
            context, context.service.receipt(context.scope, receipt_id)
        )
        return project(
            context, [receipt], acknowledge_id=receipt_id, cursor=body.completion_cursor
        )[0]["activity"]
    except Exception as error:
        raise _problem(request, error) from None


@router.get("/receipts", response_model=ReceiptPage)
def list_receipts(
    request: Request,
    view: Literal["inbox", "all"] = "inbox",
    context: BusinessContext = Depends(require_business),  # noqa: B008
) -> dict[str, Any]:
    try:
        from argus.api.business_receipt_activity import counts

        items = receipt_summaries(context, view)
        return {"items": items, "activity": counts(context, items)}
    except Exception as error:
        raise _problem(request, error) from None


@router.get("/receipts/{receipt_id}", response_model=ReceiptDetail)
def get_receipt(
    request: Request,
    receipt_id: str,
    context: BusinessContext = Depends(require_business),  # noqa: B008
) -> dict[str, Any]:
    try:
        [receipt] = _email_flagged(
            context, [context.service.receipt(context.scope, receipt_id)]
        )
        return receipt_detail(context, receipt)
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
        # The fields live in the message text: the hosted log sink keeps the
        # default format and drops keyword fields. Names and codes only, never
        # a URL, a token or a filename.
        failure = _problem(request, error)
        detail = failure.detail
        code = detail.get("code") if isinstance(detail, dict) else None
        logger.warning(
            f"receipt_source_failed receipt_id={receipt_id}"
            f" code={code or type(error).__name__} status={failure.status_code}"
        )
        raise failure from None
    logger.info(
        f"receipt_source_served receipt_id={receipt_id} media_type={media_type}"
        f" size_bytes={len(content)}"
    )
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
    # Sending a document to the AI provider is the owner's choice alone.
    owner_only(request, context)
    try:
        if consent != "true":
            raise DocumentServiceError("document_extraction_consent_required")
        _refuse_email_original(request, context, receipt_id)
        require_legacy_receipt_write(context, receipt_id)
        context.service.queue(context.scope, receipt_id)
        await dispatch_preparation(
            context.service.documents,
            context.scope.person_id,
            receipt_id,
            background_tasks,
            scope=context.scope.owner,
        )
        [receipt] = _email_flagged(
            context, [context.service.receipt(context.scope, receipt_id)]
        )
        return receipt_summary(context, receipt)
    except Exception as error:
        raise _problem(request, error) from None


@router.post(
    "/receipts/{receipt_id}/rebind",
    response_model=ReceiptDetail,
    responses={
        403: {
            "description": "`business_owner_required`: only the owner, as a person, may"
            " move a binding; `business_permission_denied` without prepare permission."
        },
        404: {
            "description": "`business_record_not_found`: no such receipt in this Business."
        },
        409: {
            "description": "`business_action_required`: the hosted bridge is not wired"
            " for this request."
        },
        422: {
            "description": "`business_preparation_binding_live`: the old grant still works;"
            " `business_preparation_binding_missing`: nothing is bound yet."
        },
    },
)
def rebind_receipt(
    request: Request,
    receipt_id: str,
    context: BusinessContext = Depends(require_business_document_write),  # noqa: B008
) -> dict[str, Any]:
    """Owner action: bind a receipt whose preparation grant is no longer live
    to the owner's current grant, with a ledger row. 409 while the old grant
    still works."""

    store = context.service.imports.store
    hub = ingestion_hub()
    pool = getattr(request.app.state, "financial_accounts_pool", None)
    if not isinstance(store, GrantImportStore) or hub is None or pool is None:
        raise _problem(request, BusinessError("business_action_required"))
    try:
        BusinessActions(pool, hub.sink).rebind_attachment_preparation(
            store.context, UUID(receipt_id)
        )
    except ActionError as error:
        raise action_problem(request, error.result) from None
    except ValueError:
        raise _problem(request, BusinessError("business_record_not_found")) from None
    return receipt_detail(context, context.service.receipt(context.scope, receipt_id))


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
        _refuse_email_original(request, context, receipt_id)
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
        _refuse_email_original(request, context, receipt_id)
        if getattr(request.app.state, "financial_accounts_pool", None) is not None:
            raise BusinessError("draft_not_prepared")
        return receipt_detail(
            context, context.service.confirm(context.scope, receipt_id, body.version, key)
        )
    except Exception as error:
        raise _problem(request, error) from None


def _period(request: Request, start: date, end: date | None) -> None:
    """A range runs forward; an omitted end means the server's today."""

    if end is not None and start > end:
        raise problem(
            request,
            status_code=422,
            code="period_reversed",
            title="Invalid period",
            detail="The period must start on or before its end.",
            headers=NO_STORE,
        )


@router.get("/expenses", response_model=ExpensePage)
def list_expenses(
    request: Request,
    start: date = Query(alias="from"),  # noqa: B008
    end: date | None = Query(default=None, alias="to"),  # noqa: B008
    context: BusinessContext = Depends(require_business),  # noqa: B008
) -> dict[str, Any]:
    _period(request, start, end)
    try:
        return {"items": expenses_with_receipts(context, start, end)}
    except Exception as error:
        raise _problem(request, error) from None


@router.get("/expenses/{expense_id}", response_model=ExpenseDetail)
def get_expense(
    request: Request,
    expense_id: str,
    context: BusinessContext = Depends(require_business),  # noqa: B008
) -> dict[str, Any]:
    try:
        return expense_detail(context, expense_id)
    except Exception as error:
        raise _problem(request, error) from None


@router.post("/expenses", response_model=BusinessExpense, status_code=201)
def record_expense(
    request: Request,
    body: ExpenseInput,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: BusinessContext = Depends(require_business),  # noqa: B008
) -> dict[str, Any]:
    owner_only(request, context)
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
        found = search_with_drafts(context, q, limit)
    except Exception as error:
        raise _problem(request, error) from None
    flags = email_receipt_flags(context.scope.owner.space_id)
    for item in found["receipts"]:
        if item["id"] in flags:
            if arrived_by_email(item["received_at"], flags[item["id"]][2]):
                item["channel"] = "email"
            item["email_delivery_ids"] = list(flags[item["id"]][0])
            item["email_original"] = flags[item["id"]][1]
    return found


@router.get("/overview", response_model=BusinessOverview)
def get_overview(
    request: Request,
    start: date = Query(alias="from"),  # noqa: B008
    end: date | None = Query(default=None, alias="to"),  # noqa: B008
    context: BusinessContext = Depends(require_business),  # noqa: B008
) -> dict[str, Any]:
    _period(request, start, end)
    try:
        return overview_with_drafts(context, start, end)
    except Exception as error:
        raise _problem(request, error) from None


@router.get("/updates", response_model=UpdatePage)
def list_updates(
    request: Request,
    context: BusinessContext = Depends(require_business),  # noqa: B008
) -> dict[str, Any]:
    try:
        return {"items": updates_with_drafts(context)}
    except Exception as error:
        raise _problem(request, error) from None
