from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

import pytest
from argus.api import state as api_state
from argus.api.chat.turn_lifecycle_hooks import ChatTurnLifecycleHooks
from argus.api.chat.turn_lifecycle_projection import (
    project_chat_turn_lifecycle_messages,
)
from argus.api.main import app
from argus.api.message_store import memory_conversation, prepare_message
from argus.domain.chat_turn_lifecycle import MemoryChatTurnLifecycleGateway
from argus.domain.owner_scope import PERSONAL
from argus.domain.store import utcnow
from argus.llm.openrouter import (
    clear_openrouter_route_receipts,
    get_openrouter_route_receipts,
)
from fastapi.testclient import TestClient


class _EvidenceCountingMemoryGateway:
    """Exercise the production evidence sinks against inspectable row stores."""

    def __init__(self) -> None:
        self.lifecycle = MemoryChatTurnLifecycleGateway(api_state.store)
        self.route_receipt_rows: list[dict[str, Any]] = []
        self.cost_ledger_rows: list[dict[str, Any]] = []

    def get_or_create_mock_user(self):
        return api_state.store.get_or_create_dev_user()

    def get_user(self, *, user_id: str):
        return api_state.store.users.get(user_id)

    def update_user(self, user_id: str, payload: dict[str, Any]):
        current = api_state.store.users[user_id]
        updated = current.model_validate(payload)
        api_state.store.users[user_id] = updated
        return updated

    def get_conversation(self, *, user_id: str, conversation_id: str):
        if api_state.store.conversation_owners.get(conversation_id) != user_id:
            return None
        return api_state.store.conversations.get(conversation_id)

    def list_messages(
        self,
        *,
        user_id: str,
        conversation_id: str,
        limit: int = 20,
        **_: Any,
    ):
        if api_state.store.conversation_owners.get(conversation_id) != user_id:
            return []
        return list(api_state.store.messages.get(conversation_id, []))[-limit:]

    def get_latest_completed_run_for_conversation(self, **_: Any):
        return None

    def check_usage_limits(self, **_: Any) -> None:
        return None

    def accept_chat_turn(self, **kwargs: Any):
        return self.lifecycle.accept_chat_turn(**kwargs)

    def transition_chat_turn(self, **kwargs: Any):
        return self.lifecycle.transition_chat_turn(**kwargs)

    def finalize_chat_turn(self, **kwargs: Any):
        return self.lifecycle.finalize_chat_turn(**kwargs)

    def accept_response_option_chat_turn(self, **kwargs: Any):
        return self.lifecycle.accept_response_option_chat_turn(**kwargs)

    def get_message(
        self,
        *,
        user_id: str,
        conversation_id: str,
        message_id: str,
    ):
        if api_state.store.conversation_owners.get(conversation_id) != user_id:
            return None
        return next(
            (
                message
                for message in api_state.store.messages.get(conversation_id, [])
                if message.id == message_id
            ),
            None,
        )

    def reconcile_stale_chat_turns(self, **kwargs: Any):
        return self.lifecycle.reconcile_stale_chat_turns(**kwargs)

    def list_projectable_chat_turns(self, **kwargs: Any):
        return self.lifecycle.list_projectable_chat_turns(**kwargs)

    def create_route_receipt(self, **kwargs: Any) -> dict[str, Any]:
        row = {"id": f"receipt-{len(self.route_receipt_rows) + 1}", **kwargs}
        self.route_receipt_rows.append(row)
        return row

    def create_cost_ledger_entry(
        self,
        *,
        entry: dict[str, Any],
    ) -> dict[str, Any]:
        row = {"id": f"cost-{len(self.cost_ledger_rows) + 1}", **entry}
        self.cost_ledger_rows.append(row)
        return row


class _OrderingMemoryGateway(_EvidenceCountingMemoryGateway):
    def __init__(self, events: list[str]) -> None:
        super().__init__()
        self.events = events

    def accept_chat_turn(self, **kwargs: Any):
        self.events.append("admit")
        return super().accept_chat_turn(**kwargs)

    def accept_response_option_chat_turn(self, **kwargs: Any):
        self.events.append("admit")
        return super().accept_response_option_chat_turn(**kwargs)

    def transition_chat_turn(self, **kwargs: Any):
        if kwargs.get("to_status") == "running":
            self.events.append("running")
        return super().transition_chat_turn(**kwargs)


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/api/v1/dev/reset")
    clear_openrouter_route_receipts()
    return client


def _conversation(client: TestClient) -> dict[str, Any]:
    response = client.post("/api/v1/conversations", json={"language": "en"})
    assert response.status_code == 200
    return response.json()["conversation"]


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
        if raw != "[DONE]":
            events.append(json.loads(raw))
    return events


