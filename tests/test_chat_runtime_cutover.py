from __future__ import annotations

import json
from contextlib import asynccontextmanager, contextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Literal

import pytest
from argus.api import state as api_state
from argus.api.main import app
from argus.api.message_store import prepare_message
from argus.domain.store import utcnow
from fastapi import Request
from fastapi.testclient import TestClient


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/api/v1/dev/reset")
    return client


def test_chat_stream_routes_through_agent_runtime_and_emits_result_card(
    monkeypatch,
) -> None:
    from argus.api.routers import agent as agent_router

    captured: dict[str, Any] = {}

    async def _fake_stream_agent_turn_events(**kwargs: Any):
        captured.update(kwargs)
        yield {"type": "stage_start", "stage": "interpret"}
        yield {"type": "token", "content": "Here is your buy-and-hold result."}
        yield {
            "type": "final",
            "payload": {
                "stage_outcome": "ready_to_respond",
                "assistant_response": "Here is your buy-and-hold result.",
                "final_response_payload": {
                    "result": {
                        "execution_status": "succeeded",
                        "resolved_strategy": {
                            "strategy_type": "buy_and_hold",
                            "symbol": "TSLA",
                        },
                        "resolved_parameters": {
                            "timeframe": "1D",
                            "date_range": {
                                "start": "2025-01-01",
                                "end": "2025-12-31",
                            },
                        },
                        "metrics": {
                            "aggregate": {"performance": {"total_return_pct": 12.5}}
                        },
                        "benchmark_metrics": {
                            "benchmark_symbol": "SPY",
                            "benchmark_return_pct": 9.2,
                        },
                        "assumptions": ["Starting capital: $10,000."],
                        "caveats": [],
                    },
                    "result_card": {
                        "title": "TSLA Buy and Hold",
                        "status_label": "Completed",
                        "rows": [
                            {"label": "Total Return", "value": "+12.5%"},
                        ],
                    },
                    "explanation_context": {
                        "strategy_type": "buy_and_hold",
                        "assumptions": ["Starting capital: $10,000."],
                        "caveats": [],
                    },
                },
            },
        }

    monkeypatch.setattr(
        agent_router,
        "stream_agent_turn_events",
        _fake_stream_agent_turn_events,
    )

    client = _client()
    conversation = client.post("/api/v1/conversations", json={}).json()["conversation"]

    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": conversation["id"],
            "message": "Buy and hold Tesla over the last year.",
            "language": "en",
        },
    )

    assert response.status_code == 200
    assert captured["thread_id"] == conversation["id"]
    assert captured["message"] == "Buy and hold Tesla over the last year."
    assert captured["user"].user_id
    assert '"type":"stage_start","stage":"interpret"' in response.text
    assert '"type":"final"' in response.text
    assert '"type":"token"' in response.text
    assert "Here is your buy-and-hold result." in response.text
    assert '"run"' in response.text

    result_line = next(
        line.removeprefix("data: ")
        for line in response.text.splitlines()
        if line.startswith("data: {") and '"run"' in line
    )
    run_payload = json.loads(result_line)["payload"]["run"]
    assert run_payload["conversation_result_card"]["title"] == "TSLA Buy and Hold"

    messages = client.get(f"/api/v1/conversations/{conversation['id']}/messages")
    assert messages.status_code == 200
    assert [message["role"] for message in messages.json()["items"]] == [
        "user",
        "assistant",
    ]


