"""Local-only replay: confirmation card turns built by the real card builder.

Memory persistence, mock auth and the synthetic market-data fixture. Keys
ending in `_API_KEY` or starting with OPENROUTER, PERPLEXITY, ALPACA or RESEND,
DATABASE_URL and SUPABASE_SERVICE_ROLE_KEY are removed from this process before
Argus imports; Argus still loads a repository-root `.env` at import without
overriding set values. Provider and database access are not recorded.

Card turns are seeded through `create_message` with empty content, as the chat
route persists them at the running head, and with the card, its payload and one
confirmation reference as both the active reference and the only artifact
reference. The legacy conversation stores the English summary sentence as
content, as `summary` on the card and inside that reference.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

# The repository root, wherever this script lives inside it.
ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "pyproject.toml").is_file() and (parent / "src" / "argus").is_dir()
)
sys.path.insert(0, str(ROOT / "src"))

API_PORT = int(os.getenv("REPLAY_API_PORT", "8593"))
WEB_PORT = int(os.getenv("REPLAY_WEB_PORT", "3293"))
LANGUAGE = os.getenv("REPLAY_LANGUAGE", "es-419")
WEB_ORIGIN = f"http://127.0.0.1:{WEB_PORT}"

for key in list(os.environ):
    if (
        key.endswith("_API_KEY")
        or key.startswith(("OPENROUTER", "PERPLEXITY", "ALPACA", "RESEND"))
        or key in {"DATABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"}
    ):
        os.environ.pop(key)

os.environ.update(
    {
        "CUADRAO_PERSISTENCE_MODE": "memory",
        "ARGUS_DEV_MEMORY_FALLBACK": "true",
        "CUADRAO_CHECKPOINTER_MODE": "memory",
        "CUADRAO_MOCK_AUTH": "true",
        "ARGUS_MARKET_DATA_PROVIDER_MODE": "synthetic_unit_fixture",
        "ARGUS_IN_PLACE_CARD_EDITS_ENABLED": "true",
        "CUADRAO_CORS_ALLOW_ORIGINS": f"{WEB_ORIGIN},http://localhost:{WEB_PORT}",
        "ARGUS_APP_ORIGIN": WEB_ORIGIN,
        "ARGUS_BACKTEST_JOBS_SHADOW_ENABLED": "false",
        "ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED": "false",
        "ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED": "false",
    }
)

from argus.agent_runtime.confirmation_artifacts import (  # noqa: E402
    confirmation_artifact_reference,
)
from argus.api import state as api_state  # noqa: E402
from argus.api.chat.confirmation import runtime_confirmation_card  # noqa: E402
from argus.api.main import app  # noqa: E402
from argus.api.message_store import create_message  # noqa: E402
from argus.api.schemas import Conversation  # noqa: E402
from argus.domain.store import utcnow  # noqa: E402

DATE_RANGE = {"start": "2024-01-02", "end": "2024-12-31"}
COVERAGE = {
    "outcome": "full_coverage",
    "requested_date_range": DATE_RANGE,
    "effective_date_range": DATE_RANGE,
    "preflight_id": "sha256:replay-coverage",
}
LEGACY_SENTENCE = (
    "Ready to test buy-and-hold for AAPL over "
    "2 de enero de 2024 al 31 de diciembre de 2024."
)


def _payload(
    confirmation_id: str,
    *,
    symbol: str,
    strategy: dict[str, Any],
    launch: dict[str, Any],
) -> dict[str, Any]:
    base_strategy = {
        "asset_universe": [symbol],
        "asset_class": "equity",
        "timeframe": "1D",
        "date_range": DATE_RANGE,
        "sizing_mode": "capital_amount",
        "comparison_baseline": "SPY",
    }
    base_launch = {
        "symbol": symbol,
        "symbols": [symbol],
        "asset_class": "equity",
        "timeframe": "1D",
        "date_range": DATE_RANGE,
        "requested_date_range": DATE_RANGE,
        "coverage_preflight": COVERAGE,
        "sizing_mode": "capital_amount",
        "parameters": {},
        "risk_rules": [],
        "benchmark_symbol": "SPY",
        "language": LANGUAGE,
    }
    return {
        "confirmation_id": confirmation_id,
        "artifact_id": confirmation_id,
        "strategy": {**base_strategy, **strategy},
        "optional_parameters": {},
        "launch_payload": {**base_launch, **launch},
        "validation": {"status": "ready_to_run", "executable": True},
    }


def _buy_and_hold(confirmation_id: str) -> dict[str, Any]:
    return _payload(
        confirmation_id,
        symbol="AAPL",
        strategy={"strategy_type": "buy_and_hold", "capital_amount": 10000},
        launch={"strategy_type": "buy_and_hold", "capital_amount": 10000},
    )


SHAPES: list[dict[str, Any]] = [
    {
        "shape": "buy_and_hold",
        "conversation_id": "00000000-0000-4000-8000-000000009301",
        "user_text": "Compra y mantén AAPL durante 2024 con 10000 dólares",
        "payload": _buy_and_hold("00000000-0000-4000-8000-000000009311"),
    },
    {
        "shape": "recurring_buys",
        "conversation_id": "00000000-0000-4000-8000-000000009302",
        "user_text": "Invierte 500 dólares cada mes en AAPL durante 2024",
        "payload": _payload(
            "00000000-0000-4000-8000-000000009312",
            symbol="AAPL",
            strategy={
                "strategy_type": "dca_accumulation",
                "cadence": "monthly",
                "capital_amount": 500,
            },
            launch={
                "strategy_type": "dca_accumulation",
                "cadence": "monthly",
                "capital_amount": 500,
            },
        ),
    },
    {
        "shape": "rsi_threshold",
        "conversation_id": "00000000-0000-4000-8000-000000009303",
        "user_text": "Compra TSLA cuando el RSI baje de 30 y vende arriba de 70",
        "payload": _payload(
            "00000000-0000-4000-8000-000000009313",
            symbol="TSLA",
            strategy={
                "strategy_type": "indicator_threshold",
                "strategy_thesis": "Buy TSLA when RSI falls below 30 and sell above 70.",
                "capital_amount": 10000,
                "extra_parameters": {
                    "indicator_parameters": {
                        "indicator": "rsi",
                        "indicator_period": 14,
                        "entry_threshold": 30,
                        "exit_threshold": 70,
                    }
                },
            },
            launch={
                "strategy_type": "indicator_threshold",
                "capital_amount": 10000,
                "entry_rule": {
                    "indicator": "rsi",
                    "operator": "below",
                    "period": 14,
                    "threshold": 30.0,
                },
                "exit_rule": {
                    "indicator": "rsi",
                    "operator": "above",
                    "period": 14,
                    "threshold": 70.0,
                },
            },
        ),
    },
    {
        "shape": "legacy_buy_and_hold",
        "conversation_id": "00000000-0000-4000-8000-000000009304",
        "user_text": "Compra y mantén AAPL durante 2024 con 10000 dólares",
        "payload": _buy_and_hold("00000000-0000-4000-8000-000000009314"),
        "legacy_sentence": LEGACY_SENTENCE,
    },
]


def _seed() -> list[dict[str, Any]]:
    store = api_state.store
    user = store.get_or_create_dev_user()
    store.users[user.id] = user.model_copy(
        update={"language": LANGUAGE, "locale": LANGUAGE}
    )
    manifest: list[dict[str, Any]] = []
    now = utcnow()
    for offset, shape in enumerate(SHAPES):
        conversation_id = shape["conversation_id"]
        created = now - timedelta(minutes=10 - offset)
        store.conversation_owners[conversation_id] = user.id
        store.conversations[conversation_id] = Conversation(
            id=conversation_id,
            title=f"Replay {shape['shape']}",
            title_source="ai_generated",
            language=LANGUAGE,
            created_at=created,
            updated_at=created,
        )
        store.messages.setdefault(conversation_id, [])
        create_message(
            user_id=user.id,
            conversation_id=conversation_id,
            role="user",
            content=shape["user_text"],
        )
        payload = shape["payload"]
        card = runtime_confirmation_card(
            {"stage_outcome": "await_approval", "confirmation_payload": payload},
            confirmation_id=payload["confirmation_id"],
            conversation_id=conversation_id,
            language=LANGUAGE,
        )
        assert card is not None
        legacy_sentence = shape.get("legacy_sentence")
        content = ""
        if legacy_sentence:
            card = {**card, "summary": legacy_sentence}
            content = legacy_sentence
        reference = confirmation_artifact_reference(
            confirmation_id=payload["confirmation_id"],
            confirmation_payload=payload,
            confirmation_card=card,
        ).model_dump(mode="python")
        create_message(
            user_id=user.id,
            conversation_id=conversation_id,
            role="assistant",
            content=content,
            metadata={
                "conversation_mode": "confirm",
                "agent_runtime_stage_outcome": "await_approval",
                "confirmation_card": card,
                "confirmation_payload": payload,
                "active_confirmation_reference": reference,
                "artifact_references": [reference],
            },
        )
        manifest.append(
            {
                "shape": shape["shape"],
                "conversation_id": conversation_id,
                "confirmation_id": payload["confirmation_id"],
                "strategy_type": card.get("strategy_type"),
                "stored_content": content,
                "stored_card_has_summary": "summary" in card,
            }
        )
    return manifest


MANIFEST = _seed()

if __name__ == "__main__":
    import uvicorn

    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain", "--", "src", "web"], cwd=ROOT, text=True
    ).strip()
    record = {
        "head": head,
        "working_tree_changes_under_src_or_web": bool(dirty),
        "language": LANGUAGE,
        "api_port": API_PORT,
        "web_origin": WEB_ORIGIN,
        "conversations": MANIFEST,
    }
    (ROOT / "temp" / "replay-manifest.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False)
    )
    print(json.dumps(record, ensure_ascii=False))
    uvicorn.run(app, host="127.0.0.1", port=API_PORT)
