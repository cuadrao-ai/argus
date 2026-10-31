from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from typing import Any

import pytest
from argus.api import state as api_state
from argus.api.main import app
from argus.api.message_store import (
    claim_response_option_action,
    create_message,
    prepare_message,
)
from argus.api.schemas import BacktestRun
from argus.domain.store import utcnow
from fastapi.testclient import TestClient


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/api/v1/dev/reset")
    return client


def _conversation(client: TestClient) -> dict[str, Any]:
    response = client.post("/api/v1/conversations", json={"language": "en"})
    assert response.status_code == 200
    return response.json()["conversation"]


def _user_id(client: TestClient) -> str:
    response = client.get("/api/v1/me")
    assert response.status_code == 200
    return str(response.json()["user"]["id"])


def _stream_payloads(stream: str, event_type: str) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
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
        event = json.loads(raw)
        if event.get("type") == event_type:
            payloads.append(event.get("payload", event))
    return payloads


def _confirmation_metadata() -> dict[str, Any]:
    return {
        "conversation_mode": "confirm",
        "agent_runtime_stage_outcome": "await_approval",
        "confirmation_payload": {
            "strategy": {
                "strategy_type": "buy_and_hold",
                "strategy_thesis": "Buy and hold Apple.",
                "asset_universe": ["AAPL"],
                "asset_class": "equity",
                "date_range": "past year",
            },
            "optional_parameters": {},
            "launch_payload": {
                "strategy_type": "buy_and_hold",
                "symbol": "AAPL",
                "symbols": ["AAPL"],
                "timeframe": "1D",
                "date_range": {"start": "2025-05-14", "end": "2026-05-14"},
                "entry_rule": None,
                "exit_rule": None,
                "sizing_mode": "capital_amount",
                "capital_amount": 1000,
                "position_size": None,
                "cadence": None,
                "parameters": {},
                "risk_rules": [],
                "benchmark_symbol": "SPY",
                "language": "en",
            },
            "validation": {"status": "ready_to_run", "executable": True},
        },
        "confirmation_card": {
            "confirmation_id": "confirm-aapl",
            "confirmation_state": "active",
            "title": "AAPL buy and hold",
            "statusLabel": "Ready to run",
            "summary": "I read this as AAPL using a buy and hold approach.",
            "rows": [
                {"label": "Strategy", "value": "Buy and hold"},
                {"label": "Assets", "value": "AAPL"},
                {"label": "Period", "value": "past year"},
            ],
            "assumptions": ["Benchmark: SPY"],
            "actions": [
                {
                    "id": "run-backtest",
                    "type": "run_backtest",
                    "label": "Run backtest",
                    "presentation": "confirmation",
                    "payload": {"confirmation_id": "confirm-aapl"},
                }
            ],
        },
    }


def _pending_strategy_metadata() -> dict[str, Any]:
    return {
        "conversation_mode": "setup",
        "agent_runtime_stage_outcome": "await_user_reply",
        "pending_strategy": {
            "strategy": {
                "strategy_type": "buy_and_hold",
                "strategy_thesis": "Buy and hold Apple.",
                "asset_universe": ["AAPL"],
                "asset_class": "equity",
                "date_range": "past year",
            },
            "requested_field": "initial_capital",
            "missing_required_fields": ["initial_capital"],
        },
    }


def _timeframe_recovery_metadata(symbol: str) -> dict[str, Any]:
    response_intent = {
        "kind": "unsupported_recovery",
        "semantic_needs": ["simplification_choice"],
        "requested_fields": ["timeframe"],
        "facts": {
            "strategy": {
                "strategy_type": "buy_and_hold",
                "asset_universe": [symbol],
                "asset_class": "equity",
            },
            "unsupported_constraints": [
                {
                    "category": "unsupported_time_granularity",
                    "raw_value": "5m",
                }
            ],
        },
        "options": [
            {"id": "option_0", "replacement_values": {"timeframe": "1D"}},
            {"id": "option_1", "replacement_values": {"timeframe": "1h"}},
        ],
    }
    clarification = {
        "kind": "unsupported_recovery",
        "reason_code": "unsupported_time_granularity",
        "prompt_source": "llm_generated",
        "requested_field": "timeframe",
        "requested_fields": ["timeframe"],
        "semantic_needs": ["simplification_choice"],
        "payload": {
            "strategy": {
                "strategy_type": "buy_and_hold",
                "asset_universe": [symbol],
                "asset_class": "equity",
            },
            "raw_value": "5m",
        },
        "options": [
            {
                "id": "option_0",
                "compatibility_label": "Retry with daily bars",
                "replacement_values": {"timeframe": "1D"},
            },
            {
                "id": "option_1",
                "compatibility_label": "Retry with 1-hour bars",
                "replacement_values": {"timeframe": "1h"},
            },
        ],
    }
    return {
        "conversation_mode": "setup",
        "agent_runtime_stage_outcome": "await_user_reply",
        "response_intent": response_intent,
        "clarification": clarification,
        "pending_strategy": {
            "strategy": {
                "strategy_type": "buy_and_hold",
                "strategy_thesis": f"Buy and hold {symbol}.",
                "asset_universe": [symbol],
                "asset_class": "equity",
                "timeframe": "5m",
                "date_range": {"start": "2024-01-01", "end": "2024-01-05"},
            },
            "requested_field": "timeframe",
            "missing_required_fields": ["timeframe"],
            "response_intent": response_intent,
        },
    }


def test_memory_newer_message_wins_before_response_option_admission() -> None:
    client = _client()
    conversation = _conversation(client)
    user_id = _user_id(client)
    source = create_message(
        user_id=user_id,
        conversation_id=conversation["id"],
        role="assistant",
        content="AAPL needs a supported timeframe.",
        metadata=_timeframe_recovery_metadata("AAPL"),
    )
    request_message = prepare_message(
        conversation_id=conversation["id"],
        role="user",
        content="Retry with daily bars",
        metadata={"chat_action": {"type": "select_response_option"}},
    )
    claim_started = Event()

    def _claim():
        claim_started.set()
        return claim_response_option_action(
            user_id=user_id,
            conversation_id=conversation["id"],
            source_assistant_id=source.id,
            option_id="option_0",
            replacement_values={"timeframe": "1D"},
            request_message=request_message,
            expected_source_metadata=source.metadata,
        )

    executor = ThreadPoolExecutor(max_workers=1)
    api_state.store.conversation_message_lock.acquire()
    try:
        claimed = executor.submit(_claim)
        assert claim_started.wait(timeout=5)
        create_message(
            user_id=user_id,
            conversation_id=conversation["id"],
            role="assistant",
            content="NVDA needs a supported timeframe.",
            metadata=_timeframe_recovery_metadata("NVDA"),
        )
    finally:
        api_state.store.conversation_message_lock.release()

    assert claimed.result(timeout=5) is None
    executor.shutdown()


