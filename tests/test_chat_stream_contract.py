from __future__ import annotations

import asyncio
import json
import time
from contextlib import asynccontextmanager
from threading import Event
from typing import Any

import pytest
from argus.api.guest_access import registered_account_context
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
async def test_threaded_runtime_event_source_does_not_block_api_event_loop() -> None:
    from argus.api.chat.runtime_worker import threaded_runtime_event_source

    async def _blocking_runtime_events():
        yield {"type": "stage_start", "stage": "interpret"}
        time.sleep(0.05)
        yield {"type": "final", "payload": {"stage_outcome": "await_approval"}}

    runtime_events = threaded_runtime_event_source(_blocking_runtime_events)

    first_event = await asyncio.wait_for(anext(runtime_events), timeout=1)
    assert first_event == {"type": "stage_start", "stage": "interpret"}

    async def _event_loop_tick() -> bool:
        await asyncio.sleep(0.01)
        return True

    next_runtime_event = asyncio.create_task(anext(runtime_events))
    tick = asyncio.create_task(_event_loop_tick())

    assert await asyncio.wait_for(tick, timeout=1) is True
    assert not next_runtime_event.done()
    assert await asyncio.wait_for(next_runtime_event, timeout=1) == {
        "type": "final",
        "payload": {"stage_outcome": "await_approval"},
    }
    await runtime_events.aclose()


@pytest.mark.asyncio
async def test_threaded_runtime_event_source_cancels_worker_on_close() -> None:
    from threading import Event

    from argus.api.chat.runtime_worker import threaded_runtime_event_source

    worker_closed = Event()

    async def _long_running_runtime_events():
        try:
            yield {"type": "stage_start", "stage": "interpret"}
            await asyncio.Event().wait()
        finally:
            worker_closed.set()

    runtime_events = threaded_runtime_event_source(_long_running_runtime_events)

    assert await asyncio.wait_for(anext(runtime_events), timeout=1) == {
        "type": "stage_start",
        "stage": "interpret",
    }

    await runtime_events.aclose()

    assert await asyncio.to_thread(worker_closed.wait, 1)


