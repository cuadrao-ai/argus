from __future__ import annotations

import json
from typing import Any

import pytest
from argus.api.main import app
from argus.domain.engine import SymbolAsset
from argus.domain.indicators import IndicatorInfo
from argus.domain.market_data.assets import ResolvedAsset
from fastapi.testclient import TestClient


def test_chat_action_display_message_resolves_label_key_by_language() -> None:
    from argus.api.chat.actions import chat_display_message
    from argus.api.schemas import ChatStreamRequest

    payload = ChatStreamRequest.model_validate(
        {
            "conversation_id": "conversation-1",
            "language": "es-419",
            "action": {
                "type": "show_breakdown",
                "label": "Explain result",
                "labelKey": "chat.result_card.explain_result",
                "presentation": "result",
                "payload": {"run_id": "run-1"},
            },
        }
    )

    assert chat_display_message(payload, language="es-419") == "Explicar resultado"
    assert chat_display_message(payload, language="en") == "Explain result"


@pytest.mark.parametrize(
    ("language", "expected"),
    [("en", "Change benchmark"), ("es-419", "Cambiar referencia")],
)
def test_coverage_recovery_action_uses_localized_typed_label(
    language: str,
    expected: str,
) -> None:
    from argus.api.chat.actions import chat_display_message, chat_request_message
    from argus.api.schemas import ChatStreamRequest

    payload = ChatStreamRequest.model_validate(
        {
            "conversation_id": "conversation-1",
            "language": language,
            "action": {
                "type": "select_response_option",
                "label": "Change benchmark",
                "labelKey": "chat.coverage_recovery.actions.change_benchmark",
                "payload": {
                    "option_id": "change_benchmark",
                    "replacement_values": {"requested_field": "comparison_baseline"},
                },
            },
        }
    )

    assert chat_request_message(payload, language=language) == expected
    assert chat_display_message(payload, language=language) == expected


@pytest.mark.parametrize(
    ("language", "expected"),
    [("en", "Retry with daily bars"), ("es-419", "Usar barras diarias")],
)
def test_timeframe_recovery_action_uses_localized_typed_label(
    language: str,
    expected: str,
) -> None:
    from argus.api.chat.actions import chat_display_message, chat_request_message
    from argus.api.schemas import ChatStreamRequest

    payload = ChatStreamRequest.model_validate(
        {
            "conversation_id": "conversation-1",
            "language": language,
            "action": {
                "type": "select_response_option",
                "label": "Retry with daily bars",
                "labelKey": "chat.clarification.timeframe_actions.daily",
                "payload": {
                    "option_id": "option_0",
                    "replacement_values": {"timeframe": "1D"},
                },
            },
        }
    )

    assert chat_request_message(payload, language=language) == expected
    assert chat_display_message(payload, language=language) == expected


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/api/v1/dev/reset")
    return client


def _stream_payloads(stream: str, event_name: str) -> list[dict[str, Any]]:
    payloads = []
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
        payload = json.loads(raw)
        event_line = next(
            (line for line in part.splitlines() if line.startswith("event: ")),
            None,
        )
        if event_line == f"event: {event_name}":
            payloads.append(payload)
            continue
        if payload.get("type") == event_name:
            if event_name == "token":
                payloads.append(
                    {"text": payload.get("content") or payload.get("text") or ""}
                )
            else:
                payloads.append(payload)
            continue
        if payload.get("type") != "final":
            continue
        final_payload = payload.get("payload")
        if not isinstance(final_payload, dict):
            continue
        if event_name == "confirmation" and isinstance(
            final_payload.get("confirmation"), dict
        ):
            payloads.append({"confirmation": final_payload["confirmation"]})
        if event_name == "result" and isinstance(final_payload.get("run"), dict):
            run = final_payload["run"]
            payloads.append({"run": run, "payload": {"run": run}})
        if event_name == "final":
            payloads.append(final_payload)
    return payloads


