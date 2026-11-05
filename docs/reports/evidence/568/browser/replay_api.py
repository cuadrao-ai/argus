"""Local-only browser replay for a withheld research answer (PR #568).

Seeds the memory-persistence API with the recorded Banco Popular probe
(docs/reports/evidence/545/probes/domain_filtered_local_source.json) composed
through the rail's real seam, once per language. No model, provider, or
hosted database is touched: the page only hydrates a persisted conversation,
which is the same path a reload takes in production.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

TREE = Path(os.environ["PR568_QA_TREE"]).resolve()
sys.path.insert(0, str(TREE / "src"))

WEB_PORT = int(os.getenv("PR568_QA_WEB_PORT", "3568"))
API_PORT = int(os.getenv("PR568_QA_API_PORT", "8568"))
WEB_ORIGIN = f"http://127.0.0.1:{WEB_PORT}"

os.environ.update(
    {
        "CUADRAO_PERSISTENCE_MODE": "memory",
        "ARGUS_DEV_MEMORY_FALLBACK": "true",
        "CUADRAO_CHECKPOINTER_MODE": "memory",
        "CUADRAO_MOCK_AUTH": "true",
        "ARGUS_MARKET_DATA_PROVIDER_MODE": "synthetic_unit_fixture",
        "ARGUS_RESEARCH_RAIL_ENABLED": "true",
        "CUADRAO_CORS_ALLOW_ORIGINS": f"{WEB_ORIGIN},http://localhost:{WEB_PORT}",
        "ARGUS_APP_ORIGIN": WEB_ORIGIN,
        "ARGUS_BACKTEST_JOBS_SHADOW_ENABLED": "false",
        "ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED": "false",
        "ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED": "false",
        "DATABASE_URL": "",
        # A parent .env must not lend the replay any provider credential.
        "OPENROUTER_API_KEY": "",
        "OPENAI_API_KEY": "",
        "ANTHROPIC_API_KEY": "",
        "PERPLEXITY_API_KEY": "",
        "ALPACA_API_KEY": "",
        "ALPACA_SECRET_KEY": "",
    }
)

from argus.agent_runtime import research_grounded as grounded  # noqa: E402
from argus.agent_runtime.stages.interpret_types import (  # noqa: E402
    StructuredInterpretation,
)
from argus.agent_runtime.state.models import StrategySummary, UserState  # noqa: E402
from argus.api import state as api_state  # noqa: E402
from argus.api.main import app  # noqa: E402
from argus.api.message_store import memory_conversation, memory_message  # noqa: E402
from argus.domain.research.perplexity_agent import _packet_from_response  # noqa: E402

RECORDING = TREE / "docs/reports/evidence/545/probes/domain_filtered_local_source.json"
QUESTION = (
    "¿Qué tasa de interés paga hoy el Banco Popular Dominicano por un "
    "certificado financiero a un año en pesos?"
)
IDS_FILE = Path(os.getenv("PR568_QA_IDS_FILE", "/dev/null"))


def _composed(language: str) -> tuple[str, dict]:
    recorded = json.loads(RECORDING.read_text())["exchanges"][-1]["response"]
    packet = _packet_from_response(recorded, latency_ms=1, on_unpriced=lambda _: None)
    interpretation = StructuredInterpretation(
        intent="unsupported_or_out_of_scope",
        task_relation="new_task",
        user_goal_summary="question",
        semantic_turn_act="educational_question",
        requires_clarification=False,
        candidate_strategy_draft=StrategySummary(),
    )
    result = grounded._packet_stage_result(
        packet=packet,
        subjects=[],
        shape="balanced",
        capability_class="balanced_lookup",
        language=language,
        interpretation=interpretation,
        user=UserState(user_id="replay", language_preference=language),
        cache_status="miss",
        question_kind="current_external",
        # The recording's own capture date, so the period filter sees what
        # the live turn saw.
        question_as_of_date=date(2026, 9, 9),
    )
    patch = result.stage_patch
    return patch["assistant_response"], {
        "conversation_mode": "guide",
        "research": patch["research"],
    }


def _seed() -> dict[str, str]:
    user = api_state.store.get_or_create_dev_user()
    ids: dict[str, str] = {}
    for language in ("en", "es-419"):
        conversation = memory_conversation(
            title="Banco Popular certificate rate",
            title_source="ai_generated",
            language=language,
            user_id=user.id,
        )
        memory_message(conversation_id=conversation.id, role="user", content=QUESTION)
        answer, metadata = _composed(language)
        memory_message(
            conversation_id=conversation.id,
            role="assistant",
            content=answer,
            metadata=metadata,
        )
        ids[language] = conversation.id
    return ids


_IDS = _seed()
if IDS_FILE != Path("/dev/null"):
    IDS_FILE.write_text(json.dumps(_IDS))

if __name__ == "__main__":
    import uvicorn

    print(
        json.dumps(
            {
                "tree": str(TREE),
                "web_origin": WEB_ORIGIN,
                "api_port": API_PORT,
                "recorded_source": str(RECORDING.relative_to(TREE)),
                "conversations": _IDS,
                "provider_calls": 0,
                "hosted_database_reads_or_writes": 0,
            }
        ),
        flush=True,
    )
    uvicorn.run(app, host="127.0.0.1", port=API_PORT, log_level="warning")