def _assert_one_public_terminal(
    *,
    conversation_id: str,
    expected_status: str,
    evidence_gateway: _EvidenceCountingMemoryGateway,
) -> dict[str, Any]:
    assert len(api_state.store.chat_turn_lifecycles) == 1
    lifecycle = next(iter(api_state.store.chat_turn_lifecycles.values()))
    assert lifecycle["conversation_id"] == conversation_id
    assert lifecycle["status"] == expected_status
    assistant_id = lifecycle["assistant_message_id"]
    assert assistant_id is not None
    assistant = next(
        message
        for message in api_state.store.messages[conversation_id]
        if message.id == assistant_id
    )
    runtime_turn = assistant.metadata["agent_runtime_turn"]
    assert runtime_turn["turn_id"] == lifecycle["turn_id"]
    assert runtime_turn["request_id"] == lifecycle["request_id"]
    assert runtime_turn["status"] == expected_status
    assert runtime_turn["terminal"] is True
    public_json = json.dumps(
        {
            "content": assistant.content,
            "metadata": assistant.metadata,
        }
    )
    for forbidden in (
        "_turn_progress",
        "input_fingerprint",
        "output_fingerprint",
        "runtime_diagnostics",
        "turn_execution",
    ):
        assert forbidden not in public_json
    assert get_openrouter_route_receipts() == []
    assert evidence_gateway.route_receipt_rows == []
    assert evidence_gateway.cost_ledger_rows == []
    return lifecycle


def _accepted_turn() -> tuple[MemoryChatTurnLifecycleGateway, object]:
    api_state.store.reset()
    conversation = memory_conversation(
        scope=PERSONAL,
        title="Lifecycle",
        title_source="system_default",
        language="en",
        user_id="user-1",
    )
    gateway = MemoryChatTurnLifecycleGateway(api_state.store)
    request_message = prepare_message(
        conversation_id=conversation.id,
        role="user",
        content="Test AAPL",
        metadata={"chat_action": {"type": "refine_strategy", "payload": {}}},
    )
    accepted = gateway.accept_chat_turn(
        user_id="user-1",
        conversation_id=conversation.id,
        request_id="request-1",
        message=request_message,
    )
    return gateway, accepted


def test_ordinary_message_runs_then_finalizes_with_durable_assistant_evidence() -> None:
    _gateway, accepted = _accepted_turn()
    hooks = ChatTurnLifecycleHooks(
        owner="ordinary_turn",
        user_id="user-1",
        conversation_id=accepted.conversation_id,
        request_id="request-1",
        request_message=accepted,
    )

    hooks.mark_running()
    assistant = hooks.complete(
        content="AAPL is ready to review.",
        metadata={"conversation_mode": "guide"},
        settle_usage=None,
    )

    row = api_state.store.chat_turn_lifecycles[accepted.id]
    assert row["status"] == "completed"
    assert row["assistant_message_id"] == assistant.id
    assert api_state.store.messages[accepted.conversation_id][-1] == assistant
    assert assistant.metadata["agent_runtime_turn"] == {
        "turn_id": accepted.id,
        "request_id": "request-1",
        "status": "completed",
        "terminal": True,
    }


def test_runtime_failure_finalizes_once_with_persisted_content_retry() -> None:
    _gateway, accepted = _accepted_turn()
    hooks = ChatTurnLifecycleHooks(
        owner="ordinary_turn",
        user_id="user-1",
        conversation_id=accepted.conversation_id,
        request_id="request-1",
        request_message=accepted,
    )
    hooks.mark_running()

    assistant = hooks.recoverable_failure(
        content="Something went wrong.",
        metadata={"conversation_mode": "recovery"},
        failure_code="agent_runtime_failure",
        retryable=True,
    )

    row = api_state.store.chat_turn_lifecycles[accepted.id]
    assert row["status"] == "recoverable_failed"
    assert row["assistant_message_id"] == assistant.id
    assert assistant.metadata["retry_last_turn"] == {
        "request_message_id": accepted.id,
        "message": accepted.content,
        "action": accepted.metadata["chat_action"],
    }
    assert assistant.metadata["agent_runtime_turn"] == {
        "turn_id": accepted.id,
        "request_id": "request-1",
        "status": "recoverable_failed",
        "terminal": True,
        "failure_code": "agent_runtime_failure",
        "retryable": True,
    }