def _conversation(client: TestClient) -> dict[str, Any]:
    return client.post("/api/v1/conversations", json={}).json()["conversation"]


def _confirmation_runtime_result() -> dict[str, Any]:
    return {
        "stage_outcome": "await_approval",
        "assistant_response": "Ready to test AAPL with buy and hold.",
        "confirmation_payload": {
            "strategy": {
                "strategy_type": "buy_and_hold",
                "asset_universe": ["AAPL"],
                "date_range": {"start": "2025-05-03", "end": "2026-05-03"},
                "capital_amount": 10000,
            },
            "optional_parameters": {
                "initial_capital": {
                    "value": 1000.0,
                    "source": "default",
                    "label": "Initial capital",
                    "description": "Starting cash",
                },
                "timeframe": {
                    "value": "1D",
                    "source": "default",
                    "label": "Timeframe",
                    "description": "Bar interval",
                },
                "fees": {"value": 0.0, "source": "default", "label": "Fees"},
                "slippage": {"value": 0.0, "source": "default", "label": "Slippage"},
            },
            "launch_payload": {
                "strategy_type": "buy_and_hold",
                "symbol": "AAPL",
                "symbols": ["AAPL"],
                "timeframe": "1D",
                "date_range": {"start": "2025-05-03", "end": "2026-05-03"},
                "sizing_mode": "capital_amount",
                "capital_amount": 1000.0,
                "benchmark_symbol": "SPY",
            },
            "validation": {"executable": True},
        },
    }


def _pending_runtime_result() -> dict[str, Any]:
    return {
        "stage_outcome": "await_user_reply",
        "assistant_prompt": "What asset should I use instead?",
        "requested_field": "asset_universe",
        "pending_strategy": {
            "strategy": {
                "strategy_type": "buy_and_hold",
                "strategy_thesis": "Buy and hold Apple.",
                "asset_universe": ["AAPL"],
                "asset_class": "equity",
                "date_range": "past year",
            },
            "requested_field": "asset_universe",
            "missing_required_fields": ["asset_universe"],
        },
    }


def _result_runtime_result() -> dict[str, Any]:
    result_card = {
        "title": "AAPL buy and hold",
        "date_range": {
            "start": "2025-05-03",
            "end": "2026-05-03",
            "display": "May 3, 2025 to May 3, 2026",
        },
        "status_label": "Completed",
        "rows": [
            {"key": "total_return_pct", "label": "Total Return (%)", "value": "+12.4%"},
            {"key": "benchmark_delta", "label": "Benchmark", "value": "+2.1% vs SPY"},
        ],
        "assumptions": ["$10,000 starting capital", "1D bars", "Benchmark: SPY"],
        "benchmark_note": "Compared with SPY.",
        "actions": [
            {
                "id": "show-breakdown",
                "type": "show_breakdown",
                "label": "Show a breakdown",
                "presentation": "result",
                "payload": {},
            },
            {
                "id": "refine-strategy",
                "type": "refine_strategy",
                "label": "Refine strategy",
                "presentation": "result",
                "payload": {},
            },
        ],
    }
    return {
        "stage_outcome": "end_run",
        "assistant_response": "Short grounded summary from the runtime.",
        "final_response_payload": {
            "result_card": result_card,
            "result": {
                "resolved_strategy": {
                    "strategy_type": "buy_and_hold",
                    "symbol": "AAPL",
                    "asset_universe": ["AAPL"],
                },
                "resolved_parameters": {
                    "timeframe": "1D",
                    "date_range": "May 3, 2025 to May 3, 2026",
                },
                "metrics": {
                    "aggregate": {
                        "performance": {
                            "total_return_pct": 12.4,
                            "delta_vs_benchmark_pct": 2.1,
                        }
                    }
                },
                "benchmark_metrics": {"benchmark_symbol": "SPY"},
            },
        },
    }