def test_refused_result_link_withholds_publication(monkeypatch) -> None:
    """When the lifecycle statement refuses the link, the turn publishes no
    result: the final frame and the persisted message carry the withheld
    recovery instead of a run, and card restoration is re-attempted with
    the standing job row."""
    from argus.api.chat import confirmation as chat_confirmation
    from argus.api.chat import result_link
    from argus.api.chat.result_link import ResultLinkOutcome
    from argus.api.routers import agent as agent_router

    async def _fake_stream_agent_turn_events(**kwargs: Any):
        yield {
            "type": "final",
            "payload": {
                "stage_outcome": "ready_to_respond",
                "assistant_response": "Here is your buy-and-hold result.",
                "final_response_payload": {
                    "result": {
                        "execution_status": "succeeded",
                        "resolved_strategy": {
                            "strategy_type": "buy_and_hold",
                            "symbol": "TSLA",
                        },
                        "resolved_parameters": {
                            "timeframe": "1D",
                            "date_range": {
                                "start": "2025-01-01",
                                "end": "2025-12-31",
                            },
                        },
                        "metrics": {
                            "aggregate": {"performance": {"total_return_pct": 12.5}}
                        },
                        "benchmark_metrics": {
                            "benchmark_symbol": "SPY",
                            "benchmark_return_pct": 9.2,
                        },
                        "assumptions": ["Starting capital: $10,000."],
                        "caveats": [],
                    },
                    "result_card": {
                        "title": "TSLA Buy and Hold",
                        "status_label": "Completed",
                        "rows": [
                            {"label": "Total Return", "value": "+12.5%"},
                        ],
                    },
                },
            },
        }

    standing_job = {"id": "job-dead", "status": "canceled", "result_run_id": None}

    def _refused_link(**kwargs: Any) -> ResultLinkOutcome:
        return ResultLinkOutcome(publishable=False, reason="refused", job=standing_job)

    restore_calls: list[dict[str, Any]] = []

    def _capture_restore(gateway: Any, *, user_id: str, job: Any) -> None:
        restore_calls.append({"user_id": user_id, "job": job})

    monkeypatch.setattr(
        agent_router,
        "stream_agent_turn_events",
        _fake_stream_agent_turn_events,
    )
    monkeypatch.setattr(result_link, "link_shadow_backtest_job_result", _refused_link)
    monkeypatch.setattr(
        chat_confirmation,
        "restore_pending_card_for_failed_job",
        _capture_restore,
    )

    client = _client()
    conversation = client.post("/api/v1/conversations", json={}).json()["conversation"]
    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": conversation["id"],
            "message": "Buy and hold Tesla over the last year.",
            "language": "en",
        },
    )

    assert response.status_code == 200
    final_line = next(
        line.removeprefix("data: ")
        for line in response.text.splitlines()
        if line.startswith("data: {") and '"type":"final"' in line.replace(" ", "")
    )
    final_payload = json.loads(final_line)["payload"]
    assert "run" not in final_payload
    assert "result_card" not in final_payload
    assert final_payload["recovery"]["code"] == "run_result_withheld"
    assert final_payload["recovery"]["retryable"] is False
    assert restore_calls == [{"user_id": restore_calls[0]["user_id"], "job": standing_job}]

    messages = client.get(f"/api/v1/conversations/{conversation['id']}/messages")
    assistant = messages.json()["items"][-1]
    assert assistant["role"] == "assistant"
    metadata = assistant["metadata"]
    assert metadata["recovery"]["code"] == "run_result_withheld"
    assert metadata["result_link_refused"]["job_id"] == "job-dead"
    assert metadata["result_link_refused"]["job_status"] == "canceled"
    assert metadata["result_link_refused"]["unpublished_run_id"]
    for absent in ("result_card", "result_run_id", "latest_run_id", "result_fact_bank"):
        assert absent not in metadata, absent
    assert "no result to show" in assistant["content"]


