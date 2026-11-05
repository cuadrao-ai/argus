"""S10: memory reaches voicing and nothing earlier.

Recall annotations live in message metadata, and `load_runtime_thread_history`
rebuilds every message as `ConversationMessage(role, content)`. These pin that
constructor rather than trusting the call sites.
"""

from __future__ import annotations

from typing import Any

import pytest
from argus.api import state as api_state
from argus.api.message_store import (
    create_message,
    load_runtime_thread_history,
    memory_conversation,
)
from argus.domain.owner_scope import PERSONAL

RECALL_TEXT = "Rejected the higher-drawdown ETH variant on 2026-07-30."
ANSWER_TEXT = "Here is how that idea performed over the period you asked about."


@pytest.fixture(autouse=True)
def _memory_message_store(monkeypatch: pytest.MonkeyPatch):
    api_state.store.reset()
    monkeypatch.setattr(api_state, "supabase_gateway", None)
    yield
    api_state.store.reset()


def _memory_recall_metadata() -> dict[str, Any]:
    return {
        "memory_recalls": [
            {
                "record_id": "9a4c1e77-3f5b-4d20-8e61-2c7b9f04a3d5",
                "label": "ETH drawdown decision",
                "value": RECALL_TEXT,
                "category": "explicit_decision_note",
            }
        ]
    }


def _seed_turn(*, with_memory: bool) -> tuple[str, str]:
    user = api_state.store.get_or_create_dev_user()
    conversation = memory_conversation(
        scope=PERSONAL,
        title="ETH idea",
        title_source="system_default",
        language="en",
        user_id=user.id,
    )
    create_message(
        user_id=user.id,
        conversation_id=conversation.id,
        role="user",
        content="How did that ETH idea do?",
    )
    create_message(
        user_id=user.id,
        conversation_id=conversation.id,
        role="assistant",
        content=ANSWER_TEXT,
        metadata=_memory_recall_metadata() if with_memory else {},
    )
    return user.id, conversation.id


def _history_payload(*, with_memory: bool) -> list[tuple[str, str]]:
    user_id, conversation_id = _seed_turn(with_memory=with_memory)
    return [
        (item.role, item.content)
        for item in load_runtime_thread_history(
            user_id=user_id,
            conversation_id=conversation_id,
        )
    ]


def test_interpreter_input_is_identical_with_and_without_stored_memories() -> None:
    """Catches recalled memory widening the interpreter's input for a turn."""
    without_memory = _history_payload(with_memory=False)
    api_state.store.reset()
    with_memory = _history_payload(with_memory=True)

    assert with_memory == without_memory
    assert RECALL_TEXT not in "".join(content for _, content in with_memory)


def test_runtime_history_entries_carry_only_role_and_content() -> None:
    """Catches a history entry regaining a metadata channel memory could ride."""
    user_id, conversation_id = _seed_turn(with_memory=True)

    history = load_runtime_thread_history(
        user_id=user_id,
        conversation_id=conversation_id,
    )

    assert history
    for entry in history:
        # Two fields only; no metadata channel for memory to ride.
        assert set(entry.model_dump()) == {"role", "content"}


def test_persisted_memory_annotation_survives_for_rendering_only() -> None:
    """Catches the annotation being dropped from the surface that renders it."""
    user_id, conversation_id = _seed_turn(with_memory=True)

    persisted = api_state.store.messages[conversation_id]
    assistant = [message for message in persisted if message.role == "assistant"][-1]

    # Still durable for hydration and rendering...
    assert assistant.metadata["memory_recalls"][0]["value"] == RECALL_TEXT
    # ...and still absent from what the next turn's interpreter would read.
    assert RECALL_TEXT not in "".join(
        entry.content
        for entry in load_runtime_thread_history(
            user_id=user_id,
            conversation_id=conversation_id,
        )
    )