def test_memory_response_option_admission_wins_and_exact_replay_survives_later_message() -> (
    None
):
    client = _client()
    conversation = _conversation(client)
    user_id = _user_id(client)
    source = create_message(
        user_id=user_id,
        conversation_id=conversation["id"],
        role="assistant",
        content="AAPL needs a supported timeframe.",
        metadata=_timeframe_recovery_metadata("AAPL"),
    )
    request_message = prepare_message(
        conversation_id=conversation["id"],
        role="user",
        content="Retry with daily bars",
        metadata={"chat_action": {"type": "select_response_option"}},
    )
    append_started = Event()

    def _append_newer():
        append_started.set()
        return create_message(
            user_id=user_id,
            conversation_id=conversation["id"],
            role="assistant",
            content="A later assistant turn.",
            metadata={},
        )

    executor = ThreadPoolExecutor(max_workers=1)
    api_state.store.conversation_message_lock.acquire()
    try:
        later_message = executor.submit(_append_newer)
        assert append_started.wait(timeout=5)
        accepted = claim_response_option_action(
            user_id=user_id,
            conversation_id=conversation["id"],
            source_assistant_id=source.id,
            option_id="option_0",
            replacement_values={"timeframe": "1D"},
            request_message=request_message,
            expected_source_metadata=source.metadata,
        )
    finally:
        api_state.store.conversation_message_lock.release()

    assert accepted is not None
    assert accepted.request_message.id == request_message.id
    assert accepted.request_message.created_at > source.created_at
    assert later_message.result(timeout=5).created_at > accepted.request_message.created_at
    replay = claim_response_option_action(
        user_id=user_id,
        conversation_id=conversation["id"],
        source_assistant_id=source.id,
        option_id="option_0",
        replacement_values={"timeframe": "1D"},
        request_message=request_message,
        expected_source_metadata=source.metadata,
    )
    assert replay is not None
    assert replay.source_message.id == source.id
    assert replay.request_message.id == request_message.id
    assert sum(
        message.id == request_message.id
        for message in api_state.store.messages[conversation["id"]]
    ) == 1
    executor.shutdown()


def test_result_followup_after_reload_preserves_saved_strategy_id() -> None:
    from argus.api import state as api_state
    from argus.api.chat.recovery import latest_result_fallback_context

    client = _client()
    conversation = _conversation(client)
    user_id = _user_id(client)
    run_id = api_state.store.new_id()
    strategy_id = api_state.store.new_id()
    run = BacktestRun(
        id=run_id,
        conversation_id=conversation["id"],
        strategy_id=strategy_id,
        status="completed",
        asset_class="equity",
        symbols=["AAPL"],
        allocation_method="equal_weight",
        benchmark_symbol="SPY",
        metrics={"aggregate": {"performance": {"total_return_pct": 8.1}}},
        config_snapshot={"template": "buy_and_hold", "symbols": ["AAPL"]},
        conversation_result_card={
            "title": "AAPL buy and hold",
            "rows": [
                {"key": "total_return_pct", "label": "Total Return", "value": "+8.1%"}
            ],
            "assumptions": ["Benchmark: SPY"],
        },
        created_at=utcnow(),
        chart=None,
        trades=[],
    )
    api_state.store.backtest_runs[run_id] = run
    api_state.store.backtest_run_owners[run_id] = user_id
    create_message(
        user_id=user_id,
        conversation_id=conversation["id"],
        role="assistant",
        content="Saved AAPL buy and hold to Strategies.",
        metadata={
            "conversation_mode": "result_review",
            "result_run_id": run.id,
            "latest_run_id": run.id,
            "result_strategy_id": strategy_id,
            "saved_strategy_id": strategy_id,
        },
    )

    fallback = latest_result_fallback_context(
        user_id=user_id,
        conversation_id=conversation["id"],
    )

    assert fallback is not None
    snapshot = fallback.latest_task_snapshot
    assert snapshot is not None
    reference = snapshot.latest_backtest_result_reference
    assert reference is not None
    assert reference.metadata["saved_strategy_id"] == strategy_id
    assert reference.metadata["result_strategy_id"] == strategy_id
    assert reference.metadata["latest_run_id"] == run_id


def test_result_followup_after_process_reload_uses_canonical_run_row(
    monkeypatch,
) -> None:
    from argus.api import state as api_state
    from argus.api.chat.recovery import latest_result_fallback_context

    client = _client()
    conversation = _conversation(client)
    user_id = _user_id(client)
    run = BacktestRun(
        id="run-live-reload",
        conversation_id=conversation["id"],
        strategy_id="strategy-live-reload",
        status="completed",
        asset_class="equity",
        symbols=["AAPL"],
        allocation_method="equal_weight",
        benchmark_symbol="SPY",
        metrics={"aggregate": {"performance": {"total_return_pct": 8.1}}},
        config_snapshot={"template": "buy_and_hold", "symbols": ["AAPL"]},
        conversation_result_card={
            "title": "AAPL buy and hold",
            "rows": [
                {"key": "total_return_pct", "label": "Total Return", "value": "+8.1%"}
            ],
            "assumptions": ["Benchmark: SPY"],
        },
        created_at=utcnow(),
        chart={
            "series": [
                {"date": "2024-01-02", "value": 10000.0},
                {"date": "2024-03-01", "value": 11200.0},
            ]
        },
        trades=[],
    )

    class _Gateway:
        def list_messages(self, **kwargs):
            del kwargs
            return []

        def get_latest_completed_run_for_conversation(self, **kwargs):
            assert kwargs == {
                "user_id": user_id,
                "conversation_id": conversation["id"],
            }
            return run

    monkeypatch.setattr(api_state, "supabase_gateway", _Gateway())

    fallback = latest_result_fallback_context(
        user_id=user_id,
        conversation_id=conversation["id"],
    )

    assert fallback is not None
    assert fallback.selected_thread_metadata is not None
    assert fallback.selected_thread_metadata["fallback_source"] == "backtest_runs"
    snapshot = fallback.latest_task_snapshot
    assert snapshot is not None
    reference = snapshot.latest_backtest_result_reference
    assert reference is not None
    assert reference.artifact_id == run.id
    assert reference.metadata["run_id"] == run.id
    assert reference.metadata["latest_run_id"] == run.id
    assert reference.metadata["chart"] == run.chart