@pytest.mark.parametrize("account_kind", ["guest", "registered"])
@pytest.mark.parametrize("threaded", [False, True])
def test_inline_and_threaded_streams_use_one_scope(
    monkeypatch: pytest.MonkeyPatch,
    threaded: bool,
    account_kind: Literal["guest", "registered"],
) -> None:
    from argus.agent_runtime.turn_execution import active_turn_execution
    from argus.api.dependencies import current_user
    from argus.api.guest_access import (
        AccountContext,
        guest_capabilities,
        registered_capabilities,
        store_account_context,
    )
    from argus.api.routers import agent as agent_router
    from argus.llm.openrouter_key_policy import (
        OpenRouterTrafficClass,
        openrouter_traffic_class,
        resolve_openrouter_api_key,
    )

    observed_contexts: list[object | None] = []
    observed_openrouter_keys: list[str] = []
    observed_scope_cleanup: list[bool] = []
    persisted_receipt_metadata: list[dict[str, Any]] = []

    async def _fake_stream_agent_turn_events(**_: Any):
        observed_contexts.append(active_turn_execution())
        observed_openrouter_keys.append(resolve_openrouter_api_key())
        yield {"type": "stage_start", "stage": "interpret"}
        yield {
            "type": "final",
            "_turn_progress": {
                "output_fingerprint": "a" * 64,
                "progress_outcome": "clarification",
                "terminal": "clarification",
                "terminal_reason": "runtime_final",
            },
            "payload": {
                "stage_outcome": "await_user_reply",
                "assistant_response": "What date range should I use for AAPL?",
                "pending_strategy": {
                    "strategy": {
                        "strategy_type": "buy_and_hold",
                        "asset_universe": ["AAPL"],
                        "asset_class": "equity",
                    },
                    "requested_field": "date_range",
                    "missing_required_fields": ["date_range"],
                },
                "response_intent": {
                    "kind": "clarification",
                    "requested_fields": ["date_range"],
                    "semantic_needs": ["period"],
                },
            },
        }

    @asynccontextmanager
    async def _isolated_workflow():
        yield "isolated-workflow"

    def _capture_receipts(**kwargs: Any) -> None:
        persisted_receipt_metadata.append(dict(kwargs["metadata"]))

    @contextmanager
    def _observed_openrouter_scope(kind: OpenRouterTrafficClass):
        with openrouter_traffic_class(kind):
            yield
        with pytest.raises(RuntimeError, match="traffic class"):
            resolve_openrouter_api_key()
        observed_scope_cleanup.append(True)

    monkeypatch.setattr(agent_router, "runtime_worker_enabled", lambda: threaded)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("OPENROUTER_API_KEY", "dev-only")
    monkeypatch.setenv("CUADRAO_PROD_OPENROUTER_API_KEY", "registered-key")
    monkeypatch.setenv("CUADRAO_GUEST_ACCESS_OPENROUTER_API_KEY", "guest-key")
    monkeypatch.setattr(
        agent_router,
        "stream_agent_turn_events",
        _fake_stream_agent_turn_events,
    )
    monkeypatch.setattr(
        agent_router.api_state,
        "isolated_agent_runtime_workflow",
        _isolated_workflow,
    )
    monkeypatch.setattr(agent_router, "persist_route_receipts", _capture_receipts)
    monkeypatch.setattr(
        agent_router,
        "openrouter_traffic_class",
        _observed_openrouter_scope,
    )

    client = _client()
    user = api_state.store.get_or_create_dev_user()

    def _verified_current_user(request: Request):
        store_account_context(
            request,
            AccountContext(
                kind=account_kind,
                user_id=user.id,
                expires_at=(
                    utcnow() + timedelta(days=7)
                    if account_kind == "guest"
                    else None
                ),
                capabilities=(
                    guest_capabilities()
                    if account_kind == "guest"
                    else registered_capabilities()
                ),
            ),
        )
        return user

    app.dependency_overrides[current_user] = _verified_current_user
    try:
        conversation = client.post("/api/v1/conversations", json={}).json()[
            "conversation"
        ]
        response = client.post(
            "/api/v1/chat/stream",
            json={
                "conversation_id": conversation["id"],
                "message": "Test buy and hold AAPL.",
                "language": "en",
            },
        )
    finally:
        app.dependency_overrides.pop(current_user, None)

    assert response.status_code == 200
    assert len(observed_contexts) == 1
    assert observed_contexts[0] is not None
    assert observed_openrouter_keys == [
        "guest-key" if account_kind == "guest" else "registered-key"
    ]
    assert observed_scope_cleanup == [True]
    with pytest.raises(RuntimeError, match="traffic class"):
        resolve_openrouter_api_key()
    assert len(persisted_receipt_metadata) == 1
    summary = persisted_receipt_metadata[0]["turn_execution"]
    assert summary["terminal"] == "clarification"
    assert summary["progress_outcome"] == "clarification"
    assert summary["output_fingerprint"] == "a" * 64
    assert "_turn_progress" not in response.text