@pytest.mark.asyncio
async def test_threaded_runtime_event_source_stops_when_consumer_loop_rejects_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.chat import runtime_worker

    worker_can_continue = Event()
    worker_finished = Event()
    worker_exceptions: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    class _Logger:
        def debug(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        def exception(self, *args: Any, **kwargs: Any) -> None:
            worker_exceptions.append((args, kwargs))

        def warning(self, *_args: Any, **_kwargs: Any) -> None:
            return None

    monkeypatch.setattr(runtime_worker, "logger", _Logger())

    async def _runtime_events():
        try:
            yield {"type": "stage_start", "stage": "interpret"}
            while not worker_can_continue.is_set():
                await asyncio.sleep(0.01)
            yield {"type": "final", "payload": {"stage_outcome": "await_approval"}}
        finally:
            worker_finished.set()

    runtime_events = runtime_worker.threaded_runtime_event_source(_runtime_events)

    assert await asyncio.wait_for(anext(runtime_events), timeout=1) == {
        "type": "stage_start",
        "stage": "interpret",
    }

    loop = asyncio.get_running_loop()
    original_call_soon_threadsafe = loop.call_soon_threadsafe

    def _reject_worker_send(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("Event loop is closed")

    monkeypatch.setattr(loop, "call_soon_threadsafe", _reject_worker_send)
    try:
        worker_can_continue.set()
        deadline = time.monotonic() + 1
        while (
            time.monotonic() < deadline
            and not worker_finished.is_set()
            and not worker_exceptions
        ):
            await asyncio.sleep(0.01)
    finally:
        monkeypatch.setattr(loop, "call_soon_threadsafe", original_call_soon_threadsafe)
        await runtime_events.aclose()

    assert worker_finished.is_set()
    assert worker_exceptions == []


@pytest.mark.asyncio
async def test_threaded_runtime_event_source_reports_stuck_worker_after_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.chat import runtime_worker

    warnings: list[tuple[str, dict[str, Any]]] = []

    class _Logger:
        def debug(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        def exception(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        def warning(self, message: str, **kwargs: Any) -> None:
            warnings.append((message, kwargs))

    monkeypatch.setattr(runtime_worker, "logger", _Logger())

    class _BlockedRuntimeEvents:
        def __init__(self) -> None:
            self._index = 0

        def __aiter__(self) -> "_BlockedRuntimeEvents":
            return self

        async def __anext__(self) -> dict[str, Any]:
            self._index += 1
            if self._index == 1:
                return {"type": "stage_start", "stage": "interpret"}
            if self._index == 2:
                time.sleep(0.2)
                return {
                    "type": "final",
                    "payload": {"stage_outcome": "await_approval"},
                }
            raise StopAsyncIteration

    def _blocked_runtime_events() -> _BlockedRuntimeEvents:
        return _BlockedRuntimeEvents()

    runtime_events = runtime_worker.threaded_runtime_event_source(
        _blocked_runtime_events
    )

    assert await asyncio.wait_for(anext(runtime_events), timeout=1) == {
        "type": "stage_start",
        "stage": "interpret",
    }

    await runtime_events.aclose()

    assert warnings
    assert warnings[-1][0] == "Threaded chat runtime worker still running after cancel"
    assert warnings[-1][1]["future_done"] is False
    assert warnings[-1][1]["worker_task_done"] is False


def test_runtime_worker_auto_mode_is_reserved_for_prod_like_streams(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.chat.runtime_worker import runtime_worker_enabled

    monkeypatch.delenv("CUADRAO_RUNTIME_STREAM_WORKER", raising=False)
    monkeypatch.setenv("CUADRAO_PERSISTENCE_MODE", "memory")
    monkeypatch.setenv("CUADRAO_CHECKPOINTER_MODE", "memory")

    assert runtime_worker_enabled() is False

    monkeypatch.setenv("CUADRAO_PERSISTENCE_MODE", "supabase")
    assert runtime_worker_enabled() is True

    monkeypatch.setenv("CUADRAO_PERSISTENCE_MODE", "memory")
    monkeypatch.setenv("CUADRAO_CHECKPOINTER_MODE", "postgres")
    assert runtime_worker_enabled() is True

    monkeypatch.setenv("CUADRAO_RUNTIME_STREAM_WORKER", "false")
    assert runtime_worker_enabled() is False

    monkeypatch.setenv("CUADRAO_RUNTIME_STREAM_WORKER", "true")
    assert runtime_worker_enabled() is True


def test_chat_stream_worker_mode_uses_isolated_runtime_workflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.routers import agent as agent_router

    workflows_seen: list[str] = []

    async def _fake_stream_agent_turn_events(**kwargs: Any):
        workflows_seen.append(kwargs["workflow"])
        yield {"type": "stage_start", "stage": "interpret"}
        yield {
            "type": "final",
            "payload": {
                "stage_outcome": "ready_to_respond",
                "assistant_response": "Ready.",
            },
        }

    @asynccontextmanager
    async def _isolated_workflow():
        yield "worker_loop_workflow"

    monkeypatch.setattr(agent_router, "runtime_worker_enabled", lambda: True)
    monkeypatch.setattr(
        agent_router,
        "stream_agent_turn_events",
        _fake_stream_agent_turn_events,
    )
    monkeypatch.setattr(
        agent_router.api_state,
        "get_agent_runtime_workflow",
        lambda request: "main_loop_workflow",
    )
    monkeypatch.setattr(
        agent_router.api_state,
        "isolated_agent_runtime_workflow",
        _isolated_workflow,
        raising=False,
    )

    client = _client()
    conversation = _conversation(client)

    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": conversation["id"],
            "message": "Explain Apple",
            "language": "en",
        },
    )

    assert response.status_code == 200
    assert workflows_seen == ["worker_loop_workflow"]


def test_internal_agent_runtime_turn_is_not_exposed_by_launch_api() -> None:
    paths = {
        getattr(route, "path", "")
        for route in app.routes
        if getattr(route, "path", "")
    }

    assert "/api/v1/chat/stream" in paths
    assert "/internal/agent-runtime/turn" not in paths


def test_chat_stream_confirmation_uses_final_payload_without_named_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.routers import agent as agent_router

    async def _fake_stream_agent_turn_events(**_: Any):
        yield {"type": "stage_start", "stage": "interpret"}
        yield {"type": "stage_outcome", "outcome": "ready_for_confirmation"}
        yield {
            "type": "final",
            "payload": {
                "stage_outcome": "await_approval",
                "assistant_response": "Ready to test AAPL with buy and hold.",
                "confirmation_payload": {
                        "strategy": {
                            "strategy_type": "buy_and_hold",
                            "asset_universe": ["AAPL"],
                            "date_range": {"start": "2025-05-03", "end": "2026-05-03"},
                            "capital_amount": 10000,
                        },
                        "optional_parameters": {},
                        "launch_payload": {
                            "strategy_type": "buy_and_hold",
                            "symbol": "AAPL",
                            "symbols": ["AAPL"],
                            "timeframe": "1D",
                            "date_range": {
                                "start": "2025-05-03",
                                "end": "2026-05-03",
                            },
                            "sizing_mode": "capital_amount",
                            "capital_amount": 10000,
                            "benchmark_symbol": "SPY",
                        },
                        "validation": {
                            "status": "ready_to_run",
                            "executable": True,
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
    conversation = _conversation(client)

    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": conversation["id"],
            "message": "Buy and hold Apple over the past year",
            "language": "en",
        },
    )

    assert response.status_code == 200
    assert "event:" not in response.text
    assert response.text.count("data: [DONE]") == 1
    payload = _final_payload(response.text)
    assert payload["confirmation"]["actions"][0]["type"] == "run_backtest"
    assert payload.get("assistant_response") is None
    assert payload["message_id"]
    assert "run" not in payload


@pytest.mark.parametrize(
    ("adjustment_reason", "expected_sidecar_count"),
    [
        ("provider_coverage_adjustment", 1),
        ("calendar_alignment", 0),
    ],
)
def test_chat_stream_persists_and_reloads_coverage_adjustment_materiality(
    monkeypatch: pytest.MonkeyPatch,
    adjustment_reason: str,
    expected_sidecar_count: int,
) -> None:
    from argus.api.routers import agent as agent_router

    requested = {"start": "2024-01-01", "end": "2024-01-05"}
    effective = {"start": "2024-01-02", "end": "2024-01-05"}
    confirmation_payload = {
        "strategy": {
            "strategy_type": "buy_and_hold",
            "asset_universe": ["AAPL"],
            "asset_class": "equity",
            "date_range": effective,
            "capital_amount": 10_000,
        },
        "optional_parameters": {},
        "launch_payload": {
            "strategy_type": "buy_and_hold",
            "symbol": "AAPL",
            "symbols": ["AAPL"],
            "asset_class": "equity",
            "timeframe": "1D",
            "date_range": effective,
            "requested_date_range": requested,
            "coverage_preflight": {
                "outcome": "adjusted_coverage",
                "requested_date_range": requested,
                "effective_date_range": effective,
                "adjustment_reason": adjustment_reason,
                "preflight_id": "sha256:coverage-materiality",
            },
            "sizing_mode": "capital_amount",
            "capital_amount": 10_000,
            "benchmark_symbol": "SPY",
        },
        "validation": {"status": "ready_to_run", "executable": True},
    }

    async def _fake_stream_agent_turn_events(**_: Any):
        yield {"type": "stage_start", "stage": "interpret"}
        yield {"type": "stage_outcome", "outcome": "ready_for_confirmation"}
        yield {
            "type": "final",
            "payload": {
                "stage_outcome": "await_approval",
                "assistant_response": "Ready to test AAPL.",
                "confirmation_payload": confirmation_payload,
            },
        }

    monkeypatch.setattr(
        agent_router,
        "stream_agent_turn_events",
        _fake_stream_agent_turn_events,
    )
    client = _client()
    conversation = _conversation(client)

    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": conversation["id"],
            "message": "Buy and hold AAPL in early January 2024",
            "language": "en",
        },
    )

    assert response.status_code == 200
    live_payload = _final_payload(response.text)
    live_card = live_payload["confirmation"]
    assert int("period_adjustment" in live_card) == expected_sidecar_count

    messages = client.get(f"/api/v1/conversations/{conversation['id']}/messages").json()[
        "items"
    ]
    persisted = next(
        message
        for message in reversed(messages)
        if message["role"] == "assistant"
        and message["metadata"].get("confirmation_payload")
    )
    metadata = persisted["metadata"]
    persisted_coverage = metadata["confirmation_payload"]["launch_payload"][
        "coverage_preflight"
    ]
    assert persisted_coverage["requested_date_range"] == requested
    assert persisted_coverage["effective_date_range"] == effective
    assert persisted_coverage["adjustment_reason"] == adjustment_reason
    reloaded_card = metadata["confirmation_card"]
    assert int("period_adjustment" in reloaded_card) == expected_sidecar_count
    assert reloaded_card == live_card


def test_chat_stream_persists_provider_canonicalized_company_name_asset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.agent_runtime.capabilities.contract import (
        build_default_capability_contract,
    )
    from argus.agent_runtime.graph.workflow import build_workflow
    from argus.agent_runtime.resolution import AssetResolution
    from argus.agent_runtime.stages import interpret as interpret_module
    from argus.agent_runtime.stages.interpret_types import StructuredInterpretation
    from argus.agent_runtime.state.models import ResolutionProvenance, StrategySummary
    from argus.api import state as api_state
    from argus.domain.market_data.assets import ResolvedAsset

    class ApplePseudoTickerInterpreter:
        async def ainvoke(self, request: Any) -> StructuredInterpretation:
            return StructuredInterpretation(
                intent="backtest_execution",
                task_relation="new_task",
                requires_clarification=False,
                user_goal_summary="El usuario quiere comprar y mantener Apple.",
                candidate_strategy_draft=StrategySummary(
                    raw_user_phrasing=request.current_user_message,
                    strategy_type="buy_and_hold",
                    strategy_thesis="Comprar y mantener Apple.",
                    asset_universe=["Apple"],
                    date_range={"start": "2025-06-16", "end": "2026-06-16"},
                    capital_amount=100000,
                ),
                semantic_turn_act="new_idea",
            )

    provider_queries: list[tuple[str, str]] = []

    def _resolution(query: str, *, field: str, source: str) -> AssetResolution:
        provider_queries.append((query, source))
        raw = query.strip()
        if raw == "APPLE" and source == "llm_extraction":
            return AssetResolution(
                status="unsupported",
                raw_text=query,
                asset=None,
                candidates=(),
                provenance=ResolutionProvenance(
                    field=field,
                    raw_text=query,
                    source=source,
                    candidate_kind="asset",
                    resolution_status="unsupported",
                    canonical_symbol=None,
                    asset_class=None,
                    validated_by="provider_catalog",
                    confidence="high",
                ),
            )
        if raw.casefold() == "apple":
            asset = ResolvedAsset(
                canonical_symbol="AAPL",
                asset_class="equity",
                name="Apple Inc.",
                raw_symbol="AAPL",
            )
            return AssetResolution(
                status="resolved",
                raw_text=query,
                asset=asset,
                candidates=(asset,),
                provenance=ResolutionProvenance(
                    field=field,
                    raw_text=query,
                    source=source,
                    candidate_kind="asset",
                    resolution_status="resolved",
                    canonical_symbol="AAPL",
                    asset_class="equity",
                    validated_by="provider_catalog",
                    confidence="medium",
                ),
            )
        return AssetResolution(
            status="unsupported",
            raw_text=query,
            asset=None,
            candidates=(),
            provenance=ResolutionProvenance(
                field=field,
                raw_text=query,
                source=source,
                candidate_kind="asset",
                resolution_status="unsupported",
                canonical_symbol=None,
                asset_class=None,
                validated_by="provider_catalog",
                confidence="low",
            ),
        )

    monkeypatch.setattr(interpret_module, "runtime_resolve_asset_candidate", _resolution)
    client = _client()
    checkpointer = api_state.build_agent_runtime_checkpointer()
    workflow = build_workflow(
        contract=build_default_capability_contract(),
        structured_interpreter=ApplePseudoTickerInterpreter(),
        checkpointer=checkpointer,
    )
    monkeypatch.setattr(
        app.state,
        "agent_runtime_checkpointer",
        checkpointer,
        raising=False,
    )
    monkeypatch.setattr(app.state, "agent_runtime_workflow", workflow, raising=False)
    conversation = _conversation(client)

    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": conversation["id"],
            "message": "Prueba comprar y mantener Apple con 100k durante el ultimo ano",
            "language": "es-419",
        },
    )

    assert response.status_code == 200
    assert ("Apple", "llm_extraction") in provider_queries
    assert ("Apple", "user_mention") not in provider_queries
    payload = _final_payload(response.text)
    confirmation_payload = payload["confirmation_payload"]
    strategy = confirmation_payload["strategy"]
    assert strategy["asset_universe"] == ["AAPL"]
    assert strategy["asset_class"] == "equity"
    assert "invalid_symbols" not in strategy.get("extra_parameters", {})
    assert confirmation_payload["launch_payload"]["symbol"] == "AAPL"
    assert confirmation_payload["launch_payload"]["symbols"] == ["AAPL"]
    confirmation = payload["confirmation"]
    assert confirmation["strategy_type"] == "buy_and_hold"
    assert confirmation["asset_class"] == "equity"
    strategy_row = next(
        row for row in confirmation["rows"] if row["key"] == "strategy"
    )
    assert strategy_row["labelKey"] == "chat.confirmation.rows.strategy"
    assets_row = next(row for row in confirmation["rows"] if row["key"] == "assets")
    assert assets_row["labelKey"] == "chat.confirmation.rows.assets"
    assert assets_row["value"] == "AAPL"

    messages = client.get(f"/api/v1/conversations/{conversation['id']}/messages").json()[
        "items"
    ]
    metadata = messages[-1]["metadata"]
    persisted_strategy = metadata["confirmation_payload"]["strategy"]
    assert persisted_strategy["asset_universe"] == ["AAPL"]
    assert "invalid_symbols" not in persisted_strategy.get("extra_parameters", {})
    assert metadata["confirmation_payload"]["launch_payload"]["symbols"] == ["AAPL"]


def test_chat_stream_result_uses_final_payload_run_without_named_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api import state as api_state
    from argus.api.routers import agent as agent_router

    result_card = {
        "title": "AAPL buy and hold",
        "date_range": {
            "start": "2025-05-03",
            "end": "2026-05-03",
            "display": "May 3, 2025 to May 3, 2026",
        },
        "status_label": "Completed",
        "rows": [{"key": "total_return_pct", "label": "Total Return", "value": "+12.4%"}],
        "assumptions": ["$10,000 starting capital", "Benchmark: SPY"],
        "actions": [
            {
                "id": "show-breakdown",
                "type": "show_breakdown",
                "label": "Show a breakdown",
                "presentation": "result",
                "payload": {},
            }
        ],
    }

    async def _fake_stream_agent_turn_events(**_: Any):
        yield {"type": "stage_start", "stage": "interpret"}
        yield {"type": "stage_start", "stage": "execute"}
        yield {"type": "stage_start", "stage": "explain"}
        yield {"type": "token", "content": "Short grounded summary."}
        yield {
            "type": "final",
            "payload": {
                "stage_outcome": "end_run",
                "assistant_response": "Short grounded summary.",
                "final_response_payload": {
                    "result_card": result_card,
                    "result": {
                        "resolved_strategy": {
                            "strategy_type": "buy_and_hold",
                            "asset_universe": ["AAPL"],
                        },
                        "resolved_parameters": {"timeframe": "1D"},
                        "metrics": {
                            "aggregate": {"performance": {"total_return_pct": 12.4}}
                        },
                        "benchmark_metrics": {"benchmark_symbol": "SPY"},
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
    conversation = _conversation(client)

    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": conversation["id"],
            "message": "Run it",
            "language": "en",
        },
    )

    assert response.status_code == 200
    assert "event:" not in response.text
    assert response.text.count("data: [DONE]") == 1
    payload = _final_payload(response.text)
    assert payload["run"]["conversation_result_card"]["title"] == "AAPL buy and hold"
    assert payload["message_id"]
    assert payload["assistant_response"] == ""
    assert "Short grounded summary." not in response.text

    messages = client.get(f"/api/v1/conversations/{conversation['id']}/messages").json()[
        "items"
    ]
    assert messages[-1]["id"] == payload["message_id"]
    assert messages[-1]["content"] == ""
    assert (
        messages[-1]["metadata"]["result_fact_bank"]["metrics"]
        == payload["run"]["metrics"]
    )
    stored_message = next(
        message
        for message in api_state.store.messages[conversation["id"]]
        if message.id == payload["message_id"]
    )
    assert stored_message.content == "Short grounded summary."


@pytest.mark.parametrize("action_type", ["show_breakdown", "save_strategy"])
def test_result_actions_enter_runtime_before_transport_handling(
    monkeypatch: pytest.MonkeyPatch,
    action_type: str,
) -> None:
    from argus.api import state as api_state
    from argus.api.routers import agent as agent_router

    captured_action_contexts: list[dict[str, Any] | None] = []

    async def _fake_stream_agent_turn_events(**kwargs: Any):
        captured_action_contexts.append(kwargs.get("action_context"))
        yield {"type": "stage_start", "stage": "interpret"}
        yield {
            "type": "final",
            "payload": {
                "stage_outcome": "ready_to_respond",
                "assistant_response": "Runtime handled the result action.",
            },
        }

    monkeypatch.setattr(
        agent_router,
        "stream_agent_turn_events",
        _fake_stream_agent_turn_events,
    )
    client = _client()
    conversation = _conversation(client)

    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": conversation["id"],
            "language": "en",
            "action": {
                "type": action_type,
                "label": action_type.replace("_", " "),
                "presentation": "result",
                "payload": {"run_id": "run-from-card"},
            },
        },
    )

    assert response.status_code == 200
    assert captured_action_contexts
    assert captured_action_contexts[0]["type"] == action_type
    final_payload = _final_payload(response.text)
    if action_type == "show_breakdown":
        assert final_payload["assistant_response"] == ""
        assert final_payload["chat_action"]["type"] == action_type
        assert final_payload["response_intent"] == {
            "kind": "result_breakdown",
            "facts": {"result_fact_bank": None},
        }
        assert "Runtime handled the result action." not in response.text
        stored_message = next(
            message
            for message in api_state.store.messages[conversation["id"]]
            if message.id == final_payload["message_id"]
        )
        assert stored_message.content == "Runtime handled the result action."
    else:
        assert final_payload["assistant_response"] == (
            "Runtime handled the result action."
        )


def test_chat_stream_artifact_naming_scheduler_failure_does_not_block_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.routers import agent as agent_router

    scheduled: list[dict[str, Any]] = []

    async def _fake_stream_agent_turn_events(**_: Any):
        yield {"type": "stage_start", "stage": "interpret"}
        yield {
            "type": "final",
            "payload": {
                "stage_outcome": "ready_to_respond",
                "assistant_response": "Short grounded summary.",
            },
        }

    def _failing_scheduler(**kwargs: Any) -> None:
        scheduled.append(kwargs)
        raise RuntimeError("title service unavailable")

    monkeypatch.setattr(
        agent_router,
        "stream_agent_turn_events",
        _fake_stream_agent_turn_events,
    )
    monkeypatch.setattr(
        agent_router,
        "schedule_artifact_naming_after_stream",
        _failing_scheduler,
        raising=False,
    )
    client = _client()
    conversation = _conversation(client)

    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": conversation["id"],
            "message": "Explain dollar cost averaging.",
            "language": "en",
        },
    )

    assert response.status_code == 200
    assert response.text.count("data: [DONE]") == 1
    assert _final_payload(response.text)["assistant_response"] == (
        "Short grounded summary."
    )
    assert len(scheduled) == 1


