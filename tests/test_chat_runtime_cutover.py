from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from argus.api.main import app
from fastapi.testclient import TestClient


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/api/v1/dev/reset")
    return client


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