def test_abandoned_projection_attaches_retry_to_owning_user_message_only() -> None:
    gateway, accepted = _accepted_turn()
    stale_at = (utcnow() - timedelta(minutes=16)).isoformat()
    api_state.store.chat_turn_lifecycles[accepted.id].update(
        accepted_at=stale_at,
        updated_at=stale_at,
    )
    [lifecycle] = gateway.reconcile_stale_chat_turns(
        conversation_id=accepted.conversation_id,
        user_id="user-1",
    )

    [projected] = project_chat_turn_lifecycle_messages(
        messages=[accepted],
        lifecycle_rows=[lifecycle],
    )

    assert projected.id == accepted.id
    assert projected.metadata["agent_runtime_turn"] == {
        "turn_id": accepted.id,
        "request_id": "request-1",
        "status": "abandoned",
        "terminal": True,
        "reconciled_outcome": None,
        "failure_code": "turn_abandoned",
        "retryable": True,
    }
    assert projected.metadata["recovery"] == {
        "code": "turn_abandoned",
        "retryable": True,
    }
    assert projected.metadata["retry_last_turn"] == {
        "request_message_id": accepted.id,
        "message": accepted.content,
        "action": accepted.metadata["chat_action"],
    }
    assert api_state.store.messages[accepted.conversation_id] == [accepted]


@pytest.mark.parametrize(
    (
        "status",
        "reconciled_outcome",
        "failure_code",
        "retryable",
    ),
    [
        ("completed", None, None, False),
        (
            "reconciled",
            "recoverable_failed",
            "agent_runtime_failure",
            True,
        ),
    ],
)
def test_linked_terminal_projection_belongs_to_assistant_only(
    status: str,
    reconciled_outcome: str | None,
    failure_code: str | None,
    retryable: bool,
) -> None:
    _gateway, accepted = _accepted_turn()
    assistant = prepare_message(
        conversation_id=accepted.conversation_id,
        role="assistant",
        content="Durable terminal result.",
        metadata={"conversation_mode": "recovery"},
    )
    [projected_user, projected_assistant] = project_chat_turn_lifecycle_messages(
        messages=[accepted, assistant],
        lifecycle_rows=[
            {
                "turn_id": accepted.id,
                "request_id": "request-1",
                "assistant_message_id": assistant.id,
                "status": status,
                "reconciled_outcome": reconciled_outcome,
                "failure_code": failure_code,
                "retryable": retryable,
            }
        ],
    )

    assert projected_user.metadata == accepted.metadata
    assert projected_assistant.metadata["agent_runtime_turn"] == {
        "turn_id": accepted.id,
        "request_id": "request-1",
        "status": status,
        "terminal": True,
        "reconciled_outcome": reconciled_outcome,
        "failure_code": failure_code,
        "retryable": retryable,
    }


def test_message_only_hooks_never_create_a_chat_turn_lifecycle() -> None:
    api_state.store.reset()
    conversation = memory_conversation(
        scope=PERSONAL,
        title="Run",
        title_source="system_default",
        language="en",
        user_id="user-1",
    )
    request_message = prepare_message(
        conversation_id=conversation.id,
        role="user",
        content="Run backtest",
        metadata={"chat_action": {"type": "run_backtest", "payload": {}}},
    )
    hooks = ChatTurnLifecycleHooks(
        owner="message_only",
        user_id="user-1",
        conversation_id=conversation.id,
        request_id="request-run",
        request_message=request_message,
    )

    hooks.mark_running()

    assert api_state.store.chat_turn_lifecycles == {}


@pytest.mark.parametrize(
    ("route", "expected_stage", "expected_status"),
    [
        ("cancel", "ready_to_respond", "completed"),
        ("deterministic_recovery", "await_user_reply", "completed"),
        ("builder_failure", "agent_runtime_failure", "recoverable_failed"),
    ],
)
def test_zero_provider_routes_have_one_durable_terminal_and_no_public_internals(
    monkeypatch: pytest.MonkeyPatch,
    route: str,
    expected_stage: str,
    expected_status: str,
) -> None:
    from argus.api.routers import agent as agent_router

    async def _provider_must_not_run(**_: Any):
        raise AssertionError("zero-provider route reached the runtime")
        yield

    client = _client()
    conversation = _conversation(client)
    evidence_gateway = _EvidenceCountingMemoryGateway()
    monkeypatch.setattr(api_state, "supabase_gateway", evidence_gateway)
    request_payload: dict[str, Any] = {
        "conversation_id": conversation["id"],
        "language": "en",
    }
    monkeypatch.setattr(
        agent_router,
        "stream_agent_turn_events",
        _provider_must_not_run,
    )

    if route == "cancel":
        api_state.store.messages[conversation["id"]].append(
            prepare_message(
                conversation_id=conversation["id"],
                role="assistant",
                content="Review this draft.",
                metadata={
                    "confirmation_card": {
                        "confirmation_id": "confirmation-1",
                    }
                },
            )
        )
        monkeypatch.setattr(
            agent_router,
            "checkpoint_has_pending_confirmation",
            lambda _values: True,
        )
        monkeypatch.setattr(
            agent_router,
            "confirmation_metadata_fallback_context",
            lambda **_: None,
        )
        request_payload["action"] = {
            "type": "cancel_confirmation",
            "label": "Cancel",
            "presentation": "confirmation",
            "payload": {"confirmation_id": "confirmation-1"},
        }
    elif route == "deterministic_recovery":
        monkeypatch.setattr(
            agent_router,
            "ordinary_turn_metadata_fallback_context",
            lambda **_: agent_router.RuntimeFallbackContext(
                recovery_message="That failed action is still saved.",
                recovery={
                    "code": "runtime_failure",
                    "retryable": True,
                },
            ),
        )
        request_payload["message"] = "Retry my failed action."
    else:
        monkeypatch.setattr(
            agent_router,
            "build_workflow_input",
            lambda **_: (_ for _ in ()).throw(
                ValueError("builder-secret-must-not-escape")
            ),
        )
        request_payload["message"] = "Test a private AAPL idea."

    response = client.post("/api/v1/chat/stream", json=request_payload)

    assert response.status_code == 200
    assert response.text.count("data: [DONE]") == 1
    events = _data_events(response.text)
    if expected_status == "recoverable_failed":
        assert [event["type"] for event in events] == ["error"]
        assert events[0]["code"] == expected_stage
    else:
        final = next(event["payload"] for event in events if event["type"] == "final")
        assert final["stage_outcome"] == expected_stage
    assert "builder-secret-must-not-escape" not in response.text
    for forbidden in (
        "_turn_progress",
        "input_fingerprint",
        "output_fingerprint",
        "runtime_diagnostics",
        "turn_execution",
    ):
        assert forbidden not in response.text
    _assert_one_public_terminal(
        conversation_id=conversation["id"],
        expected_status=expected_status,
        evidence_gateway=evidence_gateway,
    )