def test_chat_stream_runtime_stall_emits_recoverable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.routers import agent as agent_router

    async def _stalling_stream_agent_turn_events(**_: Any):
        yield {"type": "stage_start", "stage": "interpret"}
        await asyncio.sleep(1)

    monkeypatch.setattr(
        agent_router,
        "stream_agent_turn_events",
        _stalling_stream_agent_turn_events,
    )
    monkeypatch.setattr(agent_router, "RUNTIME_EVENT_TIMEOUT_SECONDS", 0.01)
    client = _client()
    conversation = _conversation(client)

    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": conversation["id"],
            "message": "what are the top market movers?",
            "language": "en",
        },
    )

    assert response.status_code == 200
    events = _data_events(response.text)
    assert events[0] == {"type": "stage_start", "stage": "interpret"}
    assert events[-1]["type"] == "error"
    assert events[-1]["code"] == "agent_runtime_failure"
    assert "conversation is saved" in events[-1]["message"]
    assert response.text.count("data: [DONE]") == 1
    messages = client.get(f"/api/v1/conversations/{conversation['id']}/messages").json()[
        "items"
    ]
    assert "runtime_diagnostics" not in response.text
    assert all(
        "runtime_diagnostics" not in (message["metadata"] or {})
        for message in messages
    )


def test_chat_stream_visible_failure_path_is_terminal_for_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.message_store import create_message
    from argus.api.routers import agent as agent_router

    late_success_persisted = Event()
    prompt = "Backtest buy and hold AAPL from January 2025 through June 2026"
    late_confirmation_payload = {
        "strategy": {
            "strategy_type": "buy_and_hold",
            "strategy_thesis": "Buy and hold AAPL.",
            "asset_universe": ["AAPL"],
            "asset_class": "equity",
            "date_range": {"start": "2025-01-01", "end": "2026-06-05"},
        },
        "optional_parameters": {},
        "launch_payload": {
            "strategy_type": "buy_and_hold",
            "symbol": "AAPL",
            "symbols": ["AAPL"],
            "timeframe": "1D",
            "date_range": {"start": "2025-01-01", "end": "2026-06-05"},
            "sizing_mode": "capital_amount",
            "capital_amount": 10000,
            "benchmark_symbol": "SPY",
        },
        "validation": {"status": "ready_to_run", "executable": True},
    }

    async def _late_success_stream_agent_turn_events(**kwargs: Any):
        yield {"type": "stage_start", "stage": "interpret"}
        time.sleep(0.05)
        create_message(
            user_id=kwargs["user"].user_id,
            conversation_id=kwargs["thread_id"],
            role="assistant",
            content="Ready to test AAPL.",
            metadata={
                "conversation_mode": "confirm",
                "agent_runtime_stage_outcome": "await_approval",
                "confirmation_payload": late_confirmation_payload,
                "confirmation_card": {
                    "confirmation_id": "late-confirmation-aapl",
                    "confirmation_state": "active",
                    "title": "AAPL buy and hold",
                    "summary": "Ready to test AAPL.",
                    "rows": [],
                    "actions": [
                        {
                            "type": "run_backtest",
                            "label": "Run backtest",
                            "presentation": "confirmation",
                            "payload": {
                                "confirmation_id": "late-confirmation-aapl"
                            },
                        }
                    ],
                },
            },
        )
        late_success_persisted.set()
        yield {
            "type": "final",
            "payload": {
                "stage_outcome": "await_approval",
                "assistant_response": "Ready to test AAPL.",
                "confirmation_payload": late_confirmation_payload,
            },
        }

    @asynccontextmanager
    async def _isolated_workflow():
        yield "worker_loop_workflow"

    monkeypatch.setattr(agent_router, "runtime_worker_enabled", lambda: True)
    # Workspace dotenv values otherwise override these intentionally tiny test clocks.
    monkeypatch.setenv("CUADRAO_RUNTIME_EVENT_TIMEOUT_SECONDS", "")
    monkeypatch.setenv("CUADRAO_RUNTIME_EVENT_KEEPALIVE_SECONDS", "")
    monkeypatch.setattr(agent_router, "RUNTIME_EVENT_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(agent_router, "RUNTIME_EVENT_KEEPALIVE_SECONDS", 0.005)
    monkeypatch.setattr(
        agent_router,
        "stream_agent_turn_events",
        _late_success_stream_agent_turn_events,
    )
    monkeypatch.setattr(
        agent_router.api_state,
        "isolated_agent_runtime_workflow",
        _isolated_workflow,
        raising=False,
    )
    client = _client()
    conversation = _conversation(client)

    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": conversation["id"],
            "message": prompt,
            "language": "en",
        },
    )

    assert response.status_code == 200
    assert late_success_persisted.wait(1)
    events = _data_events(response.text)
    error_events = [event for event in events if event.get("type") == "error"]
    final_events = [event for event in events if event.get("type") == "final"]
    messages = client.get(f"/api/v1/conversations/{conversation['id']}/messages").json()[
        "items"
    ]
    user_message, terminal_assistant = _assert_durable_retry_on_linked_assistant(
        messages,
        persisted_content=prompt,
    )
    assert error_events == [
        {
            "type": "error",
            "code": "agent_runtime_failure",
            "message": error_events[0]["message"],
            "message_id": error_events[0]["message_id"],
            "recovery": {
                "code": "runtime_failure",
                "retryable": True,
            },
            "retry_last_turn": {
                "request_message_id": user_message["id"],
                "message": prompt,
            },
        }
    ]
    assert final_events == []
    assert response.text.count("data: [DONE]") == 1

    assistant_messages = [
        message for message in messages if message["role"] == "assistant"
    ]
    failure_messages = [
        message
        for message in assistant_messages
        if message["metadata"].get("agent_runtime_stage_outcome")
        == "agent_runtime_failure"
    ]
    assert failure_messages == [terminal_assistant]
    failure_metadata = terminal_assistant["metadata"]
    assert failure_metadata["recovery"]["code"] == "runtime_failure"
    assert failure_metadata["retry_last_turn"] == {
        "request_message_id": user_message["id"],
        "message": prompt,
    }
    assert not any(
        message["metadata"].get("confirmation_payload")
        or message["metadata"].get("confirmation_card")
        or message["metadata"].get("result_card")
        or message["metadata"].get("result_run_id")
        for message in assistant_messages
        if message["id"] != terminal_assistant["id"]
    )


