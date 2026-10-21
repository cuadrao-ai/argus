from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

import pandas as pd
import pytest
from argus.api import memory_search_candidates
from argus.api import state as api_state
from argus.api.main import app
from argus.api.memory_ledger_index import MemoryLedgerWorkLimitExceeded
from argus.api.message_store import memory_conversation, memory_message
from argus.api.schemas import (
    BacktestRun,
    Collection,
    Conversation,
    DecisionNote,
    EvidenceArtifact,
    Idea,
    IdeaVersion,
    Strategy,
)
from argus.domain.market_data.assets import ResolvedAsset
from argus.domain.market_data.new_york_clock import new_york_today
from argus.domain.owner_scope import PERSONAL
from argus.domain.store import utcnow
from fastapi.testclient import TestClient
from pydantic import ValidationError


def _stream_events(stream: str) -> list[dict[str, Any]]:
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
            events.append({"type": "done"})
            continue
        events.append(json.loads(raw))
    return events


def _final_payload(stream: str) -> dict[str, Any]:
    final_events = [
        event for event in _stream_events(stream) if event.get("type") == "final"
    ]
    assert len(final_events) == 1
    payload = final_events[0]["payload"]
    assert isinstance(payload, dict)
    return payload


def _fake_resolve_asset(symbol: str) -> ResolvedAsset:
    candidate = symbol.strip().upper().replace("-", "/")
    if candidate == "TESLA":
        candidate = "TSLA"
    compact = candidate.replace("/", "")
    if compact.endswith("USD") and len(compact) > 3:
        compact = compact[:-3]

    if compact in {"AAPL", "TSLA", "MSFT", "SPY"}:
        return ResolvedAsset(
            canonical_symbol=compact,
            asset_class="equity",
            name=compact,
            raw_symbol=compact,
        )
    if compact in {"BTC", "ETH", "USDC", "USDT"}:
        return ResolvedAsset(
            canonical_symbol=compact,
            asset_class="crypto",
            name=compact,
            raw_symbol=compact,
        )
    raise ValueError("invalid_symbol")


def _fake_fetch_ohlcv(
    symbol: str,
    asset_class: str,  # noqa: ARG001
    start_date: date,
    end_date: date,
    timeframe: str,
) -> pd.DataFrame:
    freq_map = {"1D": "D", "1h": "h", "2h": "2h", "4h": "4h", "6h": "6h", "12h": "12h"}
    index = pd.date_range(
        start=start_date, end=end_date, freq=freq_map[timeframe], tz="UTC"
    )
    if len(index) < 80:
        index = pd.date_range(
            start=start_date, periods=80, freq=freq_map[timeframe], tz="UTC"
        )
    base_map = {"AAPL": 100.0, "TSLA": 200.0, "MSFT": 150.0, "SPY": 400.0, "BTC": 30000.0}
    base = base_map.get(symbol, 100.0)
    close = pd.Series(base + pd.RangeIndex(len(index)).astype(float) * 0.5, index=index)
    return pd.DataFrame(
        {
            "open": close * 0.999,
            "high": close * 1.002,
            "low": close * 0.998,
            "close": close,
            "volume": 5000.0,
        },
        index=index,
    )


def _fake_fetch_price_series(
    symbol: str,
    asset_class: str,
    start_date: date,
    end_date: date,
    timeframe: str,
) -> pd.Series:
    return _fake_fetch_ohlcv(
        symbol=symbol,
        asset_class=asset_class,
        start_date=start_date,
        end_date=end_date,
        timeframe=timeframe,
    )["close"]


def _runtime_success_result(
    *,
    symbol: str = "TSLA",
    timeframe: str = "1D",
    language: str = "en",
    assistant_response: str | None = None,
) -> dict[str, Any]:
    assistant_copy = assistant_response or (
        "Probé la idea con TSLA."
        if language.lower().startswith("es")
        else f"I tested that idea with {symbol}."
    )
    return {
        "stage_outcome": "ready_to_respond",
        "assistant_response": assistant_copy,
        "final_response_payload": {
            "result": {
                "execution_status": "succeeded",
                "resolved_strategy": {
                    "strategy_type": "rsi_mean_reversion",
                    "asset_universe": [symbol],
                },
                "resolved_parameters": {
                    "timeframe": timeframe,
                    "date_range": {
                        "start": "2025-01-01",
                        "end": "2025-12-31",
                    },
                },
                "metrics": {
                    "aggregate": {"performance": {"total_return_pct": 12.5}},
                    "by_symbol": {},
                },
                "benchmark_metrics": {
                    "benchmark_symbol": "BTC" if symbol == "BTC" else "SPY",
                    "benchmark_return_pct": 9.2,
                },
                "assumptions": ["Starting capital: $10,000."],
                "caveats": [],
            },
            "result_card": {
                "title": f"{symbol} RSI Mean Reversion",
                "status_label": "Simulation Complete",
                "rows": [{"label": "Total Return", "value": "+12.5%"}],
                "assumptions": ["Starting capital: $10,000."],
            },
        },
    }


def _runtime_success_for_message(**kwargs: Any) -> dict[str, Any]:
    message = str(kwargs.get("message", ""))
    language = str(getattr(kwargs.get("user"), "language_preference", "en"))
    upper_message = message.upper()
    symbol = "BTC" if "BTC" in upper_message or "BITCOIN" in upper_message else "TSLA"
    timeframe = "1h" if "1h" in message.lower() else "1D"
    return _runtime_success_result(
        symbol=symbol,
        timeframe=timeframe,
        language=language,
    )


async def _runtime_success_for_message_async(**kwargs: Any) -> dict[str, Any]:
    return _runtime_success_for_message(**kwargs)


async def _runtime_success_events(**kwargs: Any):
    result = _runtime_success_for_message(**kwargs)
    assistant_response = str(result.get("assistant_response") or "")
    yield {"type": "stage_start", "stage": "interpret"}
    yield {"type": "stage_start", "stage": "explain"}
    yield {"type": "stage_outcome", "outcome": str(result["stage_outcome"])}
    if assistant_response:
        yield {"type": "token", "content": assistant_response}
    yield {"type": "final", "payload": result}


@pytest.fixture(autouse=True)
def _patch_engine_io(monkeypatch: pytest.MonkeyPatch) -> None:
    from argus.api import state as api_state
    from argus.api.routers import agent as agent_router
    from argus.domain import engine as domain_engine

    monkeypatch.setattr(api_state, "supabase_gateway", None)
    monkeypatch.setattr(agent_router, "stream_agent_turn_events", _runtime_success_events)
    monkeypatch.setattr(domain_engine, "resolve_asset", _fake_resolve_asset)
    monkeypatch.setattr(domain_engine, "fetch_ohlcv", _fake_fetch_ohlcv)
    monkeypatch.setattr(domain_engine, "fetch_price_series", _fake_fetch_price_series)


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/api/v1/dev/reset")
    return client


def _store_search_conversation(
    *,
    user_id: str,
    conversation_id: str,
    title: str,
    updated_at: Any,
    archived: bool = False,
    deleted_at: Any = None,
) -> None:
    conversation = Conversation(
        id=conversation_id,
        title=title,
        title_source="user_renamed",
        pinned=False,
        archived=archived,
        deleted_at=deleted_at,
        created_at=updated_at,
        updated_at=updated_at,
        last_message_preview=None,
        language="en",
    )
    api_state.store.conversations[conversation.id] = conversation
    api_state.store.conversation_owners[conversation.id] = user_id


def test_me_returns_contract_user_profile() -> None:
    client = _client()

    response = client.get("/api/v1/me")

    assert response.status_code == 200
    assert response.headers["x-request-id"]
    payload = response.json()
    assert payload["user"]["language"] == "en"
    assert payload["user"]["locale"] == "en-US"
    assert "theme" not in payload["user"]
    assert payload["user"]["onboarding"] == {
        "completed": False,
        "stage": "language_selection",
        "language_confirmed": False,
        "primary_goal": None,
    }


def test_patch_me_updates_language_preferences() -> None:
    client = _client()

    response = client.patch(
        "/api/v1/me",
        json={"language": "es-419", "locale": "es-419"},
    )

    assert response.status_code == 200
    user = response.json()["user"]
    assert user["language"] == "es-419"
    assert user["locale"] == "es-419"


def test_conversation_messages_and_patch_follow_contract() -> None:
    client = _client()

    created = client.post(
        "/api/v1/conversations", json={"title": None, "language": "es-419"}
    )
    assert created.status_code == 200
    conversation = created.json()["conversation"]
    assert conversation["title_source"] == "system_default"
    assert conversation["language"] == "es-419"

    messages = client.get(f"/api/v1/conversations/{conversation['id']}/messages")
    assert messages.status_code == 200
    assert messages.json() == {"items": [], "next_cursor": None, "surface": "personal"}

    patched = client.patch(
        f"/api/v1/conversations/{conversation['id']}",
        json={"title": "Tesla dip idea", "pinned": True, "archived": False},
    )
    assert patched.status_code == 200
    assert patched.json()["conversation"]["title_source"] == "user_renamed"
    assert patched.json()["conversation"]["pinned"] is True