@pytest.mark.parametrize("threaded", [False, True])
def test_post_admission_builder_failure_owns_recovery_and_evidence(
    monkeypatch: pytest.MonkeyPatch,
    threaded: bool,
) -> None:
    from argus.agent_runtime.recovery_messages import recovery_message
    from argus.agent_runtime.turn_execution import active_turn_execution
    from argus.api.routers import agent as agent_router

    persisted_receipt_metadata: list[dict[str, Any]] = []

    def _broken_workflow_input(**_: Any) -> dict[str, Any]:
        raise ValueError("builder-secret-must-not-escape")

    async def _provider_must_not_run(**_: Any):
        raise AssertionError("provider runtime must not start after builder failure")
        yield

    def _capture_receipts(**kwargs: Any) -> None:
        persisted_receipt_metadata.append(dict(kwargs["metadata"]))

    monkeypatch.setattr(agent_router, "runtime_worker_enabled", lambda: threaded)
    monkeypatch.setattr(agent_router, "build_workflow_input", _broken_workflow_input)
    monkeypatch.setattr(
        agent_router,
        "stream_agent_turn_events",
        _provider_must_not_run,
    )
    monkeypatch.setattr(agent_router, "persist_route_receipts", _capture_receipts)

    client = _client()
    conversation = client.post("/api/v1/conversations", json={}).json()["conversation"]
    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": conversation["id"],
            "message": "Prueba una idea secreta.",
            "language": "es-419",
        },
    )

    assert response.status_code == 200
    assert response.text.count('"type":"error"') == 1
    assert response.text.count("data: [DONE]") == 1
    assert '"type":"final"' not in response.text
    messages = client.get(f"/api/v1/conversations/{conversation['id']}/messages").json()[
        "items"
    ]
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[-1]["content"] == recovery_message(
        "runtime_failure",
        language="es-419",
    )
    assert len(persisted_receipt_metadata) == 1
    summary = persisted_receipt_metadata[0]["turn_execution"]
    assert summary["terminal"] == "recoverable_failed"
    assert summary["progress_outcome"] == "recoverable_failed"
    assert summary["calls_reserved"] == 0
    assert summary["provider_receipt_count"] == 0
    assert "builder-secret-must-not-escape" not in json.dumps(summary)
    assert "Prueba una idea secreta" not in json.dumps(summary)
    assert active_turn_execution() is None


@pytest.mark.parametrize(
    ("route", "expected_terminal"),
    [
        ("cancel", "finished"),
        ("deterministic_recovery", "redirected"),
    ],
)
def test_early_accepted_routes_persist_one_typed_turn_summary(
    monkeypatch: pytest.MonkeyPatch,
    route: str,
    expected_terminal: str,
) -> None:
    from argus.agent_runtime.turn_execution import active_turn_execution
    from argus.api.routers import agent as agent_router

    persisted_receipt_metadata: list[dict[str, Any]] = []

    async def _provider_must_not_run(**_: Any):
        raise AssertionError("early accepted routes must not call the provider")
        yield

    def _capture_receipts(**kwargs: Any) -> None:
        persisted_receipt_metadata.append(dict(kwargs["metadata"]))

    monkeypatch.setattr(
        agent_router,
        "stream_agent_turn_events",
        _provider_must_not_run,
    )
    monkeypatch.setattr(agent_router, "persist_route_receipts", _capture_receipts)

    client = _client()
    conversation = client.post("/api/v1/conversations", json={}).json()["conversation"]
    request_payload: dict[str, Any] = {
        "conversation_id": conversation["id"],
        "language": "en",
    }
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
    else:
        monkeypatch.setattr(
            agent_router,
            "stale_confirmation_action_message",
            lambda **_: "That draft is no longer active.",
        )
        request_payload["action"] = {
            "type": "run_backtest",
            "label": "Run backtest",
            "presentation": "confirmation",
            "payload": {"confirmation_id": "confirmation-1"},
        }

    request_headers = (
        {"Idempotency-Key": "confirmation-1"}
        if route == "deterministic_recovery"
        else None
    )
    response = client.post(
        "/api/v1/chat/stream",
        json=request_payload,
        headers=request_headers,
    )

    assert response.status_code == 200
    assert response.text.count("data: [DONE]") == 1
    assert len(persisted_receipt_metadata) == 1
    summary = persisted_receipt_metadata[0]["turn_execution"]
    assert summary["terminal"] == expected_terminal
    assert summary["progress_outcome"] == expected_terminal
    assert summary["calls_reserved"] == 0
    assert summary["provider_receipt_count"] == 0
    summary_json = json.dumps(summary)
    assert "That draft is no longer active." not in summary_json
    assert active_turn_execution() is None