def test_chat_stream_runtime_keepalive_preserves_slow_progressing_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.routers import agent as agent_router

    async def _slow_progressing_stream_agent_turn_events(**_: Any):
        yield {"type": "stage_start", "stage": "interpret"}
        await asyncio.sleep(0.03)
        yield {"type": "stage_outcome", "outcome": "ready_for_confirmation"}
        yield {
            "type": "final",
            "payload": {
                "stage_outcome": "await_approval",
                "assistant_response": "Ready to test AAPL and MSFT.",
            },
        }

    monkeypatch.setattr(
        agent_router,
        "stream_agent_turn_events",
        _slow_progressing_stream_agent_turn_events,
    )
    monkeypatch.setattr(agent_router, "RUNTIME_EVENT_TIMEOUT_SECONDS", 1)
    monkeypatch.setattr(agent_router, "RUNTIME_EVENT_KEEPALIVE_SECONDS", 0.01)
    monkeypatch.setenv("CUADRAO_RUNTIME_EVENT_TIMEOUT_SECONDS", "")
    monkeypatch.setenv("CUADRAO_RUNTIME_EVENT_KEEPALIVE_SECONDS", "")
    client = _client()
    conversation = _conversation(client)

    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": conversation["id"],
            "message": "Test an equal-weight AAPL and MSFT strategy",
            "language": "en",
        },
    )

    assert response.status_code == 200
    assert ": keepalive" in response.text
    events = _data_events(response.text)
    assert events[0] == {"type": "stage_start", "stage": "interpret"}
    assert any(event.get("type") == "final" for event in events)
    assert not any(event.get("type") == "error" for event in events)
    assert response.text.count("data: [DONE]") == 1