def test_typed_retryable_runtime_final_is_a_durable_failure_without_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.routers import agent as agent_router

    async def _typed_interpreter_exhaustion(**_: Any):
        yield {
            "type": "final",
            "payload": {
                "stage_outcome": "ready_to_respond",
                "assistant_response": "interpreter-secret-must-not-escape",
                "recovery": {
                    "code": "interpreter_unavailable",
                    "retryable": True,
                },
                "retry_last_turn": {
                    "message": "tampered runtime replay text",
                },
            },
        }

    client = _client()
    conversation = _conversation(client)
    evidence_gateway = _EvidenceCountingMemoryGateway()
    monkeypatch.setattr(api_state, "supabase_gateway", evidence_gateway)
    monkeypatch.setattr(
        agent_router,
        "stream_agent_turn_events",
        _typed_interpreter_exhaustion,
    )
    usage_before = dict(api_state.store.usage_counters)

    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": conversation["id"],
            "language": "en",
            "message": "Test my private AAPL idea.",
        },
    )

    assert response.status_code == 200
    assert response.text.count("data: [DONE]") == 1
    [error] = _data_events(response.text)
    assert error["type"] == "error"
    assert error["code"] == "agent_runtime_failure"
    assert error["retry_last_turn"]["request_message_id"]
    assert error["retry_last_turn"]["message"] == "Test my private AAPL idea."
    assert "interpreter-secret-must-not-escape" not in response.text
    assert "tampered runtime replay text" not in response.text
    lifecycle = _assert_one_public_terminal(
        conversation_id=conversation["id"],
        expected_status="recoverable_failed",
        evidence_gateway=evidence_gateway,
    )
    assert lifecycle["retryable"] is True
    assert api_state.store.usage_counters == usage_before


@pytest.mark.parametrize(
    ("evidence_status", "expected_outcome"),
    [
        ("completed", "completed"),
        ("recoverable_failed", "recoverable_failed"),
    ],
)
def test_owner_message_read_reconciles_stale_terminal_evidence(
    evidence_status: str,
    expected_outcome: str,
) -> None:
    client = _client()
    conversation = _conversation(client)
    user_id = client.get("/api/v1/me").json()["user"]["id"]
    gateway = MemoryChatTurnLifecycleGateway(api_state.store)
    request_id = f"request-{evidence_status}"
    accepted = gateway.accept_chat_turn(
        user_id=user_id,
        conversation_id=conversation["id"],
        request_id=request_id,
        message=prepare_message(
            conversation_id=conversation["id"],
            role="user",
            content="Test stale evidence.",
        ),
    )
    stale_at = (utcnow() - timedelta(minutes=16)).isoformat()
    api_state.store.chat_turn_lifecycles[accepted.id].update(
        accepted_at=stale_at,
        updated_at=stale_at,
    )
    failure_code = (
        "agent_runtime_failure" if evidence_status == "recoverable_failed" else None
    )
    retryable = evidence_status == "recoverable_failed"
    assistant = prepare_message(
        conversation_id=conversation["id"],
        role="assistant",
        content="Durable terminal evidence.",
        metadata={
            "agent_runtime_turn": {
                "turn_id": accepted.id,
                "request_id": request_id,
                "status": evidence_status,
                "terminal": True,
                "failure_code": failure_code,
                "retryable": retryable,
            }
        },
    )
    api_state.store.messages[conversation["id"]].append(assistant)

    response = client.get(f"/api/v1/conversations/{conversation['id']}/messages")

    assert response.status_code == 200
    lifecycle = api_state.store.chat_turn_lifecycles[accepted.id]
    assert lifecycle["status"] == "reconciled"
    assert lifecycle["reconciled_outcome"] == expected_outcome
    assert lifecycle["assistant_message_id"] == assistant.id
    assert lifecycle["failure_code"] == failure_code
    assert lifecycle["retryable"] is retryable