def test_ordinary_message_enters_runtime_and_persists_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.agent_runtime.turn_execution import active_turn_execution
    from argus.api.routers import agent as agent_router

    runtime_calls = 0
    persisted_receipt_metadata: list[dict[str, Any]] = []

    async def _runtime_events(**_: Any):
        nonlocal runtime_calls
        runtime_calls += 1
        yield {"type": "stage_start", "stage": "interpret"}
        yield {
            "type": "final",
            "_turn_progress": {
                "output_fingerprint": "b" * 64,
                "progress_outcome": "advanced",
                "terminal": "advanced",
                "terminal_reason": "runtime_final",
            },
            "payload": {
                "stage_outcome": "ready_to_respond",
                "assistant_response": "I can help test Apple.",
            },
        }

    def _capture_receipts(**kwargs: Any) -> None:
        persisted_receipt_metadata.append(dict(kwargs["metadata"]))

    monkeypatch.setattr(agent_router, "stream_agent_turn_events", _runtime_events)
    monkeypatch.setattr(agent_router, "persist_route_receipts", _capture_receipts)

    client = _client()
    conversation = client.post("/api/v1/conversations", json={}).json()["conversation"]

    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": conversation["id"],
            "message": "I want to test Apple.",
            "language": "en",
        },
    )

    assert response.status_code == 200
    assert runtime_calls == 1
    assert len(persisted_receipt_metadata) == 1
    summary = persisted_receipt_metadata[0]["turn_execution"]
    assert summary["terminal"] == "advanced"
    assert summary["progress_outcome"] == "advanced"
    assert summary["calls_reserved"] == 0
    assert summary["provider_receipt_count"] == 0
    assert "_turn_progress" not in response.text
    assert active_turn_execution() is None


def test_chat_stream_production_path_uses_astream_events_not_invoke() -> None:
    api_source = Path("src/argus/api/main.py").read_text(encoding="utf-8")
    runtime_source = Path("src/argus/agent_runtime/runtime.py").read_text(
        encoding="utf-8"
    )

    assert ".astream_events(" in runtime_source
    assert "workflow.invoke(" not in api_source
    assert "workflow.invoke(" not in runtime_source
    assert "InMemorySessionManager" not in api_source
    assert "InMemorySessionManager" not in runtime_source


def test_chat_stream_falls_back_conversationally_for_unsupported_runtime_result(
    monkeypatch,
) -> None:
    from argus.api.routers import agent as agent_router

    async def _fake_stream_agent_turn_events(**_: Any):
        yield {"type": "stage_start", "stage": "interpret"}
        yield {
            "type": "final",
            "payload": {
                "stage_outcome": "await_user_reply",
                "assistant_prompt": (
                    "Trailing stops are not supported yet. "
                    "I can help reframe this into a supported backtest."
                ),
                "final_response_payload": {
                    "error": "unsupported_capability",
                },
            },
        }

    monkeypatch.setattr(
        agent_router,
        "stream_agent_turn_events",
        _fake_stream_agent_turn_events,
    )

    client = _client()
    conversation = client.post("/api/v1/conversations", json={}).json()["conversation"]

    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": conversation["id"],
            "message": "Backtest Tesla with a 5% trailing stop.",
            "language": "en",
        },
    )

    assert response.status_code == 200
    assert '"type":"token"' in response.text
    assert "supported backtest" in response.text.lower()
    assert '"run"' not in response.text


