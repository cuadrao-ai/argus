"""Seed saved messages for conversation read tests, without a chat runtime."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from argus.api import state as api_state
from argus.api.chat.previews import stored_message_preview
from argus.api.schemas import Message, MessageRole
from argus.domain.store import utcnow


def seed_message(
    *,
    conversation_id: str,
    role: MessageRole,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> Message:
    store = api_state.store
    messages = store.messages.setdefault(conversation_id, [])
    created_at = utcnow()
    if messages:
        created_at = max(
            created_at,
            max(row.created_at for row in messages) + timedelta(microseconds=1),
        )
    message = Message(
        id=store.new_id(),
        conversation_id=conversation_id,
        role=role,
        content=content,
        created_at=created_at,
        metadata=metadata or {},
    )
    messages.append(message)
    store.bump_search_revision()
    conversation = store.conversations.get(conversation_id)
    if conversation:
        store.conversations[conversation_id] = conversation.model_copy(
            update={
                "last_message_preview": stored_message_preview(
                    content, role=role, metadata=message.metadata
                ),
                "updated_at": created_at,
            }
        )
    return message
