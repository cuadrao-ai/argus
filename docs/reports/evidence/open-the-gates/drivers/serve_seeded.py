"""The lane's local API with one seeded conversation of six eligible research
turns, each a copy of the real NVIDIA answer recorded in this lane, so the
selection screen can be driven past the four turns it used to cap at. No
provider is called for the seed."""
from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

from dotenv import load_dotenv

TREE = Path(os.environ["OTG_TREE"]).resolve()
sys.path.insert(0, str(TREE / "src"))
load_dotenv(TREE / ".env", override=False)
API_PORT = int(os.getenv("OTG_API_PORT", "8590"))
WEB_PORT = int(os.getenv("OTG_WEB_PORT", "3590"))
WEB_ORIGIN = f"http://127.0.0.1:{WEB_PORT}"
os.environ.update(
    {
        "CUADRAO_PERSISTENCE_MODE": "memory",
        "ARGUS_DEV_MEMORY_FALLBACK": "true",
        "CUADRAO_CHECKPOINTER_MODE": "memory",
        "CUADRAO_MOCK_AUTH": "true",
        "ARGUS_MARKET_DATA_PROVIDER_MODE": "live_provider",
        "ARGUS_ASSET_PROVIDER_MODE": "live_provider",
        "ARGUS_RESEARCH_RAIL_ENABLED": "true",
        "CUADRAO_EVIDENCE_RECEIPT_SHARING_ENABLED": "true",
        "ARGUS_ENABLE_PERSONALIZATION_MEMORY": "false",
        "CUADRAO_CORS_ALLOW_ORIGINS": f"{WEB_ORIGIN},http://localhost:{WEB_PORT}",
        "ARGUS_APP_ORIGIN": WEB_ORIGIN,
        "ARGUS_BACKTEST_JOBS_SHADOW_ENABLED": "false",
        "ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED": "false",
        "ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED": "false",
        "ENABLE_MARKET_DATA_CACHE": "false",
        "DATABASE_URL": "",
        "POSTHOG_PROJECT_TOKEN": "",
    }
)
import uvicorn  # noqa: E402
from argus.api import state as api_state  # noqa: E402
from argus.api.main import app  # noqa: E402
from argus.api.message_store import memory_conversation, memory_message  # noqa: E402

RECORD = json.loads((TREE / "docs/reports/evidence/open-the-gates/after/argus-nvda-week.json").read_text())
IDS_FILE = Path(os.environ["OTG_IDS_FILE"])
QUESTIONS = [
    "why is NVIDIA stock moving this week?",
    "what did NVIDIA say about demand this week?",
    "is NVIDIA's weakness this week about China?",
    "what is NVIDIA waiting on this week?",
    "did NVIDIA insiders sell this week?",
    "how did NVIDIA close on September 9?",
]


def _seed() -> str:
    user = api_state.store.get_or_create_dev_user()
    final = [m for m in RECORD["messages"]["items"] if m["role"] == "assistant"][-1]
    conversation = memory_conversation(
        title="NVIDIA this week", title_source="ai_generated", language="en", user_id=user.id
    )
    for question in QUESTIONS:
        memory_message(conversation_id=conversation.id, role="user", content=question)
        memory_message(
            conversation_id=conversation.id,
            role="assistant",
            content=final["content"],
            metadata=final["metadata"],
        )
    return conversation.id


IDS_FILE.write_text(json.dumps({"conversation_id": _seed()}))
uvicorn.run(app, host="127.0.0.1", port=API_PORT, log_level="warning")