def test_pending_refinement_fallback_carries_source_result_reference() -> None:
    from argus.api import state as api_state
    from argus.api.chat.recovery import pending_strategy_metadata_fallback_context

    client = _client()
    conversation = _conversation(client)
    user_id = _user_id(client)
    run_id = api_state.store.new_id()
    run = BacktestRun(
        id=run_id,
        conversation_id=conversation["id"],
        strategy_id=None,
        status="completed",
        asset_class="equity",
        symbols=["MSFT"],
        allocation_method="equal_weight",
        benchmark_symbol="SPY",
        metrics={
            "aggregate": {
                "performance": {
                    "total_return_pct": 15.6,
                    "benchmark_return_pct": 16.6,
                    "delta_vs_benchmark_pct": -1.1,
                }
            }
        },
        config_snapshot={
            "template": "buy_and_hold",
            "symbols": ["MSFT"],
            "resolved_strategy": {
                "strategy_type": "buy_and_hold",
                "strategy_thesis": "Buy and hold Microsoft.",
                "asset_universe": ["MSFT"],
                "asset_class": "equity",
                "date_range": {"start": "2025-01-01", "end": "2025-12-31"},
            },
        },
        conversation_result_card={
            "title": "MSFT buy and hold",
            "status_label": "Simulation Complete",
            "rows": [],
            "assumptions": ["Benchmark: SPY"],
        },
        created_at=utcnow(),
        chart=None,
        trades=[],
    )
    api_state.store.backtest_runs[run_id] = run
    api_state.store.backtest_run_owners[run_id] = user_id
    create_message(
        user_id=user_id,
        conversation_id=conversation["id"],
        role="assistant",
        content="What would you like to change about this strategy?",
        metadata={
            "conversation_mode": "setup",
            "agent_runtime_stage_outcome": "await_user_reply",
            "pending_strategy": {
                "strategy": {
                    "strategy_type": "buy_and_hold",
                    "strategy_thesis": "Buy and hold Microsoft.",
                    "asset_universe": ["MSFT"],
                    "asset_class": "equity",
                    "date_range": {"start": "2025-01-01", "end": "2025-12-31"},
                },
                "requested_field": "refinement",
                "missing_required_fields": ["refinement"],
                "source_result": {
                    "run_id": run.id,
                    "strategy_id": run.strategy_id,
                    "conversation_id": conversation["id"],
                },
            },
            "source_result_run_id": run.id,
            "source_result_conversation_id": conversation["id"],
        },
    )

    fallback = pending_strategy_metadata_fallback_context(
        user_id=user_id,
        conversation_id=conversation["id"],
    )

    assert fallback is not None
    snapshot = fallback.latest_task_snapshot
    assert snapshot is not None
    assert snapshot.pending_strategy_summary is not None
    reference = snapshot.latest_backtest_result_reference
    assert reference is not None
    assert reference.artifact_id == run.id
    assert reference.metadata["symbols"] == ["MSFT"]
    assert fallback.selected_thread_metadata is not None
    assert fallback.selected_thread_metadata["requested_field"] == "refinement"
    assert fallback.selected_thread_metadata["source_result_run_id"] == run.id


def test_pending_refinement_fallback_uses_response_intent_latest_run_id() -> None:
    from argus.api import state as api_state
    from argus.api.chat.recovery import pending_strategy_metadata_fallback_context

    client = _client()
    conversation = _conversation(client)
    user_id = _user_id(client)
    run_id = api_state.store.new_id()
    run = BacktestRun(
        id=run_id,
        conversation_id=conversation["id"],
        strategy_id=None,
        status="completed",
        asset_class="equity",
        symbols=["AAPL"],
        allocation_method="equal_weight",
        benchmark_symbol="SPY",
        metrics={
            "aggregate": {
                "performance": {
                    "total_return_pct": 35.0,
                    "benchmark_return_pct": 24.0,
                    "delta_vs_benchmark_pct": 11.0,
                }
            }
        },
        config_snapshot={"template": "buy_and_hold", "symbols": ["AAPL"]},
        conversation_result_card={"title": "AAPL buy and hold", "rows": []},
        created_at=utcnow(),
        chart={
            "series": [
                {"date": "2024-01-02", "value": 1000.0},
                {"date": "2024-01-23", "value": 1051.63},
            ]
        },
        trades=[],
    )
    api_state.store.backtest_runs[run_id] = run
    api_state.store.backtest_run_owners[run_id] = user_id
    create_message(
        user_id=user_id,
        conversation_id=conversation["id"],
        role="assistant",
        content="What would you like to change?",
        metadata={
            "conversation_mode": "setup",
            "agent_runtime_stage_outcome": "await_user_reply",
            "chat_action": {"type": "refine_strategy", "payload": {"run_id": run.id}},
            "pending_strategy": {
                "strategy": {
                    "strategy_type": "buy_and_hold",
                    "asset_universe": ["AAPL"],
                    "asset_class": "equity",
                    "date_range": {"start": "2024-01-01", "end": "2024-12-31"},
                    "comparison_baseline": "SPY",
                },
                "requested_field": "refinement",
                "missing_required_fields": ["refinement"],
                "response_intent": {
                    "kind": "clarification",
                    "facts": {"latest_run_id": run.id},
                    "requested_fields": ["refinement"],
                },
            },
        },
    )

    fallback = pending_strategy_metadata_fallback_context(
        user_id=user_id,
        conversation_id=conversation["id"],
    )

    assert fallback is not None
    assert fallback.selected_thread_metadata is not None
    assert fallback.selected_thread_metadata["requested_field"] == "refinement"
    assert fallback.selected_thread_metadata["source_result_run_id"] == run.id
    snapshot = fallback.latest_task_snapshot
    assert snapshot is not None
    assert snapshot.pending_strategy_summary is not None
    reference = snapshot.latest_backtest_result_reference
    assert reference is not None
    assert reference.artifact_id == run.id
    assert reference.metadata["latest_run_id"] == run.id
    assert reference.metadata["chart"] == run.chart


def test_pending_response_intent_fallback_survives_ready_to_respond_outcome() -> None:
    from argus.api.chat.recovery import pending_strategy_metadata_fallback_context

    client = _client()
    conversation = _conversation(client)
    user_id = _user_id(client)
    response_intent = {
        "kind": "unsupported_recovery",
        "semantic_needs": ["simplification_choice"],
        "options": [
            {
                "label": "Compare with buy and hold",
                "replacement_values": {"strategy_type": "buy_and_hold"},
            }
        ],
    }
    create_message(
        user_id=user_id,
        conversation_id=conversation["id"],
        role="assistant",
        content=(
            "ATR 14 is not executable directly. Choose RSI, buy and hold, "
            "or moving-average crossover."
        ),
        metadata={
            "conversation_mode": "setup",
            "agent_runtime_stage_outcome": "ready_to_respond",
            "pending_strategy": {
                "strategy": {
                    "strategy_type": None,
                    "strategy_thesis": "Test TSLA with ATR 14 during 2024.",
                    "asset_universe": ["TSLA"],
                    "asset_class": "equity",
                    "date_range": {"start": "2024-01-01", "end": "2024-12-31"},
                    "capital_amount": 1000,
                    "entry_logic": "ATR 14",
                },
                "requested_field": None,
                "missing_required_fields": [],
                "response_intent": response_intent,
            },
        },
    )

    fallback = pending_strategy_metadata_fallback_context(
        user_id=user_id,
        conversation_id=conversation["id"],
    )

    assert fallback is not None
    assert fallback.latest_task_snapshot is not None
    assert fallback.latest_task_snapshot.pending_strategy_summary is not None
    assert fallback.selected_thread_metadata is not None
    assert fallback.selected_thread_metadata["response_intent"] == response_intent


