"""Local-only browser replay for the publisher honesty lane (#579, #580).

Seeds the memory-persistence API with two research turns per language, each
composed through the rail's inline entry (``grounded_result``) with the
question clock frozen at 20:17 in New York (00:17 UTC on 2026-09-10), after
the close:

- "how much did the S&P 500 move this week?". The provider response behind
  the recorded turn (open-the-gates/after/argus-spx-week.json) was not kept,
  so it is rebuilt from that transcript's own answer and twelve typed rows:
  the two pages the rows cite are its search results, each dated 2026-09-09
  as #579 records; the SPY price row cites the provider's own finance page,
  which parsing scrubs to the null the transcript shows; the invoice is zero.
- A zero-retrieval answer: the recorded response in
  377/probes/equity_control_quote.json, which called no tool, asked as a live
  quote on Apple. Its request was not kept; the user message matches what the
  recorded answer replies to.

The Spanish conversations reuse the English S&P prose the provider wrote, so
what they prove is what Argus writes: the drawer, its button, and the note.
No model, provider, or hosted database is touched; the page only hydrates the
persisted conversations, the path a reload takes in production.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

TREE = Path(os.environ["PH_QA_TREE"]).resolve()
sys.path.insert(0, str(TREE / "src"))

API_PORT = int(os.getenv("PH_QA_API_PORT", "8591"))
WEB_PORT = int(os.getenv("PH_QA_WEB_PORT", "3591"))
WEB_ORIGIN = f"http://127.0.0.1:{WEB_PORT}"
IDS_FILE = Path(os.getenv("PH_QA_IDS_FILE", "/dev/null"))
EVIDENCE = TREE / "docs/reports/evidence"
SPX_TRANSCRIPT = EVIDENCE / "open-the-gates/after/argus-spx-week.json"
ZERO_TOOL_RECORDING = EVIDENCE / "377/probes/equity_control_quote.json"
# 20:17 in New York on 2026-09-09.
ASKED_AT = datetime(2026, 9, 10, 0, 17, tzinfo=timezone.utc)
CITED_PAGE_DATE = "2026-09-09"
PROVIDER_FINANCE_PAGE = "https://www.perplexity.ai/finance/SPY"
ROW_KEYS = ("subject", "symbol", "label", "value", "kind", "unit", "as_of", "source_url")
QUESTIONS = {
    "spx": {
        "en": "how much did the S&P 500 move this week?",
        "es-419": "¿Cuánto se movió el S&P 500 esta semana?",
    },
    "not_grounded": {
        "en": "What was Apple's latest closing price?",
        "es-419": "¿Cuál fue el último precio de cierre de Apple?",
    },
}
ZERO_INVOICE = {
    "cost": {
        "currency": "USD",
        "input_cost": 0.0,
        "output_cost": 0.0,
        "cache_creation_cost": 0.0,
        "cache_read_cost": 0.0,
        "tool_calls_cost": 0.0,
        "total_cost": 0.0,
    },
    "input_tokens": 0,
    "input_tokens_details": {
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "cached_tokens": 0,
    },
    "output_tokens": 0,
    "output_tokens_details": {"reasoning_tokens": 0},
    "total_tokens": 0,
}

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
        "ARGUS_ENABLE_PERSONALIZATION_MEMORY": "false",
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

import httpx  # noqa: E402
from argus.agent_runtime import research_grounded as grounded  # noqa: E402
from argus.agent_runtime.research_query import ResearchQueryExtraction  # noqa: E402
from argus.agent_runtime.stages.interpret_types import (  # noqa: E402
    StructuredInterpretation,
)
from argus.agent_runtime.state.models import (  # noqa: E402
    RunState,
    StrategySummary,
    UserState,
)
from argus.api import state as api_state  # noqa: E402
from argus.api.main import app  # noqa: E402
from argus.api.message_store import memory_conversation, memory_message  # noqa: E402
from argus.domain.research import source_selection  # noqa: E402
from argus.domain.research.perplexity_agent import PerplexityAgentClient  # noqa: E402


class _AfterTheClose(datetime):
    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        return (
            ASKED_AT.astimezone(tz) if tz is not None else ASKED_AT.replace(tzinfo=None)
        )


source_selection.datetime = _AfterTheClose


def _spx_response() -> dict:
    summary = json.loads(SPX_TRANSCRIPT.read_text())["summary"]
    cited = list(
        dict.fromkeys(row["source_url"] for row in summary["rows"] if row["source_url"])
    )
    rows = [
        {
            **{key: row[key] for key in ROW_KEYS},
            "source_url": row["source_url"] or PROVIDER_FINANCE_PAGE,
        }
        for row in summary["rows"]
    ]
    text = json.dumps({"answer_markdown": summary["assistant_text"], "rows": rows})
    return {
        "id": "resp_rebuilt_spx_week",
        "model": "openai/gpt-5.6-sol",
        "output": [
            {"type": "skill_loaded", "name": "finance"},
            {
                "type": "finance_results",
                "categories": ["quote"],
                "tickers": ["SPY"],
                "results": [
                    {
                        "category": "quote",
                        "content": "SPY quote",
                        "sources": [PROVIDER_FINANCE_PAGE],
                        "tickers": ["SPY"],
                    }
                ],
            },
            {
                "type": "search_results",
                "results": [{"url": url, "date": CITED_PAGE_DATE} for url in cited],
            },
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            },
        ],
        "usage": ZERO_INVOICE,
    }


def _composed(
    *,
    response: dict,
    question: str,
    language: str,
    question_kind: str,
    subject: dict[str, str],
    period_of_interest: str | None,
) -> tuple[str, dict]:
    class _Replay(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=response)

    grounded._client = lambda: PerplexityAgentClient("replay", transport=_Replay())
    query = ResearchQueryExtraction(
        question_kind=question_kind,
        symbols=[subject["symbol"]],
        period_of_interest=period_of_interest,
    )
    interpretation = StructuredInterpretation(
        intent="unsupported_or_out_of_scope",
        task_relation="new_task",
        user_goal_summary="question",
        semantic_turn_act="educational_question",
        requires_clarification=False,
        candidate_strategy_draft=StrategySummary(),
    )
    result = asyncio.run(
        grounded.grounded_result(
            query=query,
            subjects=[subject],
            shape=grounded.shape_for_query(query),
            interpretation=interpretation,
            state=RunState.new(current_user_message=question, recent_thread_history=[]),
            user=UserState(user_id="replay", language_preference=language),
        )
    )
    patch = result.stage_patch
    metadata = {
        "conversation_mode": "guide",
        "agent_runtime_stage_outcome": result.outcome,
        "research": patch["research"],
    }
    if patch.get("next_experiments"):
        metadata["next_experiments"] = patch["next_experiments"]
    return patch["assistant_response"], metadata


def _seed() -> dict:
    user = api_state.store.get_or_create_dev_user()
    turns = {
        "spx": {
            "response": _spx_response(),
            "question_kind": "market_pulse",
            "subject": {
                "symbol": "SPY",
                "name": "SPDR S&P 500 ETF Trust",
                "asset_class": "equity",
            },
            "period_of_interest": "this week",
            "title": "S&P 500 this week",
        },
        "not_grounded": {
            "response": json.loads(ZERO_TOOL_RECORDING.read_text())["response"],
            "question_kind": "live_quote",
            "subject": {"symbol": "AAPL", "name": "Apple Inc.", "asset_class": "equity"},
            "period_of_interest": None,
            "title": "Apple latest close",
        },
    }
    conversations: dict[str, dict[str, str]] = {}
    composed: list[dict] = []
    for language in ("en", "es-419"):
        conversations[language] = {}
        for name, turn in turns.items():
            question = QUESTIONS[name][language]
            answer, metadata = _composed(
                response=turn["response"],
                question=question,
                language=language,
                question_kind=turn["question_kind"],
                subject=turn["subject"],
                period_of_interest=turn["period_of_interest"],
            )
            conversation = memory_conversation(
                title=turn["title"],
                title_source="ai_generated",
                language=language,
                user_id=user.id,
            )
            memory_message(conversation_id=conversation.id, role="user", content=question)
            memory_message(
                conversation_id=conversation.id,
                role="assistant",
                content=answer,
                metadata=metadata,
            )
            conversations[language][name] = conversation.id
            research = metadata["research"]
            composed.append(
                {
                    "turn": name,
                    "language": language,
                    "degraded": research.get("degraded"),
                    "sources": [
                        [source["domain"], source["source_date"]]
                        for source in research["sources"]
                    ],
                    "rows": len(research["rows"]),
                    "answer_head": answer[:120],
                }
            )
    head = subprocess.run(
        ["git", "-C", str(TREE), "rev-parse", "--short=8", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return {
        "meta": {
            "tree_head": head,
            "asked_at_utc": ASKED_AT.isoformat(),
            "question_date": source_selection.question_date().isoformat(),
            "composed": composed,
            "provider_calls": 0,
            "hosted_database_reads_or_writes": 0,
        },
        "conversations": conversations,
    }


SEED = _seed()
if IDS_FILE != Path("/dev/null"):
    IDS_FILE.write_text(json.dumps(SEED, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    import uvicorn

    print(json.dumps(SEED, ensure_ascii=False), flush=True)
    uvicorn.run(app, host="127.0.0.1", port=API_PORT, log_level="warning")
