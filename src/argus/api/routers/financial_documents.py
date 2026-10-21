"""Bounded byte uploads feed the existing import review queue."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query, Request, Response
from pydantic import BaseModel, ConfigDict, ValidationError

from argus.api.documents import (
    NO_STORE,
    DocumentContext,
    dispatch_preparation,
    document_filename,
    document_problem,
    read_document_upload,
    require_document_context,
    require_saved_document_context,
)
from argus.domain.ingestion.documents.config import SOURCE_MEDIA_TYPES
from argus.domain.ingestion.documents.models import DraftProposal, DraftStatus
from argus.domain.ingestion.documents.service import DocumentServiceError
from argus.domain.owner_scope import PERSONAL

router = APIRouter(prefix="/financial-documents", tags=["financial-documents"])


class DocumentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    connection_id: str
    status: DraftStatus
    replayed: bool
    candidate_count: int


@router.post(
    "",
    response_model=DocumentResponse,
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
async def upload_document(
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    filename: str | None = Header(default=None, alias="X-Document-Filename"),
    proposal: str | None = Header(
        default=None, alias="X-Document-Proposal", max_length=8192
    ),
    consent: str | None = Header(default=None, alias="X-Extraction-Consent"),
    context: DocumentContext = Depends(require_document_context),  # noqa: B008
) -> dict[str, object]:
    response.headers.update(NO_STORE)
    try:
        destination = (
            DraftProposal.model_validate_json(proposal)
            if proposal is not None
            else DraftProposal()
        )
    except ValidationError:
        raise document_problem(
            request, DocumentServiceError("document_proposal_invalid")
        ) from None
    media_type, content = await read_document_upload(request)
    try:
        outcome = await context.service.upload(
            user_id=context.user_id,
            content=content,
            filename=document_filename(filename),
            media_type=media_type,
            consent=consent == "true",
            proposal=destination,
            scope=PERSONAL,
        )
        if outcome.status == "queued":
            await dispatch_preparation(
                context.service,
                context.user_id,
                outcome.connection_id,
                background_tasks,
                scope=PERSONAL,
            )
        return asdict(outcome)
    except Exception as error:
        raise document_problem(request, error) from None


@router.post("/{connection_id}/prepare", response_model=DocumentResponse)
@router.post("/{connection_id}/resume", response_model=DocumentResponse)
async def resume_document(
    request: Request,
    connection_id: str,
    background_tasks: BackgroundTasks,
    consent: str | None = Header(default=None, alias="X-Extraction-Consent"),
    context: DocumentContext = Depends(require_document_context),  # noqa: B008
) -> dict[str, object]:
    try:
        outcome = context.service.queue(
            user_id=context.user_id,
            connection_id=connection_id,
            consent=consent == "true",
            scope=PERSONAL,
        )
        await dispatch_preparation(
            context.service,
            context.user_id,
            connection_id,
            background_tasks,
            scope=PERSONAL,
        )
        return asdict(outcome)
    except Exception as error:
        raise document_problem(request, error) from None


def _draft(context: DocumentContext, connection_id: str) -> dict[str, object]:
    draft = context.service.get(
        user_id=context.user_id, connection_id=connection_id, scope=PERSONAL
    )
    batch = context.service.store.get(
        user_id=context.user_id, connection_id=connection_id
    )
    return {
        **draft.model_dump(mode="json"),
        "preparation": batch.model_dump(mode="json", exclude={"metadata"})
        if batch
        else None,
    }


@router.get("")
def list_documents(
    request: Request,
    response: Response,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    context: DocumentContext = Depends(require_saved_document_context),  # noqa: B008
) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    try:
        items = []
        for connection in context.service.hub.connections.list(
            user_id=context.user_id, scope=PERSONAL
        ):
            if connection.source == "statement" and connection.status != "disconnected":
                try:
                    items.append(
                        context.service.get(
                            user_id=context.user_id,
                            connection_id=connection.id,
                            scope=PERSONAL,
                        ).model_dump(mode="json")
                    )
                except DocumentServiceError as error:
                    if error.code != "document_source_unavailable":
                        raise
        return {
            "items": items[offset : offset + limit],
            "next_offset": offset + limit if offset + limit < len(items) else None,
        }
    except Exception as error:
        raise document_problem(request, error) from None


@router.get("/{connection_id}")
def get_document(
    request: Request,
    response: Response,
    connection_id: str,
    context: DocumentContext = Depends(require_saved_document_context),  # noqa: B008
) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    try:
        return _draft(context, connection_id)
    except Exception as error:
        raise document_problem(request, error) from None


@router.get("/{connection_id}/source")
def get_source(
    request: Request,
    connection_id: str,
    context: DocumentContext = Depends(require_saved_document_context),  # noqa: B008
) -> Response:
    try:
        before = context.service.get(
            user_id=context.user_id, connection_id=connection_id, scope=PERSONAL
        )
        from argus.domain.ingestion.documents.models import DocumentExtractionError
        from argus.domain.ingestion.documents.objects import SourceStorageUnavailable
        from argus.domain.ingestion.documents.rebuilt import ensure_rebuilt_image

        try:
            ensure_rebuilt_image(
                store=context.service.store,
                user_id=context.user_id,
                connection_id=connection_id,
            )
            download = context.service.store.download_source(
                user_id=context.user_id, connection_id=connection_id
            )
        except SourceStorageUnavailable:
            raise DocumentServiceError(
                "document_storage_unavailable", retryable=True
            ) from None
        except DocumentExtractionError:
            raise DocumentServiceError("document_source_unavailable") from None
        after = context.service.get(
            user_id=context.user_id, connection_id=connection_id, scope=PERSONAL
        )
        if (before.sha256, before.media_type) != (after.sha256, after.media_type):
            raise DocumentServiceError("document_source_unavailable")
        if download is None:
            raise DocumentServiceError("document_source_unavailable")
        media_type, content = download
        suffix = SOURCE_MEDIA_TYPES[media_type]
        return Response(
            content,
            media_type=media_type,
            headers={
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Content-Disposition": f'attachment; filename="document.{suffix}"',
            },
        )
    except Exception as error:
        raise document_problem(request, error) from None


class ProposalUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int
    proposal: DraftProposal


@router.patch("/{connection_id}/proposal")
def update_proposal(
    request: Request,
    response: Response,
    connection_id: str,
    body: ProposalUpdate,
    context: DocumentContext = Depends(require_document_context),  # noqa: B008
) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    try:
        context.service.update_proposal(
            user_id=context.user_id,
            connection_id=connection_id,
            version=body.version,
            proposal=body.proposal,
            scope=PERSONAL,
        )
        return _draft(context, connection_id)
    except Exception as error:
        raise document_problem(request, error) from None
