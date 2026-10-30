"""Local browser QA: memory auth/storage, real providers, receipt observation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path.cwd()
SOURCE_ROOT = Path(os.getenv("ISSUE411_QA_SOURCE_ROOT", str(ROOT)))
OUT = Path(os.getenv("ISSUE411_QA_OUTPUT", str(ROOT / "output/playwright/issue-411")))
sys.path.insert(0, str(SOURCE_ROOT / "src"))
OUT.mkdir(parents=True, exist_ok=True)
load_dotenv(ROOT / ".env", override=True)
LOCAL_ENV = {
    "CUADRAO_PERSISTENCE_MODE": "memory",
    "ARGUS_DEV_MEMORY_FALLBACK": "true",
    "CUADRAO_CHECKPOINTER_MODE": "memory",
    "CUADRAO_MOCK_AUTH": "true",
    "ARGUS_MARKET_DATA_PROVIDER_MODE": "live_provider",
    "ARGUS_ASSET_PROVIDER_MODE": "live_provider",
    "ENABLE_MARKET_DATA_CACHE": "false",
    "ARGUS_BACKTEST_JOBS_SHADOW_ENABLED": "false",
    "ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED": "false",
    "ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED": "false",
    "ARGUS_CONTEXT_PACKETS_ENABLED": "false",
    "ARGUS_RESEARCH_RAIL_ENABLED": "true",
    "ARGUS_GROUNDED_DISCOVERY_ENABLED": "false",
    "CUADRAO_CORS_ALLOW_ORIGINS": "http://localhost:3200",
    "ARGUS_APP_ORIGIN": "http://localhost:3200",
    "DATABASE_URL": "",
}
os.environ.update(LOCAL_ENV)

from argus.api.main import app  # noqa: E402
from argus.api.routers import agent  # noqa: E402

original_persist = agent.persist_route_receipts


def observe_receipts(**kwargs: Any) -> None:
    """Copy the existing persistence-bound receipts without changing behavior."""
    row = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "conversation_id": kwargs["conversation_id"],
        "message_id": kwargs.get("message_id"),
        "run_id": kwargs.get("run_id"),
        "metadata": kwargs.get("metadata"),
        "receipts": [receipt.as_dict() for receipt in kwargs["receipts"]],
    }
    with (OUT / "route-receipts.jsonl").open("a") as stream:
        stream.write(json.dumps(row, default=str) + "\n")
    original_persist(**kwargs)


agent.persist_route_receipts = observe_receipts
(OUT / "environment.json").write_text(
    json.dumps(
        {
            "candidate_sha": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "prospective_tree": os.getenv("ISSUE411_QA_TREE"),
            "source_root": str(SOURCE_ROOT),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "local_environment": LOCAL_ENV,
            "model_environment": {
                key: value
                for key, value in os.environ.items()
                if key.startswith("ARGUS_") and key.endswith("_MODEL")
            },
            "provider_credentials_present": {
                key: bool(os.getenv(key))
                for key in ("OPENROUTER_API_KEY", "PERPLEXITY_API_KEY")
            },
            "observer": "copies receipts at API persistence boundary; calls original",
        },
        indent=2,
    )
    + "\n"
)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8200)
