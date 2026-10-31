from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from argus.api import state as api_state
from argus.api.chat.artifacts import result_fact_bank
from argus.api.chat.context_packets import (
    ContextPacketCollectionResult,
    collect_context_packet_result_for_completed_run,
    collect_context_packets_for_completed_run,
    enrich_run_with_context_packets,
)
from argus.api.chat.persistence import persist_runtime_backtest_run
from argus.api.schemas import BacktestRun, Conversation, User
from argus.context import (
    ContextPacket,
    build_alpaca_corporate_actions_packet,
    build_alpaca_market_movers_packet,
    build_alpaca_most_actives_packet,
    build_alpaca_news_packet,
    build_fred_macro_packet,
)
from argus.domain.backtest_finalization import (
    MemoryBacktestFinalizationGateway,
    PreparedBacktestFinalization,
)
from argus.domain.store import AlphaStore, utcnow


def _run() -> BacktestRun:
    return BacktestRun(
        id="run-1",
        conversation_id="conversation-1",
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
            "date_range": {"start": "2025-01-01", "end": "2025-12-31"},
        },
        conversation_result_card={
            "title": "AAPL Buy and Hold",
            "date_range": {"start": "2025-01-01", "end": "2025-12-31"},
            "rows": [],
            "assumptions": [],
        },
        created_at=utcnow(),
        chart=None,
        trades=[],
    )


def _user() -> User:
    return User(
        id="user-1",
        email="developer@argus.local",
        username="mock-developer",
        display_name="Mock Developer",
        created_at=utcnow(),
        updated_at=utcnow(),
    )


def _conversation() -> Conversation:
    return Conversation(
        id="conversation-1",
        title="New Chat",
        created_at=utcnow(),
        updated_at=utcnow(),
    )


def _fred_packet(series_id: str = "CPIAUCSL") -> ContextPacket:
    return build_fred_macro_packet(
        series_id=series_id,
        observations=[
            {"date": "2025-11-01", "value": "310.0"},
            {"date": "2025-12-01", "value": "311.5"},
        ],
        observation_start=date(2025, 1, 1),
        observation_end=date(2025, 12, 31),
    )


