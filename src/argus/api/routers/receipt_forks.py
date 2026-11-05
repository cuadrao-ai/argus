"""Receiver-authenticated writes kept separate from the public snapshot reader."""

from __future__ import annotations

from threading import RLock
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict

from argus.api import state as api_state
from argus.api.conversation_surface import (
    conversation_not_found,
    is_business_conversation,
)
from argus.api.dependencies import current_user, problem
from argus.api.guest_access import account_context, client_identity
from argus.api.message_store import memory_conversation, memory_message
from argus.api.public_excerpts import (
    public_excerpt_reader,
    require_evidence_receipt_sharing_enabled,
)
from argus.api.rate_limits import SlidingWindowLimiter
from argus.api.schemas import Conversation, Language, User
from argus.domain.owner_scope import PERSONAL
from argus.domain.postgres_public_excerpt_forks import fork_public_excerpt
from argus.domain.public_excerpt_forks import (
    ForkError,
    carried_messages,
    fork_marker,
    resolve_fork_replay,
)

router = APIRouter(prefix="/api/v1/public", tags=["public-receipts"])
_MEMORY_LOCK = RLock()
_FORK_LIMITER = SlidingWindowLimiter()


class PublicExcerptForkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    language: Language | None = None
    replace_guest_conversation_id: UUID | None = None


class PublicExcerptForkResponse(BaseModel):
    conversation: Conversation
    created: bool


def _memory_fork(*, user: User, public_id: str, payload: PublicExcerptForkRequest):
    with _MEMORY_LOCK:
        marker = fork_marker(user.id, str(payload.request_id))
        candidates = []
        for conversation_id, messages in api_state.store.messages.items():
            if api_state.store.conversation_owners.get(conversation_id) != user.id:
                continue
            for message in messages:
                provenance = (message.metadata or {}).get("shared_conversation")
                matches_request = (
                    message.role == "user"
                    and isinstance(provenance, dict)
                    and provenance.get("request_id") == str(payload.request_id)
                    and provenance.get("turn_index") == 0
                )
                if message.id == marker or matches_request:
                    candidates.append(
                        (api_state.store.conversations[conversation_id], message.metadata)
                    )
        replay = resolve_fork_replay(
            candidates, request_id=str(payload.request_id), public_id=public_id
        )
        if replay is not None:
            return replay, False
        view = public_excerpt_reader().read_public_excerpt_view(public_id=public_id)
        if view.status != "available" or view.payload is None or view.created_at is None:
            raise ForkError("receipt_unavailable", 410)
        messages = carried_messages(
            view.payload,
            snapshot_at=view.created_at,
            public_id=public_id,
            request_id=str(payload.request_id),
        )
        conversation = memory_conversation(
            title="New idea",
            title_source="system_default",
            language=payload.language or user.language,
            scope=PERSONAL,
            user_id=user.id,
        )
        for index, message in enumerate(messages):
            created = memory_message(conversation_id=conversation.id, **message)
            if index == 0:
                api_state.store.messages[conversation.id][-1] = created.model_copy(
                    update={"id": marker}
                )
        return conversation, True


@router.post("/receipts/{public_id}/fork", response_model=PublicExcerptForkResponse)
def fork_receipt(
    public_id: str,
    payload: PublicExcerptForkRequest,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
) -> PublicExcerptForkResponse:
    require_evidence_receipt_sharing_enabled()
    retry_after = _FORK_LIMITER.record_or_retry_after(
        keys=(f"receipt-fork:{client_identity(request)}",),
        limit=60,
        window_seconds=3600,
    )
    if retry_after is not None:
        raise problem(
            request,
            status_code=429,
            code="too_many_requests",
            title="Too Many Requests",
            detail="Try again shortly.",
            headers={"Retry-After": str(retry_after)},
        )
    replaced = payload.replace_guest_conversation_id
    if replaced is not None and is_business_conversation(
        user_id=user.id, conversation_id=str(replaced)
    ):
        raise conversation_not_found(request)
    if len(public_id) > 64:
        raise problem(
            request,
            status_code=410,
            code="receipt_unavailable",
            title="Shared conversation unavailable",
            detail="This link is unavailable.",
        )
    try:
        gateway = api_state.supabase_gateway
        if gateway is None:
            conversation, created = _memory_fork(
                user=user, public_id=public_id, payload=payload
            )
        else:
            if gateway.history_reader is None:
                raise ForkError("receipt_unavailable", 503)
            conversation, created = fork_public_excerpt(
                gateway.history_reader.pool,
                user_id=user.id,
                public_id=public_id,
                request_id=str(payload.request_id),
                language=payload.language or user.language,
                guest=account_context(request).kind == "guest",
                replace_guest_conversation_id=str(payload.replace_guest_conversation_id)
                if payload.replace_guest_conversation_id
                else None,
            )
    except ForkError as error:
        raise problem(
            request,
            status_code=error.status,
            code=error.code,
            title="Shared conversation unavailable",
            detail=error.code,
        ) from error
    return PublicExcerptForkResponse(conversation=conversation, created=created)
