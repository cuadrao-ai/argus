"""The unauthenticated receipt read. Deliberately the smallest router in Argus.

This module holds exactly one capability: resolve a public id to a frozen
snapshot view. It has no auth dependency, no gateway, no store, and no name for a
conversation, message, run, artifact or memory record anywhere in it. That
absence is the construction proof that a public view cannot reach private data,
and it is asserted by test rather than left to review.

An unknown id and a revoked id both answer with the same tombstone: with
unguessable ids there is nothing to enumerate, and a viewer holding a stale link
deserves an honest page instead of a broken one.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from argus.api.dependencies import problem
from argus.api.public_excerpt_schemas import (
    PublicExcerptFunnelStage,
    PublicExcerptView,
)
from argus.api.public_excerpts import (
    public_excerpt_reader,
    require_evidence_receipt_sharing_enabled,
)
from argus.domain.public_excerpts import (
    PublicExcerptUnreadableError,
    revoked_public_view,
)

router = APIRouter(prefix="/api/v1/public", tags=["public-receipts"])

MAX_PUBLIC_ID_LENGTH = 64


@router.get("/receipts/{public_id}", response_model=PublicExcerptView)
def read_public_receipt(public_id: str, request: Request) -> PublicExcerptView:
    """Read one frozen receipt. Deliberately counts nothing.

    This endpoint answers more than once per human visit, from the page's metadata
    pass, the page render, and the preview image, and a crawler expanding a pasted
    link hits it with nobody having opened anything.
    """
    require_evidence_receipt_sharing_enabled()
    if len(public_id) > MAX_PUBLIC_ID_LENGTH:
        # Bounded before it reaches storage, and answered like any other stale
        # link so an oversized id is not its own signal.
        return revoked_public_view(public_id[:MAX_PUBLIC_ID_LENGTH])
    try:
        return public_excerpt_reader().read_public_excerpt_view(public_id=public_id)
    except PublicExcerptUnreadableError as error:
        # A stored payload this build cannot parse answers as temporarily
        # unavailable, which is what it is. An uncaught validation error would
        # answer a stranger with a 500 on the first Argus page they ever see, and a
        # tombstone would tell them a live receipt is gone for good.
        raise problem(
            request,
            status_code=503,
            code="receipt_unavailable",
            title="Service Unavailable",
            detail=str(error),
            headers={"Retry-After": "120"},
        ) from error


@router.post("/receipt-funnel", status_code=204)
def record_receipt_funnel_stage(payload: PublicExcerptFunnelStage) -> Response:
    """Accept a viewer-side funnel stage and record nothing.

    Wave 1 does not track share-page views or a share funnel (SPEC 0, Iris's
    round 2 answer 4), so this endpoint counts nothing. It stays a 204 so a
    receipt page already open in a browser does not error when it reports.
    """
    del payload
    require_evidence_receipt_sharing_enabled()
    return Response(status_code=204)
