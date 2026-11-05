from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from argus.api.chat.decisions import (
    DecisionAttachmentUnsupportedError,
    DecisionCaptureError,
    DecisionMessageNotFoundError,
    DecisionNotFoundError,
    DecisionRerunInputsError,
    create_decision_for_message,
    open_decision,
    rerun_message_computation,
)
from argus.api.conversation_surface import require_personal_conversation
from argus.api.decision_contract import (
    DecisionNoteCreate,
    DecisionOpenResponse,
    DecisionRerunRequest,
    MessageComputationRerunResponse,
    MessageDecisionResponse,
)
from argus.api.dependencies import current_user, problem, require_account_capability
from argus.api.schemas import User

router = APIRouter(prefix="/api/v1", tags=["decisions"])


@router.post(
    "/conversations/{conversation_id}/messages/{message_id}/decision",
    response_model=MessageDecisionResponse,
    dependencies=[Depends(require_personal_conversation)],
)
def create_message_decision(
    conversation_id: str,
    message_id: str,
    payload: DecisionNoteCreate,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
) -> MessageDecisionResponse:
    require_account_capability(
        request,
        "can_save_decision",
        detail="Sign in to save this decision.",
        reason="save_decision",
    )
    try:
        decision = create_decision_for_message(
            user=user,
            conversation_id=conversation_id,
            message_id=message_id,
            payload=payload,
        )
    except DecisionMessageNotFoundError as exc:
        raise problem(
            request,
            status_code=404,
            code="not_found",
            title="Not Found",
            detail=str(exc),
        ) from exc
    except DecisionAttachmentUnsupportedError as exc:
        raise problem(
            request,
            status_code=409,
            code="decision_attachment_unsupported",
            title="Decision Attachment Unsupported",
            detail=str(exc),
        ) from exc
    except DecisionCaptureError as exc:
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
    return MessageDecisionResponse(decision=decision)


@router.get("/decisions/{decision_id}", response_model=DecisionOpenResponse)
def open_decision_route(
    decision_id: str,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
) -> DecisionOpenResponse:
    try:
        decision, computation, reruns = open_decision(user=user, decision_id=decision_id)
    except DecisionNotFoundError as exc:
        raise problem(
            request,
            status_code=404,
            code="not_found",
            title="Not Found",
            detail=str(exc),
        ) from exc
    return DecisionOpenResponse(decision=decision, computation=computation, reruns=reruns)


@router.post("/decisions/{decision_id}/rerun", response_model=DecisionOpenResponse)
def rerun_decision_route(
    decision_id: str,
    payload: DecisionRerunRequest,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
) -> DecisionOpenResponse:
    try:
        decision, computation, reruns = open_decision(
            user=user,
            decision_id=decision_id,
            overrides=payload.inputs,
            calculation=payload.calculation,
        )
    except DecisionNotFoundError as exc:
        raise problem(
            request,
            status_code=404,
            code="not_found",
            title="Not Found",
            detail=str(exc),
        ) from exc
    except DecisionRerunInputsError as exc:
        raise problem(
            request,
            status_code=422,
            code="validation_error",
            title="Validation Error",
            detail="Re-run inputs are invalid.",
            context={"errors": exc.errors},
        ) from exc
    return DecisionOpenResponse(decision=decision, computation=computation, reruns=reruns)


@router.post(
    "/conversations/{conversation_id}/messages/{message_id}/computation/rerun",
    response_model=MessageComputationRerunResponse,
    dependencies=[Depends(require_personal_conversation)],
)
def rerun_message_computation_route(
    conversation_id: str,
    message_id: str,
    payload: DecisionRerunRequest,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
) -> MessageComputationRerunResponse:
    try:
        computation, reruns = rerun_message_computation(
            user=user,
            conversation_id=conversation_id,
            message_id=message_id,
            overrides=payload.inputs,
            calculation=payload.calculation,
        )
    except DecisionMessageNotFoundError as exc:
        raise problem(
            request,
            status_code=404,
            code="not_found",
            title="Not Found",
            detail=str(exc),
        ) from exc
    except DecisionAttachmentUnsupportedError as exc:
        raise problem(
            request,
            status_code=409,
            code="decision_attachment_unsupported",
            title="Decision Attachment Unsupported",
            detail=str(exc),
        ) from exc
    except DecisionRerunInputsError as exc:
        raise problem(
            request,
            status_code=422,
            code="validation_error",
            title="Validation Error",
            detail="Re-run inputs are invalid.",
            context={"errors": exc.errors},
        ) from exc
    return MessageComputationRerunResponse(computation=computation, reruns=reruns)
