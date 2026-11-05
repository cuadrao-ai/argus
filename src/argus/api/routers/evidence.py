from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from argus.api.chat.evidence import (
    EvidenceArtifactNotFoundError,
    EvidenceDecisionCaptureError,
    create_decision_for_evidence_artifact,
)
from argus.api.conversation_surface import require_personal_evidence_artifact
from argus.api.dependencies import current_user, problem, require_account_capability
from argus.api.schemas import DecisionNoteCreate, DecisionNoteResponse, User

router = APIRouter(prefix="/api/v1/evidence-artifacts", tags=["evidence"])


@router.post(
    "/{artifact_id}/decision",
    response_model=DecisionNoteResponse,
    dependencies=[Depends(require_personal_evidence_artifact)],
)
def create_decision(
    artifact_id: str,
    payload: DecisionNoteCreate,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
) -> DecisionNoteResponse:
    require_account_capability(
        request,
        "can_save_decision",
        detail="Sign in to save this decision.",
        reason="save_decision",
    )
    try:
        decision, artifact = create_decision_for_evidence_artifact(
            user=user,
            artifact_id=artifact_id,
            payload=payload,
        )
    except EvidenceArtifactNotFoundError as exc:
        raise problem(
            request,
            status_code=404,
            code="not_found",
            title="Not Found",
            detail=str(exc),
        ) from exc
    except EvidenceDecisionCaptureError as exc:
        raise problem(
            request,
            status_code=500,
            code="decision_capture_failed",
            title="Decision Capture Failed",
            detail=(
                "Argus could not safely record that decision. "
                "Please retry in a moment."
            ),
        ) from exc
    return DecisionNoteResponse(decision=decision, evidence_artifact=artifact)
