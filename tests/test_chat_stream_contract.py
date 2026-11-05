from __future__ import annotations

import json
from typing import Any

import pytest
from argus.api.main import app
from fastapi.testclient import TestClient


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/api/v1/dev/reset")
    return client


def _conversation(client: TestClient) -> dict[str, Any]:
    return client.post("/api/v1/conversations", json={}).json()["conversation"]


def _data_events(stream: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for part in stream.split("\n\n"):
        data_line = next(
            (line for line in part.splitlines() if line.startswith("data: ")),
            None,
        )
        if data_line is None:
            continue
        raw = data_line.removeprefix("data: ").strip()
        if raw == "[DONE]":
            continue
        events.append(json.loads(raw))
    return events


def _final_payload(stream: str) -> dict[str, Any]:
    final_events = [
        event for event in _data_events(stream) if event.get("type") == "final"
    ]
    assert len(final_events) == 1
    payload = final_events[0]["payload"]
    assert isinstance(payload, dict)
    return payload


def _assert_durable_retry_on_linked_assistant(
    messages: list[dict[str, Any]],
    *,
    persisted_content: str,
    failure_code: str = "agent_runtime_failure",
) -> tuple[dict[str, Any], dict[str, Any]]:
    user_message = next(message for message in messages if message["role"] == "user")
    user_runtime_turn = user_message["metadata"]["agent_runtime_turn"]
    assert user_runtime_turn == {
        "status": "started",
        "conversation_id": user_message["conversation_id"],
        "request_id": user_runtime_turn["request_id"],
        "started_at": user_runtime_turn["started_at"],
    }
    assert user_runtime_turn["request_id"]
    assert user_runtime_turn["started_at"]
    assert "retry_last_turn" not in user_message["metadata"]

    linked_assistants = [
        message
        for message in messages
        if message["role"] == "assistant"
        and message["metadata"].get("agent_runtime_turn", {}).get("turn_id")
        == user_message["id"]
    ]
    assert len(linked_assistants) == 1
    assistant_message = linked_assistants[0]
    assert assistant_message["metadata"]["agent_runtime_turn"] == {
        "turn_id": user_message["id"],
        "request_id": user_runtime_turn["request_id"],
        "status": "recoverable_failed",
        "terminal": True,
        "reconciled_outcome": None,
        "failure_code": failure_code,
        "retryable": True,
    }
    expected_retry = {
        "request_message_id": user_message["id"],
        "message": persisted_content,
    }
    persisted_action = user_message["metadata"].get("chat_action")
    if persisted_action is not None:
        expected_retry["action"] = persisted_action
    assert assistant_message["metadata"]["retry_last_turn"] == expected_retry
    return user_message, assistant_message


def test_finalization_retry_metadata_preserves_structured_action() -> None:
    from argus.api.chat.retry import retry_last_turn_metadata
    from argus.api.schemas import ChatActionPayload, ChatStreamRequest

    metadata = retry_last_turn_metadata(
        payload=ChatStreamRequest(
            conversation_id="conversation-1",
            action=ChatActionPayload(
                type="run_backtest",
                label="Run backtest",
                payload={"confirmation_id": "confirmation-1"},
                presentation="confirmation",
            ),
        ),
        request_message="run backtest",
        include_structured_action=True,
    )

    assert metadata == {
        "retry_last_turn": {
            "message": "run backtest",
            "action": {
                "type": "run_backtest",
                "label": "Run backtest",
                "labelKey": None,
                "payload": {"confirmation_id": "confirmation-1"},
                "presentation": "confirmation",
            },
        }
    }


def test_finalization_retry_identity_requires_matching_failed_turn() -> None:
    from argus.api.chat.retry import retryable_finalization_execution_identity

    metadata = {
        "failure_code": "finalization_failed",
        "retry_last_turn": {"message": "run backtest"},
        "backtest_finalization": {"execution_identity": "chat:original"},
    }

    assert (
        retryable_finalization_execution_identity(
            metadata,
            request_message="run backtest",
        )
        == "chat:original"
    )
    assert (
        retryable_finalization_execution_identity(
            metadata,
            request_message="different turn",
        )
        is None
    )


def test_finalization_identity_prefers_job_then_retry_then_request() -> None:
    from argus.api.chat.retry import backtest_finalization_execution_identity

    assert (
        backtest_finalization_execution_identity(
            backtest_job={"id": "job-1"},
            retry_execution_identity="chat:original",
            idempotency_key="idempotency-1",
            request_id="request-1",
        )
        == "backtest_job:job-1"
    )
    assert (
        backtest_finalization_execution_identity(
            backtest_job=None,
            retry_execution_identity="chat:original",
            idempotency_key="idempotency-1",
            request_id="request-1",
        )
        == "chat:original"
    )
    assert (
        backtest_finalization_execution_identity(
            backtest_job=None,
            retry_execution_identity=None,
            idempotency_key=None,
            request_id="request-1",
        )
        == "/api/v1/chat/stream:request-1"
    )


@pytest.fixture(autouse=True)
def _patch_runtime_io(monkeypatch: pytest.MonkeyPatch) -> None:
    from argus.api import state as api_state

    monkeypatch.setattr(api_state, "supabase_gateway", None)


@pytest.mark.asyncio
async def test_runtime_records_exact_graph_final_before_public_filtering() -> None:
    from types import SimpleNamespace

    from argus.agent_runtime.runtime import stream_agent_turn_events
    from argus.agent_runtime.state.models import UserState
    from argus.agent_runtime.turn_execution import turn_execution_scope
    from argus.agent_runtime.turn_progress import semantic_progress_fingerprint

    entry_state = {
        "semantic_turn_act": "new_idea",
        "response_intent": {
            "kind": "clarification",
            "requested_fields": ["asset_universe"],
        },
    }
    exact_final_state = {
        "semantic_turn_act": "refine_current_idea",
        "response_intent": {
            "kind": "clarification",
            "requested_fields": ["date_range"],
        },
        "stage_outcome": "await_user_reply",
        "assistant_response": "Which date range should I use?",
    }

    class _Workflow:
        async def astream_events(self, *_: Any, **__: Any):
            if False:
                yield {}

        async def aget_state(self, _config: dict[str, Any]) -> Any:
            return SimpleNamespace(values=exact_final_state)

    with turn_execution_scope(entry_state=entry_state) as execution:
        events = [
            event
            async for event in stream_agent_turn_events(
                workflow=_Workflow(),
                user=UserState(user_id="user-1"),
                thread_id="conversation-1",
                message="Use a different date.",
                workflow_input=entry_state,
            )
        ]

    assert len(events) == 1
    final_event = events[0]
    assert final_event["type"] == "final"
    assert "semantic_turn_act" not in final_event["payload"]
    assert final_event["payload"]["assistant_response"] == (
        "Which date range should I use?"
    )
    evidence = final_event["_turn_progress"]
    assert set(evidence) == {
        "output_fingerprint",
        "progress_outcome",
        "terminal",
        "terminal_reason",
    }
    assert evidence["output_fingerprint"] == semantic_progress_fingerprint(
        exact_final_state
    )
    assert evidence["progress_outcome"] == "clarification"
    assert execution.exit_fingerprint == evidence["output_fingerprint"]
    assert "semantic_turn_act" not in json.dumps(final_event["payload"])


@pytest.mark.asyncio
async def test_runtime_exact_final_preserves_claimed_no_progress_evidence() -> None:
    from types import SimpleNamespace

    from argus.agent_runtime.runtime import stream_agent_turn_events
    from argus.agent_runtime.state.models import UserState
    from argus.agent_runtime.turn_execution import (
        claim_turn_terminal,
        turn_execution_scope,
        turn_execution_summary,
    )
    from argus.agent_runtime.turn_progress import semantic_progress_fingerprint

    entry_state = {
        "response_intent": {
            "kind": "clarification",
            "requested_fields": ["date_range"],
        },
        "pending_strategy": {
            "strategy": {
                "strategy_type": "buy_and_hold",
                "asset_universe": ["AAPL"],
                "asset_class": "equity",
            },
            "requested_field": "date_range",
        },
    }
    exact_final_state = {
        "response_intent": {
            "kind": "clarification",
            "requested_fields": ["date_range"],
            "facts": {"progress_outcome": "no_progress"},
        },
        "pending_strategy": {
            "strategy": {
                "strategy_type": "buy_and_hold",
                "asset_universe": ["MSFT"],
                "asset_class": "equity",
            },
            "requested_field": "date_range",
        },
        "stage_outcome": "ready_to_respond",
        "assistant_response": "I could not safely apply that change.",
    }

    class _Workflow:
        async def astream_events(self, *_: Any, **__: Any):
            if False:
                yield {}

        async def aget_state(self, _config: dict[str, Any]) -> Any:
            return SimpleNamespace(values=exact_final_state)

    with turn_execution_scope(entry_state=entry_state) as execution:
        assert claim_turn_terminal("no_progress", "unchanged_typed_state") is True
        events = [
            event
            async for event in stream_agent_turn_events(
                workflow=_Workflow(),
                user=UserState(user_id="user-1"),
                thread_id="conversation-1",
                message="Use Microsoft instead.",
                workflow_input=entry_state,
            )
        ]
        summary = turn_execution_summary(())

    assert len(events) == 1
    final_event = events[0]
    assert final_event["type"] == "final"
    assert final_event["payload"]["response_intent"]["facts"][
        "progress_outcome"
    ] == "no_progress"
    evidence = final_event["_turn_progress"]
    assert evidence["progress_outcome"] == "no_progress"
    assert evidence["terminal"] == "no_progress"
    assert execution.progress_outcome == "no_progress"
    assert execution.terminal == "no_progress"
    assert summary["progress_outcome"] == "no_progress"
    assert summary["terminal"] == "no_progress"
    assert evidence["output_fingerprint"] == semantic_progress_fingerprint(
        exact_final_state
    )
    assert summary["input_fingerprint"] != evidence["output_fingerprint"]
    assert "changed_fields" not in final_event["payload"]
    assert "changed_fields" not in evidence

