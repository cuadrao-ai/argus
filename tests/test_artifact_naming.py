from __future__ import annotations

from typing import Any

import pytest
from argus.api import state as api_state
from argus.api.message_store import create_message, memory_conversation
from argus.api.schemas import BacktestRun
from argus.domain.owner_scope import PERSONAL
from argus.domain.store import utcnow


@pytest.fixture(autouse=True)
def _reset_store(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_state, "supabase_gateway", None)
    api_state.store.reset()
    api_state.store.get_or_create_dev_user()


def _user_id() -> str:
    return "00000000-0000-0000-0000-000000000001"


def _completed_run(
    *, conversation_id: str, strategy_id: str | None = None
) -> BacktestRun:
    return BacktestRun(
        id=api_state.store.new_id(),
        conversation_id=conversation_id,
        strategy_id=strategy_id,
        status="completed",
        asset_class="equity",
        symbols=["TSLA"],
        allocation_method="equal_weight",
        benchmark_symbol="SPY",
        metrics={
            "aggregate": {
                "performance": {
                    "total_return_pct": 23.5,
                    "benchmark_return_pct": 24.2,
                    "delta_vs_benchmark_pct": -0.8,
                    "max_drawdown_pct": -29.9,
                }
            }
        },
        config_snapshot={
            "template": "buy_and_hold",
            "symbols": ["TSLA"],
            "date_range": {"start": "2025-05-17", "end": "2026-05-17"},
            "resolved_strategy": {
                "strategy_type": "buy_and_hold",
                "strategy_thesis": "Buy and hold Tesla against SPY.",
                "asset_universe": ["TSLA"],
                "asset_class": "equity",
                "date_range": {"start": "2025-05-17", "end": "2026-05-17"},
            },
        },
        conversation_result_card={
            "title": "TSLA Buy and Hold",
            "status_label": "Simulation Complete",
            "rows": [{"label": "Total Return", "value": "+23.5%"}],
            "assumptions": ["Benchmark: SPY"],
        },
        created_at=utcnow(),
    )


def test_conversation_title_generation_prefers_current_run_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api import artifact_naming

    conversation = memory_conversation(
        scope=PERSONAL,
        user_id=_user_id(),
        title="New idea",
        title_source="system_default",
        language="en",
    )
    run = _completed_run(conversation_id=conversation.id)
    captured: dict[str, Any] = {}

    def _suggest_entity_name(**kwargs: Any) -> str:
        captured.update(kwargs)
        return "Tesla SPY Check"

    monkeypatch.setattr(artifact_naming, "suggest_entity_name", _suggest_entity_name)

    title = artifact_naming.maybe_generate_conversation_title(
        user_id=_user_id(),
        conversation_id=conversation.id,
        language="en",
        current_run=run,
        user_message="could you check if holding Tesla beat SPY?",
        assistant_message="The strategy returned 23.5%.",
    )

    updated = api_state.store.conversations[conversation.id]
    assert title == "Tesla SPY Check"
    assert updated.title == "Tesla SPY Check"
    assert updated.title_source == "ai_generated"
    assert captured["entity_type"] == "conversation"
    assert "TSLA" in captured["context"]
    assert "SPY" in captured["context"]
    assert "2025-05-17" in captured["context"]
    assert "23.5" in captured["context"]


def test_conversation_title_generation_uses_chat_context_without_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api import artifact_naming

    conversation = memory_conversation(
        scope=PERSONAL,
        user_id=_user_id(),
        title="New idea",
        title_source="system_default",
        language="en",
    )
    create_message(
        user_id=_user_id(),
        conversation_id=conversation.id,
        role="user",
        content="Can you explain dollar cost averaging in plain English?",
    )
    create_message(
        user_id=_user_id(),
        conversation_id=conversation.id,
        role="assistant",
        content="Dollar cost averaging means investing a fixed amount on a schedule.",
    )
    captured: dict[str, Any] = {}

    def _suggest_entity_name(**kwargs: Any) -> str:
        captured.update(kwargs)
        return "DCA Basics"

    monkeypatch.setattr(artifact_naming, "suggest_entity_name", _suggest_entity_name)

    title = artifact_naming.maybe_generate_conversation_title(
        user_id=_user_id(),
        conversation_id=conversation.id,
        language="en",
        current_run=None,
        user_message=None,
        assistant_message=None,
    )

    assert title == "DCA Basics"
    assert api_state.store.conversations[conversation.id].title == "DCA Basics"
    assert "dollar cost averaging" in captured["context"].lower()
    assert "fixed amount" in captured["context"].lower()