def test_pending_edit_prompt_takes_precedence_over_older_confirmation_fallback() -> None:
    from argus.api.chat.recovery import (
        confirmation_metadata_fallback_context,
        pending_strategy_metadata_fallback_context,
    )

    client = _client()
    conversation = _conversation(client)
    user_id = _user_id(client)
    create_message(
        user_id=user_id,
        conversation_id=conversation["id"],
        role="assistant",
        content="Ready to test buy-and-hold for AAPL.",
        metadata=_confirmation_metadata(),
    )
    pending_metadata = _pending_strategy_metadata()
    pending_metadata["pending_strategy"]["requested_field"] = "asset_universe"
    pending_metadata["pending_strategy"]["missing_required_fields"] = [
        "asset_universe"
    ]
    create_message(
        user_id=user_id,
        conversation_id=conversation["id"],
        role="assistant",
        content="What asset should I use instead?",
        metadata=pending_metadata,
    )

    confirmation_fallback = confirmation_metadata_fallback_context(
        user_id=user_id,
        conversation_id=conversation["id"],
    )
    pending_fallback = pending_strategy_metadata_fallback_context(
        user_id=user_id,
        conversation_id=conversation["id"],
    )

    assert confirmation_fallback is None
    assert pending_fallback is not None
    assert pending_fallback.selected_thread_metadata is not None
    assert pending_fallback.selected_thread_metadata["requested_field"] == (
        "asset_universe"
    )


def test_failed_action_reload_keeps_explicit_zero_cost_pending_strategy() -> None:
    from argus.api.chat.recovery import failed_action_metadata_fallback_context

    client = _client()
    conversation = _conversation(client)
    user_id = _user_id(client)
    launch_payload = {
        "strategy_type": "buy_and_hold",
        "symbol": "MSFT",
        "symbols": ["MSFT"],
        "timeframe": "1D",
        "date_range": {"start": "2025-05-13", "end": "2026-05-13"},
        "sizing_mode": "capital_amount",
        "capital_amount": 1000,
        "benchmark_symbol": "SPY",
    }
    create_message(
        user_id=user_id,
        conversation_id=conversation["id"],
        role="assistant",
        content="The run failed, but the idea is still available to retry.",
        metadata={
            "conversation_mode": "setup",
            "agent_runtime_stage_outcome": "execution_failed_recoverably",
            "pending_strategy": {
                "strategy": {
                    "strategy_type": "buy_and_hold",
                    "strategy_thesis": "Buy and hold MSFT.",
                    "asset_universe": ["MSFT"],
                    "asset_class": "equity",
                    "timeframe": "1D",
                    "date_range": {
                        "start": "2025-05-13",
                        "end": "2026-05-13",
                    },
                    "sizing_mode": "capital_amount",
                    "capital_amount": 1000,
                    "comparison_baseline": "SPY",
                    "extra_parameters": {
                        "fee_rate": 0.0,
                        "slippage": 0.0,
                        "field_provenance": {
                            "fee_rate": "explicit_user",
                            "slippage": "explicit_user",
                        },
                    },
                }
            },
            "failed_action": {
                "artifact_id": "failed-zero-cost-run",
                "action_type": "run_backtest",
                "launch_payload": launch_payload,
                "failure_classification": "upstream_dependency_error",
                "error": "market_data_unavailable",
                "retryable": True,
            },
        },
    )

    fallback = failed_action_metadata_fallback_context(
        user_id=user_id,
        conversation_id=conversation["id"],
    )

    assert fallback is not None
    snapshot = fallback.latest_task_snapshot
    assert snapshot is not None
    assert snapshot.latest_failed_action_reference is not None
    pending = snapshot.pending_strategy_summary
    assert pending is not None
    assert pending.extra_parameters["fee_rate"] == 0.0
    assert pending.extra_parameters["slippage"] == 0.0
    assert pending.extra_parameters["field_provenance"] == {
        "fee_rate": "explicit_user",
        "slippage": "explicit_user",
    }


def test_failed_action_fallback_is_superseded_by_newer_completed_result() -> None:
    from argus.api import state as api_state
    from argus.api.chat.recovery import failed_action_metadata_fallback_context

    client = _client()
    conversation = _conversation(client)
    user_id = _user_id(client)
    launch_payload = {
        "strategy_type": "buy_and_hold",
        "symbol": "NVDA",
        "symbols": ["NVDA"],
        "timeframe": "1D",
        "date_range": {"start": "2026-01-01", "end": "2026-05-13"},
        "sizing_mode": "capital_amount",
        "capital_amount": 1000,
        "benchmark_symbol": "SPY",
    }
    create_message(
        user_id=user_id,
        conversation_id=conversation["id"],
        role="assistant",
        content="The run failed.",
        metadata={
            "latest_failed_action_reference": {
                "artifact_kind": "failed_action",
                "artifact_id": "failed-action-1",
                "artifact_status": "failed",
                "metadata": {
                    "action_type": "run_backtest",
                    "launch_payload": launch_payload,
                },
            }
        },
    )
    run_id = api_state.store.new_id()
    api_state.store.backtest_runs[run_id] = BacktestRun(
        id=run_id,
        conversation_id=conversation["id"],
        strategy_id=None,
        status="completed",
        asset_class="equity",
        symbols=["NVDA"],
        allocation_method="equal_weight",
        benchmark_symbol="SPY",
        metrics={"aggregate": {"performance": {"total_return_pct": 12.0}}},
        config_snapshot={"template": "buy_and_hold", "symbols": ["NVDA"]},
        conversation_result_card={
            "title": "NVDA buy and hold",
            "rows": [
                {"key": "total_return_pct", "label": "Total Return", "value": "+12.0%"}
            ],
            "assumptions": ["Benchmark: SPY"],
        },
        created_at=utcnow(),
        chart=None,
        trades=[],
    )
    api_state.store.backtest_run_owners[run_id] = user_id
    create_message(
        user_id=user_id,
        conversation_id=conversation["id"],
        role="assistant",
        content="Here is the completed result.",
        metadata={"result_run_id": run_id, "latest_run_id": run_id},
    )

    fallback = failed_action_metadata_fallback_context(
        user_id=user_id,
        conversation_id=conversation["id"],
    )

    assert fallback is None


