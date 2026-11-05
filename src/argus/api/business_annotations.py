"""Public current-note and inert supporting-file commands for an existing record."""

from __future__ import annotations

import asyncio
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response

from argus.api.business import require_business_surface
from argus.api.business_drafts import with_source_channels
from argus.api.business_reports import Context, ReportingRoute, _run
from argus.api.dependencies import problem
from argus.api.documents import (
    SOURCE_MEDIA_TYPES,
    document_filename,
    read_document_upload,
    require_saved_documents,
)
from argus.domain.business.annotations import EditCurrentNote, NoteResult, edit_note
from argus.domain.business.contracts.dossier import BusinessDossier
from argus.domain.business.reporting_query import Contract
from argus.domain.business.supporting_files import SupportingResult, append_file
from argus.domain.ingestion.documents.preparation import DocumentExtractionError
from argus.domain.ingestion.documents.service import (
    DocumentServiceError,
    DocumentsService,
)

router = APIRouter(
    route_class=ReportingRoute, dependencies=[Depends(require_business_surface)]
)

Key = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=80)]


class NoteResponse(Contract):
    result: NoteResult
    dossier: BusinessDossier


class SupportingResponse(Contract):
    result: SupportingResult
    dossier: BusinessDossier


def _dossier(context, actor, draft_id: UUID) -> BusinessDossier:  # noqa: ANN001
    return with_source_channels(
        context.service.dossier(actor, draft_id),
        space_id=str(actor.actor.space_id),
        owner_id=actor.owner_id,
        service=context.service,
    )


@router.put("/drafts/{draft_id}/current-note", response_model=NoteResponse)
def update_current_note(
    request: Request,
    response: Response,
    draft_id: UUID,
    body: EditCurrentNote,
    context: Context,
    key: Key,
) -> NoteResponse:
    def command() -> NoteResponse:
        actor = context.for_draft(draft_id)
        result = edit_note(context.service.authority, actor, draft_id, body, key)
        return NoteResponse(result=result, dossier=_dossier(context, actor, draft_id))

    return _run(request, response, command)


@router.post(
    "/drafts/{draft_id}/supporting-files",
    response_model=SupportingResponse,
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
async def upload_supporting_file(
    request: Request,
    response: Response,
    draft_id: UUID,
    context: Context,
    key: Key,
    version: Annotated[int, Header(alias="X-Draft-Version", ge=1)],
    documents: Annotated[DocumentsService, Depends(require_saved_documents)],
    filename: Annotated[str | None, Header(alias="X-Document-Filename")] = None,
) -> SupportingResponse:
    media_type, content = await read_document_upload(request)

    def command() -> SupportingResponse:
        actor = context.for_draft(draft_id)
        result = append_file(
            context.service.authority,
            documents,
            actor,
            draft_id,
            version,
            document_filename(filename),
            media_type,
            content,
            key,
        )
        return SupportingResponse(
            result=result, dossier=_dossier(context, actor, draft_id)
        )

    try:
        return await asyncio.to_thread(_run, request, response, command)
    except (DocumentServiceError, DocumentExtractionError) as error:
        raise problem(
            request,
            status_code=503 if getattr(error, "retryable", False) else 422,
            code=error.code,
            title="Supporting file unavailable",
            detail=error.code,
            headers={"Cache-Control": "no-store"},
        ) from None