@pytest.mark.parametrize("language", ["en", "es-419"])
def test_legacy_onboarding_markers_do_not_leak_through_terminal_projection(
    language: str,
) -> None:
    client = _client()
    conversation = client.post(
        "/api/v1/conversations",
        json={"language": language},
    ).json()["conversation"]
    user_id = client.get("/api/v1/me").json()["user"]["id"]
    gateway = MemoryChatTurnLifecycleGateway(api_state.store)
    protocol_message = "__ONBOARDING_GOAL__:test_stock_idea"
    accepted = gateway.accept_chat_turn(
        user_id=user_id,
        conversation_id=conversation["id"],
        request_id=f"onboarding-{language}",
        message=prepare_message(
            conversation_id=conversation["id"],
            role="user",
            content=protocol_message,
        ),
    )
    assistant = prepare_message(
        conversation_id=conversation["id"],
        role="assistant",
        content=(
            "Something went wrong. Your conversation is saved."
            if language == "en"
            else "Algo salió mal. Tu conversación está guardada."
        ),
        metadata={
            "recovery": {"code": "runtime_failure", "retryable": True},
            "retry_last_turn": {
                "request_message_id": accepted.id,
                "message": protocol_message,
            },
        },
    )
    api_state.store.messages[conversation["id"]].append(assistant)
    api_state.store.chat_turn_lifecycles[accepted.id].update(
        status="recoverable_failed",
        assistant_message_id=assistant.id,
        failure_code="runtime_initialization_failed",
        retryable=True,
        terminal_at=utcnow().isoformat(),
        updated_at=utcnow().isoformat(),
    )

    response = client.get(
        f"/api/v1/conversations/{conversation['id']}/messages",
        params={"limit": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["next_cursor"] is None
    assert len(payload["items"]) == 1
    [public_assistant] = payload["items"]
    assert public_assistant["id"] == assistant.id
    assert public_assistant["metadata"]["recovery"] == {
        "code": "runtime_failure",
        "retryable": True,
    }
    assert "retry_last_turn" not in public_assistant["metadata"]
    assert protocol_message not in response.text


@pytest.mark.parametrize(
    ("language", "protocol_message"),
    [
        ("en", "__ONBOARDING_GOAL__:test_stock_idea"),
        ("es-419", "__ONBOARDING_SKIP__"),
    ],
)
@pytest.mark.parametrize("status", ["accepted", "running", "abandoned"])
def test_legacy_onboarding_marker_process_loss_never_updates_public_previews(
    language: str,
    protocol_message: str,
    status: str,
) -> None:
    client = _client()
    conversation = client.post(
        "/api/v1/conversations",
        json={"language": language},
    ).json()["conversation"]
    user_id = client.get("/api/v1/me").json()["user"]["id"]
    gateway = MemoryChatTurnLifecycleGateway(api_state.store)
    accepted = gateway.accept_chat_turn(
        user_id=user_id,
        conversation_id=conversation["id"],
        request_id=f"onboarding-{language}-{status}",
        message=prepare_message(
            conversation_id=conversation["id"],
            role="user",
            content=protocol_message,
        ),
    )
    if status == "running":
        result = gateway.transition_chat_turn(
            turn_id=accepted.id,
            to_status="running",
            assistant_message_id=None,
            reconciled_outcome=None,
            failure_code=None,
            retryable=False,
        )
        assert result.outcome == "applied"
    elif status == "abandoned":
        stale_at = (utcnow() - timedelta(minutes=16)).isoformat()
        api_state.store.chat_turn_lifecycles[accepted.id].update(
            accepted_at=stale_at,
            updated_at=stale_at,
        )
        [row] = gateway.reconcile_stale_chat_turns(
            conversation_id=conversation["id"],
            user_id=user_id,
        )
        assert row["status"] == "abandoned"

    public_messages = client.get(f"/api/v1/conversations/{conversation['id']}/messages")
    conversations = client.get("/api/v1/conversations")
    history = client.get("/api/v1/history")
    search = client.get("/api/v1/search", params={"q": "ONBOARDING"})

    assert public_messages.status_code == 200
    assert public_messages.json()["items"] == []
    assert conversations.status_code == 200
    [public_conversation] = conversations.json()["items"]
    assert public_conversation["last_message_preview"] is None
    assert public_conversation["preview"]["kind"] == "empty"
    assert public_conversation["preview"]["text"] is None
    assert history.status_code == 200
    [history_item] = history.json()["items"]
    assert history_item["subtitle"] == ""
    assert history_item["preview"]["kind"] == "empty"
    assert history_item["preview"]["text"] is None
    assert search.status_code == 200
    assert search.json()["items"] == []
    for response in (public_messages, conversations, history, search):
        assert protocol_message not in response.text


def test_valid_deterministic_controls_finish_without_workflow_initialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.routers import agent as agent_router

    client = _client()
    conversation = _conversation(client)
    evidence_gateway = _EvidenceCountingMemoryGateway()
    monkeypatch.setattr(api_state, "supabase_gateway", evidence_gateway)
    workflow_calls = 0

    def _workflow_must_not_initialize(_request: Any) -> Any:
        nonlocal workflow_calls
        workflow_calls += 1
        raise RuntimeError("runtime unavailable")

    monkeypatch.setattr(
        api_state,
        "get_agent_runtime_workflow",
        _workflow_must_not_initialize,
    )
    request_payload: dict[str, Any] = {
        "conversation_id": conversation["id"],
        "language": "en",
    }
    api_state.store.messages[conversation["id"]].append(
        prepare_message(
            conversation_id=conversation["id"],
            role="assistant",
            content="Review this draft.",
            metadata={
                "confirmation_card": {
                    "confirmation_id": "confirmation-1",
                }
            },
        )
    )
    request_payload["action"] = {
        "type": "cancel_confirmation",
        "label": "Cancel",
        "presentation": "confirmation",
        "payload": {"confirmation_id": "confirmation-1"},
    }
    monkeypatch.setattr(
        agent_router,
        "confirmation_metadata_fallback_context",
        lambda **_: None,
    )

    response = client.post(
        "/api/v1/chat/stream",
        json=request_payload,
    )

    assert response.status_code == 200
    assert workflow_calls == 0
    events = _data_events(response.text)
    final = next(event["payload"] for event in events if event["type"] == "final")
    assert final["stage_outcome"] == "ready_to_respond"
    lifecycle = _assert_one_public_terminal(
        conversation_id=conversation["id"],
        expected_status="completed",
        evidence_gateway=evidence_gateway,
    )
    assert lifecycle["retryable"] is False
    assert final["confirmation_cancelled"] == {"confirmation_id": "confirmation-1"}


def test_ordinary_message_reaches_workflow_initialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client()
    conversation = _conversation(client)
    evidence_gateway = _EvidenceCountingMemoryGateway()
    monkeypatch.setattr(api_state, "supabase_gateway", evidence_gateway)
    workflow_calls = 0

    def _unavailable_workflow(_request: Any) -> Any:
        nonlocal workflow_calls
        workflow_calls += 1
        raise RuntimeError("runtime unavailable")

    monkeypatch.setattr(
        api_state,
        "get_agent_runtime_workflow",
        _unavailable_workflow,
    )

    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": conversation["id"],
            "language": "en",
            "message": "Help me test AAPL.",
        },
    )

    assert response.status_code == 200
    assert workflow_calls == 1
    [error] = _data_events(response.text)
    assert error["type"] == "error"
    lifecycle = _assert_one_public_terminal(
        conversation_id=conversation["id"],
        expected_status="recoverable_failed",
        evidence_gateway=evidence_gateway,
    )
    assert lifecycle["retryable"] is True
    assert evidence_gateway.route_receipt_rows == []
    assert evidence_gateway.cost_ledger_rows == []


