"""Memory-mode Argus API on a UTC process clock with the New York clock frozen
at 20:17 EDT on 2026-09-09 (00:17 UTC on 2026-09-10).

Seeds one conversation per language, each holding a finalized buy-and-hold run
from 2024, so the command palette's run dossier offers "Retest with current
data". No provider key is set and no model or provider is called.

Usage: python frozen_backend.py <port> <seed.json>
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

os.environ.update(
    {
        "TZ": "UTC",
        "CUADRAO_PERSISTENCE_MODE": "memory",
        "ARGUS_DEV_MEMORY_FALLBACK": "true",
        "ARGUS_MARKET_DATA_PROVIDER_MODE": "synthetic_unit_fixture",
        "CUADRAO_CHECKPOINTER_MODE": "memory",
        "CUADRAO_MOCK_AUTH": "true",
        "NEXT_PUBLIC_MOCK_AUTH": "true",
        "ENABLE_MARKET_DATA_CACHE": "false",
        "ARGUS_BACKTEST_JOBS_SHADOW_ENABLED": "false",
        "ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED": "false",
        "ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED": "false",
        "ARGUS_CONTEXT_PACKETS_ENABLED": "false",
        "ARGUS_ENABLE_PERSONALIZATION_MEMORY": "",
        "ARGUS_ENABLE_MEMORY_SEMANTIC_RECALL": "",
        "ARGUS_RESEARCH_RAIL_ENABLED": "",
        "OPENROUTER_API_KEY": "",
        "OPENAI_API_KEY": "",
        "ANTHROPIC_API_KEY": "",
        "ALPACA_API_KEY": "",
        "ALPACA_SECRET_KEY": "",
        "PERPLEXITY_API_KEY": "",
        "DATABASE_URL": "",
    }
)
time.tzset()

import uvicorn  # noqa: E402
from argus.api import state as api_state  # noqa: E402
from argus.api.chat.evidence import finalize_completed_backtest  # noqa: E402
from argus.api.chat.persistence import build_runtime_backtest_run  # noqa: E402
from argus.api.main import app  # noqa: E402
from argus.api.message_store import create_message  # noqa: E402
from argus.domain.engine_launch.adapter import run_launch_backtest  # noqa: E402
from argus.domain.engine_launch.models import LaunchBacktestRequest  # noqa: E402
from argus.domain.market_data import new_york_clock  # noqa: E402
from argus.domain.market_data.capabilities import EASTERN  # noqa: E402
from argus.domain.run_dossiers import project_retest_action  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

FROZEN_AT = datetime(2026, 9, 9, 20, 17, tzinfo=EASTERN)


class _Frozen(datetime):
    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        if tz is not None:
            return FROZEN_AT.astimezone(tz)
        return FROZEN_AT.astimezone(timezone.utc).replace(tzinfo=None)


new_york_clock.datetime = _Frozen

port = int(sys.argv[1])
out_path = sys.argv[2]
client = TestClient(app)
user_id = str(client.get("/api/v1/me").json()["user"]["id"])


def seed(symbol: str, language: str) -> dict[str, object]:
    conversation_id = str(
        client.post("/api/v1/conversations", json={"language": language}).json()[
            "conversation"
        ]["id"]
    )
    launch = run_launch_backtest(
        LaunchBacktestRequest.model_validate(
            {
                "strategy_type": "buy_and_hold",
                "symbol": symbol,
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
            }
        )
    )
    built = build_runtime_backtest_run(
        user_id=user_id,
        conversation_id=conversation_id,
        result_card=launch.result_card,
        envelope=launch.envelope.model_dump(mode="python"),
        default_benchmark_func=lambda _asset_class, _symbols: "SPY",
    )
    finalized = finalize_completed_backtest(
        user_id=user_id,
        conversation_id=conversation_id,
        run=built,
        execution_identity=f"frozen-clock-proof:{built.id}",
    )
    run = api_state.store.backtest_runs[finalized.run.id]
    # A conversation with no messages opens as a new chat, so the source
    # conversation carries the turn that produced its run.
    create_message(
        user_id=user_id,
        conversation_id=conversation_id,
        role="user",
        content=f"Buy and hold {symbol} through 2024 with $10,000.",
        metadata={},
    )
    create_message(
        user_id=user_id,
        conversation_id=conversation_id,
        role="assistant",
        content=str(run.conversation_result_card.get("title") or symbol),
        metadata={},
    )
    retest = project_retest_action(run=run.model_dump(mode="python"))
    return {
        "symbol": symbol,
        "conversation_id": conversation_id,
        "run_id": run.id,
        "run_window": ["2024-01-01", "2024-12-31"],
        "retest_action_state": None if retest is None else retest.state,
    }


seeded = {"en": seed("TSLA", "en"), "es-419": seed("NVDA", "es-419")}
with open(out_path, "w", encoding="utf-8") as handle:
    json.dump(
        {
            "frozen_at": FROZEN_AT.isoformat(),
            "process_tz": os.environ["TZ"],
            "host_date": str(datetime.now().date()),
            "new_york_date": str(new_york_clock.new_york_today()),
            "conversations": seeded,
        },
        handle,
        indent=2,
    )

uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