def test_runtime_confirmation_card_resolves_relative_period_and_natural_actions(
    monkeypatch,
) -> None:
    from argus.api.chat import confirmation as chat_service

    monkeypatch.setattr(
        chat_service,
        "_confirmation_today",
        lambda: date(2026, 5, 3),
    )

    card = chat_service.runtime_confirmation_card(
        {
            "stage_outcome": "await_approval",
            "confirmation_payload": {
                "strategy": {
                    "strategy_type": "rsi_threshold",
                    "strategy_thesis": "Run the supported RSI preset on Google.",
                    "asset_universe": ["GOOGL"],
                    "asset_class": "equity",
                    "date_range": "past year",
                    "entry_logic": "Buy when RSI(14) drops to 30 or below",
                    "exit_logic": "Sell when RSI(14) rises to 55 or above",
                    "capital_amount": 10000,
                },
                "optional_parameters": {
                    "timeframe": {"value": "1D", "source": "default"},
                    "initial_capital": {"value": 1000.0, "source": "default"},
                },
                "launch_payload": {
                    "strategy_type": "indicator_threshold",
                    "symbol": "GOOGL",
                    "symbols": ["GOOGL"],
                    "timeframe": "1D",
                    "date_range": {"start": "2025-05-03", "end": "2026-05-03"},
                    "entry_rule": {
                        "indicator": "rsi",
                        "operator": "below",
                        "period": 14,
                        "threshold": 30,
                    },
                    "exit_rule": {
                        "indicator": "rsi",
                        "operator": "above",
                        "period": 14,
                        "threshold": 55,
                    },
                    "sizing_mode": "capital_amount",
                    "capital_amount": 10000,
                    "benchmark_symbol": "SPY",
                },
                "validation": {"executable": True},
            },
        }
    )

    assert card is not None
    assert card["date_range"]["start"] == "2025-05-03"
    assert card["date_range"]["end"] == "2026-05-03"
    assert card["date_range"]["display"] == "May 3, 2025 - May 3, 2026"
    period = next(row for row in card["rows"] if row["key"] == "period")
    assert period["labelKey"] == "chat.confirmation.rows.period"
    assert period["value"] == card["date_range"]["display"]
    run_action = next(
        action for action in card["actions"] if action["type"] == "run_backtest"
    )
    assert run_action["id"] == "run-backtest"
    assert run_action["presentation"] == "confirmation"
    assert run_action["payload"]["confirmation_id"] == card["confirmation_id"]
    assert run_action["payload"]["launch_payload_hash"]


def test_runtime_confirmation_card_expands_compact_period_and_hides_indicator_cadence(
    monkeypatch,
) -> None:
    from argus.api.chat import confirmation as chat_service

    monkeypatch.setattr(
        chat_service,
        "_confirmation_today",
        lambda: date(2026, 5, 3),
    )

    card = chat_service.runtime_confirmation_card(
        {
            "stage_outcome": "await_approval",
            "confirmation_payload": {
                "strategy": {
                    "strategy_type": "rsi_threshold",
                    "strategy_thesis": "Run the supported RSI preset on Google.",
                    "asset_universe": ["GOOGL"],
                    "asset_class": "equity",
                    "date_range": "1y",
                    "cadence": "daily",
                    "entry_logic": "RSI drops below 30",
                    "exit_logic": "RSI rises above 55",
                    "capital_amount": 10000,
                },
                "optional_parameters": {},
            },
        }
    )

    assert card is not None
    rows_by_key = {row["key"]: row for row in card["rows"]}
    assert card["date_range"]["start"] == "2025-05-03"
    assert card["date_range"]["end"] == "2026-05-03"
    assert card["date_range"]["display"] == "May 3, 2025 - May 3, 2026"
    assert rows_by_key["period"]["labelKey"] == "chat.confirmation.rows.period"
    assert rows_by_key["period"]["value"] == card["date_range"]["display"]
    assert "cadence" not in rows_by_key