def test_failed_turn_retry_marker_is_superseded_when_late_run_artifact_is_present_on_reload(
) -> None:
    from argus.api import state as api_state
    from argus.api.chat.recovery import latest_result_fallback_context

    client = _client()
    conversation = _conversation(client)
    user_id = _user_id(client)
    prompt = "Backtest buy and hold AAPL from January 2025 through June 2026"
    create_message(
        user_id=user_id,
        conversation_id=conversation["id"],
        role="user",
        content=prompt,
        metadata={},
    )
    failed_assistant = create_message(
        user_id=user_id,
        conversation_id=conversation["id"],
        role="assistant",
        content="Something went wrong. Your conversation is saved. Please try again.",
        metadata={
            "conversation_mode": "recovery",
            "agent_runtime_stage_outcome": "agent_runtime_failure",
            "recovery": {
                "code": "runtime_failure",
                "retryable": True,
                "language": "en",
            },
            "retry_last_turn": {
                "message": prompt,
            },
        },
    )
    run_id = api_state.store.new_id()
    api_state.store.backtest_runs[run_id] = BacktestRun(
        id=run_id,
        conversation_id=conversation["id"],
        strategy_id=None,
        status="completed",
        asset_class="equity",
        symbols=["AAPL"],
        allocation_method="equal_weight",
        benchmark_symbol="SPY",
        metrics={"aggregate": {"performance": {"total_return_pct": 12.0}}},
        config_snapshot={
            "template": "buy_and_hold",
            "symbols": ["AAPL"],
            "date_range": {"start": "2025-01-01", "end": "2026-06-05"},
        },
        conversation_result_card={
            "title": "AAPL buy and hold",
            "status_label": "Simulation Complete",
            "rows": [
                {
                    "key": "total_return_pct",
                    "label": "Total Return",
                    "value": "+12.0%",
                }
            ],
            "assumptions": ["Benchmark: SPY"],
        },
        created_at=utcnow(),
        chart=None,
        trades=[],
    )
    api_state.store.backtest_run_owners[run_id] = user_id
    completed_run = api_state.store.backtest_runs[run_id]
    create_message(
        user_id=user_id,
        conversation_id=conversation["id"],
        role="assistant",
        content="Here is the completed result.",
        metadata={
            "conversation_mode": "result_review",
            "agent_runtime_stage_outcome": "ready_to_respond",
            "result_card": completed_run.conversation_result_card,
            "result_run_id": run_id,
            "latest_run_id": run_id,
            "result_conversation_id": conversation["id"],
        },
    )

    result_fallback = latest_result_fallback_context(
        user_id=user_id,
        conversation_id=conversation["id"],
    )
    assert result_fallback is not None
    assert result_fallback.latest_task_snapshot is not None
    assert (
        result_fallback.latest_task_snapshot.latest_backtest_result_reference
        is not None
    )
    result_reference = (
        result_fallback.latest_task_snapshot.latest_backtest_result_reference
    )
    assert result_reference.artifact_id == run_id

    hydrated_messages = client.get(
        f"/api/v1/conversations/{conversation['id']}/messages"
    ).json()["items"]
    failed_reload_message = next(
        message
        for message in hydrated_messages
        if message["id"] == failed_assistant.id
    )
    assert "retry_last_turn" not in failed_reload_message["metadata"]
    recovery = failed_reload_message["metadata"].get("recovery")
    assert not (isinstance(recovery, dict) and recovery.get("retryable") is True)


def test_failed_turn_retry_marker_is_not_superseded_by_result_after_new_user_turn(
) -> None:
    from argus.api import state as api_state

    client = _client()
    conversation = _conversation(client)
    user_id = _user_id(client)
    failed_prompt = "Backtest buy and hold AAPL from January 2025 through June 2026"
    create_message(
        user_id=user_id,
        conversation_id=conversation["id"],
        role="user",
        content=failed_prompt,
        metadata={},
    )
    failed_assistant = create_message(
        user_id=user_id,
        conversation_id=conversation["id"],
        role="assistant",
        content="Something went wrong. Your conversation is saved. Please try again.",
        metadata={
            "conversation_mode": "recovery",
            "agent_runtime_stage_outcome": "agent_runtime_failure",
            "recovery": {
                "code": "runtime_failure",
                "retryable": True,
                "language": "en",
            },
            "retry_last_turn": {
                "message": failed_prompt,
            },
        },
    )
    create_message(
        user_id=user_id,
        conversation_id=conversation["id"],
        role="user",
        content="Now test buy and hold MSFT for 2025",
        metadata={},
    )
    run_id = api_state.store.new_id()
    api_state.store.backtest_runs[run_id] = BacktestRun(
        id=run_id,
        conversation_id=conversation["id"],
        strategy_id=None,
        status="completed",
        asset_class="equity",
        symbols=["MSFT"],
        allocation_method="equal_weight",
        benchmark_symbol="SPY",
        metrics={"aggregate": {"performance": {"total_return_pct": 9.0}}},
        config_snapshot={
            "template": "buy_and_hold",
            "symbols": ["MSFT"],
            "date_range": {"start": "2025-01-01", "end": "2025-12-31"},
        },
        conversation_result_card={
            "title": "MSFT buy and hold",
            "status_label": "Simulation Complete",
            "rows": [
                {
                    "key": "total_return_pct",
                    "label": "Total Return",
                    "value": "+9.0%",
                }
            ],
            "assumptions": ["Benchmark: SPY"],
        },
        created_at=utcnow(),
        chart=None,
        trades=[],
    )
    api_state.store.backtest_run_owners[run_id] = user_id
    completed_run = api_state.store.backtest_runs[run_id]
    create_message(
        user_id=user_id,
        conversation_id=conversation["id"],
        role="assistant",
        content="Here is the MSFT result.",
        metadata={
            "conversation_mode": "result_review",
            "agent_runtime_stage_outcome": "ready_to_respond",
            "result_card": completed_run.conversation_result_card,
            "result_run_id": run_id,
            "latest_run_id": run_id,
            "result_conversation_id": conversation["id"],
        },
    )

    hydrated_messages = client.get(
        f"/api/v1/conversations/{conversation['id']}/messages"
    ).json()["items"]
    failed_reload_message = next(
        message
        for message in hydrated_messages
        if message["id"] == failed_assistant.id
    )
    failed_metadata = failed_reload_message["metadata"]
    assert failed_metadata.get("agent_runtime_failure_superseded") is not True
    assert failed_metadata["retry_last_turn"] == {"message": failed_prompt}
    assert failed_metadata["recovery"]["retryable"] is True