def test_unknown_conversation_messages_return_not_found() -> None:
    client = _client()

    response = client.get(
        "/api/v1/conversations/00000000-0000-4000-8000-000000000000/messages"
    )

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_deleted_conversation_messages_return_not_found() -> None:
    client = _client()
    conversation = client.post("/api/v1/conversations", json={}).json()["conversation"]

    stream = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": conversation["id"],
            "message": "Backtest Tesla when it dips",
            "language": "en",
        },
    )
    assert stream.status_code == 200

    hydrated = client.get(f"/api/v1/conversations/{conversation['id']}/messages")
    assert hydrated.status_code == 200
    assert len(hydrated.json()["items"]) > 0

    deleted = client.delete(f"/api/v1/conversations/{conversation['id']}")
    assert deleted.status_code == 200

    response = client.get(f"/api/v1/conversations/{conversation['id']}/messages")

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_backtest_rejects_mixed_asset_symbols_with_problem_details() -> None:
    client = _client()

    response = client.post(
        "/api/v1/backtests/run",
        headers={"Idempotency-Key": "mixed-assets"},
        json={
            "template": "rsi_mean_reversion",
            "asset_class": "equity",
            "symbols": ["AAPL", "BTC"],
        },
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["code"] == "mixed_asset_not_supported"
    assert payload["request_id"]
    assert payload["context"]["conflicting_symbols"] == [
        {"symbol": "AAPL", "asset_class": "equity"},
        {"symbol": "BTC", "asset_class": "crypto"},
    ]


def test_backtest_run_requires_idempotency_key_header() -> None:
    client = _client()

    response = client.post(
        "/api/v1/backtests/run",
        json={
            "template": "rsi_mean_reversion",
            "asset_class": "equity",
            "symbols": ["AAPL"],
        },
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == "idempotency_key_required"
    assert payload["request_id"]


def test_backtest_rejects_explicit_asset_class_conflict() -> None:
    client = _client()

    response = client.post(
        "/api/v1/backtests/run",
        headers={"Idempotency-Key": "asset-class-conflict"},
        json={
            "template": "rsi_mean_reversion",
            "asset_class": "crypto",
            "symbols": ["AAPL"],
        },
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["code"] == "asset_class_conflict"
    assert payload["context"] == {
        "requested_asset_class": "crypto",
        "inferred_asset_class": "equity",
        "symbols": ["AAPL"],
    }


def test_backtest_run_normalizes_defaults_persists_metrics_and_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARGUS_ENABLE_EXECUTION_REALISM", "false")
    client = _client()
    conversation = client.post("/api/v1/conversations", json={}).json()["conversation"]

    response = client.post(
        "/api/v1/backtests/run",
        headers={"Idempotency-Key": "tsla-dip"},
        json={
            "conversation_id": conversation["id"],
            "template": "rsi_mean_reversion",
            "asset_class": "equity",
            "symbols": ["TSLA"],
        },
    )

    assert response.status_code == 200
    run = response.json()["run"]
    assert run["status"] == "completed"
    assert run["asset_class"] == "equity"
    assert run["conversation_result_card"]["asset_class"] == "equity"
    assert run["benchmark_symbol"] == "SPY"
    assert run["config_snapshot"]["side"] == "long"
    assert run["config_snapshot"]["starting_capital"] == 1000
    assert "_execution_realism" not in run["config_snapshot"]
    assert "summary" not in run
    assert set(run["metrics"]) == {"aggregate", "by_symbol"}
    assert isinstance(
        run["metrics"]["aggregate"]["performance"]["total_return_pct"], float
    )
    artifact_id = run["conversation_result_card"]["evidence_artifact_id"]
    assert run["conversation_result_card"]["idea_id"]
    assert run["conversation_result_card"]["idea_version_id"]
    assert run["conversation_result_card"]["evidence_lifecycle"] == "captured"
    assert run["conversation_result_card"]["artifact_type"] == "backtest"
    assert api_state.store.evidence_artifacts[artifact_id].source_run_id == run["id"]
    assert run["conversation_result_card"]["assumptions"] == [
        "Long-only",
        "Equal weight",
        "No fees/slippage",
        "Benchmark: SPY",
    ]
    assert run["conversation_result_card"]["benchmark_note"] is None

    history = client.get("/api/v1/history")
    assert history.status_code == 200
    assert [item["type"] for item in history.json()["items"]] == ["run", "chat"]


def test_memory_direct_admission_persists_guest_traffic_class(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import timedelta

    from argus.api.guest_access import (
        AccountContext,
        guest_capabilities,
        store_account_context,
    )
    from argus.api.routers import backtest as backtest_router
    from fastapi import Request

    api_state.store.reset()
    user = api_state.store.get_or_create_dev_user()
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/backtests/run",
            "headers": [],
            "query_string": b"",
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 50000),
        }
    )
    store_account_context(
        request,
        AccountContext(
            kind="guest",
            user_id=user.id,
            expires_at=utcnow() + timedelta(days=7),
            capabilities=guest_capabilities(),
        ),
    )
    decision, job = backtest_router._admit_direct_run(
        request,
        user=user,
        idempotency_key="guest-memory-admission",
        identity_hash=f"sha256:{'a' * 64}",
        payload_hash=f"sha256:{'b' * 64}",
        launch_payload={
            "kind": "run_backtest_job",
            "request": {"template": "buy_and_hold", "symbols": ["AAPL"]},
        },
        conversation_id=None,
    )

    assert decision == "admitted"
    assert job is not None
    assert job["execution_metadata"] == {
        "source": "api_direct",
        "openrouter_traffic_class": "guest",
    }
    assert (
        api_state.store.backtest_jobs[job["id"]]["execution_metadata"]
        == (job["execution_metadata"])
    )


def test_history_excludes_archived_and_deleted_chats_by_default() -> None:
    client = _client()

    client.post("/api/v1/conversations", json={"title": "Active idea"})
    archived = client.post(
        "/api/v1/conversations", json={"title": "Archived idea"}
    ).json()["conversation"]
    deleted = client.post("/api/v1/conversations", json={"title": "Deleted idea"}).json()[
        "conversation"
    ]

    assert (
        client.patch(
            f"/api/v1/conversations/{archived['id']}",
            json={"archived": True},
        ).status_code
        == 200
    )
    assert client.delete(f"/api/v1/conversations/{deleted['id']}").status_code == 200

    response = client.get("/api/v1/history")

    assert response.status_code == 200
    chat_titles = [
        item["title"] for item in response.json()["items"] if item["type"] == "chat"
    ]
    assert chat_titles == ["Active idea"]


def test_history_chat_items_carry_title_source() -> None:
    client = _client()

    unnamed = client.post("/api/v1/conversations", json={}).json()["conversation"]
    renamed = client.post(
        "/api/v1/conversations", json={"title": "My renamed idea"}
    ).json()["conversation"]

    response = client.get("/api/v1/history")

    assert response.status_code == 200
    sources = {
        item["id"]: item.get("title_source")
        for item in response.json()["items"]
        if item["type"] == "chat"
    }
    assert sources[unnamed["id"]] == "system_default"
    assert sources[renamed["id"]] == "user_renamed"


def test_deleted_conversation_restore_moves_chat_back_to_recents() -> None:
    client = _client()

    conversation = client.post(
        "/api/v1/conversations",
        json={"title": "Restorable idea"},
    ).json()["conversation"]
    memory_message(
        conversation_id=conversation["id"],
        role="user",
        content="Can you test a DOGE buy-and-hold idea?",
    )

    assert client.delete(f"/api/v1/conversations/{conversation['id']}").status_code == 200
    default_deleted_ids = {
        item["id"]
        for item in client.get("/api/v1/history").json()["items"]
        if item["type"] == "chat"
    }
    recently_deleted_ids = {
        item["id"]
        for item in client.get("/api/v1/history?deleted=true").json()["items"]
        if item["type"] == "chat"
    }
    assert conversation["id"] not in default_deleted_ids
    assert conversation["id"] in recently_deleted_ids
    assert (
        client.get(f"/api/v1/conversations/{conversation['id']}/messages").status_code
        == 404
    )

    restore = client.patch(
        f"/api/v1/conversations/{conversation['id']}",
        json={"deleted_at": None},
    )

    assert restore.status_code == 200
    assert restore.json()["conversation"]["deleted_at"] is None
    restored_default_ids = {
        item["id"]
        for item in client.get("/api/v1/history").json()["items"]
        if item["type"] == "chat"
    }
    restored_deleted_ids = {
        item["id"]
        for item in client.get("/api/v1/history?deleted=true").json()["items"]
        if item["type"] == "chat"
    }
    assert conversation["id"] in restored_default_ids
    assert conversation["id"] not in restored_deleted_ids
    assert (
        client.get(f"/api/v1/conversations/{conversation['id']}/messages").status_code
        == 200
    )


def test_delete_all_conversations_soft_deletes_active_and_archived_chats() -> None:
    client = _client()

    active = client.post("/api/v1/conversations", json={"title": "Active idea"}).json()[
        "conversation"
    ]
    archived = client.post(
        "/api/v1/conversations", json={"title": "Archived idea"}
    ).json()["conversation"]
    already_deleted = client.post(
        "/api/v1/conversations", json={"title": "Deleted idea"}
    ).json()["conversation"]
    for conversation in (active, archived, already_deleted):
        memory_message(
            conversation_id=conversation["id"],
            role="user",
            content=f"Remember {conversation['title']}",
        )

    assert (
        client.patch(
            f"/api/v1/conversations/{archived['id']}",
            json={"archived": True},
        ).status_code
        == 200
    )
    assert (
        client.delete(f"/api/v1/conversations/{already_deleted['id']}").status_code == 200
    )

    response = client.delete("/api/v1/conversations")

    assert response.status_code == 200
    assert response.json() == {"success": True, "deleted_count": 2}
    assert client.delete("/api/v1/conversations").json()["deleted_count"] == 0
    default_chat_ids = {
        item["id"]
        for item in client.get("/api/v1/history").json()["items"]
        if item["type"] == "chat"
    }
    deleted_chat_ids = {
        item["id"]
        for item in client.get("/api/v1/history?deleted=true").json()["items"]
        if item["type"] == "chat"
    }
    deleted_archived_chat_ids = {
        item["id"]
        for item in client.get("/api/v1/history?deleted=true&archived=true").json()[
            "items"
        ]
        if item["type"] == "chat"
    }

    assert active["id"] not in default_chat_ids
    assert archived["id"] not in default_chat_ids
    assert active["id"] in deleted_chat_ids
    assert already_deleted["id"] in deleted_chat_ids
    assert archived["id"] in deleted_archived_chat_ids


def test_delete_all_conversations_memory_fallback_skips_other_users_chats() -> None:
    from argus.api import state as api_state

    client = _client()
    owned = client.post("/api/v1/conversations", json={"title": "Mine"}).json()[
        "conversation"
    ]
    other = memory_conversation(
        scope=PERSONAL,
        title="Not mine",
        title_source="system_default",
        language="en",
        user_id="other-user-id",
    )
    memory_message(
        conversation_id=owned["id"],
        role="user",
        content="Remember my idea",
    )
    memory_message(
        conversation_id=other.id,
        role="user",
        content="Keep the other user's idea",
    )

    response = client.delete("/api/v1/conversations")

    assert response.status_code == 200
    assert response.json() == {"success": True, "deleted_count": 1}
    assert api_state.store.conversations[owned["id"]].deleted_at is not None
    assert api_state.store.conversations[other.id].deleted_at is None


def test_history_can_return_archived_chats_without_deleted_chats() -> None:
    client = _client()

    active = client.post("/api/v1/conversations", json={"title": "Active idea"}).json()[
        "conversation"
    ]
    archived = client.post(
        "/api/v1/conversations", json={"title": "Archived idea"}
    ).json()["conversation"]
    deleted = client.post("/api/v1/conversations", json={"title": "Deleted idea"}).json()[
        "conversation"
    ]

    assert (
        client.patch(
            f"/api/v1/conversations/{archived['id']}",
            json={"archived": True},
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/api/v1/conversations/{deleted['id']}",
            json={"archived": True},
        ).status_code
        == 200
    )
    assert client.delete(f"/api/v1/conversations/{deleted['id']}").status_code == 200

    response = client.get("/api/v1/history?archived=true")

    assert response.status_code == 200
    chat_titles = [
        item["title"] for item in response.json()["items"] if item["type"] == "chat"
    ]
    assert chat_titles == ["Archived idea"]
    assert active["id"] not in {item["id"] for item in response.json()["items"]}


def test_history_filters_runs_by_parent_conversation_lifecycle() -> None:
    client = _client()

    active = client.post("/api/v1/conversations", json={"title": "Active idea"}).json()[
        "conversation"
    ]
    archived = client.post(
        "/api/v1/conversations", json={"title": "Archived idea"}
    ).json()["conversation"]
    deleted = client.post("/api/v1/conversations", json={"title": "Deleted idea"}).json()[
        "conversation"
    ]

    for symbol, conversation in (
        ("AAPL", active),
        ("TSLA", archived),
        ("MSFT", deleted),
    ):
        response = client.post(
            "/api/v1/backtests/run",
            headers={"Idempotency-Key": f"{symbol.lower()}-history-lifecycle"},
            json={
                "conversation_id": conversation["id"],
                "template": "rsi_mean_reversion",
                "asset_class": "equity",
                "symbols": [symbol],
            },
        )
        assert response.status_code == 200

    assert (
        client.patch(
            f"/api/v1/conversations/{archived['id']}",
            json={"archived": True},
        ).status_code
        == 200
    )
    assert client.delete(f"/api/v1/conversations/{deleted['id']}").status_code == 200

    default_history = client.get("/api/v1/history").json()["items"]
    archived_history = client.get("/api/v1/history?archived=true").json()["items"]
    deleted_history = client.get("/api/v1/history?deleted=true").json()["items"]

    assert {
        item["conversation_id"] for item in default_history if item["type"] == "run"
    } == {active["id"]}
    assert {
        item["conversation_id"] for item in archived_history if item["type"] == "run"
    } == {archived["id"]}
    assert {
        item["conversation_id"] for item in deleted_history if item["type"] == "run"
    } == {deleted["id"]}


def test_execution_realism_payload_is_ignored_when_feature_flag_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.domain.engine import normalize_backtest_config

    monkeypatch.setenv("ARGUS_ENABLE_EXECUTION_REALISM", "false")
    config = normalize_backtest_config(
        {
            "template": "rsi_mean_reversion",
            "asset_class": "equity",
            "symbols": ["AAPL"],
            "_execution_realism": {
                "enabled": True,
                "fee_bps": 25,
                "slippage_bps": 40,
            },
        }
    )

    assert "_execution_realism" not in config


@pytest.mark.parametrize("timeframe", ["1h", "2h", "4h", "6h", "12h", "1D"])
def test_backtest_accepts_supported_timeframes(timeframe: str) -> None:
    client = _client()
    response = client.post(
        "/api/v1/backtests/run",
        headers={"Idempotency-Key": f"timeframe-{timeframe.lower()}"},
        json={
            "template": "dca_accumulation",
            "asset_class": "equity",
            "symbols": ["AAPL"],
            "timeframe": timeframe,
            "parameters": {"dca_cadence": "monthly"},
        },
    )
    assert response.status_code == 200
    assert response.json()["run"]["config_snapshot"]["timeframe"] == timeframe


def test_backtest_rejects_coverage_adjustment_to_same_calendar_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.domain import engine as domain_engine

    def same_day_intraday_bars(**_: Any) -> pd.DataFrame:
        index = pd.date_range(
            start="2024-01-03T14:30:00Z",
            periods=7,
            freq="1h",
        )
        close = pd.Series(range(100, 107), index=index, dtype=float)
        return pd.DataFrame(
            {
                "open": close,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1_000.0,
            },
            index=index,
        )

    monkeypatch.setattr(domain_engine, "fetch_ohlcv", same_day_intraday_bars)
    client = _client()

    response = client.post(
        "/api/v1/backtests/run",
        headers={"Idempotency-Key": "same-day-adjusted-window"},
        json={
            "template": "buy_and_hold",
            "asset_class": "equity",
            "symbols": ["AAPL"],
            "timeframe": "1h",
            "start_date": "2024-01-01",
            "end_date": "2024-01-05",
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_chronological_date_range"


def test_backtest_rejects_stablecoin_symbol() -> None:
    client = _client()
    response = client.post(
        "/api/v1/backtests/run",
        headers={"Idempotency-Key": "stablecoin-rejected"},
        json={
            "template": "dca_accumulation",
            "asset_class": "crypto",
            "symbols": ["USDT"],
            "timeframe": "1D",
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "stablecoin_not_supported"


def test_backtest_rejects_unsupported_parameters_payload() -> None:
    client = _client()
    response = client.post(
        "/api/v1/backtests/run",
        headers={"Idempotency-Key": "unsupported-parameters"},
        json={
            "template": "rsi_mean_reversion",
            "asset_class": "equity",
            "symbols": ["AAPL"],
            "parameters": {"rsi_length": 21},
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "unsupported_parameters"


def test_backtest_allows_equity_lookback_beyond_three_years() -> None:
    client = _client()
    response = client.post(
        "/api/v1/backtests/run",
        headers={"Idempotency-Key": "equity-long-lookback"},
        json={
            "template": "dca_accumulation",
            "asset_class": "equity",
            "symbols": ["AAPL"],
            "start_date": "2020-01-01",
            "end_date": "2024-01-10",
        },
    )
    assert response.status_code == 200
    assert response.json()["run"]["asset_class"] == "equity"


def test_backtest_rejects_equity_start_before_provider_history() -> None:
    client = _client()
    response = client.post(
        "/api/v1/backtests/run",
        headers={"Idempotency-Key": "provider-history-start"},
        json={
            "template": "buy_and_hold",
            "asset_class": "equity",
            "symbols": ["AAPL"],
            "start_date": "2015-12-31",
            "end_date": "2016-01-15",
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "provider_history_start_unavailable"


def test_backtest_rejects_unknown_symbol() -> None:
    client = _client()
    response = client.post(
        "/api/v1/backtests/run",
        headers={"Idempotency-Key": "unknown-symbol"},
        json={
            "template": "dca_accumulation",
            "asset_class": "equity",
            "symbols": ["FAKE123"],
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_symbol"


def test_draft_strategy_templates_have_no_api_path() -> None:
    """Draft templates stay rejected at the direct backtest boundary."""
    client = _client()
    for template in ("momentum_breakout", "trend_follow"):
        ran = client.post(
            "/api/v1/backtests/run",
            headers={"Idempotency-Key": f"draft-{template}"},
            json={
                "template": template,
                "asset_class": "equity",
                "symbols": ["AAPL"],
            },
        )
        assert ran.status_code == 422, f"{template} accepted by POST /backtests/run"


def test_chat_stream_persists_messages_and_emits_contract_events() -> None:
    client = _client()
    conversation = client.post("/api/v1/conversations", json={}).json()["conversation"]

    response = client.post(
        "/api/v1/chat/stream",
        headers={"Idempotency-Key": "chat-tsla"},
        json={
            "conversation_id": conversation["id"],
            "message": "What if I bought Tesla whenever it dipped hard?",
            "language": "en",
        },
    )

    assert response.status_code == 200
    stream = response.text
    assert '"type":"stage_start","stage":"interpret"' in stream
    assert '"type":"stage_outcome","outcome":"ready_to_respond"' in stream
    assert '"type":"token"' not in stream
    assert '"type":"final"' in stream
    assert "data: [DONE]" in stream

    result_line = next(
        line.removeprefix("data: ")
        for line in stream.splitlines()
        if line.startswith("data: {") and '"run"' in line
    )
    assert json.loads(result_line)["payload"]["run"]["conversation_result_card"][
        "status_label"
    ]

    messages = client.get(f"/api/v1/conversations/{conversation['id']}/messages")
    assert [message["role"] for message in messages.json()["items"]] == [
        "user",
        "assistant",
    ]


def test_chat_stream_with_es_419_emits_spanish_assistant_copy() -> None:
    client = _client()
    conversation = client.post("/api/v1/conversations", json={}).json()["conversation"]

    response = client.post(
        "/api/v1/chat/stream",
        headers={"Idempotency-Key": "chat-spanish"},
        json={
            "conversation_id": conversation["id"],
            "message": "Backtest Tesla when it dips",
            "language": "es-419",
        },
    )

    assert response.status_code == 200
    assert '"type":"token"' not in response.text

    messages = client.get(f"/api/v1/conversations/{conversation['id']}/messages")
    assert messages.status_code == 200
    assistant_message = messages.json()["items"][-1]
    assert assistant_message["role"] == "assistant"
    assert assistant_message["content"] == ""
    assert assistant_message["metadata"]["result_fact_bank"]["symbols"] == ["TSLA"]
    assert api_state.store.messages[conversation["id"]][-1].content


def test_chat_stream_defaults_to_english_assistant_copy() -> None:
    client = _client()
    conversation = client.post("/api/v1/conversations", json={}).json()["conversation"]

    response = client.post(
        "/api/v1/chat/stream",
        headers={"Idempotency-Key": "chat-default-language"},
        json={
            "conversation_id": conversation["id"],
            "message": "Backtest Tesla when it dips",
        },
    )

    assert response.status_code == 200
    assert '"type":"token"' not in response.text

    messages = client.get(f"/api/v1/conversations/{conversation['id']}/messages")
    assert messages.status_code == 200
    assistant_message = messages.json()["items"][-1]
    assert assistant_message["role"] == "assistant"
    assert assistant_message["content"] == ""
    assert assistant_message["metadata"]["result_fact_bank"]["symbols"] == ["TSLA"]
    assert api_state.store.messages[conversation["id"]][-1].content


def test_chat_stream_sends_profile_language_to_runtime() -> None:
    client = _client()
    conversation = client.post("/api/v1/conversations", json={}).json()["conversation"]

    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": conversation["id"],
            "message": "Backtest Tesla when it dips",
            "language": "en",
        },
    )

    assert response.status_code == 200
    stream = response.text
    assert "event:" not in stream
    assert stream.count("data: [DONE]") == 1
    events = _stream_events(stream)
    token_events = [event for event in events if event.get("type") == "token"]
    assert token_events == []
    final_payload = _final_payload(stream)
    assert final_payload["stage_outcome"] == "ready_to_respond"
    assert final_payload["assistant_response"] == ""
    assert final_payload["message_id"]
    assert final_payload["run"]["conversation_id"] == conversation["id"]
    messages = client.get(f"/api/v1/conversations/{conversation['id']}/messages").json()[
        "items"
    ]
    assert [message["role"] for message in messages] == ["user", "assistant"]
    runtime_turn = messages[-1]["metadata"]["agent_runtime_turn"]
    assert runtime_turn["status"] == "completed"
    assert runtime_turn["terminal"] is True


def test_conversations_cursor_pagination_is_stable() -> None:
    client = _client()
    for idx in range(3):
        created = client.post(
            "/api/v1/conversations",
            json={"title": f"Idea {idx + 1}"},
        )
        assert created.status_code == 200

    first_page = client.get("/api/v1/conversations?limit=2")
    assert first_page.status_code == 200
    payload = first_page.json()
    assert len(payload["items"]) == 2
    assert payload["next_cursor"] is not None

    second_page = client.get(
        f"/api/v1/conversations?limit=2&cursor={payload['next_cursor']}"
    )
    assert second_page.status_code == 200
    second_payload = second_page.json()
    assert second_payload["items"]
    first_ids = {item["id"] for item in payload["items"]}
    second_ids = {item["id"] for item in second_payload["items"]}
    assert first_ids.isdisjoint(second_ids)


def test_messages_cursor_pagination_is_stable() -> None:
    client = _client()
    conversation = client.post("/api/v1/conversations", json={}).json()["conversation"]
    for idx in range(3):
        response = client.post(
            "/api/v1/chat/stream",
            json={
                "conversation_id": conversation["id"],
                "message": f"Test message {idx}",
                "language": "en",
            },
        )
        assert response.status_code == 200

    first_page = client.get(
        f"/api/v1/conversations/{conversation['id']}/messages?limit=2"
    )
    assert first_page.status_code == 200
    first_payload = first_page.json()
    assert len(first_payload["items"]) == 2
    assert first_payload["next_cursor"] is not None

    second_page = client.get(
        f"/api/v1/conversations/{conversation['id']}/messages?limit=2&cursor={first_payload['next_cursor']}"
    )
    assert second_page.status_code == 200
    second_payload = second_page.json()
    assert second_payload["items"]
    first_ids = {item["id"] for item in first_payload["items"]}
    second_ids = {item["id"] for item in second_payload["items"]}
    assert first_ids.isdisjoint(second_ids)


def test_messages_can_open_one_bounded_page_at_an_owned_message_anchor() -> None:
    client = _client()
    conversation = client.post("/api/v1/conversations", json={}).json()["conversation"]
    first = memory_message(
        conversation_id=conversation["id"],
        role="user",
        content="First transcript turn.",
    )
    anchor = memory_message(
        conversation_id=conversation["id"],
        role="user",
        content="Anchored transcript turn.",
    )
    third = memory_message(
        conversation_id=conversation["id"],
        role="assistant",
        content="Following transcript turn.",
    )

    response = client.get(
        f"/api/v1/conversations/{conversation['id']}/messages",
        params={"limit": 2, "anchor_message_id": anchor.id},
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload["items"]] == [anchor.id, third.id]
    assert first.id not in {item["id"] for item in payload["items"]}
    assert len(payload["items"]) <= 2


def test_messages_reject_foreign_message_anchor_without_leaking_ownership() -> None:
    client = _client()
    target = client.post("/api/v1/conversations", json={}).json()["conversation"]
    other = client.post("/api/v1/conversations", json={}).json()["conversation"]
    foreign = memory_message(
        conversation_id=other["id"],
        role="user",
        content="Foreign anchor.",
    )

    response = client.get(
        f"/api/v1/conversations/{target['id']}/messages",
        params={"anchor_message_id": foreign.id},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_search_supports_cursor_after_grouping_by_conversation() -> None:
    client = _client()
    conversation_ids = [
        client.post(
            "/api/v1/conversations", json={"title": f"Tesla alpha chat {index}"}
        ).json()["conversation"]["id"]
        for index in range(3)
    ]

    first_page = client.get("/api/v1/search?q=tesla&limit=2")
    assert first_page.status_code == 200
    payload = first_page.json()
    assert payload["items"]
    assert payload["next_cursor"] is not None
    assert {item["type"] for item in payload["items"]} == {"conversation"}

    second_page = client.get(
        f"/api/v1/search?q=tesla&limit=2&cursor={payload['next_cursor']}"
    )
    assert second_page.status_code == 200
    second_payload = second_page.json()
    first_ids = {(item["type"], item["id"]) for item in payload["items"]}
    second_ids = {(item["type"], item["id"]) for item in second_payload["items"]}
    assert first_ids.isdisjoint(second_ids)
    assert {item["id"] for item in payload["items"] + second_payload["items"]} == set(
        conversation_ids
    )


def test_search_asset_rollup_is_first_and_does_not_consume_conversation_cursor() -> None:
    client = _client()
    user_id = api_state.store.get_or_create_dev_user().id
    now = utcnow()
    conversation_ids: list[str] = []
    for index in range(2):
        conversation = client.post(
            "/api/v1/conversations",
            json={"title": f"TSLA history {index}"},
        ).json()["conversation"]
        conversation_ids.append(conversation["id"])
        run = BacktestRun(
            id=f"asset-rollup-run-{index}",
            conversation_id=conversation["id"],
            strategy_id=None,
            status="completed",
            asset_class="equity",
            symbols=["TSLA"],
            allocation_method="equal_weight",
            benchmark_symbol="SPY",
            metrics={},
            config_snapshot={"template": "buy_and_hold"},
            conversation_result_card={"title": f"TSLA run {index}"},
            created_at=now - timedelta(minutes=index),
        )
        api_state.store.backtest_runs[run.id] = run
        api_state.store.backtest_run_owners[run.id] = user_id

    first_page = client.get("/api/v1/search?q=TSLA&limit=1")

    assert first_page.status_code == 200
    first_payload = first_page.json()
    assert first_payload["items"][0] == {
        "type": "asset_rollup",
        "symbol": "TSLA",
        "run_count": 2,
        "result_count": 2,
        "decision_counts": {
            "promising": 0,
            "watching": 0,
            "rejected": 0,
            "revisit_later": 0,
        },
        "last_touched_at": now.isoformat().replace("+00:00", "Z"),
    }
    first_conversations = [
        item["conversation_id"]
        for item in first_payload["items"]
        if item["type"] == "conversation"
    ]
    assert len(first_conversations) == 1
    assert first_payload["next_cursor"] is not None

    second_page = client.get(
        "/api/v1/search",
        params={
            "q": "TSLA",
            "limit": 1,
            "cursor": first_payload["next_cursor"],
        },
    )

    assert second_page.status_code == 200
    second_payload = second_page.json()
    second_conversations = [
        item["conversation_id"]
        for item in second_payload["items"]
        if item["type"] == "conversation"
    ]
    assert len(second_conversations) == 1
    assert set(first_conversations + second_conversations) == set(conversation_ids)
    assert second_payload["next_cursor"] is None


def test_search_asset_rollup_uses_owned_canonical_run_and_decision_lineage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.domain import engine as domain_engine

    provider_calls: list[str] = []

    def fail_if_resolved(symbol: str) -> ResolvedAsset:
        provider_calls.append(symbol)
        raise AssertionError("Omnisearch asset rollups must not resolve symbols")

    monkeypatch.setattr(domain_engine, "resolve_asset", fail_if_resolved)
    client = _client()
    user_id = api_state.store.get_or_create_dev_user().id
    other_user_id = "00000000-0000-0000-0000-000000000099"
    now = utcnow()
    conversation_rows = (
        ("asset-rollup-active", False, None, user_id),
        ("asset-rollup-archived", True, None, user_id),
        ("asset-rollup-deleted", False, now, user_id),
        ("asset-rollup-foreign", False, None, other_user_id),
    )
    for conversation_id, archived, deleted_at, owner_id in conversation_rows:
        _store_search_conversation(
            user_id=owner_id,
            conversation_id=conversation_id,
            title=f"Canonical history {conversation_id}",
            updated_at=now,
            archived=archived,
            deleted_at=deleted_at,
        )

    runs = (
        BacktestRun(
            id="asset-rollup-active-run",
            conversation_id="asset-rollup-active",
            strategy_id=None,
            status="completed",
            asset_class="equity",
            symbols=["TSLA", "AAPL"],
            allocation_method="equal_weight",
            benchmark_symbol="SPY",
            metrics={},
            config_snapshot={"template": "buy_and_hold"},
            conversation_result_card={"title": "Active multi-asset run"},
            created_at=now - timedelta(days=3),
        ),
        BacktestRun(
            id="asset-rollup-archived-run",
            conversation_id="asset-rollup-archived",
            strategy_id=None,
            status="completed",
            asset_class="equity",
            symbols=["TSLA"],
            allocation_method="equal_weight",
            benchmark_symbol="SPY",
            metrics={},
            config_snapshot={"template": "buy_and_hold"},
            conversation_result_card={"title": "Archived TSLA run"},
            created_at=now - timedelta(days=2),
        ),
        BacktestRun(
            id="asset-rollup-deleted-run",
            conversation_id="asset-rollup-deleted",
            strategy_id=None,
            status="completed",
            asset_class="equity",
            symbols=["TSLA"],
            allocation_method="equal_weight",
            benchmark_symbol="SPY",
            metrics={},
            config_snapshot={"template": "buy_and_hold"},
            conversation_result_card={"title": "Deleted TSLA run"},
            created_at=now,
        ),
        BacktestRun(
            id="asset-rollup-foreign-run",
            conversation_id="asset-rollup-foreign",
            strategy_id=None,
            status="completed",
            asset_class="equity",
            symbols=["TSLA"],
            allocation_method="equal_weight",
            benchmark_symbol="SPY",
            metrics={},
            config_snapshot={"template": "buy_and_hold"},
            conversation_result_card={"title": "Foreign TSLA run"},
            created_at=now,
        ),
        BacktestRun(
            id="asset-rollup-failed-run",
            conversation_id="asset-rollup-active",
            strategy_id=None,
            status="failed",
            asset_class="equity",
            symbols=["TSLA"],
            allocation_method="equal_weight",
            benchmark_symbol="SPY",
            metrics={},
            config_snapshot={"template": "buy_and_hold"},
            conversation_result_card={"title": "Failed TSLA run"},
            created_at=now,
        ),
    )
    for run in runs:
        api_state.store.backtest_runs[run.id] = run
        api_state.store.backtest_run_owners[run.id] = (
            other_user_id if run.id == "asset-rollup-foreign-run" else user_id
        )

    decisions = (
        (
            runs[0],
            "asset-rollup-active-evidence",
            "asset-rollup-active-decision",
            "promising",
            now - timedelta(days=1),
        ),
        (
            runs[1],
            "asset-rollup-archived-evidence",
            "asset-rollup-archived-decision",
            "watching",
            now,
        ),
    )
    for run, evidence_id, decision_id, state, touched_at in decisions:
        artifact = EvidenceArtifact(
            id=evidence_id,
            idea_id=f"{evidence_id}-idea",
            idea_version_id=f"{evidence_id}-version",
            source_conversation_id=run.conversation_id,
            source_run_id=run.id,
            artifact_type="backtest",
            lifecycle="decided",
            title=f"{run.id} evidence",
            digest="Canonical evidence.",
            payload={},
            created_at=touched_at,
            updated_at=touched_at,
        )
        decision = DecisionNote(
            id=decision_id,
            idea_id=artifact.idea_id,
            idea_version_id=artifact.idea_version_id,
            evidence_artifact_id=artifact.id,
            source_conversation_id=run.conversation_id,
            decision_state=state,
            note="Canonical decision.",
            created_at=touched_at,
            updated_at=touched_at,
        )
        api_state.store.evidence_artifacts[artifact.id] = artifact
        api_state.store.evidence_artifact_owners[artifact.id] = user_id
        api_state.store.decision_notes[decision.id] = decision
        api_state.store.decision_note_owners[decision.id] = user_id

    prefix = client.get("/api/v1/search?q=tsl&limit=20")
    exact = client.get("/api/v1/search?q=TSLA&limit=20")
    multi_asset = client.get("/api/v1/search?q=AAPL&limit=20")
    alias_no_match = client.get("/api/v1/search?q=Tesla&limit=20")

    assert prefix.status_code == exact.status_code == multi_asset.status_code == 200
    expected_tsla = {
        "type": "asset_rollup",
        "symbol": "TSLA",
        "run_count": 2,
        "result_count": 2,
        "decision_counts": {
            "promising": 1,
            "watching": 1,
            "rejected": 0,
            "revisit_later": 0,
        },
        "last_touched_at": now.isoformat().replace("+00:00", "Z"),
    }
    assert prefix.json()["items"][0] == expected_tsla
    assert exact.json()["items"][0] == expected_tsla
    assert multi_asset.json()["items"][0] == {
        "type": "asset_rollup",
        "symbol": "AAPL",
        "run_count": 1,
        "result_count": 1,
        "decision_counts": {
            "promising": 1,
            "watching": 0,
            "rejected": 0,
            "revisit_later": 0,
        },
        "last_touched_at": (now - timedelta(days=1)).isoformat().replace("+00:00", "Z"),
    }
    assert [
        item for item in alias_no_match.json()["items"] if item["type"] == "asset_rollup"
    ] == []
    assert provider_calls == []


def test_search_asset_rollup_preserves_pair_punctuation_and_rejects_true_multi_symbol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.domain import engine as domain_engine

    provider_calls: list[str] = []

    def fail_if_resolved(symbol: str) -> ResolvedAsset:
        provider_calls.append(symbol)
        raise AssertionError("Omnisearch asset rollups must not resolve symbols")

    monkeypatch.setattr(domain_engine, "resolve_asset", fail_if_resolved)
    client = _client()
    user_id = api_state.store.get_or_create_dev_user().id
    now = utcnow()
    conversation_id = "asset-rollup-symbol-normalization"
    _store_search_conversation(
        user_id=user_id,
        conversation_id=conversation_id,
        title="Canonical pair and equity history",
        updated_at=now,
    )
    for index, symbol in enumerate(("BTC/USD", "TSLA", "TSM")):
        run = BacktestRun(
            id=f"asset-rollup-symbol-normalization-{index}",
            conversation_id=conversation_id,
            strategy_id=None,
            status="completed",
            asset_class="crypto" if symbol == "BTC/USD" else "equity",
            symbols=[symbol],
            allocation_method="equal_weight",
            benchmark_symbol="BTC" if symbol == "BTC/USD" else "SPY",
            metrics={},
            config_snapshot={"template": "buy_and_hold"},
            conversation_result_card={"title": f"{symbol} run"},
            created_at=now - timedelta(minutes=index),
        )
        api_state.store.backtest_runs[run.id] = run
        api_state.store.backtest_run_owners[run.id] = user_id

    exact = client.get(
        "/api/v1/search",
        params={"q": "  bTc/uSd  ", "limit": 20},
    )
    prefix = client.get(
        "/api/v1/search",
        params={"q": "btc/", "limit": 20},
    )
    multi_symbol = client.get(
        "/api/v1/search",
        params={"q": "BTC/USD TSLA", "limit": 20},
    )
    ambiguous = client.get(
        "/api/v1/search",
        params={"q": "ts", "limit": 20},
    )

    for response in (exact, prefix, multi_symbol, ambiguous):
        assert response.status_code == 200
    for response in (exact, prefix):
        asset_items = [
            item for item in response.json()["items"] if item["type"] == "asset_rollup"
        ]
        assert len(asset_items) == 1
        assert asset_items[0]["symbol"] == "BTC/USD"
        assert asset_items[0]["run_count"] == 1
    for response in (multi_symbol, ambiguous):
        assert [
            item for item in response.json()["items"] if item["type"] == "asset_rollup"
        ] == []
    assert provider_calls == []


def test_search_asset_rollup_matches_expanding_and_combining_casefolds() -> None:
    from argus.domain.conversation_recall import project_asset_rollup

    now = utcnow()
    runs = [
        {
            "id": "combining-casefold-run",
            "conversation_id": "combining-casefold-conversation",
            "status": "completed",
            "symbols": ["ǰ/USD"],
            "created_at": now,
        },
        {
            "id": "expanding-casefold-run",
            "conversation_id": "expanding-casefold-conversation",
            "status": "completed",
            "symbols": ["ẞ/EUR"],
            "created_at": now - timedelta(minutes=1),
        },
    ]

    combining = project_asset_rollup(
        runs=runs,
        evidence=[],
        decisions=[],
        query="J\u030c/USD",
    )
    expanding = project_asset_rollup(
        runs=runs,
        evidence=[],
        decisions=[],
        query="ss/e",
    )

    assert combining is not None
    assert combining.symbol == "ǰ/USD"
    assert expanding is not None
    assert expanding.symbol == "ẞ/EUR"


def test_search_memory_mode_symbol_only_query_returns_only_asset_rollup() -> None:
    from argus.api.pagination import encode_cursor

    client = _client()
    user_id = api_state.store.get_or_create_dev_user().id
    now = utcnow()
    conversation = client.post(
        "/api/v1/conversations",
        json={"title": "SS Europe unrelated conversation"},
    ).json()["conversation"]
    run = BacktestRun(
        id="asset-rollup-expanding-casefold-api",
        conversation_id=conversation["id"],
        strategy_id=None,
        status="completed",
        asset_class="currency_pair",
        symbols=["ẞ/EUR"],
        allocation_method="equal_weight",
        benchmark_symbol="ẞ/EUR",
        metrics={},
        config_snapshot={"template": "buy_and_hold"},
        conversation_result_card={"title": "Expanding casefold run"},
        created_at=now,
    )
    api_state.store.backtest_runs[run.id] = run
    api_state.store.backtest_run_owners[run.id] = user_id

    response = client.get(
        "/api/v1/search",
        params={"q": "ss/e", "include_ledger_groups": "true"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "type": "asset_rollup",
                "symbol": "ẞ/EUR",
                "run_count": 1,
                "result_count": 1,
                "decision_counts": {
                    "promising": 0,
                    "watching": 0,
                    "rejected": 0,
                    "revisit_later": 0,
                },
                "last_touched_at": now.isoformat().replace("+00:00", "Z"),
            }
        ],
        "next_cursor": None,
        "ledger_groups": [
            {"decision_state": "promising", "count": 0},
            {"decision_state": "watching", "count": 0},
            {"decision_state": "rejected", "count": 0},
            {"decision_state": "revisit_later", "count": 0},
        ],
    }

    cursor = encode_cursor(now.isoformat(), conversation["id"])
    rejected = client.get(
        "/api/v1/search",
        params={"q": "ss/e", "cursor": cursor},
    )
    assert rejected.status_code == 400
    assert rejected.json()["code"] == "validation_error"


def test_search_memory_mode_accepts_a_two_character_stored_symbol() -> None:
    client = _client()
    user_id = api_state.store.get_or_create_dev_user().id
    now = utcnow()
    conversation_ids: list[str] = []
    expected_match_counts: dict[str, int] = {}
    for index in range(2):
        conversation = client.post(
            "/api/v1/conversations",
            json={"title": f"Aircraft research {index}"},
        ).json()["conversation"]
        conversation_ids.append(conversation["id"])
        run_count = 3 if index == 0 else 1
        expected_match_counts[conversation["id"]] = run_count
        for run_index in range(run_count):
            run = BacktestRun(
                id=("asset-rollup-two-character-symbol-" f"{index}-{run_index}"),
                conversation_id=conversation["id"],
                strategy_id=None,
                status="completed",
                asset_class="equity",
                symbols=["BA"],
                allocation_method="equal_weight",
                benchmark_symbol="SPY",
                metrics={},
                config_snapshot={"template": "buy_and_hold"},
                conversation_result_card={"title": f"BA result {index}-{run_index}"},
                created_at=(
                    now - timedelta(minutes=index) - timedelta(seconds=run_index)
                ),
            )
            api_state.store.backtest_runs[run.id] = run
            api_state.store.backtest_run_owners[run.id] = user_id

    distractor = client.post(
        "/api/v1/conversations",
        json={"title": "Balanced allocation without Boeing"},
    ).json()["conversation"]

    first_page = client.get(
        "/api/v1/search",
        params={"q": "ba", "limit": 1},
    )

    assert first_page.status_code == 200
    first_payload = first_page.json()
    assert first_payload["items"][0] == {
        "type": "asset_rollup",
        "symbol": "BA",
        "run_count": 4,
        "result_count": 4,
        "decision_counts": {
            "promising": 0,
            "watching": 0,
            "rejected": 0,
            "revisit_later": 0,
        },
        "last_touched_at": now.isoformat().replace("+00:00", "Z"),
    }
    first_conversations = [
        item for item in first_payload["items"] if item["type"] == "conversation"
    ]
    assert len(first_conversations) == 1
    assert first_conversations[0]["match"]["layer"] == "run"
    assert first_payload["next_cursor"] is not None

    second_page = client.get(
        "/api/v1/search",
        params={
            "q": "ba",
            "limit": 1,
            "cursor": first_payload["next_cursor"],
        },
    )

    assert second_page.status_code == 200
    second_payload = second_page.json()
    second_conversations = [
        item for item in second_payload["items"] if item["type"] == "conversation"
    ]
    assert len(second_conversations) == 1
    assert {
        item["conversation_id"] for item in first_conversations + second_conversations
    } == set(conversation_ids)
    assert distractor["id"] not in {
        item["conversation_id"] for item in first_conversations + second_conversations
    }
    assert {item["title"] for item in first_conversations + second_conversations} == {
        "Aircraft research 0",
        "Aircraft research 1",
    }
    assert {
        item["conversation_id"]: item["match"]["count"]
        for item in first_conversations + second_conversations
    } == expected_match_counts
    assert second_payload["next_cursor"] is None


@pytest.mark.parametrize(
    ("promoted_title", "pinned"),
    (("BA", False), ("Pinned aircraft thesis", True)),
)
def test_two_character_symbol_search_preserves_rank_tiers_beyond_window(
    promoted_title: str,
    pinned: bool,
) -> None:
    client = _client()
    user_id = api_state.store.get_or_create_dev_user().id
    now = utcnow()

    promoted = client.post(
        "/api/v1/conversations",
        json={"title": promoted_title},
    ).json()["conversation"]
    if pinned:
        promoted = client.patch(
            f"/api/v1/conversations/{promoted['id']}",
            json={"pinned": True},
        ).json()["conversation"]
    promoted_run = BacktestRun(
        id=f"promoted-ba-run-{pinned}",
        conversation_id=promoted["id"],
        strategy_id=None,
        status="completed",
        asset_class="equity",
        symbols=["BA"],
        allocation_method="equal_weight",
        benchmark_symbol="SPY",
        metrics={},
        config_snapshot={"template": "buy_and_hold"},
        conversation_result_card={"title": "Promoted BA result"},
        created_at=now - timedelta(days=1),
    )
    api_state.store.backtest_runs[promoted_run.id] = promoted_run
    api_state.store.backtest_run_owners[promoted_run.id] = user_id

    for index in range(25):
        conversation = client.post(
            "/api/v1/conversations",
            json={"title": f"Recent aircraft research {index}"},
        ).json()["conversation"]
        run = BacktestRun(
            id=f"recent-ba-run-{pinned}-{index}",
            conversation_id=conversation["id"],
            strategy_id=None,
            status="completed",
            asset_class="equity",
            symbols=["BA"],
            allocation_method="equal_weight",
            benchmark_symbol="SPY",
            metrics={},
            config_snapshot={"template": "buy_and_hold"},
            conversation_result_card={"title": f"Recent BA result {index}"},
            created_at=now + timedelta(minutes=index),
        )
        api_state.store.backtest_runs[run.id] = run
        api_state.store.backtest_run_owners[run.id] = user_id

    response = client.get(
        "/api/v1/search",
        params={"q": "ba", "limit": 1},
    )

    assert response.status_code == 200
    conversations = [
        item for item in response.json()["items"] if item["type"] == "conversation"
    ]
    assert len(conversations) == 1
    assert conversations[0]["conversation_id"] == promoted["id"]


def test_two_character_symbol_search_bounds_run_detail_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client()
    user_id = api_state.store.get_or_create_dev_user().id
    now = utcnow()

    for index in range(60):
        conversation = client.post(
            "/api/v1/conversations",
            json={"title": f"Aircraft scale research {index}"},
        ).json()["conversation"]
        run = BacktestRun(
            id=f"bounded-ba-run-{index}",
            conversation_id=conversation["id"],
            strategy_id=None,
            status="completed",
            asset_class="equity",
            symbols=["BA"],
            allocation_method="equal_weight",
            benchmark_symbol="SPY",
            metrics={},
            config_snapshot={"template": "buy_and_hold"},
            conversation_result_card={"title": f"Bounded BA result {index}"},
            created_at=now + timedelta(minutes=index),
        )
        api_state.store.backtest_runs[run.id] = run
        api_state.store.backtest_run_owners[run.id] = user_id

    original = memory_search_candidates._symbol_query_match
    detail_calls = 0

    def counted_symbol_query_match(*args: object, **kwargs: object):
        nonlocal detail_calls
        detail_calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(
        memory_search_candidates,
        "_symbol_query_match",
        counted_symbol_query_match,
    )

    response = client.get(
        "/api/v1/search",
        params={"q": "ba", "limit": 1},
    )

    assert response.status_code == 200
    assert detail_calls <= 20
    assert response.json()["next_cursor"] is not None

    detail_calls = 0
    cursor_response = client.get(
        "/api/v1/search",
        params={
            "q": "ba",
            "limit": 1,
            "cursor": response.json()["next_cursor"],
        },
    )

    assert cursor_response.status_code == 200
    assert detail_calls <= 40


def test_search_memory_mode_matches_multi_word_queries_like_supabase() -> None:
    # Memory mode shares the Supabase matcher semantics: a multi-word query
    # matches when every token appears, not only as one contiguous substring.
    client = _client()
    conversation = client.post(
        "/api/v1/conversations", json={"title": "Tesla alpha chat"}
    ).json()["conversation"]

    response = client.get("/api/v1/search", params={"q": "tesla chat"})
    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["id"] for item in items] == [conversation["id"]]
    assert {item["type"] for item in items} == {"conversation"}


@pytest.mark.parametrize("query", ["a", "GL D", "__"])
def test_search_memory_mode_defers_queries_without_an_indexable_token(
    query: str,
) -> None:
    client = _client()
    client.post("/api/v1/conversations", json={"title": "A GL chat"})

    response = client.get("/api/v1/search", params={"q": query})

    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "next_cursor": None,
        "ledger_groups": None,
    }


def test_search_rejects_query_above_512_code_points() -> None:
    response = _client().get(
        "/api/v1/search",
        params={"q": "x" * 513},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_search_maps_memory_ledger_work_limit_to_typed_problem(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.routers import search as search_router

    def _fail_bounded_ledger(**_: Any) -> None:
        raise MemoryLedgerWorkLimitExceeded

    monkeypatch.setattr(search_router, "memory_search_read", _fail_bounded_ledger)

    response = _client().get(
        "/api/v1/search",
        params={"q": "broadanchor", "include_ledger_groups": "true"},
    )

    assert response.status_code == 503
    payload = response.json()
    assert payload["code"] == "search_temporarily_unavailable"
    assert payload["type"].endswith("/search-temporarily-unavailable")
    assert payload["status"] == 503
    assert "SQLite" not in payload["detail"]
    assert "10,000" not in payload["detail"]


def test_search_memory_mode_recalls_user_message_with_typed_match_anchor() -> None:
    client = _client()
    conversation = client.post(
        "/api/v1/conversations",
        json={"title": "Ordinary allocation notes"},
    ).json()["conversation"]
    matched = memory_message(
        conversation_id=conversation["id"],
        role="user",
        content="I called this my copper lantern threshold.",
    )
    memory_message(
        conversation_id=conversation["id"],
        role="assistant",
        content="The copper lantern threshold is only assistant-authored here.",
    )

    response = client.get(
        "/api/v1/search",
        params={"q": "copper lantern", "limit": 20},
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["type"] == "conversation"
    assert items[0]["id"] == conversation["id"]
    assert items[0]["conversation_id"] == conversation["id"]
    assert items[0]["matched_text"] == "I called this my copper lantern threshold."
    assert items[0]["match"] == {
        "layer": "message",
        "fragment": "I called this my copper lantern threshold.",
        "count": 1,
        "message_id": matched.id,
    }


def test_search_memory_mode_centers_fragment_on_late_message_match() -> None:
    client = _client()
    conversation = client.post(
        "/api/v1/conversations",
        json={"title": "Ordinary allocation notes"},
    ).json()["conversation"]
    content = (
        ("Earlier copper-only context. " * 30)
        + "My copper lantern threshold was twelve percent."
        + (" Later unrelated context." * 20)
    )
    memory_message(
        conversation_id=conversation["id"],
        role="user",
        content=content,
    )

    response = client.get(
        "/api/v1/search",
        params={"q": "copper threshold", "limit": 20},
    )

    assert response.status_code == 200
    [item] = response.json()["items"]
    fragment = item["match"]["fragment"]
    assert len(fragment) <= 500
    assert fragment in content
    assert "copper lantern threshold" in fragment
    assert fragment != content[:500]
    assert item["matched_text"] == fragment
    repeated = client.get(
        "/api/v1/search",
        params={"q": "copper threshold", "limit": 20},
    )
    assert repeated.json()["items"][0]["match"]["fragment"] == fragment


def test_search_sends_no_recall_usage_event(monkeypatch) -> None:
    """recall_usage was retired from PostHog by SPEC 0 package 0C-1."""
    posts: list[object] = []
    monkeypatch.setenv("POSTHOG_PROJECT_TOKEN", "ph_project_token")
    monkeypatch.setenv("POSTHOG_REGION", "us")
    monkeypatch.setattr(
        "argus.observability.envelope.httpx.post",
        lambda *args, **kwargs: posts.append((args, kwargs)),
    )
    client = _client()
    user_id = api_state.store.get_or_create_dev_user().id
    memory_conversation(
        scope=PERSONAL,
        title="Tesla recall source",
        title_source="user_renamed",
        language="en",
        user_id=user_id,
    )

    response = client.get("/api/v1/search?q=tesla&limit=20")

    assert response.status_code == 200
    assert posts == []


def test_search_collapses_p1_artifacts_into_source_conversation() -> None:
    client = _client()
    user_id = api_state.store.get_or_create_dev_user().id
    now = utcnow()
    conversation = Conversation(
        id="conversation-evidence-order",
        title="AAPL evidence source conversation",
        title_source="user_renamed",
        pinned=False,
        archived=False,
        deleted_at=None,
        created_at=now - timedelta(minutes=5),
        updated_at=now + timedelta(minutes=5),
        last_message_preview="AAPL evidence chat wrapper",
        language="en",
    )
    run = BacktestRun(
        id="run-evidence-order",
        conversation_id=conversation.id,
        strategy_id=None,
        status="completed",
        asset_class="equity",
        symbols=["AAPL"],
        allocation_method="equal_weight",
        benchmark_symbol="SPY",
        metrics={"aggregate": {}, "by_symbol": {}},
        config_snapshot={"symbols": ["AAPL"], "benchmark_symbol": "SPY"},
        conversation_result_card={
            "title": "AAPL evidence backtest",
            "artifact_type": "backtest",
            "evidence_artifact_id": "artifact-evidence-order",
            "evidence_lifecycle": "captured",
        },
        created_at=now,
    )
    idea = Idea(
        id="idea-evidence-order",
        source_conversation_id=conversation.id,
        title="AAPL evidence idea",
        summary="AAPL evidence summary",
        lifecycle="captured",
        active_version_id="version-evidence-order",
        created_at=now,
        updated_at=now,
    )
    version = IdeaVersion(
        id="version-evidence-order",
        idea_id=idea.id,
        source_conversation_id=conversation.id,
        source_run_id=run.id,
        version_number=1,
        canonical_spec={"symbols": ["AAPL"], "benchmark_symbol": "SPY"},
        strategy_snapshot={"symbols": ["AAPL"]},
        title=idea.title,
        summary=idea.summary,
        lifecycle="captured",
        created_at=now,
    )
    artifact = EvidenceArtifact(
        id="artifact-evidence-order",
        idea_id=idea.id,
        idea_version_id=version.id,
        source_conversation_id=conversation.id,
        source_run_id=run.id,
        artifact_type="backtest",
        lifecycle="captured",
        title="AAPL evidence artifact",
        digest="AAPL evidence artifact digest.",
        payload={"provenance": {"symbols": ["AAPL"], "benchmark_symbol": "SPY"}},
        created_at=now,
        updated_at=now,
    )
    decision = DecisionNote(
        id="decision-evidence-order",
        idea_id=idea.id,
        idea_version_id=version.id,
        evidence_artifact_id=artifact.id,
        source_conversation_id=conversation.id,
        decision_state="promising",
        note="AAPL evidence decision note.",
        created_at=now,
        updated_at=now,
    )
    api_state.store.conversations[conversation.id] = conversation
    api_state.store.conversation_owners[conversation.id] = user_id
    api_state.store.backtest_runs[run.id] = run
    api_state.store.backtest_run_owners[run.id] = user_id
    api_state.store.ideas[idea.id] = idea
    api_state.store.idea_owners[idea.id] = user_id
    api_state.store.idea_versions[version.id] = version
    api_state.store.idea_version_owners[version.id] = user_id
    api_state.store.evidence_artifacts[artifact.id] = artifact
    api_state.store.evidence_artifact_owners[artifact.id] = user_id
    api_state.store.decision_notes[decision.id] = decision
    api_state.store.decision_note_owners[decision.id] = user_id

    response = client.get("/api/v1/search?q=evidence&limit=10")

    assert response.status_code == 200
    items = response.json()["items"]
    assert [(item["type"], item["id"]) for item in items] == [
        ("conversation", conversation.id)
    ]
    assert items[0]["dossier"]["decision"]["state"] == "promising"


def test_search_idea_result_carries_latest_decision_state() -> None:
    client = _client()
    user_id = api_state.store.get_or_create_dev_user().id
    now = utcnow()
    idea = Idea(
        id="idea-ledger-status",
        source_conversation_id="conversation-ledger-status",
        title="NVDA momentum ledger idea",
        summary="NVDA momentum ledger summary",
        lifecycle="decided",
        active_version_id="version-ledger-status",
        created_at=now - timedelta(minutes=10),
        updated_at=now,
    )
    older_decision = DecisionNote(
        id="decision-ledger-older",
        idea_id=idea.id,
        idea_version_id="version-ledger-status",
        evidence_artifact_id="artifact-ledger-status",
        source_conversation_id="conversation-ledger-status",
        decision_state="watching",
        note="Initial watch.",
        created_at=now - timedelta(minutes=5),
        updated_at=now - timedelta(minutes=5),
    )
    latest_decision = DecisionNote(
        id="decision-ledger-latest",
        idea_id=idea.id,
        idea_version_id="version-ledger-status",
        evidence_artifact_id="artifact-ledger-status",
        source_conversation_id="conversation-ledger-status",
        decision_state="promising",
        note="Upgraded after a fresh re-run.",
        created_at=now,
        updated_at=now,
    )
    api_state.store.ideas[idea.id] = idea
    api_state.store.idea_owners[idea.id] = user_id
    conversation = Conversation(
        id="conversation-ledger-status",
        title="NVDA momentum ledger",
        title_source="user_renamed",
        pinned=False,
        archived=False,
        deleted_at=None,
        created_at=now,
        updated_at=now,
        last_message_preview=None,
        language="en",
    )
    api_state.store.conversations[conversation.id] = conversation
    api_state.store.conversation_owners[conversation.id] = user_id
    for decision in (older_decision, latest_decision):
        api_state.store.decision_notes[decision.id] = decision
        api_state.store.decision_note_owners[decision.id] = user_id

    response = client.get("/api/v1/search?q=ledger&limit=10")

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["type"] == "conversation"
    assert items[0]["decision_states"] == ["promising", "watching"]


def test_search_decision_state_filter_returns_only_matching_ideas() -> None:
    client = _client()
    user_id = api_state.store.get_or_create_dev_user().id
    now = utcnow()
    promising_idea = Idea(
        id="idea-ledger-promising",
        source_conversation_id="conversation-ledger-promising",
        title="QQQ trend idea",
        summary="QQQ trend summary",
        lifecycle="decided",
        active_version_id="version-ledger-promising",
        created_at=now,
        updated_at=now,
    )
    rejected_idea = Idea(
        id="idea-ledger-rejected",
        source_conversation_id="conversation-ledger-rejected",
        title="ARKK reversion idea",
        summary="ARKK reversion summary",
        lifecycle="decided",
        active_version_id="version-ledger-rejected",
        created_at=now,
        updated_at=now,
    )
    promising_decision = DecisionNote(
        id="decision-ledger-promising",
        idea_id=promising_idea.id,
        idea_version_id="version-ledger-promising",
        evidence_artifact_id="artifact-ledger-promising",
        source_conversation_id="conversation-ledger-promising",
        decision_state="promising",
        note="Keep.",
        created_at=now,
        updated_at=now,
    )
    rejected_decision = DecisionNote(
        id="decision-ledger-rejected",
        idea_id=rejected_idea.id,
        idea_version_id="version-ledger-rejected",
        evidence_artifact_id="artifact-ledger-rejected",
        source_conversation_id="conversation-ledger-rejected",
        decision_state="rejected",
        note="Drop.",
        created_at=now,
        updated_at=now,
    )
    for idea in (promising_idea, rejected_idea):
        api_state.store.ideas[idea.id] = idea
        api_state.store.idea_owners[idea.id] = user_id
        _store_search_conversation(
            user_id=user_id,
            conversation_id=idea.source_conversation_id or "",
            title=idea.title,
            updated_at=now,
        )
    for decision in (promising_decision, rejected_decision):
        api_state.store.decision_notes[decision.id] = decision
        api_state.store.decision_note_owners[decision.id] = user_id

    response = client.get("/api/v1/search?q=&decision_state=promising&limit=20")

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["id"] for item in items] == [promising_idea.source_conversation_id]
    assert items[0]["type"] == "conversation"
    assert items[0]["decision_states"] == ["promising"]


def test_search_ledger_groups_are_backend_ordered_and_counted() -> None:
    client = _client()
    user_id = api_state.store.get_or_create_dev_user().id
    now = utcnow()
    ideas = [
        Idea(
            id="idea-ledger-group-promising-1",
            source_conversation_id="conversation-ledger-group-promising-1",
            title="AAPL promising idea",
            summary="AAPL promising summary",
            lifecycle="decided",
            active_version_id="version-ledger-group-promising-1",
            created_at=now - timedelta(minutes=3),
            updated_at=now - timedelta(minutes=3),
        ),
        Idea(
            id="idea-ledger-group-promising-2",
            source_conversation_id="conversation-ledger-group-promising-2",
            title="MSFT promising idea",
            summary="MSFT promising summary",
            lifecycle="decided",
            active_version_id="version-ledger-group-promising-2",
            created_at=now - timedelta(minutes=2),
            updated_at=now - timedelta(minutes=2),
        ),
        Idea(
            id="idea-ledger-group-watching",
            source_conversation_id="conversation-ledger-group-watching",
            title="BTC watching idea",
            summary="BTC watching summary",
            lifecycle="decided",
            active_version_id="version-ledger-group-watching",
            created_at=now - timedelta(minutes=1),
            updated_at=now - timedelta(minutes=1),
        ),
    ]
    decisions = [
        DecisionNote(
            id="decision-ledger-group-promising-1",
            idea_id=ideas[0].id,
            idea_version_id="version-ledger-group-promising-1",
            evidence_artifact_id="artifact-ledger-group-promising-1",
            source_conversation_id=ideas[0].source_conversation_id,
            decision_state="promising",
            note="Keep reviewing.",
            created_at=now - timedelta(minutes=3),
            updated_at=now - timedelta(minutes=3),
        ),
        DecisionNote(
            id="decision-ledger-group-promising-2",
            idea_id=ideas[1].id,
            idea_version_id="version-ledger-group-promising-2",
            evidence_artifact_id="artifact-ledger-group-promising-2",
            source_conversation_id=ideas[1].source_conversation_id,
            decision_state="promising",
            note="Still promising.",
            created_at=now - timedelta(minutes=2),
            updated_at=now - timedelta(minutes=2),
        ),
        DecisionNote(
            id="decision-ledger-group-watching",
            idea_id=ideas[2].id,
            idea_version_id="version-ledger-group-watching",
            evidence_artifact_id="artifact-ledger-group-watching",
            source_conversation_id=ideas[2].source_conversation_id,
            decision_state="watching",
            note="Watch for a better window.",
            created_at=now - timedelta(minutes=1),
            updated_at=now - timedelta(minutes=1),
        ),
    ]
    for idea in ideas:
        api_state.store.ideas[idea.id] = idea
        api_state.store.idea_owners[idea.id] = user_id
        _store_search_conversation(
            user_id=user_id,
            conversation_id=idea.source_conversation_id or "",
            title=idea.title,
            updated_at=idea.updated_at,
        )
    for decision in decisions:
        api_state.store.decision_notes[decision.id] = decision
        api_state.store.decision_note_owners[decision.id] = user_id

    response = client.get("/api/v1/search?q=&include_ledger_groups=true&limit=20")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ledger_groups"] == [
        {"decision_state": "promising", "count": 2},
        {"decision_state": "watching", "count": 1},
        {"decision_state": "rejected", "count": 0},
        {"decision_state": "revisit_later", "count": 0},
    ]
    assert {item["id"] for item in payload["items"]} == {
        idea.source_conversation_id for idea in ideas
    }
    assert all(item["type"] == "conversation" for item in payload["items"])


def test_search_decision_state_filter_keeps_unfiltered_ledger_groups() -> None:
    client = _client()
    user_id = api_state.store.get_or_create_dev_user().id
    now = utcnow()
    promising_idea = Idea(
        id="idea-ledger-filter-group-promising",
        source_conversation_id="conversation-ledger-filter-group-promising",
        title="NVDA promising idea",
        summary="NVDA promising summary",
        lifecycle="decided",
        active_version_id="version-ledger-filter-group-promising",
        created_at=now,
        updated_at=now,
    )
    watching_idea = Idea(
        id="idea-ledger-filter-group-watching",
        source_conversation_id="conversation-ledger-filter-group-watching",
        title="ETH watching idea",
        summary="ETH watching summary",
        lifecycle="decided",
        active_version_id="version-ledger-filter-group-watching",
        created_at=now,
        updated_at=now,
    )
    promising_decision = DecisionNote(
        id="decision-ledger-filter-group-promising",
        idea_id=promising_idea.id,
        idea_version_id="version-ledger-filter-group-promising",
        evidence_artifact_id="artifact-ledger-filter-group-promising",
        source_conversation_id=promising_idea.source_conversation_id,
        decision_state="promising",
        note="Promising.",
        created_at=now,
        updated_at=now,
    )
    watching_decision = DecisionNote(
        id="decision-ledger-filter-group-watching",
        idea_id=watching_idea.id,
        idea_version_id="version-ledger-filter-group-watching",
        evidence_artifact_id="artifact-ledger-filter-group-watching",
        source_conversation_id=watching_idea.source_conversation_id,
        decision_state="watching",
        note="Watching.",
        created_at=now,
        updated_at=now,
    )
    for idea in (promising_idea, watching_idea):
        api_state.store.ideas[idea.id] = idea
        api_state.store.idea_owners[idea.id] = user_id
        _store_search_conversation(
            user_id=user_id,
            conversation_id=idea.source_conversation_id or "",
            title=idea.title,
            updated_at=idea.updated_at,
        )
    for decision in (promising_decision, watching_decision):
        api_state.store.decision_notes[decision.id] = decision
        api_state.store.decision_note_owners[decision.id] = user_id

    response = client.get(
        "/api/v1/search?q=&decision_state=promising&include_ledger_groups=true&limit=20"
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload["items"]] == [
        promising_idea.source_conversation_id
    ]
    assert payload["ledger_groups"] == [
        {"decision_state": "promising", "count": 1},
        {"decision_state": "watching", "count": 1},
        {"decision_state": "rejected", "count": 0},
        {"decision_state": "revisit_later", "count": 0},
    ]


def test_search_preserves_pinned_chat_above_p1_artifacts() -> None:
    client = _client()
    user_id = api_state.store.get_or_create_dev_user().id
    now = utcnow()
    conversation = Conversation(
        id="conversation-pinned-search-order",
        title="AAPL pinned conversation",
        title_source="user_renamed",
        pinned=True,
        archived=False,
        deleted_at=None,
        created_at=now - timedelta(minutes=5),
        updated_at=now + timedelta(minutes=10),
        last_message_preview="AAPL pinned source",
        language="en",
    )
    artifact = EvidenceArtifact(
        id="artifact-pinned-search-order",
        idea_id="idea-pinned-search-order",
        idea_version_id="version-pinned-search-order",
        source_conversation_id=conversation.id,
        source_run_id="run-pinned-search-order",
        artifact_type="backtest",
        lifecycle="captured",
        title="AAPL evidence artifact",
        digest="AAPL evidence artifact digest.",
        payload={"provenance": {"symbols": ["AAPL"], "benchmark_symbol": "SPY"}},
        created_at=now,
        updated_at=now,
    )
    api_state.store.conversations[conversation.id] = conversation
    api_state.store.conversation_owners[conversation.id] = user_id
    api_state.store.evidence_artifacts[artifact.id] = artifact
    api_state.store.evidence_artifact_owners[artifact.id] = user_id

    response = client.get("/api/v1/search?q=aapl&limit=10")

    assert response.status_code == 200
    assert [(item["type"], item["id"]) for item in response.json()["items"]] == [
        ("conversation", conversation.id)
    ]


def test_search_preserves_exact_chat_above_lower_relevance_p1_artifacts() -> None:
    client = _client()
    user_id = api_state.store.get_or_create_dev_user().id
    now = utcnow()
    conversation = Conversation(
        id="conversation-exact-search-order",
        title="AAPL",
        title_source="user_renamed",
        pinned=False,
        archived=False,
        deleted_at=None,
        created_at=now - timedelta(minutes=5),
        updated_at=now + timedelta(minutes=10),
        last_message_preview="AAPL exact source",
        language="en",
    )
    artifact = EvidenceArtifact(
        id="artifact-exact-search-order",
        idea_id="idea-exact-search-order",
        idea_version_id="version-exact-search-order",
        source_conversation_id=conversation.id,
        source_run_id="run-exact-search-order",
        artifact_type="backtest",
        lifecycle="captured",
        title="AAPL evidence artifact",
        digest="AAPL evidence artifact digest.",
        payload={"provenance": {"symbols": ["AAPL"], "benchmark_symbol": "SPY"}},
        created_at=now,
        updated_at=now,
    )
    api_state.store.conversations[conversation.id] = conversation
    api_state.store.conversation_owners[conversation.id] = user_id
    api_state.store.evidence_artifacts[artifact.id] = artifact
    api_state.store.evidence_artifact_owners[artifact.id] = user_id

    response = client.get("/api/v1/search?q=aapl&limit=10")

    assert response.status_code == 200
    assert [(item["type"], item["id"]) for item in response.json()["items"]] == [
        ("conversation", conversation.id)
    ]


def test_search_orders_matching_object_layer_before_recency() -> None:
    client = _client()
    user_id = api_state.store.get_or_create_dev_user().id
    now = utcnow()
    artifact_conversation = Conversation(
        id="conversation-object-layer-search-order",
        title="Older research conversation",
        title_source="user_renamed",
        pinned=False,
        archived=False,
        deleted_at=None,
        created_at=now - timedelta(days=2),
        updated_at=now - timedelta(days=2),
        last_message_preview="Research notes",
        language="en",
    )
    recent_conversation = Conversation(
        id="conversation-recent-search-order",
        title="Gold allocation conversation",
        title_source="user_renamed",
        pinned=False,
        archived=False,
        deleted_at=None,
        created_at=now,
        updated_at=now,
        last_message_preview="Recent allocation notes",
        language="en",
    )
    artifact = EvidenceArtifact(
        id="artifact-object-layer-search-order",
        idea_id="idea-object-layer-search-order",
        idea_version_id="version-object-layer-search-order",
        source_conversation_id=artifact_conversation.id,
        source_run_id="run-object-layer-search-order",
        artifact_type="backtest",
        lifecycle="captured",
        title="Gold evidence review",
        digest="Gold evidence from the completed test.",
        payload={},
        created_at=now - timedelta(days=1),
        updated_at=now - timedelta(days=1),
    )
    for conversation in (artifact_conversation, recent_conversation):
        api_state.store.conversations[conversation.id] = conversation
        api_state.store.conversation_owners[conversation.id] = user_id
    api_state.store.evidence_artifacts[artifact.id] = artifact
    api_state.store.evidence_artifact_owners[artifact.id] = user_id

    response = client.get("/api/v1/search?q=gold&limit=10")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [
        artifact_conversation.id,
        recent_conversation.id,
    ]


def test_search_memory_mode_excludes_other_users_owned_objects() -> None:
    client = _client()
    other_user_id = "00000000-0000-0000-0000-000000000099"
    now = utcnow()
    memory_conversation(
        scope=PERSONAL,
        title="Leaky Tesla alpha chat",
        title_source="user_renamed",
        language="en",
        user_id=other_user_id,
    )
    strategy = Strategy(
        id="other-strategy",
        name="Leaky Tesla strategy",
        name_source="user_renamed",
        template="rsi_mean_reversion",
        asset_class="equity",
        symbols=["TSLA"],
        parameters={},
        metrics_preferences=["total_return_pct"],
        benchmark_symbol="SPY",
        created_at=now,
        updated_at=now,
    )
    collection = Collection(
        id="other-collection",
        name="Leaky Tesla collection",
        name_source="user_renamed",
        created_at=now,
        updated_at=now,
    )
    run = BacktestRun(
        id="other-run",
        conversation_id=None,
        strategy_id=None,
        status="completed",
        asset_class="equity",
        symbols=["TSLA"],
        allocation_method="equal_weight",
        benchmark_symbol="SPY",
        metrics={},
        config_snapshot={"template": "rsi_mean_reversion"},
        conversation_result_card={"title": "Leaky Tesla backtest"},
        created_at=now,
    )
    api_state.store.strategies[strategy.id] = strategy
    api_state.store.collections[collection.id] = collection
    api_state.store.backtest_runs[run.id] = run
    api_state.store.backtest_run_owners[run.id] = other_user_id
    api_state.store.strategy_owners = {strategy.id: other_user_id}
    api_state.store.collection_owners = {collection.id: other_user_id}

    response = client.get("/api/v1/search?q=leaky&limit=20")

    assert response.status_code == 200
    assert response.json()["items"] == []


def test_search_empty_query_includes_archived_recents_and_excludes_deleted() -> None:
    client = _client()
    user_id = api_state.store.get_or_create_dev_user().id
    now = utcnow()
    _store_search_conversation(
        user_id=user_id,
        conversation_id="conversation-archived-recent",
        title="Archived gold idea",
        updated_at=now,
        archived=True,
    )
    _store_search_conversation(
        user_id=user_id,
        conversation_id="conversation-active-older",
        title="Active gold idea",
        updated_at=now - timedelta(minutes=1),
    )
    _store_search_conversation(
        user_id=user_id,
        conversation_id="conversation-deleted-newest",
        title="Deleted gold idea",
        updated_at=now + timedelta(minutes=1),
        deleted_at=now,
    )

    response = client.get("/api/v1/search?q=&limit=20")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [
        "conversation-archived-recent",
        "conversation-active-older",
    ]


def test_search_id_scoped_recall_hydrates_visible_history_outside_ranked_page() -> None:
    client = _client()
    user_id = api_state.store.get_or_create_dev_user().id
    now = utcnow()
    target_id = "00000000-0000-0000-0000-000000000777"
    _store_search_conversation(
        user_id=user_id,
        conversation_id=target_id,
        title="Visible active conversation",
        updated_at=now - timedelta(days=7),
    )
    deleted_id = "00000000-0000-0000-0000-000000000778"
    foreign_id = "00000000-0000-0000-0000-000000000779"
    _store_search_conversation(
        user_id=user_id,
        conversation_id=deleted_id,
        title="Deleted conversation",
        updated_at=now,
        deleted_at=now,
    )
    archived_id = "00000000-0000-0000-0000-000000000780"
    _store_search_conversation(
        user_id=user_id,
        conversation_id=archived_id,
        title="Remotely archived conversation",
        updated_at=now + timedelta(minutes=102),
        archived=True,
    )
    _store_search_conversation(
        user_id="00000000-0000-0000-0000-000000000999",
        conversation_id=foreign_id,
        title="Foreign conversation",
        updated_at=now,
    )
    for index in range(101):
        conversation_id = f"conversation-archived-pinned-{index:03d}"
        _store_search_conversation(
            user_id=user_id,
            conversation_id=conversation_id,
            title=f"Archived pinned conversation {index}",
            updated_at=now + timedelta(minutes=index),
            archived=True,
        )
        conversation = api_state.store.conversations[conversation_id]
        api_state.store.conversations[conversation_id] = conversation.model_copy(
            update={"pinned": True}
        )

    ranked = client.get("/api/v1/search", params={"q": "", "limit": 100})
    recalled = client.get(
        "/api/v1/search",
        params={
            "q": "",
            "limit": 4,
            "conversation_id": [
                target_id,
                archived_id,
                deleted_id,
                foreign_id,
            ],
            "include_ledger_groups": "true",
        },
    )

    assert ranked.status_code == 200
    assert target_id not in {item["id"] for item in ranked.json()["items"]}
    assert recalled.status_code == 200
    payload = recalled.json()
    items_by_id = {item["id"]: item for item in payload["items"]}
    assert set(items_by_id) == {target_id, archived_id}
    assert items_by_id[target_id]["archived"] is False
    assert items_by_id[archived_id]["archived"] is True
    assert items_by_id[target_id]["title"] == "Visible active conversation"
    assert items_by_id[target_id]["dossier"] is None
    assert items_by_id[target_id]["total_runs"] == 0
    assert items_by_id[target_id]["decided_runs"] == 0
    assert payload["next_cursor"] is None
    assert len(payload["ledger_groups"]) == 4


def test_search_id_scoped_recall_rejects_ranked_search_controls() -> None:
    client = _client()

    response = client.get(
        "/api/v1/search",
        params={
            "q": "gold",
            "limit": 1,
            "conversation_id": ["00000000-0000-0000-0000-000000000001"],
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"


def test_search_id_scoped_recall_caps_visible_conversation_ids_at_fifty() -> None:
    client = _client()

    response = client.get(
        "/api/v1/search",
        params={
            "q": "",
            "limit": 50,
            "conversation_id": [
                f"00000000-0000-0000-0000-{index:012d}" for index in range(51)
            ],
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_decision_endpoint_marks_evidence_artifact_decided() -> None:
    client = _client()
    conversation = client.post("/api/v1/conversations", json={}).json()["conversation"]

    response = client.post(
        "/api/v1/chat/stream",
        headers={"Idempotency-Key": "chat-p1-evidence"},
        json={
            "conversation_id": conversation["id"],
            "message": "Backtest TSLA from 2025 to 2025",
            "language": "en",
        },
    )
    payload = _final_payload(response.text)
    artifact_id = payload["run"]["conversation_result_card"]["evidence_artifact_id"]

    decision = client.post(
        f"/api/v1/evidence-artifacts/{artifact_id}/decision",
        json={"decision_state": "promising", "note": "Worth revisiting."},
    )

    assert decision.status_code == 200
    body = decision.json()
    assert body["decision"]["decision_state"] == "promising"
    assert body["decision"]["note"] == "Worth revisiting."
    assert body["evidence_artifact"]["lifecycle"] == "decided"
    artifact = api_state.store.evidence_artifacts[artifact_id]
    assert api_state.store.ideas[artifact.idea_id].lifecycle == "decided"
    assert api_state.store.idea_versions[artifact.idea_version_id].lifecycle == "decided"
    assistant_result_cards = [
        message.metadata.get("result_card")
        for messages in api_state.store.messages.values()
        for message in messages
        if message.role == "assistant"
        and isinstance(message.metadata.get("result_card"), dict)
    ]
    assert any(
        card.get("evidence_artifact_id") == artifact_id
        and card.get("decision_state") == "promising"
        for card in assistant_result_cards
    )
    reloaded = client.get(f"/api/v1/conversations/{conversation['id']}/messages")
    assert reloaded.status_code == 200
    reloaded_cards = [
        item.get("metadata", {}).get("result_card")
        for item in reloaded.json()["items"]
        if isinstance(item.get("metadata", {}).get("result_card"), dict)
    ]
    assert any(
        card.get("evidence_artifact_id") == artifact_id
        and card.get("decision_state") == "promising"
        for card in reloaded_cards
    )
    api_state.store.evidence_artifacts[artifact_id] = artifact.model_copy(
        update={"digest": "PRIVATE ENGLISH ARTIFACT DIGEST"}
    )
    recalled = client.get("/api/v1/search?q=Worth%20revisiting&limit=20")
    assert recalled.status_code == 200
    assert len(recalled.json()["items"]) == 1
    recalled_conversation = recalled.json()["items"][0]
    assert recalled_conversation["type"] == "conversation"
    assert recalled_conversation["id"] == conversation["id"]
    assert recalled_conversation["matched_text"] == ""
    assert recalled_conversation["match"]["fragment"] == ""
    assert recalled_conversation["match"]["layer"] == "decision"
    assert recalled_conversation["match"]["count"] == 1
    assert "message_id" not in recalled_conversation["match"]
    assert "PRIVATE ENGLISH ARTIFACT DIGEST" not in recalled.text
    assert recalled_conversation["dossier"]["decision"]["note"] == "Worth revisiting."


def test_decision_endpoint_is_idempotent_per_evidence_artifact() -> None:
    client = _client()
    conversation = client.post("/api/v1/conversations", json={}).json()["conversation"]

    response = client.post(
        "/api/v1/chat/stream",
        headers={"Idempotency-Key": "chat-p1-decision-idempotent"},
        json={
            "conversation_id": conversation["id"],
            "message": "Backtest TSLA from 2025 to 2025",
            "language": "en",
        },
    )
    artifact_id = _final_payload(response.text)["run"]["conversation_result_card"][
        "evidence_artifact_id"
    ]

    first = client.post(
        f"/api/v1/evidence-artifacts/{artifact_id}/decision",
        json={"decision_state": "watching", "note": "Track it."},
    )
    second = client.post(
        f"/api/v1/evidence-artifacts/{artifact_id}/decision",
        json={"decision_state": "promising", "note": "Still promising."},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    first_body = first.json()
    second_body = second.json()
    assert second_body["decision"]["id"] == first_body["decision"]["id"]
    assert second_body["decision"]["decision_state"] == "promising"
    assert second_body["decision"]["note"] == "Still promising."
    decisions_for_artifact = [
        decision
        for decision in api_state.store.decision_notes.values()
        if decision.evidence_artifact_id == artifact_id
    ]
    assert len(decisions_for_artifact) == 1


def test_decision_endpoint_invalid_body_returns_problem_details() -> None:
    client = _client()
    response = client.post(
        "/api/v1/evidence-artifacts/artifact-1/decision",
        json={},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["type"] == "https://api.argus.app/problems/validation-error"
    assert body["title"] == "Validation Error"
    assert body["status"] == 422
    assert body["code"] == "validation_error"
    assert body["request_id"]
    assert isinstance(body["context"]["errors"], list)
    assert "decision_state" in str(body["context"]["errors"])


def test_decision_note_write_limit_is_500_and_legacy_reads_remain_compatible() -> None:
    from argus.api.schemas import DecisionNoteCreate, SearchDossierDecision

    accepted = DecisionNoteCreate(decision_state="watching", note="x" * 500)
    assert accepted.note == "x" * 500

    with pytest.raises(ValidationError):
        DecisionNoteCreate(decision_state="watching", note="x" * 501)

    legacy = SearchDossierDecision(state="watching", note="x" * 2000)
    assert legacy.note == "x" * 2000

    client = _client()
    rejected = client.post(
        "/api/v1/evidence-artifacts/artifact-1/decision",
        json={"decision_state": "watching", "note": "x" * 501},
    )
    assert rejected.status_code == 422
    assert "note" in str(rejected.json()["context"]["errors"])


def test_search_projects_one_typed_conversation_dossier() -> None:
    client = _client()
    conversation = client.post("/api/v1/conversations", json={}).json()["conversation"]

    response = client.post(
        "/api/v1/chat/stream",
        headers={"Idempotency-Key": "chat-p1-search"},
        json={
            "conversation_id": conversation["id"],
            "message": "Backtest TSLA from 2025 to 2025",
            "language": "en",
        },
    )
    artifact_id = _final_payload(response.text)["run"]["conversation_result_card"][
        "evidence_artifact_id"
    ]
    client.post(
        f"/api/v1/evidence-artifacts/{artifact_id}/decision",
        json={
            "decision_state": "watching",
            "note": "Track it.\nReview risk before the next run.",
        },
    )

    payload = client.get("/api/v1/search?q=TSLA&limit=20").json()

    conversations = [item for item in payload["items"] if item["type"] == "conversation"]
    assert len(conversations) == 1
    item = conversations[0]
    assert item["type"] == "conversation"
    assert item["id"] == conversation["id"]
    assert item["conversation_id"] == conversation["id"]
    assert item["preview"]["kind"] == "result"
    assert item["preview"]["symbols"] == ["TSLA"]
    assert item["preview"]["text"] is None

    dossier = item["dossier"]
    assert list(dossier) == [
        "run_id",
        "run_label",
        "completed_at",
        "result_message_id",
        "tested",
        "outcome",
        "decision",
        "actions",
    ]
    assert dossier["run_id"]
    assert dossier["result_message_id"]
    assert dossier["decision"] == {
        "state": "watching",
        "note": "Track it.\nReview risk before the next run.",
        "run_label": dossier["run_label"],
    }
    assert dossier["tested"]["symbols"] == ["TSLA"]
    assert dossier["tested"]["strategy_family"] == "rsi_mean_reversion"
    assert dossier["outcome"]["run_label"]
    assert dossier["outcome"]["benchmark_symbol"] == "SPY"
    assert "quick_take" not in dossier["outcome"]
    assert dossier["outcome"]["result_fact_bank"]["symbols"] == ["TSLA"]
    assert dossier["outcome"]["metrics"] == [{"name": "total_return_pct", "value": 12.5}]
    assert item["total_runs"] == 1
    assert item["decided_runs"] == 1
    assert "actions" not in item

    history = client.get(
        f"/api/v1/conversations/{conversation['id']}/run-dossiers?limit=20"
    )
    assert history.status_code == 200
    assert history.json() == {
        "items": [dossier],
        "next_cursor": None,
        "total_runs": 1,
        "decided_runs": 1,
    }


def test_run_dossier_history_uses_non_leaking_ownership_and_cursor_errors() -> None:
    client = _client()
    user_id = api_state.store.get_or_create_dev_user().id
    now = utcnow()
    _store_search_conversation(
        user_id=user_id,
        conversation_id="owned-dossier-history",
        title="Owned history",
        updated_at=now,
    )
    _store_search_conversation(
        user_id="other-owner",
        conversation_id="foreign-dossier-history",
        title="Foreign history",
        updated_at=now,
    )
    _store_search_conversation(
        user_id=user_id,
        conversation_id="deleted-dossier-history",
        title="Deleted history",
        updated_at=now,
        deleted_at=now,
    )

    owned = client.get("/api/v1/conversations/owned-dossier-history/run-dossiers")
    malformed = client.get(
        "/api/v1/conversations/owned-dossier-history/run-dossiers",
        params={"cursor": "not-a-cursor"},
    )
    over_bound = client.get(
        "/api/v1/conversations/owned-dossier-history/run-dossiers",
        params={"limit": 101},
    )
    hidden = [
        client.get(f"/api/v1/conversations/{conversation_id}/run-dossiers")
        for conversation_id in (
            "missing-dossier-history",
            "foreign-dossier-history",
            "deleted-dossier-history",
        )
    ]

    assert owned.status_code == 200
    assert owned.json() == {
        "items": [],
        "next_cursor": None,
        "total_runs": 0,
        "decided_runs": 0,
    }
    assert malformed.status_code == 400
    assert malformed.json()["detail"] == "Invalid cursor."
    assert over_bound.status_code == 422
    assert [response.status_code for response in hidden] == [404, 404, 404]
    assert {response.json()["detail"] for response in hidden} == {
        "Conversation not found."
    }


def test_search_dossier_preserves_canonical_metric_priority_when_bounded() -> None:
    from argus.domain.conversation_recall import project_conversation_recall

    now = utcnow()
    conversation_id = "bounded-metric-priority"
    run_id = "bounded-metric-priority-run"
    performance = {
        "total_return_pct": 12.5,
        "benchmark_return_pct": 8.0,
        "delta_vs_benchmark_pct": 4.5,
        "max_drawdown_pct": -6.0,
        "sharpe_ratio": 1.2,
    }
    projected = project_conversation_recall(
        conversation={
            "id": conversation_id,
            "title": "Bounded metric priority",
            "updated_at": now,
        },
        runs=[
            {
                "id": run_id,
                "conversation_id": conversation_id,
                "status": "completed",
                "symbols": ["GLD"],
                "benchmark_symbol": "SPY",
                "conversation_result_card": {"title": "GLD outcome"},
                "metrics": {"aggregate": {"performance": performance}},
                "created_at": now,
            }
        ],
        ideas=[],
        evidence=[
            {
                "id": "bounded-metric-priority-evidence",
                "source_conversation_id": conversation_id,
                "source_run_id": run_id,
                "payload": {
                    "metrics": {
                        "aggregate": {
                            "performance": {
                                name: value + 100 for name, value in performance.items()
                            }
                        }
                    }
                },
                "created_at": now,
            }
        ],
        decisions=[],
        query="",
    )

    assert projected is not None
    outcome = projected[1].dossier.outcome
    assert outcome is not None
    assert [metric.name for metric in outcome.metrics] == [
        "total_return_pct",
        "benchmark_return_pct",
        "delta_vs_benchmark_pct",
        "max_drawdown_pct",
    ]
    assert {metric.name: metric.value for metric in outcome.metrics} == {
        metric.name: performance[metric.name] for metric in outcome.metrics
    }
    assert outcome.result_fact_bank["metrics"]["aggregate"]["performance"] == performance


def test_search_dossier_accepts_postgres_trimmed_fractional_activity() -> None:
    from argus.domain.conversation_recall import project_conversation_recall

    projected = project_conversation_recall(
        conversation={
            "id": "trimmed-postgres-fraction",
            "title": "Trimmed PostgreSQL timestamp",
            "updated_at": "2026-07-27T15:00:00+00:00",
            "_recall_summary": {"latest_activity": "2026-07-30T07:38:21.24646+00:00"},
        },
        runs=[],
        ideas=[],
        evidence=[],
        decisions=[],
        query="",
    )

    assert projected is not None
    assert (
        projected[1].updated_at.isoformat(timespec="microseconds")
        == "2026-07-30T07:38:21.246460+00:00"
    )


def test_search_dossier_keeps_an_old_decided_result_on_one_run() -> None:
    from argus.domain.conversation_recall import project_conversation_recall

    now = utcnow()
    completed_at = now - timedelta(days=120)
    conversation_id = "stale-decided-result"
    run_id = "stale-decided-result-run"
    artifact_id = "stale-decided-result-evidence"
    projected = project_conversation_recall(
        conversation={
            "id": conversation_id,
            "title": "Stale decided result",
            "updated_at": now,
        },
        runs=[
            {
                "id": run_id,
                "conversation_id": conversation_id,
                "status": "completed",
                "symbols": ["GLD"],
                "benchmark_symbol": "SPY",
                "conversation_result_card": {"title": "Old GLD outcome"},
                "created_at": completed_at,
            }
        ],
        ideas=[],
        evidence=[
            {
                "id": artifact_id,
                "source_conversation_id": conversation_id,
                "source_run_id": run_id,
                "created_at": completed_at,
            }
        ],
        decisions=[
            {
                "id": "stale-decided-result-decision",
                "source_conversation_id": conversation_id,
                "evidence_artifact_id": artifact_id,
                "decision_state": "watching",
                "created_at": completed_at,
            }
        ],
        query="",
    )

    assert projected is not None
    dossier = projected[1].dossier
    assert dossier is not None
    assert dossier.run_id == run_id
    assert dossier.completed_at == completed_at
    assert dossier.decision is not None
    assert dossier.decision.state == "watching"


def test_search_dossier_result_anchor_does_not_depend_on_later_user_copy() -> None:
    from argus.domain.conversation_recall import project_conversation_recall

    now = utcnow()
    conversation_id = "untaken-suggestion"
    run_id = "untaken-suggestion-run"
    artifact_id = "untaken-suggestion-evidence"
    assistant_offer = {
        "id": "untaken-suggestion-offer",
        "conversation_id": conversation_id,
        "role": "assistant",
        "content": "Here are supported next experiments.",
        "metadata": {
            "result_run_id": run_id,
            "next_experiments": {
                "version": "argus_next_experiments/v1",
                "rows": [
                    {
                        "kind": "change_date_range",
                        "label": "Test a different date range",
                    }
                ],
            },
        },
        "created_at": now - timedelta(minutes=1),
    }
    projection_inputs = {
        "conversation": {
            "id": conversation_id,
            "title": "Untaken suggestion",
            "updated_at": now,
        },
        "runs": [
            {
                "id": run_id,
                "conversation_id": conversation_id,
                "status": "completed",
                "symbols": ["GLD"],
                "benchmark_symbol": "SPY",
                "conversation_result_card": {"title": "Current GLD outcome"},
                "created_at": now - timedelta(minutes=3),
            }
        ],
        "ideas": [],
        "evidence": [
            {
                "id": artifact_id,
                "source_conversation_id": conversation_id,
                "source_run_id": run_id,
                "created_at": now - timedelta(minutes=3),
            }
        ],
        "decisions": [
            {
                "id": "untaken-suggestion-decision",
                "source_conversation_id": conversation_id,
                "evidence_artifact_id": artifact_id,
                "decision_state": "watching",
                "created_at": now - timedelta(minutes=2),
            }
        ],
        "query": "",
    }

    offered = project_conversation_recall(
        **projection_inputs,
        messages=[assistant_offer],
    )
    followed_up = project_conversation_recall(
        **projection_inputs,
        messages=[
            assistant_offer,
            {
                "id": "untaken-suggestion-user-reply",
                "conversation_id": conversation_id,
                "role": "user",
                "content": "Let me try something else.",
                "created_at": now,
            },
        ],
    )

    assert offered is not None
    assert offered[1].dossier is not None
    assert offered[1].dossier.result_message_id == assistant_offer["id"]
    assert followed_up is not None
    assert followed_up[1].dossier is not None
    assert followed_up[1].dossier.result_message_id == assistant_offer["id"]


def test_search_default_dossier_does_not_mix_an_older_run_decision() -> None:
    client = _client()
    conversation = client.post("/api/v1/conversations", json={}).json()["conversation"]
    first_response = client.post(
        "/api/v1/chat/stream",
        headers={"Idempotency-Key": "dossier-first-run"},
        json={
            "conversation_id": conversation["id"],
            "message": "Backtest AAPL from 2025 to 2025",
            "language": "en",
        },
    )
    first = _final_payload(first_response.text)["run"]
    artifact_id = first["conversation_result_card"]["evidence_artifact_id"]
    client.post(
        f"/api/v1/evidence-artifacts/{artifact_id}/decision",
        json={"decision_state": "watching", "note": "Anchor this older run."},
    )
    second_response = client.post(
        "/api/v1/chat/stream",
        headers={"Idempotency-Key": "dossier-second-run"},
        json={
            "conversation_id": conversation["id"],
            "message": "Backtest TSLA from 2025 to 2025",
            "language": "en",
        },
    )
    second = _final_payload(second_response.text)["run"]

    response = client.get("/api/v1/search?q=anchor&limit=20")

    assert response.status_code == 200
    item = response.json()["items"][0]
    dossier = item["dossier"]
    assert dossier["run_id"] == second["id"]
    assert dossier["run_label"] == second["conversation_result_card"]["title"]
    assert dossier["decision"] is None
    assert item["total_runs"] == 2
    assert item["decided_runs"] == 1


def test_search_actions_anchor_latest_run_without_generation_or_auto_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.agent_runtime import runtime as agent_runtime
    from argus.domain import engine as domain_engine

    def unexpected_external_call(*_: object, **__: object) -> None:
        raise AssertionError("Omnisearch action projection must stay deterministic")

    monkeypatch.setattr(domain_engine, "resolve_asset", unexpected_external_call)
    monkeypatch.setattr(domain_engine, "fetch_ohlcv", unexpected_external_call)
    monkeypatch.setattr(agent_runtime, "run_agent_turn", unexpected_external_call)

    client = _client()
    user_id = api_state.store.get_or_create_dev_user().id
    now = utcnow()
    conversation_id = "actionable-dossier-conversation"
    _store_search_conversation(
        user_id=user_id,
        conversation_id=conversation_id,
        title="Actionable GLD dossier",
        updated_at=now,
    )
    run = BacktestRun(
        id="actionable-dossier-run",
        conversation_id=conversation_id,
        strategy_id=None,
        status="completed",
        asset_class="equity",
        symbols=["GLD"],
        allocation_method="equal_weight",
        benchmark_symbol="SPY",
        metrics={},
        config_snapshot={
            "template": "buy_and_hold",
            "symbols": ["GLD"],
            "timeframe": "1D",
            "date_range": {"start": "2024-01-01", "end": "2024-12-31"},
            "benchmark_symbol": "SPY",
            "resolved_strategy": {
                "strategy_type": "buy_and_hold",
                "asset_universe": ["GLD"],
                "asset_class": "equity",
                "entry_rule": {"type": "start_of_period"},
                "exit_rule": {"type": "end_of_period"},
            },
            "resolved_parameters": {
                "timeframe": "1D",
                "date_range": {"start": "2024-01-01", "end": "2024-12-31"},
                "sizing_mode": "capital_amount",
                "capital_amount": 10_000,
                "benchmark_symbol": "SPY",
            },
        },
        conversation_result_card={
            "title": "Annual GLD buy and hold",
            "evidence_artifact_id": "gld-evidence",
            "idea_id": "gld-idea",
            "idea_version_id": "gld-idea-version",
        },
        created_at=now,
    )
    artifact = EvidenceArtifact(
        id="actionable-dossier-evidence",
        idea_id="actionable-dossier-idea",
        idea_version_id="actionable-dossier-version",
        source_conversation_id=conversation_id,
        source_run_id=run.id,
        artifact_type="backtest",
        lifecycle="decided",
        title="Annual GLD buy and hold",
        digest="GLD was tested against SPY.",
        payload={},
        created_at=now,
        updated_at=now,
    )
    decision = DecisionNote(
        id="actionable-dossier-decision",
        idea_id=artifact.idea_id,
        idea_version_id=artifact.idea_version_id,
        evidence_artifact_id=artifact.id,
        source_conversation_id=conversation_id,
        decision_state="watching",
        note="Review after the next annual window.",
        created_at=now,
        updated_at=now,
    )
    api_state.store.backtest_runs[run.id] = run
    api_state.store.backtest_run_owners[run.id] = user_id
    api_state.store.evidence_artifacts[artifact.id] = artifact
    api_state.store.evidence_artifact_owners[artifact.id] = user_id
    api_state.store.decision_notes[decision.id] = decision
    api_state.store.decision_note_owners[decision.id] = user_id
    run_ids_before = set(api_state.store.backtest_runs)

    response = client.get("/api/v1/search", params={"q": "GLD", "limit": 20})

    assert response.status_code == 200
    conversation = next(
        item for item in response.json()["items"] if item["type"] == "conversation"
    )
    retest, change_decision = conversation["dossier"]["actions"]
    # The dossier projects identity, policy, and server-owned pre-click
    # eligibility. The executable setup and old generated prompt are gone, so
    # the obsolete send-the-prose path cannot be driven from this payload.
    assert retest == {
        "type": "retest_run",
        "source_run_id": run.id,
        "run_label": "Annual GLD buy and hold",
        "window_policy": "preserve_start_ending_latest_available",
        "contract_version": "argus_retest_run/v2",
        "state": "new_data_available",
        "reason_code": None,
        "repair": None,
    }
    assert "canonical_setup" not in retest
    assert "send_text" not in retest
    assert change_decision == {
        "type": "decision",
        "availability": "available",
        "evidence_artifact_id": artifact.id,
        "decision_state": "watching",
        "note": "Review after the next annual window.",
        "run_label": "Annual GLD buy and hold",
    }
    assert set(api_state.store.backtest_runs) == run_ids_before


def test_search_actions_keep_latest_run_attribution_and_conversion_gate_guest() -> None:
    from argus.domain.conversation_recall import project_conversation_recall

    now = utcnow()
    older = {
        "id": "older-run",
        "conversation_id": "multi-run-action-conversation",
        "status": "completed",
        "asset_class": "equity",
        "symbols": ["AAPL"],
        "benchmark_symbol": "SPY",
        "config_snapshot": {
            "template": "buy_and_hold",
            "timeframe": "1D",
            "date_range": {"start": "2024-01-01", "end": "2024-06-30"},
            "resolved_parameters": {
                "sizing_mode": "capital_amount",
                "capital_amount": 1_000,
            },
        },
        "conversation_result_card": {
            "title": "Older AAPL run",
            "evidence_artifact_id": "older-evidence",
            "idea_id": "older-idea",
            "idea_version_id": "older-idea-version",
        },
        "created_at": now - timedelta(days=1),
    }
    latest = {
        **older,
        "id": "latest-run",
        "symbols": ["MSFT"],
        "conversation_result_card": {
            "title": "Latest MSFT run",
            "evidence_artifact_id": "latest-evidence",
            "idea_id": "latest-idea",
            "idea_version_id": "latest-idea-version",
        },
        "created_at": now,
    }
    evidence = [
        {
            "id": "older-evidence",
            "source_conversation_id": "multi-run-action-conversation",
            "source_run_id": "older-run",
            "created_at": now - timedelta(days=1),
        },
        {
            "id": "latest-evidence",
            "source_conversation_id": "multi-run-action-conversation",
            "source_run_id": "latest-run",
            "created_at": now,
        },
    ]
    decisions = [
        {
            "id": "older-decision",
            "source_conversation_id": "multi-run-action-conversation",
            "evidence_artifact_id": "older-evidence",
            "decision_state": "watching",
            "note": "This belongs to the older run.",
            "created_at": now - timedelta(hours=12),
        }
    ]

    projected = project_conversation_recall(
        conversation={
            "id": "multi-run-action-conversation",
            "title": "Two run dossier",
            "updated_at": now,
        },
        runs=[older, latest],
        ideas=[],
        evidence=evidence,
        decisions=decisions,
        query="",
        decision_action_availability="account_conversion_required",
    )

    assert projected is not None
    _, item = projected
    assert item.dossier is not None
    assert [action.type for action in item.dossier.actions] == [
        "retest_run",
        "decision",
    ]
    assert item.dossier.actions[0].source_run_id == "latest-run"
    decision_action = item.dossier.actions[1]
    assert decision_action.type == "decision"
    assert decision_action.evidence_artifact_id == "latest-evidence"
    assert decision_action.availability == "account_conversion_required"
    assert item.dossier.decision is None
    assert item.total_runs == 2
    assert item.decided_runs == 1


def _chat_persisted_retest_fixture(
    monkeypatch: pytest.MonkeyPatch,
    *,
    request_payload: dict[str, Any],
    language: str = "es-419",
) -> tuple[Any, Any, dict[str, Any], dict[str, Any]]:
    from argus.api.chat.persistence import build_runtime_backtest_run
    from argus.domain.engine_launch.adapter import run_launch_backtest
    from argus.domain.engine_launch.models import LaunchBacktestRequest
    from argus.domain.retest_setup import retest_setup_from_run

    monkeypatch.setenv("ARGUS_ENABLE_EXECUTION_REALISM", "true")
    monkeypatch.setenv("ARGUS_MARKET_DATA_PROVIDER_MODE", "synthetic_unit_fixture")
    launch = run_launch_backtest(LaunchBacktestRequest.model_validate(request_payload))
    assert launch.envelope.execution_status == "succeeded"
    assert launch.result_card is not None
    envelope = launch.envelope.model_dump(mode="python")
    run = build_runtime_backtest_run(
        user_id="action-fixture-user",
        conversation_id="action-fixture-conversation",
        result_card=launch.result_card,
        envelope=envelope,
        classify_symbol_func=_fake_resolve_asset,
        default_benchmark_func=lambda _asset_class, _symbols: "SPY",
        run_id=f"action-fixture-{request_payload['strategy_type']}",
    )
    assert run is not None
    # Finalization attaches evidence identity last; model a finalized run so
    # eligibility sees the same shape admission requires.
    run = run.model_copy(
        update={
            "conversation_result_card": {
                **(run.conversation_result_card or {}),
                "evidence_artifact_id": "action-fixture-evidence",
                "idea_id": "action-fixture-idea",
                "idea_version_id": "action-fixture-idea-version",
            }
        }
    )

    from argus.domain.conversation_recall import project_conversation_recall

    projected = project_conversation_recall(
        conversation={
            "id": run.conversation_id,
            "title": "Real chat-produced run",
            "updated_at": run.created_at,
        },
        runs=[run.model_dump(mode="python")],
        ideas=[],
        evidence=[
            {
                "id": "action-fixture-evidence",
                "source_conversation_id": run.conversation_id,
                "source_run_id": run.id,
                "title": "Action fixture evidence",
                "digest": "Action fixture result.",
                "payload": {},
                "created_at": run.created_at,
                "updated_at": run.created_at,
            }
        ],
        decisions=[],
        query="",
        language=language,
    )
    assert projected is not None
    _, item = projected
    assert item.dossier is not None
    action = next(
        (
            candidate
            for candidate in item.dossier.actions
            if candidate.type == "retest_run"
        ),
        None,
    )
    stored_run = run.model_dump(mode="python")
    # The action is now identity-only, so setup fidelity is asserted where it
    # actually lives: the server-side reconstruction the confirmation uses.
    setup = retest_setup_from_run(stored_run, today=new_york_today())
    return (action, setup, envelope, stored_run)


def _run_fresh_spanish_dates() -> tuple[str, str]:
    current_end = new_york_today()
    current_start = current_end - timedelta(days=365)
    return current_start.isoformat(), current_end.isoformat()


def _stable_test_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def test_search_retest_preserves_chat_dca_contribution_and_principal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    action, setup, _, _ = _chat_persisted_retest_fixture(
        monkeypatch,
        request_payload={
            "strategy_type": "dca_accumulation",
            "symbol": "TSLA",
            "timeframe": "1D",
            "date_range": {"start": "2024-01-01", "end": "2024-12-31"},
            "entry_rule": None,
            "exit_rule": None,
            "sizing_mode": "capital_amount",
            "capital_amount": 500.0,
            "position_size": None,
            "cadence": "monthly",
            "parameters": {},
            "risk_rules": [],
            "benchmark_symbol": "SPY",
        },
    )

    assert action is not None
    assert setup is not None
    assert setup.capital_amount == 500.0
    assert setup.recurring_contribution == 500.0
    assert setup.starting_capital == 0.0
    assert setup.execution_realism is None


def test_search_retest_reads_nested_chat_modeled_costs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution_realism = {
        "enabled": True,
        "fee_bps": 10.0,
        "slippage_bps": 5.0,
    }
    action, setup, _, _ = _chat_persisted_retest_fixture(
        monkeypatch,
        request_payload={
            "strategy_type": "buy_and_hold",
            "symbol": "TSLA",
            "timeframe": "1D",
            "date_range": {"start": "2024-01-01", "end": "2024-12-31"},
            "entry_rule": None,
            "exit_rule": None,
            "sizing_mode": "capital_amount",
            "capital_amount": 10_000.0,
            "position_size": None,
            "cadence": None,
            "parameters": {},
            "risk_rules": [],
            "benchmark_symbol": "SPY",
            "_execution_realism": execution_realism,
        },
    )

    assert action is not None
    assert setup is not None
    assert setup.execution_realism == execution_realism


@pytest.mark.parametrize(
    ("request_payload", "strategy_copy"),
    [
        (
            {
                "strategy_type": "indicator_threshold",
                "symbol": "TSLA",
                "timeframe": "1D",
                "date_range": {"start": "2024-01-01", "end": "2024-12-31"},
                "entry_rule": {
                    "indicator": "rsi",
                    "operator": "below",
                    "threshold": 30,
                },
                "exit_rule": {
                    "indicator": "rsi",
                    "operator": "above",
                    "threshold": 55,
                },
                "sizing_mode": "capital_amount",
                "capital_amount": 10_000.0,
                "position_size": None,
                "cadence": None,
                "parameters": {},
                "risk_rules": [],
                "benchmark_symbol": "SPY",
            },
            "estrategia de umbral de indicador",
        ),
        (
            {
                "strategy_type": "signal_strategy",
                "symbol": "TSLA",
                "timeframe": "1D",
                "date_range": {"start": "2024-01-01", "end": "2024-12-31"},
                "entry_rule": {
                    "type": "moving_average_crossover",
                    "fast_indicator": "sma",
                    "fast_period": 20,
                    "slow_indicator": "sma",
                    "slow_period": 50,
                    "direction": "bullish",
                },
                "exit_rule": {
                    "type": "moving_average_crossover",
                    "fast_indicator": "sma",
                    "fast_period": 20,
                    "slow_indicator": "sma",
                    "slow_period": 50,
                    "direction": "bearish",
                },
                "sizing_mode": "capital_amount",
                "capital_amount": 10_000.0,
                "position_size": None,
                "cadence": None,
                "parameters": {},
                "risk_rules": [],
                "benchmark_symbol": "SPY",
            },
            "estrategia de señales",
        ),
    ],
)
def test_search_retest_localizes_the_spanish_confirmation_card(
    monkeypatch: pytest.MonkeyPatch,
    request_payload: dict[str, Any],
    strategy_copy: str,
) -> None:
    """Spanish now rides the confirmation card, not a generated prompt.

    The old action carried localized `send_text`; the typed envelope carries
    none, so this asserts the localization survives where it moved to.
    """
    from argus.agent_runtime.retest_confirmation import (
        retest_confirmation_payload,
        retest_runtime_result,
    )
    from argus.api.chat.confirmation import runtime_confirmation_card

    action, setup, _, _ = _chat_persisted_retest_fixture(
        monkeypatch,
        request_payload=request_payload,
        language="es-419",
    )
    assert action is not None
    assert setup is not None

    def _card(language: str) -> dict[str, Any]:
        payload = retest_confirmation_payload(
            setup,
            language=language,
            confirmation_id=f"confirmation-retest-{language}",
        )
        assert payload is not None
        card = runtime_confirmation_card(
            retest_runtime_result(payload),
            confirmation_id=f"confirmation-retest-{language}",
            conversation_id="retest-fixture-conversation",
            language=language,
        )
        assert card is not None
        return card

    spanish = _card("es-419")
    english = _card("en")

    assert spanish["status"] == "ready_to_run"
    # Language reaches the card: the window renders in Spanish.
    assert " de " in spanish["date_range"]["display"]
    assert spanish["date_range"]["start"] == setup.start.isoformat()

    def _rule_values(card: dict[str, Any]) -> dict[str, str]:
        return {
            row["key"]: row["value"]
            for row in card["rows"]
            if row["key"] in {"entry_rule", "exit_rule"}
        }

    spanish_rules = _rule_values(spanish)
    english_rules = _rule_values(english)
    assert spanish_rules, "the confirmation must describe its executable rules"
    # The retired action localized rules inside a generated prompt. That
    # localization now lives in the card, so it must still be language-aware.
    assert spanish_rules != english_rules
    for value in spanish_rules.values():
        # Human prose, never the raw rule structure the old prompt embedded.
        assert "{" not in value and '"type"' not in value
    for row in spanish["rows"]:
        assert row.get("labelKey"), "clients localize labels from labelKey"
    rendered = _stable_test_json(spanish).casefold()
    assert "muestra la confirmación" not in rendered
    # NOTE: the card summary/title are persisted-compat English (#523):
    # clients localize the card from the typed fields beside them, so the
    # summary is not asserted against `strategy_copy`. The summary does still
    # reach readers through `last_message_preview`; that leak is #528.
    assert strategy_copy


def test_search_retest_omits_unfaithful_dca_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unfaithful snapshot must not be offered at all.

    Eligibility and admission share one reconstruction, so a run the backend
    cannot faithfully replay simply has no action on the dossier.
    """
    action, setup, _, run = _chat_persisted_retest_fixture(
        monkeypatch,
        request_payload={
            "strategy_type": "dca_accumulation",
            "symbol": "TSLA",
            "timeframe": "1D",
            "date_range": {"start": "2024-01-01", "end": "2024-12-31"},
            "entry_rule": None,
            "exit_rule": None,
            "sizing_mode": "capital_amount",
            "capital_amount": 500.0,
            "position_size": None,
            "cadence": "monthly",
            "parameters": {},
            "risk_rules": [],
            "benchmark_symbol": "SPY",
        },
    )
    assert action is not None
    assert setup is not None and setup.capital_amount == 500.0

    from argus.domain.conversation_recall import project_conversation_recall

    # Start from the real writer-shaped setup and remove the only facts that
    # distinguish a recurring contribution from a starting principal.
    resolved_parameters = run["config_snapshot"]["resolved_parameters"]
    engine_config = resolved_parameters["engine_config"]
    for key in ("recurring_contribution", "starting_capital"):
        resolved_parameters.pop(key)
    for config in (engine_config, run["config_snapshot"]["engine_config"]):
        config.pop("dca_capital", None)
    projected = project_conversation_recall(
        conversation={
            "id": run["conversation_id"],
            "title": "Incomplete DCA",
            "updated_at": utcnow(),
        },
        runs=[run],
        ideas=[],
        evidence=[
            {
                "id": "incomplete-dca-evidence",
                "source_conversation_id": run["conversation_id"],
                "source_run_id": run["id"],
                "title": "Incomplete DCA",
                "digest": "Incomplete DCA result.",
                "payload": {},
                "created_at": run["created_at"],
                "updated_at": run["created_at"],
            }
        ],
        decisions=[],
        query="",
    )
    assert projected is not None
    _, item = projected
    assert item.dossier is not None
    assert all(candidate.type != "retest_run" for candidate in item.dossier.actions)


def test_search_run_fresh_omits_oversized_action_without_failing_recall() -> None:
    from argus.domain.conversation_recall import project_conversation_recall

    now = utcnow()
    oversized_rule_spec = {
        "conditions": [
            {
                "indicator": "sma",
                "operator": "above",
                "threshold": index,
                "description": "x" * 200,
            }
            for index in range(30)
        ]
    }
    projected = project_conversation_recall(
        conversation={
            "id": "oversized-run-fresh-conversation",
            "title": "Large signal strategy",
            "updated_at": now,
        },
        runs=[
            {
                "id": "oversized-run-fresh-run",
                "conversation_id": "oversized-run-fresh-conversation",
                "status": "completed",
                "asset_class": "equity",
                "symbols": ["AAPL"],
                "benchmark_symbol": "SPY",
                "config_snapshot": {
                    "template": "signal_strategy",
                    "timeframe": "1D",
                    "date_range": {
                        "start": "2024-01-01",
                        "end": "2024-12-31",
                    },
                    "resolved_strategy": {
                        "strategy_type": "signal_strategy",
                        "asset_class": "equity",
                        "rule_spec": oversized_rule_spec,
                    },
                    "resolved_parameters": {
                        "timeframe": "1D",
                        "sizing_mode": "capital_amount",
                        "capital_amount": 10_000,
                        "benchmark_symbol": "SPY",
                    },
                },
                "conversation_result_card": {"title": "Large signal result"},
                "created_at": now,
            }
        ],
        ideas=[],
        evidence=[
            {
                "id": "oversized-run-fresh-evidence",
                "source_conversation_id": "oversized-run-fresh-conversation",
                "source_run_id": "oversized-run-fresh-run",
                "title": "Large signal result",
                "digest": "Large signal result.",
                "payload": {},
                "created_at": now,
                "updated_at": now,
            }
        ],
        decisions=[],
        query="",
    )

    assert projected is not None
    _, item = projected
    assert item.title == "Large signal strategy"
    assert item.dossier is not None
    assert item.dossier.tested is not None
    assert all(candidate.type != "run_fresh" for candidate in item.dossier.actions)


def test_invalid_cursor_returns_problem_details() -> None:
    client = _client()
    response = client.get("/api/v1/search?q=tesla&limit=5&cursor=not-a-valid-cursor")
    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == "validation_error"


def test_chat_missing_symbol_asks_clarifying_question(monkeypatch) -> None:
    from argus.api.routers import agent as agent_router

    client = _client()
    conversation = client.post("/api/v1/conversations", json={}).json()["conversation"]

    async def _missing_symbol_events(**_: Any):
        yield {
            "type": "final",
            "payload": {
                "stage_outcome": "await_user_reply",
                "assistant_prompt": "Which symbols do you want to test?",
                "final_response_payload": {"error": "missing_required_input"},
            },
        }

    monkeypatch.setattr(
        agent_router,
        "stream_agent_turn_events",
        _missing_symbol_events,
    )

    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": conversation["id"],
            "message": "Run RSI",
            "language": "en",
        },
    )

    assert response.status_code == 200
    assert "Which symbols do you want to test?" in response.text
    assert "running_backtest" not in response.text
    assert '"run"' not in response.text


def test_chat_run_uses_extracted_timeframe_not_hardcoded_1d(monkeypatch) -> None:
    from argus.api.routers import agent as agent_router

    client = _client()
    conversation = client.post("/api/v1/conversations", json={}).json()["conversation"]

    async def _btc_1h_events(**_: Any):
        result = _runtime_success_result(symbol="BTC", timeframe="1h")
        yield {"type": "final", "payload": result}

    monkeypatch.setattr(agent_router, "stream_agent_turn_events", _btc_1h_events)

    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": conversation["id"],
            "message": "Run BTC 1h",
        },
    )

    assert response.status_code == 200
    # The timeframe "1h" should be in the result run config_snapshot
    assert '"timeframe":"1h"' in response.text or '"timeframe": "1h"' in response.text


def test_chat_stream_passes_thread_context_to_runtime(monkeypatch) -> None:
    from argus.api import state as api_state
    from argus.api.routers import agent as agent_router

    client = _client()
    conversation = client.post("/api/v1/conversations", json={}).json()["conversation"]

    # Insert a message into memory store manually
    from datetime import datetime, timezone

    from argus.api.schemas import Message

    msg1 = Message(
        id="msg1",
        conversation_id=conversation["id"],
        role="user",
        content="Tell me about AAPL",
        created_at=datetime.now(timezone.utc),
    )
    api_state.store.messages[conversation["id"]] = [msg1]

    captured_runtime: dict[str, Any] = {}

    async def _fake_stream_agent_turn_events(**kwargs: Any):
        captured_runtime.update(kwargs)
        yield {
            "type": "final",
            "payload": _runtime_success_result(symbol="AAPL", assistant_response="ok"),
        }

    monkeypatch.setattr(
        agent_router,
        "stream_agent_turn_events",
        _fake_stream_agent_turn_events,
    )

    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": conversation["id"],
            "message": "Backtest it",
        },
    )

    assert response.status_code == 200
    assert captured_runtime["thread_id"] == conversation["id"]
    assert captured_runtime["message"] == "Backtest it"


def test_starter_prompts_returns_generic_suggestions() -> None:
    client = _client()

    resp = client.get("/api/v1/chat/starter-prompts")
    assert resp.status_code == 200
    assert len(resp.json()["prompts"]) == 4
    assert "Test Apple against SPY over the last 12 months." in resp.json()["prompts"]


def test_starter_prompts_follow_profile_language() -> None:
    client = _client()

    response = client.patch(
        "/api/v1/me",
        json={"language": "es-419"},
    )
    assert response.status_code == 200

    resp = client.get("/api/v1/chat/starter-prompts")
    assert resp.status_code == 200
    prompts = resp.json()["prompts"]
    assert len(prompts) == 4
    assert "Prueba Bitcoin en lo que va del año." in prompts
    assert all("2024" not in prompt for prompt in prompts)
