"""Behavior contract for the private-alpha onboarding strip-out.

Registered users go straight from authentication into ordinary chat. There is
no onboarding gate, no hidden ``__ONBOARDING_*`` control protocol, and no
onboarding-specific routing, persistence, or starter-prompt derivation. Legacy
persisted profile state stays inert, and legacy persisted marker messages stay
hidden from every public read surface.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from argus.api import state as api_state
from argus.api.main import app
from argus.api.message_store import memory_conversation, memory_message
from argus.api.schemas import OnboardingState
from argus.domain.market_data.assets import ResolvedAsset
from argus.domain.owner_scope import PERSONAL
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]

ORDINARY_REPLY = "Mock ordinary runtime reply."


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


def _fake_resolve_asset(symbol: str) -> ResolvedAsset:
    candidate = symbol.strip().upper().replace("-", "/")
    compact = candidate.replace("/", "")
    if compact.endswith("USD") and len(compact) > 3:
        compact = compact[:-3]
    asset_class = "crypto" if compact in {"BTC", "ETH", "SOL"} else "equity"
    return ResolvedAsset(
        symbol=compact,
        asset_class=asset_class,
        provider="synthetic",
    )


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
    close = pd.Series(100.0 + pd.RangeIndex(len(index)).astype(float) * 0.5, index=index)
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


def _runtime_result_for_message(message: str) -> dict[str, Any]:
    if "backtest" not in message.lower():
        return {
            "stage_outcome": "ready_to_respond",
            "assistant_response": ORDINARY_REPLY,
        }
    return {
        "stage_outcome": "ready_to_respond",
        "assistant_response": "I tested that idea with TSLA.",
        "final_response_payload": {
            "result": {
                "execution_status": "succeeded",
                "resolved_strategy": {
                    "strategy_type": "rsi_mean_reversion",
                    "asset_universe": ["TSLA"],
                },
                "resolved_parameters": {
                    "timeframe": "1D",
                    "date_range": {"start": "2025-01-01", "end": "2025-12-31"},
                },
                "metrics": {
                    "aggregate": {"performance": {"total_return_pct": 12.5}},
                    "by_symbol": {},
                },
                "benchmark_metrics": {
                    "benchmark_symbol": "SPY",
                    "benchmark_return_pct": 9.2,
                },
                "assumptions": ["Starting capital: $10,000."],
                "caveats": [],
            },
            "result_card": {
                "title": "TSLA RSI Mean Reversion",
                "status_label": "Simulation Complete",
                "rows": [{"label": "Total Return", "value": "+12.5%"}],
                "assumptions": ["Starting capital: $10,000."],
            },
        },
    }


async def _runtime_events(**kwargs: Any):
    message = str(kwargs.get("message", ""))
    result = _runtime_result_for_message(message)
    yield {"type": "stage_start", "stage": "interpret"}
    yield {"type": "stage_outcome", "outcome": str(result["stage_outcome"])}
    yield {"type": "token", "content": str(result["assistant_response"])}
    yield {"type": "final", "payload": result}


@pytest.fixture(autouse=True)
def _patch_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    from argus.domain import engine as domain_engine

    monkeypatch.setattr(api_state, "supabase_gateway", None)
    monkeypatch.setattr(domain_engine, "resolve_asset", _fake_resolve_asset)
    monkeypatch.setattr(domain_engine, "fetch_ohlcv", _fake_fetch_ohlcv)
    monkeypatch.setattr(domain_engine, "fetch_price_series", _fake_fetch_price_series)


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/api/v1/dev/reset")
    return client


def _set_legacy_onboarding_stage(client: TestClient, stage: str) -> str:
    """Seed the legacy persisted profile shape directly, as old rows have it.

    No API takes onboarding state from a client. `PATCH /me` sets only
    `language_confirmed`, when a language is saved, so
    the seed mutates the store the way a legacy database row would look.
    """

    user_id = client.get("/api/v1/me").json()["user"]["id"]
    user = api_state.store.users[user_id]
    api_state.store.users[user_id] = user.model_copy(
        update={
            "onboarding": OnboardingState(
                completed=False,
                stage=stage,
                language_confirmed=stage != "language_selection",
                primary_goal=None,
            )
        }
    )
    return user_id


def _ordinary_turn_reaches_runtime(client: TestClient) -> None:
    conversation = client.post("/api/v1/conversations", json={}).json()["conversation"]
    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": conversation["id"],
            "message": "Buy and hold AAPL over the last 12 months.",
            "language": "en",
        },
    )
    assert response.status_code == 200
    events = _stream_events(response.text)
    stages = [event["stage"] for event in events if event.get("type") == "stage_start"]
    assert stages[0] == "interpret"
    finals = [event for event in events if event.get("type") == "final"]
    assert len(finals) == 1
    assert finals[0]["payload"]["assistant_response"] == ORDINARY_REPLY


def test_patch_me_ignores_legacy_onboarding_field() -> None:
    client = _client()
    before = client.get("/api/v1/me").json()["user"]["onboarding"]

    response = client.patch(
        "/api/v1/me",
        json={
            "display_name": "Renamed",
            "onboarding": {
                "stage": "ready",
                "language_confirmed": True,
                "primary_goal": "test_stock_idea",
                "completed": True,
            },
        },
    )
    assert response.status_code == 200
    user = response.json()["user"]
    assert user["display_name"] == "Renamed"
    assert user["onboarding"] == before

    after = client.get("/api/v1/me").json()["user"]["onboarding"]
    assert after == before


def test_language_preference_updates_still_work() -> None:
    client = _client()
    response = client.patch(
        "/api/v1/me",
        json={"language": "es-419", "locale": "es-419"},
    )
    assert response.status_code == 200
    user = response.json()["user"]
    assert user["language"] == "es-419"
    assert user["locale"] == "es-419"

    back = client.patch("/api/v1/me", json={"language": "en", "locale": "en-US"})
    assert back.status_code == 200
    assert back.json()["user"]["language"] == "en"


def test_legacy_marker_messages_stay_hidden_from_reads() -> None:
    """Legacy persisted control messages never reach public read surfaces."""

    client = _client()
    user_id = client.get("/api/v1/me").json()["user"]["id"]
    conversation = memory_conversation(
        scope=PERSONAL,
        title="Legacy",
        title_source="system_default",
        language="en",
        user_id=user_id,
    )
    memory_message(
        conversation_id=conversation.id,
        role="user",
        content="__ONBOARDING_GOAL__:test_stock_idea",
    )
    memory_message(
        conversation_id=conversation.id,
        role="user",
        content="__ONBOARDING_SKIP__",
    )
    memory_message(
        conversation_id=conversation.id,
        role="assistant",
        content="Great. Share the stock idea you want to test and I'll run it.",
    )
    memory_message(
        conversation_id=conversation.id,
        role="user",
        content="Buy and hold AAPL this year.",
    )

    messages = client.get(f"/api/v1/conversations/{conversation.id}/messages")
    assert messages.status_code == 200
    items = messages.json()["items"]
    assert items
    assert all("__ONBOARDING_" not in message["content"] for message in items)
    contents = [message["content"] for message in items]
    assert "Buy and hold AAPL this year." in contents

    conversations = client.get("/api/v1/conversations").json()["items"]
    previews = [
        str(conversation_item.get("last_message_preview") or "")
        for conversation_item in conversations
    ]
    assert all("__ONBOARDING_" not in preview for preview in previews)


def test_no_active_source_carries_onboarding_protocol() -> None:
    """Marker literals exist only in legacy read filters, and the profile router
    touches onboarding state only to record that a language was chosen."""

    allowed_backend = {
        REPO_ROOT / "src/argus/api/chat/legacy_onboarding_markers.py",
    }
    allowed_frontend = {
        REPO_ROOT / "web/lib/chat-retry-actions.ts",
    }

    offending: list[str] = []
    for root, allowed in (
        (REPO_ROOT / "src", allowed_backend),
        (REPO_ROOT / "web", allowed_frontend),
    ):
        for path in root.rglob("*"):
            if path.suffix not in {".py", ".ts", ".tsx"}:
                continue
            if {"node_modules", ".next", "__tests__", "e2e"} & set(path.parts):
                continue
            if path in allowed:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "__ONBOARDING_" in text:
                offending.append(str(path.relative_to(REPO_ROOT)))
    assert offending == []

    profile_router = (REPO_ROOT / "src/argus/api/routers/profile.py").read_text(
        encoding="utf-8"
    )
    onboarding_lines = [
        line for line in profile_router.splitlines() if "onboarding" in line.lower()
    ]
    assert onboarding_lines, "PATCH /me records the chosen language in onboarding"
    assert all(
        "language_confirmed" in line for line in onboarding_lines
    ), onboarding_lines