@pytest.mark.parametrize(
    "turn_kind",
    ["ordinary_text", "response_option", "durable_retry"],
)
def test_ordinary_turn_is_running_before_first_workflow_operation(
    monkeypatch: pytest.MonkeyPatch,
    turn_kind: str,
) -> None:
    client = _client()
    conversation = _conversation(client)
    user_id = client.get("/api/v1/me").json()["user"]["id"]
    source = prepare_message(
        conversation_id=conversation["id"],
        role="assistant",
        content="Which timeframe?",
        metadata={
            "clarification": {
                "options": [
                    {
                        "id": "daily",
                        "label": "Use daily bars",
                        "replacement_values": {"timeframe": "1D"},
                    }
                ]
            },
            "pending_strategy": {
                "strategy": {
                    "strategy_type": "buy_and_hold",
                    "asset_universe": ["AAPL"],
                    "asset_class": "equity",
                },
                "requested_field": "timeframe",
            },
        },
    )
    request_payload: dict[str, Any] = {
        "conversation_id": conversation["id"],
        "language": "en",
        "message": "Test AAPL.",
    }
    if turn_kind != "ordinary_text":
        api_state.store.messages[conversation["id"]].append(source)
        request_payload.pop("message")
        request_payload["action"] = {
            "type": "select_response_option",
            "label": "Use daily bars",
            "payload": {
                "source_assistant_id": source.id,
                "option_id": "daily",
                "replacement_values": {"timeframe": "1D"},
            },
        }
    if turn_kind == "durable_retry":
        lifecycle = MemoryChatTurnLifecycleGateway(api_state.store)
        original = lifecycle.accept_response_option_chat_turn(
            user_id=user_id,
            conversation_id=conversation["id"],
            request_id="request-original",
            message=prepare_message(
                conversation_id=conversation["id"],
                role="user",
                content="Use daily bars",
                metadata={
                    "chat_action": {
                        "type": "select_response_option",
                        "label": "Use daily bars",
                        "payload": {
                            "option_id": "daily",
                            "replacement_values": {"timeframe": "1D"},
                        },
                        "presentation": None,
                    }
                },
            ),
            source_assistant_id=source.id,
            expected_source_metadata=source.metadata,
            option_id="daily",
            replacement_values={"timeframe": "1D"},
        )
        assert original is not None
        _accepted_source, original_request = original
        hooks = ChatTurnLifecycleHooks(
            owner="ordinary_turn",
            user_id=user_id,
            conversation_id=conversation["id"],
            request_id="request-original",
            request_message=original_request,
        )
        hooks.recoverable_failure(
            content="Please retry.",
            metadata={"conversation_mode": "recovery"},
            failure_code="agent_runtime_failure",
            retryable=True,
        )
        request_payload["action"]["payload"].update(
            request_message_id=original_request.id,
            source_assistant_id="tampered-source",
            option_id="tampered-option",
            replacement_values={"timeframe": "5m"},
        )

    ordering: list[str] = []
    gateway = _OrderingMemoryGateway(ordering)
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)

    def _workflow_operation(_request: Any) -> Any:
        ordering.append("workflow_acquire")
        raise RuntimeError("stop after first workflow operation")

    monkeypatch.setattr(
        api_state,
        "get_agent_runtime_workflow",
        _workflow_operation,
    )

    response = client.post("/api/v1/chat/stream", json=request_payload)

    assert response.status_code == 200
    assert ordering == ["admit", "running", "workflow_acquire"]
    assert len(api_state.store.chat_turn_lifecycles) == (
        2 if turn_kind == "durable_retry" else 1
    )
    latest = max(
        api_state.store.chat_turn_lifecycles.values(),
        key=lambda row: row["accepted_at"],
    )
    assert latest["status"] == "recoverable_failed"
    assert latest["failure_code"] == "runtime_initialization_failed"
    assert api_state.store.usage_counters == {}
    assert gateway.route_receipt_rows == []
    assert gateway.cost_ledger_rows == []
    assert get_openrouter_route_receipts() == []


