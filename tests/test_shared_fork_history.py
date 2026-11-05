"""Every bounded imported turn reaches ordinary model history, including reload."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from argus.api import state as api_state
from argus.api.message_store import (
    load_runtime_thread_history,
    memory_conversation,
    memory_message,
)
from argus.api.public_excerpt_schemas import (
    PublicExcerptAnswerTurn,
    PublicExcerptTurnsPayload,
)
from argus.domain.owner_scope import PERSONAL
from argus.domain.public_excerpt_forks import FORK_TEXT_BYTES, carried_messages


def seed_imported(*, count=12, ordinary=25):
    user_id = str(uuid4())
    conversation = memory_conversation(
        scope=PERSONAL,
        user_id=user_id,
        title="New idea",
        title_source="system_default",
        language="en",
    )
    payload = PublicExcerptTurnsPayload(
        turns=[
            PublicExcerptAnswerTurn(question=f"Question {i}", answer=f"Answer {i}")
            for i in range(count)
        ]
    )
    messages = carried_messages(
        payload,
        snapshot_at=datetime.now(timezone.utc),
        public_id="public",
        request_id=str(uuid4()),
    )
    for message in messages:
        memory_message(conversation_id=conversation.id, **message)
    for i in range(ordinary):
        memory_message(conversation_id=conversation.id, role="user", content=f"Own {i}")
    return user_id, conversation, messages


@pytest.mark.parametrize("count", [12, 500])
def test_memory_history_keeps_all_carried_pairs_and_normal_ordinary_window(
    monkeypatch, count
):
    monkeypatch.setattr(api_state, "supabase_gateway", None)
    api_state.store.reset()
    user_id, conversation, imported = seed_imported(count=count)
    history = load_runtime_thread_history(
        user_id=user_id, conversation_id=conversation.id
    )
    assert [turn.content for turn in history[: 2 * count]] == [
        turn["content"] for turn in imported
    ]
    assert len(history) == 2 * count + 20
    assert [turn.content for turn in history[-20:]] == [f"Own {i}" for i in range(5, 25)]
    assert (
        sum(len(turn.content.encode()) for turn in history[: 2 * count])
        <= FORK_TEXT_BYTES
    )
    named = load_runtime_thread_history(
        user_id=user_id, conversation_id=conversation.id, drop_shared_turns=True
    )
    assert all(turn.content.startswith("Own ") for turn in named)


@pytest.mark.parametrize("count", [12, 500])
@pytest.mark.parametrize("with_artifact", [False, True])
def test_model_history_preserves_import_through_runtime_and_checkpoint(
    monkeypatch, count, with_artifact
):
    from argus.agent_runtime.capabilities.contract import (
        build_default_capability_contract,
    )
    from argus.agent_runtime.llm_interpreter import OpenRouterStructuredInterpreter
    from argus.agent_runtime.runtime import build_workflow_input
    from argus.agent_runtime.stages.interpret_types import InterpretationRequest
    from argus.agent_runtime.state.models import StrategySummary, TaskSnapshot, UserState

    monkeypatch.setattr(api_state, "supabase_gateway", None)
    api_state.store.reset()
    user_id, conversation, imported = seed_imported(count=count)
    workflow_input = build_workflow_input(
        user=UserState(user_id=user_id),
        message="Follow up",
        recent_thread_history=load_runtime_thread_history(
            user_id=user_id, conversation_id=conversation.id
        ),
    )
    serde = api_state.build_agent_runtime_checkpoint_serde()
    restored = serde.loads_typed(serde.dumps_typed(workflow_input))
    history = restored["run_state"].recent_thread_history
    assert len(history) == 2 * count + 6
    request = InterpretationRequest(
        current_user_message="Follow up",
        recent_thread_history=history,
        user=UserState(user_id=user_id),
        latest_task_snapshot=TaskSnapshot(
            pending_strategy_summary=StrategySummary(strategy_type="buy_and_hold")
        )
        if with_artifact
        else None,
    )
    interpreter = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )
    messages = interpreter._messages(request)
    actual = [message.content for message in messages if message.type in {"human", "ai"}]
    assert actual[: 2 * count] == [turn["content"] for turn in imported]
    assert actual[-1] == "Follow up"
    assert len(actual) == 2 * count + 1 + (0 if with_artifact else 6)
    assert "shared_context" not in str([message.model_dump() for message in messages])


def test_interpretation_and_answer_adapters_keep_imports_but_clarifier_uses_current_reason(
    monkeypatch,
):
    from types import SimpleNamespace

    from argus.agent_runtime.calculated_answer import _messages as answer_messages
    from argus.agent_runtime.interpreter.dca_audits import (
        _strategy_family_continuity_audit_messages,
    )
    from argus.agent_runtime.interpreter.discovery_focused_read import _history_lines
    from argus.agent_runtime.llm_clarifier import (
        ClarificationRequest,
        OpenRouterClarificationGenerator,
    )
    from argus.agent_runtime.runtime import build_workflow_input
    from argus.agent_runtime.stages.interpret_types import InterpretationRequest
    from argus.agent_runtime.state.models import UserState

    monkeypatch.setattr(api_state, "supabase_gateway", None)
    api_state.store.reset()
    user_id, conversation, imported = seed_imported()
    state = build_workflow_input(
        user=UserState(user_id=user_id),
        message="Follow up",
        recent_thread_history=load_runtime_thread_history(
            user_id=user_id, conversation_id=conversation.id
        ),
    )["run_state"]
    request = InterpretationRequest(
        current_user_message="Follow up",
        recent_thread_history=state.recent_thread_history,
        user=UserState(user_id=user_id),
    )
    clarification_messages = OpenRouterClarificationGenerator()._messages(
        ClarificationRequest(
            current_user_message="Follow up",
            recent_thread_history=state.recent_thread_history,
        )
    )
    clarification_text = str([m.model_dump() for m in clarification_messages])
    assert all(turn["content"] not in clarification_text for turn in imported)
    assert "Follow up" in clarification_text
    outputs = [
        _history_lines(request),
        str(
            _strategy_family_continuity_audit_messages(
                response=SimpleNamespace(model_dump=lambda **_: {}), request=request
            )
        ),
        str(
            answer_messages(
                message="Follow up",
                language="en",
                history=state.recent_thread_history,
                market_facts={},
                not_looked_up=[],
                pending=None,
            )
        ),
    ]
    for output in outputs:
        assert all(turn["content"] in output for turn in imported)
        assert "shared_context" not in output


def test_supabase_import_reader_pages_all_selected_turns_with_owner_filter():
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from argus.domain.supabase_gateway import SupabaseGateway

    from tests.test_supabase_gateway_pagination import _message_row

    user_id, conversation_id = str(uuid4()), str(uuid4())
    rows = [
        {**_message_row(i), "metadata": {"shared_conversation": {"turn_index": i // 2}}}
        for i in range(1000)
    ]
    client, query = MagicMock(), MagicMock()
    client.table.return_value = query
    for method in ("select", "eq", "contains", "order", "range"):
        getattr(query, method).return_value = query
    query.execute.side_effect = [
        SimpleNamespace(data=rows[:500]),
        SimpleNamespace(data=rows[500:]),
        SimpleNamespace(data=[]),
    ]
    messages = SupabaseGateway(client=client).list_shared_messages(
        user_id=user_id, conversation_id=conversation_id
    )
    assert len(messages) == len(rows)
    query.eq.assert_any_call("user_id", user_id)
    query.eq.assert_any_call("conversation_id", conversation_id)
    query.contains.assert_called_once_with("metadata", {"shared_conversation": {}})
    assert query.range.call_count == 3


def test_shared_history_selector_enforces_import_bound_only():
    from argus.agent_runtime.history import select_thread_history
    from argus.agent_runtime.state.models import ConversationMessage

    oversized = "x" * (FORK_TEXT_BYTES + 1)
    assert (
        select_thread_history([ConversationMessage(role="user", content=oversized)])[
            0
        ].content
        == oversized
    )
    with pytest.raises(ValueError, match="import bound"):
        select_thread_history(
            [ConversationMessage(role="user", content=oversized, shared_context=True)]
        )