def test_late_artifact_from_failed_request_stays_suppressed_after_retry_user_turn(
) -> None:
    from argus.api import state as api_state

    client = _client()
    conversation = _conversation(client)
    user_id = _user_id(client)
    prompt = "Backtest buy and hold AAPL from January 2025 through June 2026"
    failed_request_id = "failed-request-a"
    retry_request_id = "retry-request-b"
    create_message(
        user_id=user_id,
        conversation_id=conversation["id"],
        role="user",
        content=prompt,
        metadata={
            "agent_runtime_turn": {
                "status": "started",
                "conversation_id": conversation["id"],
                "request_id": failed_request_id,
            }
        },
    )
    create_message(
        user_id=user_id,
        conversation_id=conversation["id"],
        role="assistant",
        content="Something went wrong. Your conversation is saved. Please try again.",
        metadata={
            "conversation_mode": "recovery",
            "agent_runtime_stage_outcome": "agent_runtime_failure",
            "agent_runtime_turn": {
                "status": "failed",
                "terminal": True,
                "conversation_id": conversation["id"],
                "request_id": failed_request_id,
            },
            "recovery": {
                "code": "runtime_failure",
                "retryable": True,
                "language": "en",
            },
            "retry_last_turn": {
                "message": prompt,
            },
        },
    )
    create_message(
        user_id=user_id,
        conversation_id=conversation["id"],
        role="user",
        content=prompt,
        metadata={
            "agent_runtime_turn": {
                "status": "started",
                "conversation_id": conversation["id"],
                "request_id": retry_request_id,
            },
            "chat_action": {
                "type": "retry_last_turn",
                "payload": {"message": prompt},
            },
        },
    )

    old_request_metadata = _confirmation_metadata()
    old_request_metadata["agent_runtime_turn"] = {
        "status": "succeeded",
        "terminal": True,
        "conversation_id": conversation["id"],
        "request_id": failed_request_id,
    }
    suppressed = create_message(
        user_id=user_id,
        conversation_id=conversation["id"],
        role="assistant",
        content="Ready to test the old request.",
        metadata=old_request_metadata,
    )
    persisted_ids = {
        message.id for message in api_state.store.messages[conversation["id"]]
    }
    assert suppressed.id not in persisted_ids

    retry_metadata = _confirmation_metadata()
    retry_metadata["agent_runtime_turn"] = {
        "status": "succeeded",
        "terminal": True,
        "conversation_id": conversation["id"],
        "request_id": retry_request_id,
    }
    retry_artifact = create_message(
        user_id=user_id,
        conversation_id=conversation["id"],
        role="assistant",
        content="Ready to test the retry request.",
        metadata=retry_metadata,
    )
    persisted_ids = {
        message.id for message in api_state.store.messages[conversation["id"]]
    }
    assert retry_artifact.id in persisted_ids


def test_late_artifact_guard_fails_closed_when_strict_supabase_read_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api import state as api_state

    class FailingListGateway:
        def list_messages(self, **_: Any) -> list[Any]:
            raise RuntimeError("supabase read failed")

        def create_message(self, **_: Any) -> Any:
            raise AssertionError("late artifact write should not be attempted")

    client = _client()
    conversation = _conversation(client)
    user_id = _user_id(client)
    monkeypatch.setenv("ARGUS_DEV_MEMORY_FALLBACK", "false")
    monkeypatch.setattr(api_state, "supabase_gateway", FailingListGateway())
    metadata = _confirmation_metadata()
    metadata["agent_runtime_turn"] = {
        "status": "succeeded",
        "terminal": True,
        "conversation_id": conversation["id"],
        "request_id": "request-a",
    }

    with pytest.raises(RuntimeError, match="supabase read failed"):
        create_message(
            user_id=user_id,
            conversation_id=conversation["id"],
            role="assistant",
            content="Ready to test AAPL.",
            metadata=metadata,
        )


def _seed_completed_run(user_id: str, conversation_id: str) -> str:
    from argus.api import state as api_state

    run_id = api_state.store.new_id()
    run = BacktestRun(
        id=run_id,
        conversation_id=conversation_id,
        strategy_id=None,
        status="completed",
        asset_class="equity",
        symbols=["AAPL"],
        allocation_method="equal_weight",
        benchmark_symbol="SPY",
        metrics={
            "aggregate": {
                "performance": {"total_return_pct": 46.8},
                "risk": {"max_drawdown_pct": -13.8},
            },
            "by_symbol": {},
        },
        config_snapshot={"template": "buy_and_hold", "symbols": ["AAPL"]},
        conversation_result_card={
            "title": "AAPL buy and hold",
            "status_label": "Simulation Complete",
            "rows": [],
        },
        created_at=utcnow(),
    )
    api_state.store.backtest_runs[run_id] = run
    api_state.store.backtest_run_owners[run_id] = user_id
    return run_id


def _fact_answer_metadata(run_id: str) -> dict[str, Any]:
    return {
        "conversation_mode": "confirm",
        "agent_runtime_stage_outcome": "ready_to_respond",
        "result_run_id": run_id,
        "latest_run_id": run_id,
        "response_intent": {
            "kind": "unsupported_recovery",
            "facts": {
                "limitation_code": "latest_result_metric_unavailable",
                "requested_metric": "sortino_ratio",
            },
        },
    }


def test_confirmation_fallback_preserves_latest_result_context() -> None:
    from argus.api.chat.recovery import confirmation_metadata_fallback_context

    client = _client()
    conversation = _conversation(client)
    user_id = _user_id(client)
    run_id = _seed_completed_run(user_id, conversation["id"])
    create_message(
        user_id=user_id,
        conversation_id=conversation["id"],
        role="assistant",
        content="Simulation complete.",
        metadata={
            "agent_runtime_stage_outcome": "ready_to_respond",
            "result_run_id": run_id,
            "result_card": {"title": "AAPL buy and hold"},
        },
    )
    create_message(
        user_id=user_id,
        conversation_id=conversation["id"],
        role="assistant",
        content="Ready to run the six month version.",
        metadata=_confirmation_metadata(),
    )

    fallback = confirmation_metadata_fallback_context(
        user_id=user_id,
        conversation_id=conversation["id"],
    )

    assert fallback is not None
    snapshot = fallback.latest_task_snapshot
    assert snapshot is not None
    assert snapshot.active_confirmation_reference is not None
    assert snapshot.pending_strategy_summary is not None
    # A typed result question during an active confirmation must still see the
    # completed run, or the interpreter loses the latest-result context.
    reference = snapshot.latest_backtest_result_reference
    assert reference is not None
    assert reference.metadata["result_run_id"] == run_id
    assert fallback.selected_thread_metadata is not None
    assert fallback.selected_thread_metadata["source_result_run_id"] == run_id


def test_fact_answer_message_does_not_invalidate_active_confirmation() -> None:
    from argus.api.chat.recovery import confirmation_metadata_fallback_context

    client = _client()
    conversation = _conversation(client)
    user_id = _user_id(client)
    run_id = _seed_completed_run(user_id, conversation["id"])
    create_message(
        user_id=user_id,
        conversation_id=conversation["id"],
        role="assistant",
        content="Ready to run the six month version.",
        metadata=_confirmation_metadata(),
    )
    create_message(
        user_id=user_id,
        conversation_id=conversation["id"],
        role="assistant",
        content="The Sortino ratio is not stored for this result.",
        metadata=_fact_answer_metadata(run_id),
    )

    fallback = confirmation_metadata_fallback_context(
        user_id=user_id,
        conversation_id=conversation["id"],
    )

    # The typed fact reply carries result_run_id for continuity, but it is not
    # a new result card: the pending confirmation must stay active.
    assert fallback is not None
    assert fallback.latest_task_snapshot is not None
    assert fallback.latest_task_snapshot.active_confirmation_reference is not None
    assert fallback.latest_task_snapshot.latest_backtest_result_reference is not None