def test_unauthorized_conversation_does_not_reconcile_or_disclose_turn() -> None:
    client = _client()
    foreign_user_id = "00000000-0000-0000-0000-000000000099"
    conversation = memory_conversation(
        scope=PERSONAL,
        title="Foreign lifecycle",
        title_source="system_default",
        language="en",
        user_id=foreign_user_id,
    )
    gateway = MemoryChatTurnLifecycleGateway(api_state.store)
    accepted = gateway.accept_chat_turn(
        user_id=foreign_user_id,
        conversation_id=conversation.id,
        request_id="foreign-request",
        message=prepare_message(
            conversation_id=conversation.id,
            role="user",
            content="Private foreign turn.",
        ),
    )
    stale_at = (utcnow() - timedelta(minutes=16)).isoformat()
    api_state.store.chat_turn_lifecycles[accepted.id].update(
        accepted_at=stale_at,
        updated_at=stale_at,
    )
    before = dict(api_state.store.chat_turn_lifecycles[accepted.id])

    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": conversation.id,
            "message": "Try to enter a foreign conversation.",
        },
    )

    assert response.status_code == 404
    assert api_state.store.chat_turn_lifecycles[accepted.id] == before
    assert accepted.id not in response.text
    assert "foreign-request" not in response.text


def test_disconnect_without_terminal_evidence_leaves_running_turn_reconcilable() -> None:
    _gateway, accepted = _accepted_turn()
    hooks = ChatTurnLifecycleHooks(
        owner="ordinary_turn",
        user_id="user-1",
        conversation_id=accepted.conversation_id,
        request_id="request-1",
        request_message=accepted,
    )

    hooks.mark_running()

    lifecycle = api_state.store.chat_turn_lifecycles[accepted.id]
    assert lifecycle["status"] == "running"
    assert lifecycle["assistant_message_id"] is None
    assert lifecycle["terminal_at"] is None


