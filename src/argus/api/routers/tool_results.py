"""Authenticated no-turn updates to a declared local tool's message artifact."""

from __future__ import annotations

import copy
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from argus.api.business import own_business_only
from argus.api.chat.tool_results import tool_cards_from_metadata
from argus.api.conversation_surface import require_open_business_chat
from argus.api.dependencies import current_user, problem
from argus.api.message_store import (
    latest_message,
    message_preview,
    owned_conversation_message,
    update_message_artifact,
)
from argus.api.schemas import Message, User
from argus.domain.computation_marker import computation_from_tool_cards
from argus.domain.pending_artifacts import (
    DeadPendingArtifactError,
    PendingArtifactLayout,
    PendingArtifactUpdate,
    apply_pending_artifact_update,
    pending_artifact_is_dead,
)
from argus.domain.supabase_conversation_messages import StaleMessageArtifactError
from argus.domain.tool_contracts import ToolCall
from argus.domain.tool_declaration import ToolCatalog

router = APIRouter(prefix="/api/v1", tags=["tool-results"])


def get_tool_catalog() -> ToolCatalog:
    from argus.domain.capability_registry import get_tool_catalog as catalog

    return catalog()


class ToolResultRecomputeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_id: UUID
    input_revision: int = Field(ge=0, strict=True)
    arguments: dict[str, JsonValue] = Field(min_length=1, max_length=32)


class ToolResultRecomputeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: Message


@router.post(
    "/conversations/{conversation_id}/tool-results/{artifact_id}/recompute",
    response_model=ToolResultRecomputeResponse,
    dependencies=[Depends(require_open_business_chat)],
)
async def recompute_tool_result(
    conversation_id: UUID,
    artifact_id: UUID,
    payload: ToolResultRecomputeRequest,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
) -> ToolResultRecomputeResponse:
    # Chat is the owner's: a chosen client grant is refused on every chat route.
    own_business_only(request, user.id)
    conversation = str(conversation_id)
    artifact = str(artifact_id)
    source = owned_conversation_message(
        user_id=user.id, conversation_id=conversation, message_id=str(payload.message_id)
    )
    if source is None or source.role != "assistant":
        raise problem(
            request,
            status_code=404,
            code="not_found",
            title="Not Found",
            detail="That result is not available.",
        )
    source = source.model_copy(deep=True)
    cards = tool_cards_from_metadata(source.metadata or {})
    card = next((item for item in cards if item.artifact_id == artifact), None)
    if card is None:
        raise problem(
            request,
            status_code=404,
            code="not_found",
            title="Not Found",
            detail="That result is not available.",
        )
    latest = latest_message(user_id=user.id, conversation_id=conversation)
    layout = PendingArtifactLayout(
        card_key="tool_result_cards",
        card_state_key="artifact_state",
        reference_key="",
        references_key="artifact_references",
        reference_type="tool_result",
        artifact_id=artifact,
    )
    if (
        latest is None
        or latest.id != source.id
        or pending_artifact_is_dead(source.metadata, layout=layout)
    ):
        raise problem(
            request,
            status_code=409,
            code="artifact_action_invalid_state",
            title="Conflict",
            detail="The result is no longer active.",
        )
    if card.input_revision != payload.input_revision:
        raise _changed(request)
    declaration = get_tool_catalog().get(card.tool_name)
    if declaration is None or (declaration.card.card_type, declaration.card.version) != (
        card.card_type,
        card.card_version,
    ):
        raise problem(
            request,
            status_code=422,
            code="tool_inputs_not_editable",
            title="Not Editable",
            detail="That result cannot be recomputed by this build.",
        )
    try:
        arguments = declaration.recompute_arguments(card.arguments, payload.arguments)
    except (ValueError, TypeError, ValidationError) as exc:
        raise problem(
            request,
            status_code=422,
            code="tool_arguments_invalid",
            title="Validation Error",
            detail="Those inputs do not satisfy this tool's declaration.",
        ) from exc
    outcome = await declaration.invoke(arguments)
    revised = declaration.result_card(
        call=ToolCall(
            tool_name=card.tool_name,
            call_id=card.call_id,
            arguments=arguments.model_dump(mode="json"),
        ),
        outcome=outcome,
        artifact_id=card.artifact_id,
        input_revision=card.input_revision + 1,
    )
    current = [revised if item.artifact_id == artifact else item for item in cards]
    documents = [item.model_dump(mode="json") for item in current]
    # The marker is derived from every current card by its one owner, so a
    # decision saved after this edit stores every option's current inputs.
    computation = computation_from_tool_cards(current, catalog=get_tool_catalog())
    metadata: dict[str, JsonValue] = {"tool_result_cards": documents}
    if computation is not None:
        metadata["computation"] = computation.model_dump(mode="json")
    content, assumptions = _recomputed_answer(source, revised, current)
    if assumptions is not None:
        metadata["answer_assumptions"] = assumptions

    def _write(**values: Any) -> Message:
        # The rewritten prose is the conversation's preview when this answer is its
        # latest message, as a confirmation edit's is.
        return update_message_artifact(
            user_id=user.id,
            conversation_id=conversation,
            **values,
            preview=message_preview(
                values["content"], role=str(source.role), metadata=values["metadata"]
            ),
        )

    # The message remains the only durable owner. No checkpoint projection is
    # written here; subsequent turns re-read these current artifact facts.
    try:
        updated = apply_pending_artifact_update(
            layout=layout,
            source_message=source,
            expected_source_metadata=copy.deepcopy(source.metadata),
            expected_latest_message_id=latest.id,
            prepare=lambda: PendingArtifactUpdate(content=content, metadata=metadata),
            write=_write,
        )
    except (StaleMessageArtifactError, DeadPendingArtifactError) as exc:
        raise _changed(request) from exc
    assert updated is not None  # This adapter always supplies a prepared update.
    return ToolResultRecomputeResponse(message=updated)


def _recomputed_answer(
    source: Message, revised: Any, current: list[Any]
) -> tuple[str, list[dict[str, str]] | None]:
    """The prose re-rendered from the message's current cards when the answer
    stated its figures through references, so every figure it states stays a
    card's, with the assumed inputs it never names; any other prose stays as
    stored, with nothing to list."""
    from argus.agent_runtime.answer_calculation import (
        ANSWER_TEMPLATE_KEY,
        fallback_answer_lead,
        render_answer_text,
        template_cards,
        unstated_assumptions,
    )

    template = (source.metadata or {}).get(ANSWER_TEMPLATE_KEY)
    names = template_cards(template) if isinstance(template, dict) else {}
    by_artifact = {card.artifact_id: card for card in current}
    if revised.artifact_id not in names.values() or any(
        artifact not in by_artifact for artifact in names.values()
    ):
        return source.content, None
    assert isinstance(template, dict)
    text_template = str(template.get("text") or "")
    cards = {name: by_artifact[artifact] for name, artifact in names.items()}
    succeeded = all(card.outcome.status == "succeeded" for card in cards.values())
    if succeeded:
        text, failure = render_answer_text(text_template, cards)
        if failure is None:
            return text, unstated_assumptions(text_template, cards)
    lead = fallback_answer_lead(
        str(template.get("language") or "en"), succeeded=succeeded
    )
    return lead, []


def _changed(request: Request) -> Exception:
    return problem(
        request,
        status_code=409,
        code="tool_result_changed",
        title="Conflict",
        detail="The result changed while this request was in flight. Nothing was applied.",
    )