def test_conversation_title_finalizer_persists_utility_route_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.chat import title_finalization
    from argus.llm.openrouter import record_openrouter_route_receipt

    conversation = memory_conversation(
        scope=PERSONAL,
        user_id=_user_id(),
        title="New idea",
        title_source="system_default",
        language="en",
    )
    run = _completed_run(conversation_id=conversation.id)
    receipts: list[dict[str, Any]] = []

    class FakeGateway:
        def get_conversation(self, *, user_id: str, conversation_id: str):
            del user_id
            return api_state.store.conversations.get(conversation_id)

        def patch_conversation(
            self,
            *,
            user_id: str,
            conversation_id: str,
            patch: dict[str, Any],
        ) -> None:
            del user_id
            current = api_state.store.conversations[conversation_id]
            api_state.store.conversations[conversation_id] = current.model_copy(
                update={**patch, "updated_at": utcnow()}
            )

        def create_route_receipt(self, **kwargs: Any) -> dict[str, Any]:
            receipts.append(kwargs)
            return kwargs

    def _suggest_entity_name(**_: Any) -> str:
        record_openrouter_route_receipt(
            task="name_suggestion",
            model_name="utility/primary",
            mode="json_schema",
            schema_name="name_suggestion",
            latency_ms=42,
            outcome="succeeded",
            token_usage={"prompt_tokens": 10, "completion_tokens": 4},
        )
        return "Tesla SPY Check"

    monkeypatch.setattr(api_state, "supabase_gateway", FakeGateway())
    monkeypatch.setenv("ARGUS_UTILITY_MODEL", "utility/primary")
    monkeypatch.setenv("ARGUS_UTILITY_FALLBACK_MODEL", "utility/fallback")
    monkeypatch.setattr(
        "argus.api.artifact_naming.suggest_entity_name",
        _suggest_entity_name,
    )

    title = title_finalization.finalize_conversation_title_after_turn(
        user_id=_user_id(),
        conversation_id=conversation.id,
        language="en",
        current_run=run,
        user_message="could you check if holding Tesla beat SPY?",
        assistant_message="The strategy returned 23.5%.",
        message_id="message-1",
        run_id=run.id,
    )

    assert title == "Tesla SPY Check"
    assert api_state.store.conversations[conversation.id].title_source == "ai_generated"
    assert len(receipts) == 1
    receipt = receipts[0]["receipt"]
    assert receipt["task"] == "name_suggestion"
    assert receipt["tier"] == "utility"
    assert receipt["model"] == "utility/primary"
    assert receipt["fallback_model"] == "utility/fallback"
    assert receipt["outcome"] == "succeeded"
    assert receipt["token_usage"] == {"prompt_tokens": 10, "completion_tokens": 4}
    assert receipts[0]["message_id"] == "message-1"
    assert receipts[0]["run_id"] == run.id
    assert receipts[0]["metadata"]["runtime_artifact"] == "conversation_title"


def test_conversation_title_finalizer_records_observable_skip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.chat import title_finalization

    conversation = memory_conversation(
        scope=PERSONAL,
        user_id=_user_id(),
        title="My renamed thread",
        title_source="user_renamed",
        language="en",
    )
    receipts: list[dict[str, Any]] = []

    class FakeGateway:
        def get_conversation(self, *, user_id: str, conversation_id: str):
            del user_id
            return api_state.store.conversations.get(conversation_id)

        def create_route_receipt(self, **kwargs: Any) -> dict[str, Any]:
            receipts.append(kwargs)
            return kwargs

    monkeypatch.setattr(api_state, "supabase_gateway", FakeGateway())
    monkeypatch.setenv("ARGUS_UTILITY_MODEL", "utility/primary")
    monkeypatch.setenv("ARGUS_UTILITY_FALLBACK_MODEL", "utility/fallback")

    title = title_finalization.finalize_conversation_title_after_turn(
        user_id=_user_id(),
        conversation_id=conversation.id,
        language="en",
        current_run=_completed_run(conversation_id=conversation.id),
        user_message="new text",
        assistant_message="new answer",
        message_id="message-1",
    )

    assert title is None
    assert len(receipts) == 1
    receipt = receipts[0]["receipt"]
    assert receipt["task"] == "name_suggestion"
    assert receipt["tier"] == "utility"
    assert receipt["outcome"] == "skipped"
    assert receipt["failure_mode"] == "title_not_generated"
    assert receipts[0]["metadata"]["runtime_artifact"] == "conversation_title"


def test_conversation_title_generation_never_overwrites_user_renamed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api import artifact_naming

    conversation = memory_conversation(
        scope=PERSONAL,
        user_id=_user_id(),
        title="My Tesla Research",
        title_source="user_renamed",
        language="en",
    )

    def _raise_if_called(**_: Any) -> str:
        raise AssertionError("LLM naming should not run for user-renamed chats")

    monkeypatch.setattr(artifact_naming, "suggest_entity_name", _raise_if_called)

    title = artifact_naming.maybe_generate_conversation_title(
        user_id=_user_id(),
        conversation_id=conversation.id,
        language="en",
        current_run=_completed_run(conversation_id=conversation.id),
        user_message="new text",
        assistant_message="new answer",
    )

    assert title is None
    assert api_state.store.conversations[conversation.id].title == "My Tesla Research"
    assert api_state.store.conversations[conversation.id].title_source == "user_renamed"
