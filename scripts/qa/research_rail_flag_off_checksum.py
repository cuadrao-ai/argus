"""Flag-off byte-identity harness for the research rail.

Runs a fixed set of deterministic chat turns through the real HTTP stream
surface with ARGUS_RESEARCH_RAIL_ENABLED off, then emits one SHA-256 over the
canonicalized stream frames and persisted transcripts. Run it from a checkout
of the baseline commit and from the lane head; equal digests prove flag-off
behavior is byte-identical across the change (volatile identifiers and
timestamps are canonicalized, everything else is compared exactly).

Usage: .venv/bin/python scripts/qa/research_rail_flag_off_checksum.py
The script resolves ``argus`` from the current working directory's ``src``,
so the same file can be dropped into the baseline worktree unchanged.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

os.environ.update(
    {
        "ARGUS_RESEARCH_RAIL_ENABLED": "false",
        "ARGUS_MARKET_DATA_PROVIDER_MODE": "synthetic_unit_fixture",
        "ARGUS_ASSET_PROVIDER_MODE": "synthetic_unit_fixture",
        "CUADRAO_PERSISTENCE_MODE": "memory",
        "CUADRAO_CHECKPOINTER_MODE": "memory",
        "ARGUS_DEV_MEMORY_FALLBACK": "true",
        "CUADRAO_MOCK_AUTH": "true",
        "NEXT_PUBLIC_MOCK_AUTH": "true",
        "ARGUS_CONTEXT_PACKETS_ENABLED": "false",
        "ARGUS_GROUNDED_DISCOVERY_ENABLED": "false",
        "CUADRAO_RUNTIME_STREAM_WORKER": "off",
        "OPENROUTER_API_KEY": "",
        "ALPACA_API_KEY": "",
        "ALPACA_SECRET_KEY": "",
        "PERPLEXITY_API_KEY": "",
    }
)
sys.path.insert(0, str(Path.cwd() / "src"))

VOLATILE_KEYS = {
    "id",
    "message_id",
    "request_id",
    "conversation_id",
    "turn_id",
    "request_message_id",
    "confirmation_id",
    "artifact_id",
    "confirmation_message_id",
    "created_at",
    "updated_at",
    "retrieved_at",
    "queued_at",
    "started_at",
    "finished_at",
    "expires_at",
    "timestamp",
    "preflight_id",
    "launch_payload_hash",
    "canonical_launch_payload_hash",
    "thread_id",
    "checkpoint_id",
    "period_start",
    "period_end",
    "resets_at",
}


def canonical(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: ("<VOLATILE>" if key in VOLATILE_KEYS else canonical(item))
            for key, item in sorted(value.items())
        }
    if isinstance(value, list):
        return [canonical(item) for item in value]
    return value


def stream_frames(raw: str) -> list[Any]:
    frames: list[Any] = []
    for part in raw.split("\n\n"):
        for line in part.splitlines():
            if not line.startswith("data: "):
                continue
            body = line.removeprefix("data: ").strip()
            if body == "[DONE]":
                frames.append("[DONE]")
                continue
            try:
                frames.append(canonical(json.loads(body)))
            except ValueError:
                frames.append(body)
    return frames


def main() -> None:
    from argus.agent_runtime.capabilities.contract import (
        build_default_capability_contract,
    )
    from argus.agent_runtime.graph.workflow import build_workflow
    from argus.agent_runtime.stages.interpret_types import StructuredInterpretation
    from argus.agent_runtime.state.models import StrategySummary
    from argus.api import state as api_state
    from argus.api.main import app
    from fastapi.testclient import TestClient

    class DeterministicInterpreter:
        """Typed interpretations keyed by the turn script, no LLM anywhere."""

        def __call__(self, request: Any) -> StructuredInterpretation | None:
            message = request.current_user_message
            if message.startswith("EDU"):
                return StructuredInterpretation(
                    intent="beginner_guidance",
                    task_relation="new_task",
                    user_goal_summary="educational question",
                    semantic_turn_act="educational_question",
                    requires_clarification=False,
                    candidate_strategy_draft=StrategySummary(),
                    assistant_response="A drawdown is the drop from a peak.",
                )
            if message.startswith("STATS"):
                return StructuredInterpretation(
                    intent="unsupported_or_out_of_scope",
                    task_relation="new_task",
                    user_goal_summary="stats question",
                    semantic_turn_act="unsupported_request",
                    requires_clarification=False,
                    candidate_strategy_draft=StrategySummary(
                        asset_universe=["SPY"], asset_class="equity"
                    ),
                )
            return StructuredInterpretation(
                intent="conversation_followup",
                task_relation="continue",
                user_goal_summary="followup",
                semantic_turn_act="new_idea",
                requires_clarification=False,
                candidate_strategy_draft=StrategySummary(),
                assistant_response="Tell me more about the idea.",
            )

    client = TestClient(app)
    client.post("/api/v1/dev/reset")
    checkpointer = api_state.build_agent_runtime_checkpointer()
    workflow = build_workflow(
        contract=build_default_capability_contract(),
        structured_interpreter=DeterministicInterpreter(),
        checkpointer=checkpointer,
    )
    app.state.agent_runtime_checkpointer = checkpointer
    app.state.agent_workflow = workflow

    conversation = client.post("/api/v1/conversations", json={}).json()[
        "conversation"
    ]
    turns = [
        "EDU what is a drawdown?",
        "STATS how has the S&P 500 performed lately?",
        "PLAIN let's think about an idea",
    ]
    observed: list[Any] = []
    for message in turns:
        response = client.post(
            "/api/v1/chat/stream",
            json={"conversation_id": conversation["id"], "message": message},
        )
        observed.append(
            {
                "turn": message,
                "status": response.status_code,
                "frames": stream_frames(response.text),
            }
        )
    transcript = client.get(
        f"/api/v1/conversations/{conversation['id']}/messages"
    ).json()
    observed.append({"transcript": canonical(transcript)})
    usage = client.get("/api/v1/me/usage").json()
    observed.append({"usage": canonical(usage)})

    serialized = json.dumps(observed, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(serialized.encode()).hexdigest()
    print(json.dumps({"digest": digest, "turns": len(turns)}, indent=2))
    out = Path(os.environ.get("RAIL_CHECKSUM_OUT", "flag_off_checksum.json"))
    out.write_text(
        json.dumps({"digest": digest, "observed": observed}, indent=2, sort_keys=True)
    )


if __name__ == "__main__":
    main()