@pytest.mark.asyncio
async def test_events_cannot_reset_the_absolute_turn_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.agent_runtime import turn_execution
    from argus.api.routers import agent as agent_router

    class _Clock:
        def __init__(self) -> None:
            self.value = 0.0

        def __call__(self) -> float:
            return self.value

        def advance(self, seconds: float) -> None:
            self.value += seconds

    clock = _Clock()
    monkeypatch.setattr(turn_execution, "_monotonic", clock)
    monkeypatch.setenv("CUADRAO_TURN_DEADLINE_SECONDS", "0.25")
    monkeypatch.setenv("CUADRAO_RUNTIME_EVENT_TIMEOUT_SECONDS", "1")
    monkeypatch.setenv("CUADRAO_RUNTIME_EVENT_KEEPALIVE_SECONDS", "0.1")

    async def _many_timely_events():
        for index in range(40):
            clock.advance(0.03)
            yield {"type": "token", "content": str(index)}

    seen: list[dict[str, Any]] = []
    with turn_execution.turn_execution_scope(entry_state={}):
        with pytest.raises(agent_router.RuntimeEventTimeoutError) as exc_info:
            async for event in agent_router._runtime_events_with_keepalive(
                _many_timely_events()
            ):
                if event is not None:
                    seen.append(event)

    diagnostics = exc_info.value.diagnostics
    assert len(seen) < 40
    assert diagnostics["code"] == "turn_deadline_exhausted"
    assert diagnostics["timeout_seconds"] == 0.25
    assert diagnostics["elapsed_seconds"] >= 0.25


