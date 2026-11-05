"""One live turn after a stored result, through the app's own runtime path.

Builds the workflow with argus.api.state.build_agent_runtime_workflow, hands it
the stored DOCN buy-and-hold result the local app saved, asks one question
about it, and records every OpenRouter call's prompt tokens and cost plus the
research invoice. Keys come from AFTER_RESULT_ENV_FILE, read and never written.
Both provider modes are assigned outright because that file pins synthetic data.

Usage: after_result_turn_cost.py <label> <messages.json> <out.json>
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

TREE = Path(os.environ["AFTER_RESULT_TREE"]).resolve()
sys.path.insert(0, str(TREE / "src"))
load_dotenv(os.environ["AFTER_RESULT_ENV_FILE"], override=False)
os.environ.update(
    {
        "CUADRAO_PERSISTENCE_MODE": "memory",
        "ARGUS_DEV_MEMORY_FALLBACK": "true",
        "CUADRAO_CHECKPOINTER_MODE": "memory",
        "ARGUS_MARKET_DATA_PROVIDER_MODE": "live_provider",
        "ARGUS_ASSET_PROVIDER_MODE": "live_provider",
        "ARGUS_RESEARCH_RAIL_ENABLED": "true",
        "ARGUS_ENABLE_PERSONALIZATION_MEMORY": "false",
        "ARGUS_BACKTEST_JOBS_SHADOW_ENABLED": "false",
        "ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED": "false",
        "ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED": "false",
        "CUADRAO_APPROVAL_EMAIL_SMTP_PASSWORD": "",
        "ENABLE_MARKET_DATA_CACHE": "false",
        "DATABASE_URL": "",
        "POSTHOG_PROJECT_TOKEN": "",
    }
)
LABEL, MESSAGES_PATH, OUT_PATH = sys.argv[1:4]
QUESTION = "Why did it fall so much along the way?"

from langgraph.checkpoint.memory import MemorySaver  # noqa: E402

from argus.agent_runtime.runtime import run_agent_turn  # noqa: E402
from argus.agent_runtime.state.models import (  # noqa: E402
    ArtifactReference,
    TaskSnapshot,
    UserState,
)
from argus.api.state import build_agent_runtime_workflow  # noqa: E402
from argus.llm import openrouter  # noqa: E402


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=TREE, capture_output=True, text=True, check=False
    ).stdout.strip()


async def main() -> None:
    items = json.loads(Path(MESSAGES_PATH).read_text())["items"]
    index = next(
        i for i, message in enumerate(items) if (message.get("metadata") or {}).get("result_fact_bank")
    )
    metadata = items[index]["metadata"]["result_fact_bank"]
    history = [
        {"role": message["role"], "content": message.get("content") or ""}
        for message in items[: index + 1]
    ]
    reference = ArtifactReference(
        artifact_kind="backtest_result",
        artifact_id=str(metadata["run_id"]),
        artifact_status="completed",
        metadata=metadata,
    )
    workflow = build_agent_runtime_workflow(checkpointer=MemorySaver())
    openrouter.clear_openrouter_route_receipts()
    result = await run_agent_turn(
        workflow=workflow,
        user=UserState(user_id="after-result-cost", language_preference="en"),
        thread_id=f"after-result-cost-{LABEL}",
        message=QUESTION,
        recent_thread_history=history,
        fallback_latest_task_snapshot=TaskSnapshot(
            latest_task_type="results_explanation",
            completed=True,
            latest_backtest_result_reference=reference,
        ),
        fallback_selected_thread_metadata={
            "latest_task_type": "results_explanation",
            "last_stage_outcome": "ready_to_respond",
        },
    )
    calls = []
    for receipt in openrouter.get_openrouter_route_receipts():
        fields = receipt.as_dict()
        usage = fields.get("token_usage") or {}
        calls.append(
            {
                "task": fields.get("task"),
                "model": fields.get("model"),
                "outcome": fields.get("outcome"),
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "usage_cost_usd": fields.get("usage_cost_usd"),
                "latency_ms": fields.get("latency_ms"),
            }
        )
    research_usage = (result.get("research") or {}).get("usage") or {}
    openrouter_cost = sum(call["usage_cost_usd"] or 0 for call in calls)
    record = {
        "label": LABEL,
        "git_head": _git("rev-parse", "HEAD"),
        "git_status": _git("status", "--porcelain"),
        "latest_result_context_module_loaded": (
            "argus.agent_runtime.interpreter.latest_result_context" in sys.modules
        ),
        "question": QUESTION,
        "stored_result_chars": len(json.dumps(metadata, default=str)),
        "stage_outcome": result.get("stage_outcome"),
        "answer": (result.get("assistant_response") or "")[:2000],
        "suggested_questions": (result.get("suggested_questions") or {}).get("questions"),
        "sources": len((result.get("research") or {}).get("sources") or []),
        "openrouter_calls": calls,
        "interpretation_prompt_tokens": [
            call["prompt_tokens"] for call in calls if call["task"] == "interpretation"
        ],
        "interpretation_cost_usd": round(
            sum(call["usage_cost_usd"] or 0 for call in calls if call["task"] == "interpretation"), 6
        ),
        "openrouter_cost_usd": round(openrouter_cost, 6),
        "research_cost_usd": research_usage.get("cost_usd"),
        "turn_cost_usd": round(openrouter_cost + (research_usage.get("cost_usd") or 0), 6),
        "unpriced_openrouter_calls": sum(
            1 for call in calls if call["usage_cost_usd"] is None and call["outcome"] == "succeeded"
        ),
    }
    Path(OUT_PATH).write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({key: record[key] for key in record if key not in {"answer", "openrouter_calls"}}, indent=2))


asyncio.run(main())
