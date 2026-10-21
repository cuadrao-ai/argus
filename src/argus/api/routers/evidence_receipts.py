"""Owner routes for public evidence receipts: create, list, revoke.

Every route here is behind the default-off sharing flag and answers 404 while it
is off, so the endpoints do not exist for a client until the founder turns them
on.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from loguru import logger

from argus.api.conversation_surface import (
    require_personal_conversation,
    require_personal_evidence_artifact,
)
from argus.api.dependencies import current_user, problem, require_account_capability
from argus.api.guest_access import client_identity
from argus.api.pagination import decode_cursor, encode_cursor, invalid_cursor_problem
from argus.api.public_excerpt_schemas import (
    PublicExcerptCandidates,
    PublicExcerptCreate,
    PublicExcerptCreateResponse,
    PublicExcerptListResponse,
    PublicExcerptPreview,
    PublicExcerptRevokeResponse,
    PublicExcerptSelection,
    PublicExcerptSelectionCreate,
)
from argus.api.public_excerpts import (
    RECEIPT_CREATE_DAILY_LIMIT,
    RECEIPT_CREATE_DAILY_WINDOW_SECONDS,
    RECEIPT_CREATE_LIMIT,
    RECEIPT_CREATE_WINDOW_SECONDS,
    EvidenceReceiptSourceMissingError,
    create_receipt_for_artifact,
    create_receipt_for_messages,
    preview_receipt_for_messages,
    public_excerpt_repository,
    receipt_candidates,
    require_evidence_receipt_sharing_enabled,
)
from argus.api.rate_limits import SlidingWindowLimiter
from argus.api.schemas import User
from argus.domain.public_excerpts import (
    PublicExcerptOwnerNoteError,
    PublicExcerptSanitizationError,
    PublicExcerptSourceError,
    normalize_owner_note,
    snapshot_list_item,
)
from argus.domain.supabase_public_excerpts import (
    DEFAULT_OWNER_PAGE_SIZE,
    MAX_OWNER_PAGE_SIZE,
)
from argus.observability.product_events import capture_product_event

router = APIRouter(prefix="/api/v1", tags=["evidence-receipts"])

_RECEIPT_CREATE_LIMITER = SlidingWindowLimiter()


def reset_receipt_create_limiter_for_tests() -> None:
    _RECEIPT_CREATE_LIMITER.reset()


def _require_uuid(value: str, request: Request) -> str:
    """Reject an id that is not a uuid before it can reach a query.

    These ids land in filters on uuid columns. An unvalidated one is a cast error
    surfacing as a 500 at best, so the shape is checked here and the caller hears
    the ordinary not-found answer.
    """
    try:
        return str(UUID(value))
    except (ValueError, AttributeError, TypeError):
        raise problem(
            request,
            status_code=404,
            code="not_found",
            title="Not Found",
            detail="That result is not available.",
        ) from None


def _decode_receipt_cursor(
    cursor: str | None, request: Request
) -> tuple[str, str] | None:
    """Fully validate a cursor before any part of it reaches a query.

    The cursor is opaque and client-supplied, and both halves are interpolated into
    a PostgREST filter string on the way to a keyset comparison. A timestamp that
    parses is not enough: the item id half reaches an ``id.lt`` filter on a uuid
    column, so a fabricated cursor could produce a cast error, and a value carrying
    filter punctuation could alter the filter itself. Both halves are therefore
    parsed and re-serialised from their parsed forms, so what reaches the query is
    canonical rather than whatever arrived.
    """
    if not cursor:
        return None
    raw_created_at, raw_id = decode_cursor(cursor, request)
    try:
        created_at = datetime.fromisoformat(raw_created_at)
        cursor_id = UUID(raw_id)
    except (ValueError, AttributeError, TypeError):
        raise invalid_cursor_problem(request) from None
    return created_at.isoformat(), str(cursor_id)


def _enforce_create_rate_limit(request: Request, *, user: User) -> None:
    """Rate-limit receipt creation, honouring the documented admin bypass.

    `docs/API_CONTRACT.md` says backend quota and rate-limit restrictions are
    bypassed for `profiles.is_admin`, and the mock developer account is an admin, so
    an unconditional limiter also blocked internal QA of this surface. The limit
    still applies to every ordinary account, which is who section 7.4 is about.
    """
    if user.is_admin:
        return
    visitor = client_identity(request)
    for limit, window in (
        (RECEIPT_CREATE_LIMIT, RECEIPT_CREATE_WINDOW_SECONDS),
        (RECEIPT_CREATE_DAILY_LIMIT, RECEIPT_CREATE_DAILY_WINDOW_SECONDS),
    ):
        retry_after = _RECEIPT_CREATE_LIMITER.record_or_retry_after(
            keys=(
                f"receipt-create:user:{user.id}:{window}",
                f"receipt-create:visitor:{visitor}:{window}",
            ),
            limit=limit,
            window_seconds=window,
        )
        if retry_after is None:
            continue
        raise problem(
            request,
            status_code=429,
            code="too_many_requests",
            title="Too Many Requests",
            detail="You have created a lot of links recently. Try again shortly.",
            headers={"Retry-After": str(retry_after)},
        )


@router.post(
    "/evidence-artifacts/{artifact_id}/public-excerpt",
    response_model=PublicExcerptCreateResponse,
    dependencies=[Depends(require_personal_evidence_artifact)],
)
def create_public_excerpt(
    artifact_id: str,
    payload: PublicExcerptCreate,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
) -> PublicExcerptCreateResponse:
    require_evidence_receipt_sharing_enabled()
    require_account_capability(
        request,
        "can_save_decision",
        detail="Sign in to share a result.",
        reason="share_result",
    )
    owned_artifact_id = _require_uuid(artifact_id, request)
    try:
        owner_note = normalize_owner_note(payload.owner_note)
    except PublicExcerptOwnerNoteError as exc:
        raise problem(
            request,
            status_code=422,
            code="receipt_note_rejected",
            title="Note Rejected",
            detail=str(exc),
        ) from exc
    _enforce_create_rate_limit(request, user=user)
    try:
        snapshot, created = create_receipt_for_artifact(
            user=user,
            artifact_id=owned_artifact_id,
            owner_note=owner_note,
        )
    except EvidenceReceiptSourceMissingError as exc:
        raise problem(
            request,
            status_code=404,
            code="not_found",
            title="Not Found",
            detail="That result is not available.",
        ) from exc
    except PublicExcerptSourceError as exc:
        raise _selection_error(request, exc) from exc
    except PublicExcerptSanitizationError as exc:
        # Fail closed. A payload that cannot be proven clean is never published.
        logger.error("Receipt payload failed the never-expose audit", error=str(exc))
        raise problem(
            request,
            status_code=500,
            code="receipt_sanitization_failed",
            title="Could Not Share",
            detail="Argus could not safely build that link. Please try again later.",
        ) from exc
    if created:
        # Only a real insert counts. Sharing the same result again returns the
        # existing link, and counting that would inflate the funnel's creation
        # stage with retries and reloads.
        capture_product_event(
            "receipt_created",
            user_id=user.id,
            status="created",
            attributes={
                "receipt_digest": snapshot.payload_digest[:16],
                "kind": snapshot.kind,
            },
        )
    return PublicExcerptCreateResponse(receipt=snapshot_list_item(snapshot))


@router.get("/public-excerpts", response_model=PublicExcerptListResponse)
def list_public_excerpts(
    request: Request,
    limit: int = Query(default=DEFAULT_OWNER_PAGE_SIZE, ge=1, le=MAX_OWNER_PAGE_SIZE),
    cursor: str | None = None,
    user: User = Depends(current_user),  # noqa: B008
) -> PublicExcerptListResponse:
    """The owner's receipts, newest first, paginated.

    Paginated rather than capped: Data Controls is the only place an owner can find
    a snapshot id to revoke, so a row hidden behind a cap would be a public page
    they cannot take down.
    """
    require_evidence_receipt_sharing_enabled()
    require_account_capability(
        request,
        "can_save_decision",
        detail="Sign in to review shared links.",
        reason="share_result",
    )
    before = _decode_receipt_cursor(cursor, request)

    # One extra row answers "is there another page" without a second query.
    page = public_excerpt_repository().list_public_excerpt_snapshots(
        owner_id=user.id,
        limit=limit + 1,
        before=before,
    )
    has_more = len(page) > limit
    snapshots = page[:limit]
    next_cursor = (
        encode_cursor(snapshots[-1].created_at.isoformat(), snapshots[-1].id)
        if has_more and snapshots
        else None
    )
    return PublicExcerptListResponse(
        items=[snapshot_list_item(snapshot) for snapshot in snapshots],
        next_cursor=next_cursor,
    )


@router.delete(
    "/public-excerpts/{snapshot_id}",
    response_model=PublicExcerptRevokeResponse,
)
def revoke_public_excerpt(
    snapshot_id: str,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
) -> PublicExcerptRevokeResponse:
    require_evidence_receipt_sharing_enabled()
    require_account_capability(
        request,
        "can_save_decision",
        detail="Sign in to manage shared links.",
        reason="share_result",
    )
    snapshot, _revoked_now = public_excerpt_repository().revoke_public_excerpt_snapshot(
        owner_id=user.id,
        snapshot_id=_require_uuid(snapshot_id, request),
    )
    if snapshot is None:
        raise problem(
            request,
            status_code=404,
            code="not_found",
            title="Not Found",
            detail="That link is not available.",
        )
    return PublicExcerptRevokeResponse(receipt=snapshot_list_item(snapshot))


def _selection_error(request: Request, error: Exception) -> Exception:
    if isinstance(error, EvidenceReceiptSourceMissingError):
        return problem(
            request,
            status_code=404,
            code="not_found",
            title="Not Found",
            detail="That conversation is not available.",
        )
    assert isinstance(error, PublicExcerptSourceError)
    return problem(
        request,
        status_code=409 if error.reason == "preview_changed" else 422,
        code="receipt_preview_changed"
        if error.reason == "preview_changed"
        else "receipt_source_unsupported",
        title="Not Shareable",
        detail="That selection cannot be shared.",
        context={"reason": error.reason, "field": error.field},
    )


def _selection_owner(request: Request, conversation_id: str) -> str:
    require_evidence_receipt_sharing_enabled()
    require_account_capability(
        request,
        "can_save_decision",
        detail="Sign in to share an answer.",
        reason="share_result",
    )
    return _require_uuid(conversation_id, request)


@router.get(
    "/conversations/{conversation_id}/public-excerpt-candidates",
    response_model=PublicExcerptCandidates,
    dependencies=[Depends(require_personal_conversation)],
)
def public_excerpt_candidates(
    conversation_id: str, request: Request, user: Annotated[User, Depends(current_user)]
) -> PublicExcerptCandidates:  # noqa: B008
    owned_id = _selection_owner(request, conversation_id)
    try:
        return receipt_candidates(user=user, conversation_id=owned_id)
    except (EvidenceReceiptSourceMissingError, PublicExcerptSourceError) as error:
        raise _selection_error(request, error) from error


@router.post(
    "/conversations/{conversation_id}/public-excerpt-preview",
    response_model=PublicExcerptPreview,
    dependencies=[Depends(require_personal_conversation)],
)
def preview_public_excerpt(
    conversation_id: str,
    payload: PublicExcerptSelection,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> PublicExcerptPreview:  # noqa: B008
    owned_id = _selection_owner(request, conversation_id)
    try:
        return preview_receipt_for_messages(
            user=user,
            conversation_id=owned_id,
            message_ids=[str(value) for value in payload.message_ids],
            owner_note=payload.owner_note,
        )
    except (EvidenceReceiptSourceMissingError, PublicExcerptSourceError) as error:
        raise _selection_error(request, error) from error


@router.post(
    "/conversations/{conversation_id}/public-excerpt",
    response_model=PublicExcerptCreateResponse,
    dependencies=[Depends(require_personal_conversation)],
)
def create_selected_public_excerpt(
    conversation_id: str,
    payload: PublicExcerptSelectionCreate,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> PublicExcerptCreateResponse:  # noqa: B008
    owned_id = _selection_owner(request, conversation_id)
    _enforce_create_rate_limit(request, user=user)
    try:
        snapshot, created = create_receipt_for_messages(
            user=user,
            conversation_id=owned_id,
            message_ids=[str(value) for value in payload.message_ids],
            owner_note=payload.owner_note,
            expected_digest=payload.payload_digest,
        )
    except (EvidenceReceiptSourceMissingError, PublicExcerptSourceError) as error:
        raise _selection_error(request, error) from error
    if created:
        capture_product_event(
            "receipt_created",
            user_id=user.id,
            status="created",
            attributes={
                "receipt_digest": snapshot.payload_digest[:16],
                "kind": snapshot.kind,
            },
        )
    return PublicExcerptCreateResponse(receipt=snapshot_list_item(snapshot))