@pytest.mark.asyncio
async def test_turn_deadline_diagnostic_uses_total_turn_elapsed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.agent_runtime import turn_execution
    from argus.api.routers import agent as agent_router

    class _Clock:
        def __init__(self) -> None:
            self.value = 10.0

        def __call__(self) -> float:
            return self.value

        def advance(self, seconds: float) -> None:
            self.value += seconds

    clock = _Clock()
    monkeypatch.setattr(turn_execution, "_monotonic", clock)
    monkeypatch.setenv("CUADRAO_TURN_DEADLINE_SECONDS", "0.25")
    monkeypatch.setenv("CUADRAO_RUNTIME_EVENT_TIMEOUT_SECONDS", "5")
    monkeypatch.setenv("CUADRAO_RUNTIME_EVENT_KEEPALIVE_SECONDS", "0.1")

    async def _events():
        clock.advance(0.2)
        yield {"type": "stage_start", "stage": "interpret"}
        clock.advance(0.06)
        yield {"type": "stage_outcome", "outcome": "ready_for_confirmation"}

    with turn_execution.turn_execution_scope(entry_state={}):
        with pytest.raises(agent_router.RuntimeEventTimeoutError) as exc_info:
            async for _event in agent_router._runtime_events_with_keepalive(_events()):
                pass

    diagnostics = exc_info.value.diagnostics
    assert diagnostics["code"] == "turn_deadline_exhausted"
    assert diagnostics["timeout_seconds"] == 0.25
    assert diagnostics["elapsed_seconds"] == pytest.approx(0.26)
    assert diagnostics["event_count"] == 1


@pytest.mark.asyncio
async def test_runtime_keepalive_wrapper_cleans_pending_task_on_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.routers import agent as agent_router

    cleanup_seen = asyncio.Event()

    async def _runtime_events():
        yield {"type": "stage_start", "stage": "interpret"}
        try:
            await asyncio.sleep(60)
            yield {"type": "final", "payload": {"stage_outcome": "await_approval"}}
        finally:
            cleanup_seen.set()

    monkeypatch.setattr(agent_router, "RUNTIME_EVENT_TIMEOUT_SECONDS", 1)
    monkeypatch.setattr(agent_router, "RUNTIME_EVENT_KEEPALIVE_SECONDS", 0.01)
    wrapped_events = agent_router._runtime_events_with_keepalive(_runtime_events())

    assert await anext(wrapped_events) == {
        "type": "stage_start",
        "stage": "interpret",
    }
    assert await anext(wrapped_events) is None
    await wrapped_events.aclose()

    await asyncio.wait_for(cleanup_seen.wait(), timeout=1)


@pytest.mark.asyncio
async def test_stream_close_persists_provider_receipt_with_request_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.routers import agent as agent_router
    from argus.api.schemas import ChatStreamRequest, User
    from argus.llm.openrouter import record_openrouter_route_receipt
    from starlette.requests import Request

    persisted_receipts: list[dict[str, Any]] = []
    runtime_closed = asyncio.Event()

    async def _runtime_events(**_: Any):
        try:
            record_openrouter_route_receipt(
                task="interpretation",
                model_name="unit-test-model",
                mode="json_schema",
                schema_name="LLMInterpretationResponse",
                latency_ms=5,
                outcome="succeeded",
            )
            record_openrouter_route_receipt(
                task="chat_composer",
                model_name="unit-test-model",
                mode="text",
                schema_name=None,
                latency_ms=3,
                outcome="succeeded",
            )
            yield {"type": "stage_start", "stage": "interpret"}
            await asyncio.Event().wait()
        finally:
            runtime_closed.set()

    def _capture_receipts(**kwargs: Any) -> None:
        persisted_receipts.append(kwargs)

    monkeypatch.setattr(agent_router, "stream_agent_turn_events", _runtime_events)
    monkeypatch.setattr(agent_router, "persist_route_receipts", _capture_receipts)

    client = _client()
    conversation = _conversation(client)
    user = User.model_validate(client.get("/api/v1/me").json()["user"])
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/chat/stream",
            "query_string": b"",
            "headers": [],
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "app": app,
        }
    )
    request.state.request_id = "request-disconnect"
    request.state.account_context = registered_account_context(user.id)
    response = await agent_router.chat_stream(
        ChatStreamRequest(
            conversation_id=conversation["id"],
            message="Test AAPL.",
            language="en",
        ),
        request,
        idempotency_key=None,
        user=user,
    )

    assert "stage_start" in str(await anext(response.body_iterator))
    await response.body_iterator.aclose()
    await asyncio.wait_for(runtime_closed.wait(), timeout=1)

    durable_messages = client.get(
        f"/api/v1/conversations/{conversation['id']}/messages"
    ).json()["items"]
    request_message = next(
        message for message in durable_messages if message["role"] == "user"
    )
    assert len(persisted_receipts) == 1
    assert len(persisted_receipts[0]["receipts"]) == 2
    assert persisted_receipts[0]["message_id"] == request_message["id"]
    assert persisted_receipts[0]["metadata"]["request_id"] == "request-disconnect"
    assert persisted_receipts[0]["metadata"]["turn_id"] == request_message["id"]
    assert persisted_receipts[0]["metadata"]["source"] == "api_turn"


def test_chat_stream_missing_runtime_final_emits_recoverable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.routers import agent as agent_router

    async def _incomplete_stream_agent_turn_events(**_: Any):
        yield {"type": "stage_start", "stage": "interpret"}

    monkeypatch.setattr(
        agent_router,
        "stream_agent_turn_events",
        _incomplete_stream_agent_turn_events,
    )
    client = _client()
    conversation = _conversation(client)

    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": conversation["id"],
            "message": "what are the top market movers?",
            "language": "en",
        },
    )

    assert response.status_code == 200
    events = _data_events(response.text)
    assert events[0] == {"type": "stage_start", "stage": "interpret"}
    assert events[-1]["type"] == "error"
    assert events[-1]["code"] == "agent_runtime_failure"
    assert "conversation is saved" in events[-1]["message"]
    assert response.text.count("data: [DONE]") == 1


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