@pytest.mark.parametrize("language", ["en", "es-419"])
def test_issue_272_recovered_draft_clarifies_only_the_missing_field(
    language: str,
) -> None:
    from argus.agent_runtime.capabilities.contract import (
        build_default_capability_contract,
    )
    from argus.agent_runtime.stages.clarify import clarify_stage
    from argus.agent_runtime.state.models import RunState
    from argus.api.chat.recovery import ordinary_turn_metadata_fallback_context

    client = _client()
    conversation = _conversation(client)
    user_id = _user_id(client)
    pending_strategy = {
        "strategy_type": "buy_and_hold",
        "strategy_thesis": "Buy and hold NVDA.",
        "asset_universe": ["NVDA"],
        "asset_class": "equity",
        "timeframe": "1D",
        "date_range": {"start": "2023-01-03", "end": "2024-12-31"},
        "comparison_baseline": "SPY",
    }
    create_message(
        user_id=user_id,
        conversation_id=conversation["id"],
        role="assistant",
        content="The prior action failed before the amount was supplied.",
        metadata={
            "conversation_mode": "recovery",
            "agent_runtime_stage_outcome": "execution_failed_recoverably",
            "pending_strategy": {
                "strategy": pending_strategy,
                "requested_field": "capital_amount",
                "missing_required_fields": ["capital_amount"],
                "response_intent": {
                    "kind": "clarification",
                    "semantic_needs": ["sizing_amount"],
                    "requested_fields": ["capital_amount"],
                },
            },
            "failed_action": {
                "artifact_id": "issue-272-incomplete-failed-action",
                "action_type": "run_backtest",
                "launch_payload": {
                    "strategy_type": "buy_and_hold",
                    "symbols": ["NVDA"],
                    "timeframe": "1D",
                    "date_range": {
                        "start": "2023-01-03",
                        "end": "2024-12-31",
                    },
                    "benchmark_symbol": "SPY",
                },
                "failure_classification": "invalid_request",
                "error": "capital_amount_required",
                "retryable": True,
            },
        },
    )

    recovered = ordinary_turn_metadata_fallback_context(
        user_id=user_id,
        conversation_id=conversation["id"],
        language=language,
    )

    assert recovered is not None
    snapshot = recovered.latest_task_snapshot
    assert snapshot is not None
    assert snapshot.pending_strategy_summary is not None
    assert (
        snapshot.pending_strategy_summary.model_dump(
            exclude_none=True,
            exclude_defaults=True,
            exclude={"resolution_provenance"},
        )
        == pending_strategy
    )
    assert snapshot.latest_failed_action_reference is not None
    assert recovered.selected_thread_metadata["requested_field"] == "capital_amount"

    state = RunState.new(
        current_user_message="Continue." if language == "en" else "Continua.",
        recent_thread_history=[],
    )
    state.intent = "strategy_drafting"
    state.requested_field = recovered.selected_thread_metadata["requested_field"]
    state.missing_required_fields = ["capital_amount"]
    state.candidate_strategy_draft = snapshot.pending_strategy_summary

    clarification = clarify_stage(
        state=state,
        contract=build_default_capability_contract(),
        clarification_generator=None,
        language=language,
    )

    assert clarification.outcome == "await_user_reply"
    assert clarification.patch["requested_field"] == "capital_amount"
    assert clarification.patch["requested_fields"] == ["capital_amount"]
    assert clarification.patch["response_intent"]["semantic_needs"] == ["sizing_amount"]


def test_issue_272_failure_pending_does_not_displace_completed_result() -> None:
    from argus.api import state as api_state
    from argus.api.chat.recovery import ordinary_turn_metadata_fallback_context

    client = _client()
    conversation = _conversation(client)
    user_id = _user_id(client)
    run_id = _seed_completed_run(user_id, conversation["id"])
    completed_run = api_state.store.backtest_runs[run_id]
    completed_run.symbols = ["MSFT"]
    completed_run.config_snapshot = {
        "template": "buy_and_hold",
        "symbols": ["MSFT"],
    }
    create_message(
        user_id=user_id,
        conversation_id=conversation["id"],
        role="assistant",
        content="The MSFT result is complete.",
        metadata={
            "conversation_mode": "result_review",
            "agent_runtime_stage_outcome": "ready_to_respond",
            "result_card": completed_run.conversation_result_card,
            "result_run_id": run_id,
            "latest_run_id": run_id,
        },
    )
    create_message(
        user_id=user_id,
        conversation_id=conversation["id"],
        role="assistant",
        content="The later action failed before the draft was complete.",
        metadata={
            "conversation_mode": "recovery",
            "agent_runtime_stage_outcome": "execution_failed_recoverably",
            "pending_strategy": {
                "strategy": {
                    "strategy_type": "buy_and_hold",
                    "asset_universe": ["MSFT"],
                    "asset_class": "equity",
                },
                "requested_field": "capital_amount",
                "missing_required_fields": ["capital_amount", "date_range"],
            },
            "failed_action": {
                "artifact_id": "issue-272-sparse-failed-action",
                "action_type": "run_backtest",
                "launch_payload": {
                    "strategy_type": "buy_and_hold",
                    "symbols": ["MSFT"],
                    "timeframe": "1D",
                    "benchmark_symbol": "SPY",
                },
                "failure_classification": "invalid_request",
                "error": "capital_amount_required",
                "retryable": True,
            },
        },
    )

    recovered = ordinary_turn_metadata_fallback_context(
        user_id=user_id,
        conversation_id=conversation["id"],
        language="en",
    )

    assert recovered is not None
    snapshot = recovered.latest_task_snapshot
    assert snapshot is not None
    assert snapshot.pending_strategy_summary is None
    assert snapshot.latest_backtest_result_reference is not None
    assert snapshot.latest_backtest_result_reference.artifact_id == run_id
    assert snapshot.latest_failed_action_reference is not None
    assert (
        snapshot.latest_failed_action_reference.artifact_id
        == "issue-272-sparse-failed-action"
    )


