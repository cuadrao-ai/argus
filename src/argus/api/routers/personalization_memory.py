"""Registered-only personalization-memory endpoints.

Each handler enters through the single memory API gate: a verified Guest is
denied with 403 account_conversion_required before any memory code runs, and
the default-off ARGUS_ENABLE_PERSONALIZATION_MEMORY flag plus an injected
service are both required before the subsystem is reachable at all.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from typing import TypeVar

from fastapi import APIRouter, Depends, Request, Response

from argus.api.conversation_surface import (
    evidence_source_conversation_id,
    is_business_conversation,
    message_conversation_id,
)
from argus.api.dependencies import current_user, problem
from argus.api.guest_access import account_context
from argus.api.personalization_memory import (
    MemoryApiContext,
    personalization_memory_exposed,
    personalization_memory_unavailable_problem,
    require_memory_api_context,
)
from argus.api.personalization_memory_assessor import (
    assess_memory_content,
    candidate_content_for_assessment,
)
from argus.api.personalization_memory_schemas import (
    MemoryAvailabilityResponse,
    MemoryCandidateOut,
    MemoryConfirmationResponse,
    MemoryConfirmRequest,
    MemoryConsentSettingsResponse,
    MemoryControlResponse,
    MemoryDeclineResponse,
    MemoryEditRequest,
    MemoryEnableRequest,
    MemoryExplanationResponse,
    MemoryExportDocument,
    MemoryProposalResponse,
    MemoryProposeRequest,
    MemoryProposeSavedDecisionRequest,
    MemoryRecordOut,
    MemoryRecordsResponse,
    MemoryRetrievalResponse,
    MemoryRetrieveRequest,
    RetrievedMemoryOut,
)
from argus.api.schemas import User
from argus.memory.contracts import (
    MemoryCandidateDraft,
    MemoryEdit,
    MemoryProposalTrigger,
    MemoryProvenance,
    MemorySourceKind,
    SensitivityAssessment,
    SensitivityStatus,
)
from argus.memory.service import SAVED_DECISION_FUTURE_BENEFIT
from argus.memory.subject import PersonalizationMemoryUnavailable

router = APIRouter(prefix="/api/v1", tags=["personalization-memory"])


def _assessed_or_problem(request: Request, content: str) -> SensitivityAssessment:
    # Sensitivity is backend truth: content is classified here, never claimed
    # by the client, and an unavailable classifier fails closed as 503.
    assessment = assess_memory_content(content)
    if assessment.status is SensitivityStatus.UNASSESSED:
        raise problem(
            request,
            status_code=503,
            code="memory_assessment_unavailable",
            title="Memory Assessment Unavailable",
            detail="Argus could not review that content right now. Try again.",
        )
    return assessment


def _restricted_content_problem(request: Request):
    return problem(
        request,
        status_code=400,
        code="memory_sensitivity_restricted",
        title="Content Not Storable",
        detail="Argus keeps sensitive details out of memory.",
    )


ResultT = TypeVar("ResultT")


def _provenance_names_business_conversation(
    *, user_id: str, provenance: Iterable[MemoryProvenance]
) -> bool:
    """Whether a memory source is a Business conversation, one of its messages, or
    evidence it produced. Memory stays Personal."""

    for ref in provenance:
        conversation_id: str | None = None
        if ref.source_kind is MemorySourceKind.CONVERSATION:
            conversation_id = ref.source_id
        elif ref.source_kind is MemorySourceKind.MESSAGE:
            conversation_id = message_conversation_id(
                user_id=user_id, message_id=ref.source_id
            )
        elif ref.source_kind is MemorySourceKind.EVIDENCE_ARTIFACT:
            conversation_id = evidence_source_conversation_id(
                user_id=user_id, artifact_id=ref.source_id
            )
        if is_business_conversation(user_id=user_id, conversation_id=conversation_id):
            return True
    return False


def _refuse_business_provenance(
    request: Request, ctx: MemoryApiContext, provenance: Iterable[MemoryProvenance]
) -> None:
    """Memory is Personal: a Business chat is never its source."""
    if _provenance_names_business_conversation(
        user_id=ctx.subject.owner_id, provenance=provenance
    ):
        raise _invalid_memory_request(request)


def _invalid_memory_request(request: Request):
    return problem(
        request,
        status_code=400,
        code="invalid_memory_request",
        title="Invalid Memory Request",
        detail="The request is not valid for personalization memory.",
    )


def _run(request: Request, call: Callable[[], ResultT]) -> ResultT:
    try:
        return call()
    except PersonalizationMemoryUnavailable:
        raise personalization_memory_unavailable_problem(request) from None
    except ValueError:
        # The original message may quote request content; do not echo it.
        raise _invalid_memory_request(request) from None


@router.get("/memory/availability", response_model=MemoryAvailabilityResponse)
def personalization_memory_availability(
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
) -> MemoryAvailabilityResponse:
    """Presentation probe: lets the client hide the surface entirely.

    Never touches the memory subsystem; a guest is denied like everywhere
    else and a non-exposed registered account simply sees available=false.
    """
    account = account_context(request)
    if account.kind != "registered":
        raise problem(
            request,
            status_code=403,
            code="account_conversion_required",
            title="Account Required",
            detail="Create an account to use personalization memory.",
        )
    return MemoryAvailabilityResponse(available=personalization_memory_exposed(user))


@router.post("/memory/enable", response_model=MemoryConsentSettingsResponse)
def enable_memory(
    payload: MemoryEnableRequest,
    request: Request,
    ctx: MemoryApiContext = Depends(require_memory_api_context),  # noqa: B008
) -> MemoryConsentSettingsResponse:
    settings = _run(
        request,
        lambda: ctx.service.enable(
            ctx.subject,
            frozenset(payload.categories),
            idempotency_key=payload.idempotency_key,
        ),
    )
    return MemoryConsentSettingsResponse.from_domain(settings)


@router.post("/memory/candidates", response_model=MemoryProposalResponse)
def propose_memory(
    payload: MemoryProposeRequest,
    request: Request,
    ctx: MemoryApiContext = Depends(require_memory_api_context),  # noqa: B008
) -> MemoryProposalResponse:
    provenance = tuple(ref.to_domain() for ref in payload.provenance)
    _refuse_business_provenance(request, ctx, provenance)
    sensitivity = _assessed_or_problem(
        request,
        candidate_content_for_assessment(
            label=payload.label,
            value=payload.value,
            future_benefit=payload.future_benefit,
        ),
    )
    draft = MemoryCandidateDraft(
        category=payload.category,
        value=payload.value,
        label=payload.label,
        future_benefit=payload.future_benefit,
        provenance=provenance,
        trigger=MemoryProposalTrigger.EXPLICIT_REQUEST,
        sensitivity=sensitivity,
    )
    result = _run(
        request,
        lambda: ctx.service.propose(ctx.subject, draft, payload.context),
    )
    if result is None:
        return MemoryProposalResponse(created=False)
    return MemoryProposalResponse(
        created=True,
        candidate=MemoryCandidateOut.from_domain(result.candidate),
    )


@router.post(
    "/memory/candidates/saved-decision",
    response_model=MemoryProposalResponse,
)
def propose_saved_decision_memory(
    payload: MemoryProposeSavedDecisionRequest,
    request: Request,
    ctx: MemoryApiContext = Depends(require_memory_api_context),  # noqa: B008
) -> MemoryProposalResponse:
    source = _run(request, payload.to_source)
    _refuse_business_provenance(request, ctx, (source.provenance,))
    sensitivity = _assessed_or_problem(
        request,
        candidate_content_for_assessment(
            label=payload.label,
            value=payload.value,
            future_benefit=SAVED_DECISION_FUTURE_BENEFIT,
        ),
    )
    result = _run(
        request,
        lambda: ctx.service.propose_saved_decision(
            ctx.subject,
            source,
            sensitivity=sensitivity,
            context=payload.context,
        ),
    )
    if result is None:
        return MemoryProposalResponse(created=False)
    return MemoryProposalResponse(
        created=True,
        candidate=MemoryCandidateOut.from_domain(result.candidate),
    )


@router.post(
    "/memory/candidates/{candidate_id}/confirm",
    response_model=MemoryConfirmationResponse,
)
def confirm_memory_candidate(
    candidate_id: str,
    payload: MemoryConfirmRequest,
    request: Request,
    ctx: MemoryApiContext = Depends(require_memory_api_context),  # noqa: B008
) -> MemoryConfirmationResponse:
    # No re-attestation: confirmation applies to exactly the assessed content
    # that was proposed, and the service preflights the stored assessment.
    result = _run(
        request,
        lambda: ctx.service.confirm(
            ctx.subject,
            candidate_id,
            context=payload.context,
        ),
    )
    return MemoryConfirmationResponse.from_domain(result)


@router.post(
    "/memory/candidates/{candidate_id}/decline",
    response_model=MemoryDeclineResponse,
)
def decline_memory_candidate(
    candidate_id: str,
    request: Request,
    ctx: MemoryApiContext = Depends(require_memory_api_context),  # noqa: B008
) -> MemoryDeclineResponse:
    declined = _run(request, lambda: ctx.service.decline(ctx.subject, candidate_id))
    return MemoryDeclineResponse(declined=declined)


@router.get("/memory/settings", response_model=MemoryConsentSettingsResponse)
def memory_settings(
    request: Request,
    ctx: MemoryApiContext = Depends(require_memory_api_context),  # noqa: B008
) -> MemoryConsentSettingsResponse:
    settings = _run(request, lambda: ctx.service.settings(ctx.subject))
    return MemoryConsentSettingsResponse.from_domain(settings)


@router.get("/memory/export", response_model=MemoryExportDocument)
def export_memory(
    request: Request,
    response: Response,
    ctx: MemoryApiContext = Depends(require_memory_api_context),  # noqa: B008
) -> MemoryExportDocument:
    """Data portability: everything memory holds, in one readable document."""
    settings = _run(request, lambda: ctx.service.settings(ctx.subject))
    records = _run(request, lambda: ctx.service.inspect(ctx.subject))
    response.headers["Content-Disposition"] = (
        'attachment; filename="argus-memory-export.json"'
    )
    return MemoryExportDocument(
        exported_at=datetime.now(timezone.utc),
        settings=MemoryConsentSettingsResponse.from_domain(settings),
        records=[MemoryRecordOut.from_domain(record) for record in records],
    )


@router.get("/memory/records", response_model=MemoryRecordsResponse)
def inspect_memory_records(
    request: Request,
    ctx: MemoryApiContext = Depends(require_memory_api_context),  # noqa: B008
) -> MemoryRecordsResponse:
    records = _run(request, lambda: ctx.service.inspect(ctx.subject))
    return MemoryRecordsResponse(
        records=[MemoryRecordOut.from_domain(record) for record in records]
    )


@router.get(
    "/memory/records/{record_id}/explanation",
    response_model=MemoryExplanationResponse,
)
def explain_memory_record(
    record_id: str,
    request: Request,
    ctx: MemoryApiContext = Depends(require_memory_api_context),  # noqa: B008
) -> MemoryExplanationResponse:
    explanation = _run(request, lambda: ctx.service.explain(ctx.subject, record_id))
    if explanation is None:
        raise problem(
            request,
            status_code=404,
            code="not_found",
            title="Not Found",
            detail="Memory record not found.",
        )
    return MemoryExplanationResponse.from_domain(explanation)


@router.post("/memory/retrieval", response_model=MemoryRetrievalResponse)
def retrieve_memories(
    payload: MemoryRetrieveRequest,
    request: Request,
    ctx: MemoryApiContext = Depends(require_memory_api_context),  # noqa: B008
) -> MemoryRetrievalResponse:
    retrieved = _run(
        request,
        lambda: ctx.service.retrieve(
            ctx.subject,
            payload.query,
            payload.purpose,
            payload.context,
            limit=payload.limit,
        ),
    )
    return MemoryRetrievalResponse(
        memories=[RetrievedMemoryOut.from_domain(memory) for memory in retrieved]
    )


@router.patch("/memory/records/{record_id}", response_model=MemoryControlResponse)
def edit_memory_record(
    record_id: str,
    payload: MemoryEditRequest,
    request: Request,
    ctx: MemoryApiContext = Depends(require_memory_api_context),  # noqa: B008
) -> MemoryControlResponse:
    edited_parts = [
        part
        for part in (
            f"label: {payload.label}" if payload.label is not None else None,
            f"value: {payload.value}" if payload.value is not None else None,
        )
        if part is not None
    ]
    sensitivity = _assessed_or_problem(request, "\n".join(edited_parts))
    if sensitivity.status is not SensitivityStatus.CLEAR:
        raise _restricted_content_problem(request)
    edit = MemoryEdit(
        value=payload.value,
        label=payload.label,
        sensitivity=sensitivity,
    )
    result = _run(request, lambda: ctx.service.edit(ctx.subject, record_id, edit))
    return MemoryControlResponse.from_domain(result)


@router.delete("/memory/records/{record_id}", response_model=MemoryControlResponse)
def delete_memory_record(
    record_id: str,
    request: Request,
    ctx: MemoryApiContext = Depends(require_memory_api_context),  # noqa: B008
) -> MemoryControlResponse:
    result = _run(request, lambda: ctx.service.delete(ctx.subject, record_id))
    return MemoryControlResponse.from_domain(result)


@router.post("/memory/disable", response_model=MemoryControlResponse)
def disable_memory(
    request: Request,
    ctx: MemoryApiContext = Depends(require_memory_api_context),  # noqa: B008
) -> MemoryControlResponse:
    result = _run(request, lambda: ctx.service.disable(ctx.subject))
    return MemoryControlResponse.from_domain(result)


@router.post("/memory/reset", response_model=MemoryControlResponse)
def reset_memory(
    request: Request,
    ctx: MemoryApiContext = Depends(require_memory_api_context),  # noqa: B008
) -> MemoryControlResponse:
    result = _run(request, lambda: ctx.service.reset(ctx.subject))
    return MemoryControlResponse.from_domain(result)