def _async_backtest_job_runtime_result() -> dict[str, Any]:
    return {
        "stage_outcome": "ready_to_respond",
        "assistant_response": (
            "I started the backtest. You can leave this chat and come back; "
            "I will show the result here as soon as it is ready."
        ),
        "final_response_payload": {
            "backtest_job": {
                "id": "job-async-1",
                "conversation_id": "conversation-1",
                "request_message_id": "request-message-1",
                "confirmation_message_id": "confirmation-message-1",
                "status": "queued",
                "result_run_id": None,
                "failure_code": None,
                "failure_detail": None,
                "retryable": False,
                "queued_at": "2026-06-06T12:00:00Z",
                "started_at": None,
                "finished_at": None,
                "created_at": "2026-06-06T12:00:00Z",
                "updated_at": "2026-06-06T12:00:00Z",
            }
        },
        "artifact_references": [
            {
                "artifact_kind": "backtest_job",
                "artifact_id": "job-async-1",
                "artifact_status": "queued",
                "metadata": {
                    "id": "job-async-1",
                    "conversation_id": "conversation-1",
                    "status": "queued",
                },
            }
        ],
    }


@pytest.mark.parametrize("benchmark_symbol", ["QQQ", "IWM"])
def test_runtime_backtest_run_persists_explicit_benchmark_from_envelope(
    benchmark_symbol: str,
) -> None:
    from argus.api.chat.persistence import build_runtime_backtest_run

    engine_config = {
        "template": "buy_and_hold",
        "asset_class": "equity",
        "symbols": ["AAPL"],
        "timeframe": "1D",
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "side": "long",
        "starting_capital": 1000.0,
        "allocation_method": "equal_weight",
        "benchmark_symbol": benchmark_symbol,
        "parameters": {},
    }
    run = build_runtime_backtest_run(
        user_id="user-1",
        conversation_id="conversation-1",
        result_card={
            "title": "AAPL buy and hold",
            "rows": [],
            "metrics": [],
            "assumptions": [f"Benchmark: {benchmark_symbol}"],
            "actions": [],
        },
        envelope={
            "resolved_strategy": {
                "strategy_type": "buy_and_hold",
                "symbol": "AAPL",
                "asset_universe": ["AAPL"],
            },
            "resolved_parameters": {
                "timeframe": "1D",
                "date_range": {"start": "2024-01-01", "end": "2024-12-31"},
                "benchmark_symbol": benchmark_symbol,
                "engine_config": engine_config,
            },
            "metrics": {"aggregate": {"performance": {"total_return_pct": 12.4}}},
            "benchmark_metrics": {
                "symbol": benchmark_symbol,
                "aggregate": {"total_return_pct": 8.1},
            },
        },
        classify_symbol_func=lambda symbol: SymbolAsset(
            symbol=symbol.strip().upper(), asset_class="equity"
        ),
        default_benchmark_func=lambda _asset_class, _symbols: "SPY",
    )

    assert run is not None
    assert run.benchmark_symbol == benchmark_symbol
    assert run.config_snapshot["benchmark_symbol"] == benchmark_symbol
    assert run.config_snapshot["resolved_parameters"]["benchmark_symbol"] == (
        benchmark_symbol
    )
    assert run.config_snapshot["engine_config"] == engine_config