def test_issue_272_current_clarification_keeps_pending_primary_without_result_read(
    monkeypatch,
) -> None:
    from argus.api import state as api_state
    from argus.api.chat import recovery as recovery_module

    client = _client()
    conversation = _conversation(client)
    user_id = _user_id(client)
    run_id = _seed_completed_run(user_id, conversation["id"])
    completed_run = api_state.store.backtest_runs[run_id]
    completed_run.symbols = ["MSFT"]
    completed_run.config_snapshot = {
        "template": "buy_and_hold",
        "symbols": ["MSFT"],
    }
    create_message(
        user_id=user_id,
        conversation_id=conversation["id"],
        role="assistant",
        content="The MSFT result is complete.",
        metadata={
            "conversation_mode": "result_review",
            "agent_runtime_stage_outcome": "ready_to_respond",
            "result_card": completed_run.conversation_result_card,
            "result_run_id": run_id,
            "latest_run_id": run_id,
        },
    )
    failed_action_id = "issue-272-retained-aapl-failed-action"
    create_message(
        user_id=user_id,
        conversation_id=conversation["id"],
        role="assistant",
        content="How much would you like to invest in NVDA?",
        metadata={
            "conversation_mode": "drafting",
            "agent_runtime_stage_outcome": "await_user_reply",
            "pending_strategy": {
                "strategy": {
                    "strategy_type": "buy_and_hold",
                    "strategy_thesis": "Buy and hold NVDA.",
                    "asset_universe": ["NVDA"],
                    "asset_class": "equity",
                    "timeframe": "1D",
                    "date_range": {
                        "start": "2023-01-03",
                        "end": "2024-12-31",
                    },
                    "comparison_baseline": "SPY",
                },
                "requested_field": "capital_amount",
                "missing_required_fields": ["capital_amount"],
                "response_intent": {
                    "kind": "clarification",
                    "semantic_needs": ["sizing_amount"],
                    "requested_fields": ["capital_amount"],
                },
                "source_result": {
                    "run_id": run_id,
                    "strategy_id": None,
                    "conversation_id": conversation["id"],
                },
            },
            "source_result_run_id": run_id,
            "failed_action": {
                "artifact_id": failed_action_id,
                "action_type": "run_backtest",
                "launch_payload": {
                    "strategy_type": "buy_and_hold",
                    "symbols": ["AAPL"],
                    "timeframe": "1D",
                    "date_range": {
                        "start": "2024-01-02",
                        "end": "2024-12-31",
                    },
                    "capital_amount": 1000,
                    "benchmark_symbol": "SPY",
                },
                "failure_classification": "upstream_dependency_error",
                "error": "market_data_unavailable",
                "retryable": True,
            },
        },
    )

    def _unexpected_result_lookup(**_kwargs: Any) -> None:
        raise AssertionError(
            "a current pending clarification must not query the result fallback"
        )

    monkeypatch.setattr(
        recovery_module,
        "latest_result_fallback_context",
        _unexpected_result_lookup,
    )

    recovered = recovery_module.ordinary_turn_metadata_fallback_context(
        user_id=user_id,
        conversation_id=conversation["id"],
        language="en",
    )

    assert recovered is not None
    snapshot = recovered.latest_task_snapshot
    assert snapshot is not None
    pending = snapshot.pending_strategy_summary
    assert pending is not None
    assert pending.asset_universe == ["NVDA"]
    assert snapshot.latest_backtest_result_reference is not None
    assert snapshot.latest_backtest_result_reference.artifact_id == run_id
    assert snapshot.latest_failed_action_reference is not None
    assert snapshot.latest_failed_action_reference.artifact_id == failed_action_id
    assert recovered.selected_thread_metadata is not None
    assert recovered.selected_thread_metadata["last_stage_outcome"] == "await_user_reply"
    assert (
        recovered.selected_thread_metadata["fallback_source"]
        == "pending_strategy_metadata"
    )
    assert recovered.selected_thread_metadata["requested_field"] == "capital_amount"


def test_fact_answer_message_does_not_block_pending_strategy_fallback() -> None:
    from argus.api.chat.recovery import pending_strategy_metadata_fallback_context

    client = _client()
    conversation = _conversation(client)
    user_id = _user_id(client)
    run_id = _seed_completed_run(user_id, conversation["id"])
    pending_metadata = _pending_strategy_metadata()
    pending_metadata["pending_strategy"]["strategy"]["date_range"] = {
        "start": "2025-01-01",
        "end": "2025-12-31",
    }
    pending_metadata["pending_strategy"]["source_result"] = {
        "run_id": run_id,
        "strategy_id": None,
        "conversation_id": conversation["id"],
    }
    pending_metadata["source_result_run_id"] = run_id

    create_message(
        user_id=user_id,
        conversation_id=conversation["id"],
        role="assistant",
        content="What would you like to change?",
        metadata=pending_metadata,
    )
    create_message(
        user_id=user_id,
        conversation_id=conversation["id"],
        role="assistant",
        content="The Sortino ratio is not stored for this result.",
        metadata=_fact_answer_metadata(run_id),
    )

    fallback = pending_strategy_metadata_fallback_context(
        user_id=user_id,
        conversation_id=conversation["id"],
    )

    assert fallback is not None
    snapshot = fallback.latest_task_snapshot
    assert snapshot is not None
    assert snapshot.pending_strategy_summary is not None
    assert snapshot.pending_strategy_summary.asset_universe == ["AAPL"]
    reference = snapshot.latest_backtest_result_reference
    assert reference is not None
    assert reference.artifact_id == run_id
    assert fallback.selected_thread_metadata is not None
    assert fallback.selected_thread_metadata["source_result_run_id"] == run_id


def test_pending_refinement_after_fact_answer_recovers_latest_result_reference() -> None:
    from argus.api.chat.recovery import pending_strategy_metadata_fallback_context

    client = _client()
    conversation = _conversation(client)
    user_id = _user_id(client)
    run_id = _seed_completed_run(user_id, conversation["id"])
    create_message(
        user_id=user_id,
        conversation_id=conversation["id"],
        role="assistant",
        content="Simulation complete.",
        metadata={
            "agent_runtime_stage_outcome": "execution_succeeded",
            "result_run_id": run_id,
            "latest_run_id": run_id,
            "result_card": {"title": "AAPL buy and hold"},
        },
    )
    pending_metadata = _pending_strategy_metadata()
    pending_metadata["pending_strategy"]["requested_field"] = "refinement"
    pending_metadata["pending_strategy"]["missing_required_fields"] = ["refinement"]
    create_message(
        user_id=user_id,
        conversation_id=conversation["id"],
        role="assistant",
        content="What would you like to change?",
        metadata=pending_metadata,
    )
    create_message(
        user_id=user_id,
        conversation_id=conversation["id"],
        role="assistant",
        content="The peak date was June 2, 2026.",
        metadata=_fact_answer_metadata(run_id),
    )

    fallback = pending_strategy_metadata_fallback_context(
        user_id=user_id,
        conversation_id=conversation["id"],
    )

    assert fallback is not None
    assert fallback.latest_task_snapshot is not None
    reference = fallback.latest_task_snapshot.latest_backtest_result_reference
    assert reference is not None
    assert reference.artifact_id == run_id
    assert fallback.selected_thread_metadata is not None
    assert fallback.selected_thread_metadata["requested_field"] == "refinement"
    assert fallback.selected_thread_metadata["source_result_run_id"] == run_id
