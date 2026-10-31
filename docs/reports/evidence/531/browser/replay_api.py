"""Local-only browser replay for the persisted-result language contract.

Run this from the repository root. The seed is an already-recorded real
English-authored result; the process uses only memory persistence and performs
no model, provider, or hosted-database work.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path.cwd()
SOURCE_ROOT = Path(os.getenv("ISSUE531_QA_SOURCE_ROOT", str(ROOT))).resolve()
sys.path.insert(0, str(SOURCE_ROOT / "src"))

WEB_PORT = int(os.getenv("ISSUE531_QA_WEB_PORT", "3211"))
API_PORT = int(os.getenv("ISSUE531_QA_API_PORT", "8531"))
WEB_ORIGIN = f"http://127.0.0.1:{WEB_PORT}"

os.environ.update(
    {
        "CUADRAO_PERSISTENCE_MODE": "memory",
        "ARGUS_DEV_MEMORY_FALLBACK": "true",
        "CUADRAO_CHECKPOINTER_MODE": "memory",
        "CUADRAO_MOCK_AUTH": "true",
        "CUADRAO_CORS_ALLOW_ORIGINS": (
            f"{WEB_ORIGIN},http://localhost:{WEB_PORT}"
        ),
        "ARGUS_APP_ORIGIN": WEB_ORIGIN,
        "ARGUS_BACKTEST_JOBS_SHADOW_ENABLED": "false",
        "ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED": "false",
        "ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED": "false",
        "DATABASE_URL": "",
    }
)

from argus.api import state as api_state  # noqa: E402
from argus.api.main import app  # noqa: E402
from argus.api.schemas import Conversation, Message  # noqa: E402

CONVERSATION_ID = "00000000-0000-4000-8000-000000005311"
SOURCE_CONVERSATION_ID = "3f650497-a69b-412d-9fa0-78663098f209"
SOURCE_RUN_ID = "d8ad8120-b2b4-51d6-b28e-6e164d10c4e9"
REPLAY_RUN_ID = "00000000-0000-4000-8000-000000005312"
RESULT_MESSAGE_ID = "b215f293-81d5-427c-ae11-e0cab659f63e"


def _replace_ids(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _replace_ids(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_ids(item) for item in value]
    if value == SOURCE_CONVERSATION_ID:
        return CONVERSATION_ID
    if value == SOURCE_RUN_ID:
        return REPLAY_RUN_ID
    return value


def _seed() -> None:
    payload_path = (
        ROOT / "docs/reports/evidence/411/browser/en-discovery-messages.json"
    )
    source = json.loads(payload_path.read_text())
    rows: list[dict[str, Any]] = []
    for row in source["items"]:
        rows.append(_replace_ids(row))
        if row["id"] == RESULT_MESSAGE_ID:
            break

    messages = [Message.model_validate(row) for row in rows]
    user = api_state.store.get_or_create_dev_user()
    api_state.store.conversation_owners[CONVERSATION_ID] = user.id
    api_state.store.messages[CONVERSATION_ID] = messages
    api_state.store.conversations[CONVERSATION_ID] = Conversation(
        id=CONVERSATION_ID,
        title="META Buy and Hold Strategy",
        title_source="ai_generated",
        language="en",
        created_at=messages[0].created_at,
        updated_at=messages[-1].created_at,
        last_message_preview=messages[-1].content,
    )


_seed()

if __name__ == "__main__":
    import uvicorn

    candidate = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=SOURCE_ROOT, text=True
    ).strip()
    print(
        json.dumps(
            {
                "candidate_sha": candidate,
                "source_root": str(SOURCE_ROOT),
                "web_origin": WEB_ORIGIN,
                "api_port": API_PORT,
                "provider_calls": 0,
                "hosted_database_reads_or_writes": 0,
            }
        )
    )
    uvicorn.run(app, host="127.0.0.1", port=API_PORT)