def test_runtime_backtest_run_freezes_replay_snapshot_and_chart_payload() -> None:
    from argus.api.chat.persistence import build_runtime_backtest_run

    engine_config = {
        "template": "rsi_mean_reversion",
        "asset_class": "equity",
        "symbols": ["AAPL"],
        "timeframe": "1D",
        "start_date": "2024-01-01",
        "end_date": "2024-01-31",
        "side": "long",
        "starting_capital": 1000.0,
        "allocation_method": "equal_weight",
        "benchmark_symbol": "SPY",
        "parameters": {"rsi_window": 14},
    }
    result_card = {
        "title": "AAPL RSI",
        "rows": [],
        "metrics": [],
        "assumptions": ["Benchmark: SPY"],
        "chart": {
            "kind": "portfolio_equity",
            "series": [{"time": "2024-01-02", "value": 1000.0}],
            "markers": [
                {
                    "time": "2024-01-02",
                    "type": "entry",
                    "label": "Buy AAPL",
                    "symbols": ["AAPL"],
                }
            ],
            "value_summary": {
                "peak_value": 1000.0,
                "lowest_value": 1000.0,
                "currency": "USD",
                "source": "strategy_portfolio_equity_close",
            },
        },
        "actions": [
            {
                "type": "show_breakdown",
                "payload": {"nested": {"source": "engine"}},
            }
        ],
    }
    envelope = {
        "resolved_strategy": {
            "strategy_type": "rsi_mean_reversion",
            "symbol": "AAPL",
            "asset_universe": ["AAPL"],
        },
        "resolved_parameters": {
            "timeframe": "1D",
            "date_range": {"start": "2024-01-01", "end": "2024-01-31"},
            "benchmark_symbol": "SPY",
            "engine_config": engine_config,
        },
        "metrics": {"aggregate": {"performance": {"total_return_pct": 4.2}}},
        "benchmark_metrics": {"symbol": "SPY"},
        "provider_metadata": {"provider": "alpaca", "coverage": {"bars": 21}},
    }

    run = build_runtime_backtest_run(
        user_id="user-1",
        conversation_id="conversation-1",
        result_card=result_card,
        envelope=envelope,
        classify_symbol_func=lambda symbol: SymbolAsset(
            symbol=symbol.strip().upper(), asset_class="equity"
        ),
        default_benchmark_func=lambda _asset_class, _symbols: "SPY",
    )
    assert run is not None

    engine_config["parameters"]["rsi_window"] = 21
    envelope["resolved_parameters"]["date_range"]["start"] = "2023-01-01"
    envelope["provider_metadata"]["coverage"]["bars"] = 0
    result_card["chart"]["markers"][0]["label"] = "Mutated"
    result_card["actions"][0]["payload"]["nested"]["source"] = "mutated"

    assert run.config_snapshot["engine_config"]["parameters"]["rsi_window"] == 14
    assert run.config_snapshot["resolved_parameters"]["date_range"]["start"] == (
        "2024-01-01"
    )
    assert run.config_snapshot["provider_metadata"]["coverage"]["bars"] == 21
    assert run.chart["markers"][0]["label"] == "Buy AAPL"
    assert run.trades[0]["label"] == "Buy AAPL"
    assert (
        run.conversation_result_card["actions"][0]["payload"]["nested"]["source"]
        == "engine"
    )


def test_runtime_backtest_run_prefers_resolved_explicit_benchmark_over_default() -> None:
    from argus.api.chat.persistence import build_runtime_backtest_run

    run = build_runtime_backtest_run(
        user_id="user-1",
        conversation_id="conversation-1",
        result_card={
            "title": "BTC buy and hold",
            "rows": [],
            "metrics": [],
            "assumptions": ["Benchmark: ETH"],
            "actions": [],
        },
        envelope={
            "resolved_strategy": {
                "strategy_type": "buy_and_hold",
                "symbol": "BTC",
                "asset_universe": ["BTC"],
            },
            "resolved_parameters": {
                "timeframe": "1D",
                "date_range": {"start": "2024-01-01", "end": "2024-12-31"},
                "benchmark_symbol": "ETH",
            },
            "metrics": {"aggregate": {"performance": {"total_return_pct": 12.4}}},
            "benchmark_metrics": {"aggregate": {"total_return_pct": 8.1}},
        },
        classify_symbol_func=lambda symbol: SymbolAsset(
            symbol=symbol.strip().upper(), asset_class="crypto"
        ),
        default_benchmark_func=lambda _asset_class, _symbols: "BTC",
    )

    assert run is not None
    assert run.benchmark_symbol == "ETH"
    assert run.config_snapshot["benchmark_symbol"] == "ETH"