def test_runtime_confirmation_card_simplifies_counted_one_year_period(
    monkeypatch,
) -> None:
    from argus.api.chat import confirmation as chat_service

    monkeypatch.setattr(
        chat_service,
        "_confirmation_today",
        lambda: date(2026, 5, 3),
    )

    card = chat_service.runtime_confirmation_card(
        {
            "stage_outcome": "await_approval",
            "confirmation_payload": {
                "strategy": {
                    "strategy_type": "rsi_threshold",
                    "strategy_thesis": "Run the supported RSI preset on Google.",
                    "asset_universe": ["GOOGL"],
                    "asset_class": "equity",
                    "date_range": "past 1 year",
                    "entry_logic": "RSI drops below 30",
                    "exit_logic": "RSI rises above 55",
                },
                "optional_parameters": {},
            },
        }
    )

    assert card is not None
    rows_by_key = {row["key"]: row for row in card["rows"]}
    assert card["date_range"]["start"] == "2025-05-03"
    assert card["date_range"]["end"] == "2026-05-03"
    assert card["date_range"]["display"] == "May 3, 2025 - May 3, 2026"
    assert rows_by_key["period"]["labelKey"] == "chat.confirmation.rows.period"
    assert rows_by_key["period"]["value"] == card["date_range"]["display"]


def test_runtime_confirmation_card_formats_machine_date_tokens(
    monkeypatch,
) -> None:
    from argus.api.chat import confirmation as chat_service

    monkeypatch.setattr(
        chat_service,
        "_confirmation_today",
        lambda: date(2026, 5, 3),
    )

    def card_for(date_range: str) -> dict[str, Any]:
        card = chat_service.runtime_confirmation_card(
            {
                "stage_outcome": "await_approval",
                "confirmation_payload": {
                    "strategy": {
                        "strategy_type": "indicator_threshold",
                        "strategy_thesis": "Run a dip-buying strategy on Apple.",
                        "asset_universe": ["AAPL"],
                        "asset_class": "equity",
                        "date_range": date_range,
                        "entry_logic": "Buy when RSI <= 30",
                        "exit_logic": "Sell when RSI >= 55",
                    },
                    "optional_parameters": {},
                },
            }
        )
        assert card is not None
        return card

    last_three_months = card_for("last_3_months")
    ytd = card_for("year_to_date")

    last_rows = {row["key"]: row for row in last_three_months["rows"]}
    ytd_rows = {row["key"]: row for row in ytd["rows"]}
    assert last_three_months["strategy_type"] == "indicator_threshold"
    assert last_three_months["date_range"]["start"] == "2026-02-03"
    assert last_three_months["date_range"]["end"] == "2026-05-03"
    assert last_three_months["date_range"]["display"] == "February 3, 2026 - May 3, 2026"
    assert last_rows["period"]["labelKey"] == "chat.confirmation.rows.period"
    assert last_rows["period"]["value"] == last_three_months["date_range"]["display"]
    assert ytd["date_range"]["start"] == "2026-01-01"
    assert ytd["date_range"]["end"] == "2026-05-03"
    assert ytd["date_range"]["display"] == "January 1, 2026 - May 3, 2026"
    assert ytd_rows["period"]["labelKey"] == "chat.confirmation.rows.period"
    assert ytd_rows["period"]["value"] == ytd["date_range"]["display"]


def test_runtime_confirmation_card_formats_structured_date_range(
    monkeypatch,
) -> None:
    from argus.api.chat import confirmation as chat_service

    monkeypatch.setattr(
        chat_service,
        "_confirmation_today",
        lambda: date(2026, 5, 3),
    )

    card = chat_service.runtime_confirmation_card(
        {
            "stage_outcome": "await_approval",
            "confirmation_payload": {
                "strategy": {
                    "strategy_type": "buy_and_hold",
                    "strategy_thesis": "Buy and hold Bitcoin from January 1 last year.",
                    "asset_universe": ["BTC"],
                    "asset_class": "crypto",
                    "date_range": {"start": "2025-01-01", "end": "today"},
                },
                "optional_parameters": {},
            },
        }
    )

    assert card is not None
    assert card["asset_class"] == "crypto"
    rows_by_label = {row["label"]: row["value"] for row in card["rows"]}
    assert rows_by_label["Period"] == "January 1, 2025 - May 3, 2026"
