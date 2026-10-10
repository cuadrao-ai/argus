"""Which side of a person's chats a request and a conversation belong to.

The client names a surface, never a space. ``surface_scope`` turns the surface
into an ``OwnerScope`` with ``resolve_business_scope``. Business answers 404
unless the pilot is on and the person has started their space, like the other
Business routes. A stored conversation's side comes from its ``owner_space_id``
through ``conversation_scope``. Personal artifacts (decisions, evidence,
receipts, memory) never attach to a Business conversation:
``require_personal_conversation`` answers 404 for one.

Business chat has its own flag inside the pilot. While it is off no Business
conversation is created and nothing writes a turn into one
(``refuse_closed_chat``, ``require_open_business_chat``); reading and deleting
existing ones still works.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Literal
from uuid import UUID

if TYPE_CHECKING:
    from argus.agent_runtime.business.context import (
        AuthorizedBusinessContext,
        BusinessActionService,
    )
    from argus.domain.business.contracts.recovery import DurableTurn, SenderLease

from fastapi import Depends, HTTPException, Request

from argus.api import state as api_state
from argus.api.business import unavailable_problem
from argus.api.business_spaces import business_spaces, space_missing_problem
from argus.api.dependencies import current_user, problem
from argus.api.schemas import ConversationSurface, User
from argus.domain.business.config import business_chat_enabled, business_pilot_enabled
from argus.domain.business.scope import resolve_business_scope
from argus.domain.owner_scope import PERSONAL, OwnerScope, holds, scope_of


def refuse_closed_chat(request: Request, surface: ConversationSurface) -> None:
    if surface == "business" and not business_chat_enabled():
        raise problem(
            request,
            status_code=404,
            code="business_chat_unavailable",
            title="Not Found",
            detail="Business chat is not available.",
            headers={"Cache-Control": "no-store"},
        )


def surface_scope(
    request: Request, *, user_id: str, surface: ConversationSurface
) -> OwnerScope:
    if surface != "business":
        return PERSONAL
    spaces = business_spaces()
    if not business_pilot_enabled() or spaces is None:
        raise unavailable_problem(request)
    resolved = resolve_business_scope(spaces, user_id)
    if resolved is None:
        raise space_missing_problem(request)
    return resolved.owner


def memory_conversation_scope(conversation_id: str) -> OwnerScope:
    return scope_of(api_state.store.conversation_spaces.get(conversation_id))


def memory_conversation_in_scope(conversation_id: str, scope: OwnerScope) -> bool:
    return holds(scope, api_state.store.conversation_spaces.get(conversation_id))


def conversation_scope(*, user_id: str, conversation_id: str) -> OwnerScope | None:
    """The scope of the person's stored conversation, or None when there is none."""

    gateway = api_state.supabase_gateway
    if gateway is None:
        if api_state.store.conversation_owners.get(conversation_id) not in {
            None,
            user_id,
        }:
            return None
        if conversation_id not in api_state.store.conversations:
            return None
        return memory_conversation_scope(conversation_id)
    canonical = _uuid_text(conversation_id)
    if canonical is None:
        return None
    return gateway.conversation_scope(user_id=user_id, conversation_id=canonical)


def is_business_conversation(*, user_id: str, conversation_id: str | None) -> bool:
    if conversation_id is None:
        return False
    scope = conversation_scope(user_id=user_id, conversation_id=conversation_id)
    return scope is not None and scope != PERSONAL


def conversation_not_found(request: Request) -> HTTPException:
    return problem(
        request,
        status_code=404,
        code="not_found",
        title="Not Found",
        detail="Conversation not found.",
    )


def require_personal_conversation(
    conversation_id: str,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
) -> None:
    """404 for a Business conversation; anything else reaches the route unchanged."""

    if is_business_conversation(user_id=user.id, conversation_id=conversation_id):
        raise conversation_not_found(request)


def require_open_business_chat(
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
) -> None:
    """No turn or card action on a Business conversation while Business chat
    is off; a Personal one reaches the route unchanged. The id is read from the
    path so each route keeps its own parameter type."""

    if not business_chat_enabled() and is_business_conversation(
        user_id=user.id, conversation_id=str(request.path_params["conversation_id"])
    ):
        refuse_closed_chat(request, "business")


def _uuid_text(value: str) -> str | None:
    try:
        return str(UUID(value))
    except (AttributeError, TypeError, ValueError):
        return None


def evidence_source_conversation_id(*, user_id: str, artifact_id: str) -> str | None:
    stored = api_state.store.evidence_artifacts.get(artifact_id)
    if stored is not None:
        if api_state.store.evidence_artifact_owners.get(artifact_id) != user_id:
            return None
        return stored.source_conversation_id
    gateway = api_state.supabase_gateway
    canonical = _uuid_text(artifact_id)
    if gateway is None or canonical is None:
        return None
    fetched = gateway.get_evidence_artifact(user_id=user_id, artifact_id=canonical)
    return fetched.source_conversation_id if fetched is not None else None


def require_personal_evidence_artifact(
    artifact_id: str,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
) -> None:
    """The same 404 for an evidence artifact a Business conversation produced."""

    source = evidence_source_conversation_id(user_id=user.id, artifact_id=artifact_id)
    if is_business_conversation(user_id=user.id, conversation_id=source):
        raise conversation_not_found(request)


def message_conversation_id(*, user_id: str, message_id: str) -> str | None:
    gateway = api_state.supabase_gateway
    if gateway is None:
        for conversation_id, messages in api_state.store.messages.items():
            if any(message.id == message_id for message in messages):
                return conversation_id
        return None
    canonical = _uuid_text(message_id)
    if canonical is None:
        return None
    return gateway.message_conversation_id(user_id=user_id, message_id=canonical)


def authorized_business_turn_context(
    *,
    actions: BusinessActionService,
    user_id: str,
    space_id: str,
    turn: DurableTurn,
    lease: SenderLease,
    message_id: str,
    received_at: datetime,
    channel: Literal["web", "whatsapp"],
    begin_reply: Callable[[], str | None],
    language: str = "es-419",
) -> AuthorizedBusinessContext:
    from argus.agent_runtime.business.context import AuthorizedBusinessContext
    from argus.domain.business.contracts.authority import TrustedActor

    actor = TrustedActor(
        actor_id=UUID(user_id), actor_kind="owner_via_agent", space_id=UUID(space_id)
    )
    authorization = actions.resolve_actor(actor)
    return AuthorizedBusinessContext(
        actions=actions,
        authorization=authorization,
        turn_key=turn.turn_key,
        lease=lease,
        message_id=UUID(message_id),
        received_at=received_at,
        channel=channel,
        begin_reply=begin_reply,
        language=language,
    )