def _stream_events_from_runtime(runtime):
    async def _events(**kwargs: Any):
        yield {"type": "final", "payload": runtime(**kwargs)}

    return _events


@pytest.fixture(autouse=True)
def _patch_runtime_io(monkeypatch: pytest.MonkeyPatch) -> None:
    from argus.api import backtest_service
    from argus.api import state as api_state
    from argus.api.chat import persistence as chat_persistence

    monkeypatch.setattr(api_state, "supabase_gateway", None)
    monkeypatch.setattr(
        backtest_service,
        "classify_symbol",
        lambda symbol: SymbolAsset(symbol=symbol.strip().upper(), asset_class="equity"),
    )
    monkeypatch.setattr(
        chat_persistence,
        "classify_symbol",
        lambda symbol: SymbolAsset(symbol=symbol.strip().upper(), asset_class="equity"),
    )


def test_discovery_endpoints_return_assets_and_indicators(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.routers import discovery as discovery_router

    monkeypatch.setattr(
        discovery_router,
        "search_assets",
        lambda q, limit=12: [
            ResolvedAsset(
                canonical_symbol="AAPL",
                asset_class="equity",
                name="Apple Inc.",
                raw_symbol=q,
            )
        ],
    )
    monkeypatch.setattr(
        discovery_router,
        "search_indicators",
        lambda q, limit=12: [
            IndicatorInfo("rsi", "RSI", "Relative Strength Index", "executable")
        ],
    )
    client = _client()

    assets = client.get("/api/v1/discovery/assets?q=apple&limit=5")
    indicators = client.get("/api/v1/discovery/indicators?q=rsi&limit=5")

    assert assets.status_code == 200
    assert assets.json()["items"][0]["insert_text"] == "AAPL"
    assert indicators.status_code == 200
    assert indicators.json()["items"][0]["provider"] == "pandas-ta-classic"
    assert indicators.json()["items"][0]["support_status"] == "supported"


def test_discovery_indicators_show_only_supported_indicators(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.routers import discovery as discovery_router

    monkeypatch.setattr(
        discovery_router,
        "search_indicators",
        lambda q, limit=12: [
            IndicatorInfo("rsi", "RSI", "Relative Strength Index", "executable"),
            IndicatorInfo("atr", "ATR", "Average true range", "draft_only"),
        ],
    )
    client = _client()

    response = client.get("/api/v1/discovery/indicators?q=r&limit=5")

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["symbol"] for item in items] == ["rsi"]
    assert all(item["support_status"] == "supported" for item in items)


def test_discovery_assets_preserve_provider_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.routers import discovery as discovery_router

    monkeypatch.setattr(
        discovery_router,
        "search_assets",
        lambda q, limit=12: [
            ResolvedAsset(
                canonical_symbol="BTC",
                asset_class="crypto",
                name="Bitcoin",
                raw_symbol=q,
                provider="kraken",
            )
        ],
    )
    client = _client()

    response = client.get("/api/v1/discovery/assets?q=btc&limit=5")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["symbol"] == "BTC"
    assert item["asset_class"] == "crypto"
    assert item["provider"] == "kraken"


def test_discovery_assets_display_currency_pair_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.routers import discovery as discovery_router

    monkeypatch.setattr(
        discovery_router,
        "search_assets",
        lambda q, limit=12: [
            ResolvedAsset(
                canonical_symbol="EURUSD",
                asset_class="currency_pair",
                name="EUR/USD",
                raw_symbol=q,
            )
        ],
    )
    client = _client()

    response = client.get("/api/v1/discovery/assets?q=eur/usd&limit=5")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["description"] == "Currency Pair"
    assert item["provider"] == "kraken"
    assert "currency_pair" not in item["description"]