def test_run_backtest_route_uses_message_only_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.routers import agent as agent_router

    async def _provider_must_not_run(**_: Any):
        raise AssertionError("deterministic stale Run must not reach runtime")
        yield

    monkeypatch.setattr(
        agent_router,
        "stream_agent_turn_events",
        _provider_must_not_run,
    )
    monkeypatch.setattr(
        agent_router,
        "stale_confirmation_action_message",
        lambda **_: "That draft is no longer active.",
    )
    client = _client()
    conversation = _conversation(client)

    response = client.post(
        "/api/v1/chat/stream",
        headers={"Idempotency-Key": "confirmation-1"},
        json={
            "conversation_id": conversation["id"],
            "action": {
                "type": "run_backtest",
                "label": "Run backtest",
                "presentation": "confirmation",
                "payload": {"confirmation_id": "confirmation-1"},
            },
            "language": "en",
        },
    )

    assert response.status_code == 200
    assert api_state.store.chat_turn_lifecycles == {}


@pytest.mark.parametrize(
    "action_type",
    ["change_dates", "change_asset", "adjust_assumptions"],
)
@pytest.mark.parametrize("invalid_state", ["missing", "stale", "invalid"])
@pytest.mark.parametrize("language", ["en", "es-419"])
def test_invalid_non_run_confirmation_action_rejects_before_admission(
    monkeypatch: pytest.MonkeyPatch,
    action_type: str,
    invalid_state: str,
    language: str,
) -> None:
    from argus.agent_runtime.recovery_messages import recovery_message
    from argus.api.routers import agent as agent_router

    async def _provider_must_not_run(**_: Any):
        raise AssertionError("rejected confirmation action reached the runtime")
        yield

    client = _client()
    conversation = _conversation(client)
    evidence_gateway = _EvidenceCountingMemoryGateway()
    monkeypatch.setattr(api_state, "supabase_gateway", evidence_gateway)
    monkeypatch.setattr(
        agent_router,
        "stream_agent_turn_events",
        _provider_must_not_run,
    )
    monkeypatch.setattr(
        agent_router,
        "stale_confirmation_action_message",
        lambda **_: (
            "That draft is no longer active." if invalid_state == "stale" else None
        ),
    )
    monkeypatch.setattr(
        agent_router,
        "checkpoint_has_pending_confirmation",
        lambda _values: invalid_state == "invalid",
    )
    monkeypatch.setattr(
        agent_router,
        "recent_metadata_invalidates_confirmation",
        lambda _messages: invalid_state == "invalid",
    )

    action_payload = (
        {} if invalid_state == "missing" else {"confirmation_id": "confirmation-1"}
    )
    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": conversation["id"],
            "action": {
                "type": action_type,
                "label": action_type.replace("_", " ").title(),
                "presentation": "confirmation",
                "payload": action_payload,
            },
            "language": language,
        },
    )

    assert response.status_code == 409
    expected_recovery_code = (
        "confirmation_action_missing_identity"
        if invalid_state == "missing"
        else "confirmation_action_stale_card"
    )
    assert response.json()["detail"] == recovery_message(
        expected_recovery_code,
        language=language,
    )
    assert api_state.store.messages[conversation["id"]] == []
    assert api_state.store.chat_turn_lifecycles == {}
    assert evidence_gateway.route_receipt_rows == []
    assert evidence_gateway.cost_ledger_rows == []
    assert get_openrouter_route_receipts() == []


@pytest.mark.parametrize("action_type", ["change_dates", "cancel_confirmation"])
@pytest.mark.parametrize("invalid_state", ["missing", "stale", "no_active"])
def test_invalid_non_run_confirmation_rejects_even_when_workflow_init_fails(
    monkeypatch: pytest.MonkeyPatch,
    action_type: str,
    invalid_state: str,
) -> None:
    from argus.api.routers import agent as agent_router

    client = _client()
    conversation = _conversation(client)
    evidence_gateway = _EvidenceCountingMemoryGateway()
    monkeypatch.setattr(api_state, "supabase_gateway", evidence_gateway)
    monkeypatch.setattr(
        api_state,
        "get_agent_runtime_workflow",
        lambda _request: (_ for _ in ()).throw(RuntimeError("runtime unavailable")),
    )
    monkeypatch.setattr(
        agent_router,
        "stale_confirmation_action_message",
        lambda **_: (
            "That draft is no longer active." if invalid_state == "stale" else None
        ),
    )
    action_payload = (
        {} if invalid_state == "missing" else {"confirmation_id": "confirmation-1"}
    )
    usage_before = dict(api_state.store.usage_counters)

    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": conversation["id"],
            "action": {
                "type": action_type,
                "label": action_type.replace("_", " ").title(),
                "presentation": "confirmation",
                "payload": action_payload,
            },
            "language": "en",
        },
    )

    assert response.status_code == 409
    assert api_state.store.messages[conversation["id"]] == []
    assert api_state.store.chat_turn_lifecycles == {}
    assert api_state.store.usage_counters == usage_before
    assert evidence_gateway.route_receipt_rows == []
    assert evidence_gateway.cost_ledger_rows == []
    assert get_openrouter_route_receipts() == []