def test_chat_stream_runtime_initialization_failure_emits_recoverable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api import state as api_state

    def _broken_workflow(_request: Any) -> Any:
        raise RuntimeError("workflow import failed")

    monkeypatch.setattr(api_state, "get_agent_runtime_workflow", _broken_workflow)
    client = _client()
    conversation = _conversation(client)
    message = "Compra y mantén ETH de enero de 2024 hasta marzo de 2024 con 100000"

    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": conversation["id"],
            "message": message,
            "language": "es-419",
        },
    )

    assert response.status_code == 200
    events = _data_events(response.text)
    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert events[0]["code"] == "agent_runtime_failure"
    assert "conversation is saved" in events[0]["message"]
    assert events[0]["recovery"] == {
        "code": "runtime_failure",
        "retryable": True,
    }
    assert response.text.count("data: [DONE]") == 1
    messages = client.get(f"/api/v1/conversations/{conversation['id']}/messages").json()[
        "items"
    ]
    user_message, assistant_message = _assert_durable_retry_on_linked_assistant(
        messages,
        persisted_content=message,
        failure_code="runtime_initialization_failed",
    )
    assert (
        events[0]["retry_last_turn"]
        == assistant_message["metadata"]["retry_last_turn"]
    )
    assert [message["role"] for message in messages[-2:]] == ["user", "assistant"]
    assert messages[-1] == assistant_message
    assert assistant_message["content"] == events[0]["message"]
    assert assistant_message["metadata"]["recovery"] == events[0]["recovery"]
    assert assistant_message["metadata"]["retry_last_turn"]["request_message_id"] == (
        user_message["id"]
    )


def test_chat_stream_runtime_failure_persists_retry_last_turn_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.routers import agent as agent_router

    async def _incomplete_stream_agent_turn_events(**_: Any):
        yield {"type": "stage_start", "stage": "interpret"}

    monkeypatch.setattr(
        agent_router,
        "stream_agent_turn_events",
        _incomplete_stream_agent_turn_events,
    )
    client = _client()
    conversation = _conversation(client)

    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": conversation["id"],
            "message": "what if I bought $125 of BTC every two weeks in 2022?",
            "language": "en",
        },
    )

    assert response.status_code == 200
    messages = client.get(f"/api/v1/conversations/{conversation['id']}/messages").json()[
        "items"
    ]
    user_message, assistant_message = _assert_durable_retry_on_linked_assistant(
        messages,
        persisted_content="what if I bought $125 of BTC every two weeks in 2022?",
    )
    assert messages[-1] == assistant_message
    assert assistant_message["metadata"]["retry_last_turn"]["request_message_id"] == (
        user_message["id"]
    )
    assert assistant_message["metadata"]["recovery"] == {
        "code": "runtime_failure",
        "retryable": True,
    }
    assert assistant_message["metadata"]["agent_runtime_stage_outcome"] == (
        "agent_runtime_failure"
    )


def test_chat_stream_runtime_failure_emits_typed_recovery_for_spanish_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.routers import agent as agent_router

    async def _incomplete_stream_agent_turn_events(**_: Any):
        yield {"type": "stage_start", "stage": "interpret"}

    monkeypatch.setattr(
        agent_router,
        "stream_agent_turn_events",
        _incomplete_stream_agent_turn_events,
    )
    client = _client()
    conversation = _conversation(client)
    message = "Compra y mantén ETH de enero de 2024 hasta marzo de 2024 con 100000"

    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": conversation["id"],
            "message": message,
            "language": "es-419",
        },
    )

    assert response.status_code == 200
    events = _data_events(response.text)
    error_event = events[-1]
    assert error_event["type"] == "error"
    assert "conversation is saved" in error_event["message"]
    assert error_event["recovery"] == {
        "code": "runtime_failure",
        "retryable": True,
    }
    messages = client.get(f"/api/v1/conversations/{conversation['id']}/messages").json()[
        "items"
    ]
    user_message, assistant_message = _assert_durable_retry_on_linked_assistant(
        messages,
        persisted_content=message,
    )
    assert (
        error_event["retry_last_turn"]
        == assistant_message["metadata"]["retry_last_turn"]
    )
    assert messages[-1] == assistant_message
    assert assistant_message["content"] == error_event["message"]
    assert assistant_message["metadata"]["retry_last_turn"]["request_message_id"] == (
        user_message["id"]
    )
    assert assistant_message["metadata"]["recovery"] == error_event["recovery"]


def test_chat_stream_typed_interpreter_recovery_uses_canonical_bound_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.routers import agent as agent_router

    async def _fake_stream_agent_turn_events(**_: Any):
        yield {"type": "stage_start", "stage": "interpret"}
        yield {
            "type": "final",
            "payload": {
                "stage_outcome": "ready_to_respond",
                "assistant_response": (
                    "Guardé tu mensaje, pero no pude convertirlo en una "
                    "configuración de prueba confiable. Intenta de nuevo en "
                    "un momento."
                ),
                "retry_last_turn": {
                    "message": (
                        "Compra y mantén ETH de enero de 2024 hasta marzo de "
                        "2024 con 100000"
                    )
                },
                "recovery": {
                    "code": "interpreter_unavailable",
                    "retryable": True,
                    "language": "es-419",
                },
            },
        }

    monkeypatch.setattr(
        agent_router,
        "stream_agent_turn_events",
        _fake_stream_agent_turn_events,
    )
    client = _client()
    conversation = _conversation(client)

    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": conversation["id"],
            "message": (
                "Compra y mantén ETH de enero de 2024 hasta marzo de 2024 "
                "con 100000"
            ),
            "language": "es-419",
        },
    )

    assert response.status_code == 200
    events = _data_events(response.text)
    assert [event["type"] for event in events] == ["stage_start", "error"]
    error = events[-1]
    assert error["code"] == "agent_runtime_failure"
    assert error["recovery"] == {
        "code": "runtime_failure",
        "retryable": True,
    }
    assert "Guardé tu mensaje" not in response.text
    assert response.text.count("data: [DONE]") == 1
    messages = client.get(f"/api/v1/conversations/{conversation['id']}/messages").json()[
        "items"
    ]
    user_message, assistant_message = _assert_durable_retry_on_linked_assistant(
        messages,
        persisted_content=(
            "Compra y mantén ETH de enero de 2024 hasta marzo de 2024 con 100000"
        ),
    )
    assert error["retry_last_turn"] == assistant_message["metadata"]["retry_last_turn"]
    assert error["retry_last_turn"]["request_message_id"] == user_message["id"]


