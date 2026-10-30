"""Local Argus API for the open-the-gates lane: memory persistence, mock auth,
real interpreter and research provider, live asset provider so any ticker
resolves. Port 8590, own CORS origin for the web dev server on 3590."""
from __future__ import annotations

import os
import sys
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
from argus.api.main import app  # noqa: E402

uvicorn.run(app, host="127.0.0.1", port=API_PORT, log_level="info")
