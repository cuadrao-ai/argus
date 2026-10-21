"""Provider-free complete turn paths from imported history to receiver actions.

Structured model reads are fixtures. These prove routing and grounding plumbing,
not the live model's semantic interpretation quality.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from argus.agent_runtime.graph.workflow import build_workflow
from argus.agent_runtime.runtime import run_agent_turn
from argus.agent_runtime.stages.interpret_types import StructuredInterpretation
from argus.agent_runtime.state.models import StrategySummary, UserState
from argus.api import state as api_state
from argus.api.message_store import (
    load_runtime_thread_history,
    memory_conversation,
    memory_message,
)
from argus.api.public_excerpt_schemas import (
    PublicExcerptResearchTurn,
    PublicExcerptTurnsPayload,
)
from argus.domain.owner_scope import PERSONAL
from argus.domain.public_excerpt_forks import carried_messages
from langgraph.checkpoint.memory import MemorySaver


class RecordingInterpreter:
    def __init__(self, result):
        self.result = result
        self.requests = []

    async def ainvoke(self, request):
        self.requests.append(request)
        return self.result


@pytest.fixture
def imported(monkeypatch):
    monkeypatch.setattr(api_state, "supabase_gateway", None)
    api_state.store.reset()
    user = api_state.store.get_or_create_dev_user()
    conversation = memory_conversation(
        scope=PERSONAL,
        title="New idea",
        title_source="system_default",
        language="en",
        user_id=user.id,
    )
    payload = PublicExcerptTurnsPayload(
        turns=[
            PublicExcerptResearchTurn(
                question="What is AAPL worth?",
                answer="Snapshot: AAPL was $100.",
                retrieved_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
                owner_note="Owner private note",
                anchor_symbols=["AAPL"],
                asset_class="equity",
            )
        ]
    )
    messages = carried_messages(
        payload,
        snapshot_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
        public_id="frozen-public",
        request_id=str(uuid4()),
    )
    for message in messages:
        memory_message(conversation_id=conversation.id, **message)
    return user, conversation


@pytest.mark.asyncio
async def test_current_figures_followup_dispatches_fresh_research_from_imported_history(
    imported, monkeypatch
):
    from argus.agent_runtime import research_grounded
    from argus.domain.research.cache import cache_clear
    from argus.domain.research.perplexity_agent import PerplexityAgentClient

    from tests.research.conftest import RecordingTransport, agent_response

    user, conversation = imported
    monkeypatch.setenv("ARGUS_RESEARCH_RAIL_ENABLED", "true")
    cache_clear()
    transport = RecordingTransport(
        [agent_response(text="Apple closed at $312.41 on 2026-08-06.")]
    )
    monkeypatch.setattr(
        research_grounded,
        "_client",
        lambda: PerplexityAgentClient("fixture", transport=transport),
    )
    interpreter = RecordingInterpreter(
        StructuredInterpretation(
            intent="conversation_followup",
            task_relation="continue",
            requires_clarification=False,
            user_goal_summary="Get a current AAPL quote",
            semantic_turn_act="educational_question",
            research_query={"question_kind": "live_quote", "symbols": ["AAPL"]},
        )
    )
    workflow = build_workflow(
        structured_interpreter=interpreter, checkpointer=MemorySaver()
    )
    result = await run_agent_turn(
        workflow=workflow,
        user=UserState(user_id=user.id),
        thread_id=conversation.id,
        message="What is its price right now?",
        recent_thread_history=load_runtime_thread_history(
            user_id=user.id, conversation_id=conversation.id
        ),
    )
    assert transport.requests, "current figures must reach the normal grounding provider"
    assert result["stage_outcome"] == "ready_to_respond"
    assert "$312.41" in result["assistant_response"]
    assert "Snapshot: AAPL was $100." not in result["assistant_response"]
    assert result.get("confirmation_payload") is None
    assert (
        interpreter.requests[0]
        .recent_thread_history[1]
        .content.startswith("Snapshot: AAPL was $100.")
    )
    assert interpreter.requests[0].latest_task_snapshot is None
    assert not api_state.store.backtest_runs
    cache_clear()


def test_changed_carried_backtest_produces_new_confirmation_without_live_run(
    monkeypatch,
):
    from argus.api.main import app
    from fastapi.testclient import TestClient

    from tests.test_public_excerpt_api import _create, _seed

    monkeypatch.setattr(api_state, "supabase_gateway", None)
    monkeypatch.setenv("ARGUS_EVIDENCE_RECEIPT_SHARING_ENABLED", "true")
    api_state.store.reset()
    client = TestClient(app)
    user_id = _seed(client)
    receipt = _create(client)
    fork = client.post(
        f"/api/v1/public/receipts/{receipt['public_id']}/fork",
        json={"request_id": str(uuid4())},
    ).json()
    conversation_id = fork["conversation"]["id"]
    assert api_state.store.conversation_owners[conversation_id] == user_id
    initial_runs = set(api_state.store.backtest_runs)
    interpreter = RecordingInterpreter(
        StructuredInterpretation(
            intent="backtest_execution",
            task_relation="new_task",
            requires_clarification=False,
            user_goal_summary="Test the shared AAPL idea with 300 dollars",
            semantic_turn_act="new_idea",
            candidate_strategy_draft=StrategySummary(
                strategy_type="buy_and_hold",
                asset_universe=["AAPL"],
                asset_class="equity",
                date_range={"start": "2024-01-02", "end": "2024-12-31"},
                capital_amount=300,
                sizing_mode="capital_amount",
            ),
        )
    )
    workflow = build_workflow(
        structured_interpreter=interpreter, checkpointer=MemorySaver()
    )
    monkeypatch.setattr(
        api_state, "get_agent_runtime_workflow", lambda _request=None: workflow
    )
    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": conversation_id,
            "message": "Change it to $300",
            "language": "en",
        },
    )
    assert response.status_code == 200, response.text
    imported = api_state.store.messages[conversation_id][:2]
    own_confirmation = api_state.store.messages[conversation_id][-1]
    assert (
        own_confirmation.metadata["confirmation_payload"]["strategy"]["capital_amount"]
        == 300
    )
    assert own_confirmation.metadata["confirmation_card"]["confirmation_id"]
    assert "shared_conversation" not in own_confirmation.metadata
    assert interpreter.requests[0].latest_task_snapshot is None
    assert len(interpreter.requests[0].recent_thread_history) == 2
    assert set(api_state.store.backtest_runs) == initial_runs
    assert not api_state.store.backtest_jobs
    assert all(set(message.metadata) == {"shared_conversation"} for message in imported)
