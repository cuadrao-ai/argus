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
from argus.agent_runtime.state.models import UserState
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