def test_chat_stream_empty_final_persists_visible_recovery_for_user_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.routers import agent as agent_router

    async def _fake_stream_agent_turn_events(**_: Any):
        yield {"type": "stage_start", "stage": "interpret"}
        yield {
            "type": "final",
            "payload": {
                "stage_outcome": "ready_to_respond",
                "assistant_response": None,
            },
        }

    monkeypatch.setattr(
        agent_router,
        "stream_agent_turn_events",
        _fake_stream_agent_turn_events,
    )
    client = _client()
    conversation = _conversation(client)
    message = "What if I bought Bitcoin this year so far?"

    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": conversation["id"],
            "message": message,
            "language": "en",
        },
    )

    assert response.status_code == 200
    events = _data_events(response.text)
    assert events[-1]["type"] == "error"
    assert events[-1]["message"]
    assert events[-1]["recovery"] == {
        "code": "runtime_failure",
        "retryable": True,
    }
    assert response.text.count("data: [DONE]") == 1
    messages = client.get(f"/api/v1/conversations/{conversation['id']}/messages").json()[
        "items"
    ]
    assert [message["role"] for message in messages[-2:]] == ["user", "assistant"]
    user_message, assistant_message = _assert_durable_retry_on_linked_assistant(
        messages,
        persisted_content=message,
    )
    assert (
        events[-1]["retry_last_turn"]
        == assistant_message["metadata"]["retry_last_turn"]
    )
    assert messages[-1] == assistant_message
    assert assistant_message["content"] == events[-1]["message"]
    assert assistant_message["metadata"]["conversation_mode"] == "recovery"
    assert assistant_message["metadata"]["retry_last_turn"]["request_message_id"] == (
        user_message["id"]
    )
    assert assistant_message["metadata"]["recovery"] == events[-1]["recovery"]


def test_chat_stream_persists_runtime_start_marker_on_user_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.routers import agent as agent_router

    async def _crashing_stream_agent_turn_events(**_: Any):
        raise RuntimeError("runtime died before first event")
        yield {"type": "final", "payload": {}}

    monkeypatch.setattr(
        agent_router,
        "stream_agent_turn_events",
        _crashing_stream_agent_turn_events,
    )
    client = _client()
    conversation = _conversation(client)

    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": conversation["id"],
            "message": "Test AAPL and MSFT",
            "language": "en",
        },
    )

    assert response.status_code == 200
    messages = client.get(f"/api/v1/conversations/{conversation['id']}/messages").json()[
        "items"
    ]
    _, terminal_assistant = _assert_durable_retry_on_linked_assistant(
        messages,
        persisted_content="Test AAPL and MSFT",
    )
    assert messages[-1] == terminal_assistant
    assert terminal_assistant["metadata"]["agent_runtime_stage_outcome"] == (
        "agent_runtime_failure"
    )


def test_chat_stream_finalizes_ai_title_after_meaningful_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api import state as api_state
    from argus.api.routers import agent as agent_router

    async def _fake_stream_agent_turn_events(**_: Any):
        yield {"type": "stage_start", "stage": "interpret"}
        yield {
            "type": "final",
            "payload": {
                "stage_outcome": "ready_to_respond",
                "assistant_response": (
                    "Dollar cost averaging means investing a fixed amount "
                    "on a schedule."
                ),
            },
        }

    def _suggest_entity_name(**kwargs: Any) -> str:
        assert kwargs["entity_type"] == "conversation"
        assert "dollar cost averaging" in kwargs["context"].lower()
        return "DCA Basics"

    monkeypatch.setenv("ARGUS_ENABLE_ARTIFACT_NAMING_IN_TESTS", "1")
    monkeypatch.setattr(
        agent_router,
        "stream_agent_turn_events",
        _fake_stream_agent_turn_events,
    )
    monkeypatch.setattr(
        "argus.api.artifact_naming.suggest_entity_name",
        _suggest_entity_name,
    )
    client = _client()
    conversation = _conversation(client)

    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": conversation["id"],
            "message": "Can you explain dollar cost averaging?",
            "language": "en",
        },
    )

    assert response.status_code == 200
    assert response.text.count("data: [DONE]") == 1
    updated = api_state.store.conversations[conversation["id"]]
    assert updated.title == "DCA Basics"
    assert updated.title_source == "ai_generated"


def test_chat_stream_final_text_wins_over_provisional_streamed_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.routers import agent as agent_router

    async def _fake_stream_agent_turn_events(**_: Any):
        yield {"type": "stage_start", "stage": "interpret"}
        yield {"type": "stage_outcome", "outcome": "needs_clarification"}
        yield {"type": "token", "content": "I can show you a confirmation if you want."}
        yield {
            "type": "final",
            "payload": {
                "stage_outcome": "await_user_reply",
                "assistant_response": "Which end date should I use?",
                "pending_strategy": {
                    "strategy": {
                        "strategy_type": None,
                        "asset_universe": [],
                        "date_range": None,
                    },
                    "missing_required_fields": ["asset_universe"],
                },
            },
        }

    monkeypatch.setattr(
        agent_router,
        "stream_agent_turn_events",
        _fake_stream_agent_turn_events,
    )
    client = _client()
    conversation = _conversation(client)

    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": conversation["id"],
            "message": "hello from browser smoke",
            "language": "en",
        },
    )

    assert response.status_code == 200
    payload = _final_payload(response.text)
    assert payload["assistant_response"] == "Which end date should I use?"

    messages = client.get(f"/api/v1/conversations/{conversation['id']}/messages").json()[
        "items"
    ]
    assert messages[-1]["id"] == payload["message_id"]
    assert messages[-1]["content"] == "Which end date should I use?"


def test_chat_stream_persists_streamed_text_when_final_text_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.routers import agent as agent_router

    async def _fake_stream_agent_turn_events(**_: Any):
        yield {"type": "stage_start", "stage": "interpret"}
        yield {"type": "stage_outcome", "outcome": "needs_clarification"}
        yield {"type": "token", "content": "Visible clarification."}
        yield {
            "type": "final",
            "payload": {
                "stage_outcome": "await_user_reply",
                "pending_strategy": {
                    "strategy": {
                        "strategy_type": None,
                        "asset_universe": [],
                        "date_range": None,
                    },
                    "missing_required_fields": ["asset_universe"],
                },
            },
        }

    monkeypatch.setattr(
        agent_router,
        "stream_agent_turn_events",
        _fake_stream_agent_turn_events,
    )
    client = _client()
    conversation = _conversation(client)

    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": conversation["id"],
            "message": "hello from browser smoke",
            "language": "en",
        },
    )

    assert response.status_code == 200
    payload = _final_payload(response.text)
    assert payload["assistant_response"] == "Visible clarification."

    messages = client.get(f"/api/v1/conversations/{conversation['id']}/messages").json()[
        "items"
    ]
    assert messages[-1]["id"] == payload["message_id"]
    assert messages[-1]["content"] == "Visible clarification."