def test_collect_context_packets_uses_run_window_and_current_provider_scope(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ARGUS_CONTEXT_PACKETS_ENABLED", "true")
    run = _run()

    packets = collect_context_packets_for_completed_run(
        run,
        fred_series=("CPIAUCSL",),
        budget_seconds=2.0,
        fetch_fred_macro_packet_func=lambda **kwargs: _fred_packet(kwargs["series_id"]),
        fetch_alpaca_news_packet_func=lambda **kwargs: build_alpaca_news_packet(
            symbols=kwargs["symbols"],
            news_items=[
                {
                    "id": "news-1",
                    "headline": "Apple reports product update",
                    "symbols": ["AAPL"],
                    "created_at": "2025-12-01T00:00:00Z",
                }
            ],
            start=kwargs["start"],
            end=kwargs["end"],
        ),
        fetch_alpaca_corporate_actions_packet_func=(
            lambda **kwargs: build_alpaca_corporate_actions_packet(
                symbols=kwargs["symbols"],
                corporate_actions=[
                    {
                        "id": "action-1",
                        "symbol": "AAPL",
                        "type": "split",
                        "ex_date": "2025-06-01",
                    }
                ],
                start=kwargs["start"],
                end=kwargs["end"],
            )
        ),
        fetch_alpaca_market_movers_packet_func=(
            lambda **kwargs: build_alpaca_market_movers_packet(
                market_type=kwargs["market_type"],
                movers={"gainers": [{"symbol": "AAPL", "change": 1.2}]},
            )
        ),
        fetch_alpaca_most_actives_packet_func=(
            lambda **kwargs: build_alpaca_most_actives_packet(
                by=kwargs["by"],
                most_actives=[{"symbol": "AAPL", "volume": 123456}],
            )
        ),
    )

    packet_types = {packet.packet_type for packet in packets}
    assert packet_types == {
        "macro",
        "news",
        "corporate_actions",
        "market_movers",
        "most_actives",
    }
    assert all(packet.not_for == "simulation_truth" for packet in packets)


def test_context_packet_collection_skips_stale_packets_with_status(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ARGUS_CONTEXT_PACKETS_ENABLED", "true")
    stale_news = ContextPacket(
        provider="alpaca",
        packet_type="news",
        retrieved_at=datetime.now(timezone.utc) - timedelta(days=2),
        freshness="fresh",
    )

    result = collect_context_packet_result_for_completed_run(
        _run(),
        fred_series=(),
        budget_seconds=2.0,
        fetch_alpaca_news_packet_func=lambda **_: stale_news,
        fetch_alpaca_corporate_actions_packet_func=lambda **_: (_ for _ in ()).throw(
            RuntimeError("actions unavailable")
        ),
        fetch_alpaca_market_movers_packet_func=lambda **_: (_ for _ in ()).throw(
            RuntimeError("movers unavailable")
        ),
        fetch_alpaca_most_actives_packet_func=lambda **_: (_ for _ in ()).throw(
            RuntimeError("actives unavailable")
        ),
    )

    assert result.packets == []
    assert any(
        status["provider_task"] == "alpaca:news"
        and status["outcome"] == "stale"
        and status["packet_id"] == stale_news.id
        for status in result.statuses
    )
    assert {
        status["provider_task"]
        for status in result.statuses
        if status["outcome"] == "skipped"
    } == {
        "alpaca:corporate_actions",
        "alpaca:market_movers",
        "alpaca:most_actives",
    }


def test_enriched_run_records_context_collection_status_without_live_fetch() -> None:
    status = [
        {
            "provider_task": "alpaca:news",
            "outcome": "stale",
            "packet_id": "packet-1",
            "freshness": "stale",
        }
    ]

    enriched = enrich_run_with_context_packets(
        _run(),
        [],
        collection_status=status,
    )

    assert enriched.conversation_result_card["context_packets"] == []
    assert enriched.conversation_result_card["context_packet_ids"] == []
    assert enriched.conversation_result_card["context_collection_status"] == status


def test_enriched_run_replays_attached_context_packet_facts() -> None:
    enriched = enrich_run_with_context_packets(_run(), [_fred_packet()])
    fact_bank = result_fact_bank(enriched)

    assert enriched.conversation_result_card["context_packet_ids"]
    assert fact_bank["context_packets"][0]["provider"] == "fred"
    assert fact_bank["context_packets"][0]["not_for"] == "simulation_truth"


def test_checkpoint_context_detection_prefers_enriched_result_reference() -> None:
    from argus.agent_runtime.state.models import ArtifactReference, TaskSnapshot
    from argus.api.chat.recovery import (
        checkpoint_latest_result_has_context_packets,
        result_reference_has_context_packets,
    )

    stale_values = {
        "latest_task_snapshot": TaskSnapshot(
            latest_task_type="results_explanation",
            completed=True,
            latest_backtest_result_reference=ArtifactReference(
                artifact_kind="backtest_result",
                artifact_id="run-1",
                artifact_status="completed",
                metadata=result_fact_bank(_run()),
            ),
        )
    }
    enriched_reference = ArtifactReference(
        artifact_kind="backtest_result",
        artifact_id="run-1",
        artifact_status="completed",
        metadata=result_fact_bank(
            enrich_run_with_context_packets(_run(), [_fred_packet()])
        ),
    )

    assert checkpoint_latest_result_has_context_packets(stale_values) is False
    assert result_reference_has_context_packets(enriched_reference) is True


def test_persist_runtime_backtest_run_attaches_immutable_context_packets(
    monkeypatch,
) -> None:
    class Gateway:
        def __init__(self) -> None:
            self.runs: list[BacktestRun] = []
            self.packets: list[dict[str, Any]] = []
            self.attachments: list[dict[str, Any]] = []

        def finalize_backtest_completion(
            self,
            *,
            finalization: PreparedBacktestFinalization,
        ):
            finalized = MemoryBacktestFinalizationGateway(
                api_state.store
            ).finalize_backtest_completion(finalization=finalization)
            self.runs.append(finalized.run)
            return finalized

        def create_context_packet(
            self,
            *,
            user_id: str,
            packet: dict[str, Any],
        ) -> dict[str, Any]:
            del user_id
            self.packets.append(packet)
            return packet

        def attach_context_packet_to_run(
            self,
            *,
            user_id: str,
            attachment: dict[str, Any],
        ) -> dict[str, Any]:
            del user_id
            self.attachments.append(attachment)
            return attachment

    gateway = Gateway()
    monkeypatch.setattr(api_state, "store", AlphaStore())
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)
    monkeypatch.setattr(
        "argus.api.chat.persistence.collect_context_packet_result_for_completed_run",
        lambda run: ContextPacketCollectionResult(
            packets=[_fred_packet()],
            statuses=[],
        ),
    )

    run = persist_runtime_backtest_run(
        user=_user(),
        conversation=_conversation(),
        result_card={
            "title": "AAPL Buy and Hold",
            "rows": [],
            "assumptions": [],
        },
        envelope={
            "resolved_strategy": {
                "strategy_type": "buy_and_hold",
                "asset_universe": ["AAPL"],
            },
            "resolved_parameters": {
                "date_range": {"start": "2025-01-01", "end": "2025-12-31"},
                "benchmark_symbol": "SPY",
            },
            "metrics": {"aggregate": {"performance": {"total_return_pct": 12.0}}},
            "benchmark_metrics": {"benchmark_symbol": "SPY"},
            "provider_metadata": {
                "provider": "alpaca",
                "asset_class": "equity",
                "timeframe": "1D",
                "feed": "iex",
            },
        },
        execution_identity="backtest_job:context-packet-test",
    )

    assert run is not None
    assert run.config_snapshot["provider_metadata"] == {
        "provider": "alpaca",
        "asset_class": "equity",
        "timeframe": "1D",
        "feed": "iex",
    }
    assert gateway.runs[0].conversation_result_card["context_packets"]
    assert gateway.packets[0]["not_for"] == "simulation_truth"
    assert gateway.attachments[0]["run_id"] == run.id
    assert gateway.attachments[0]["immutable_snapshot"] is True

