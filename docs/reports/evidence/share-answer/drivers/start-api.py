"""Run real Argus against this lane's disposable LOCAL Supabase stack.

Provider credentials stay in the existing environment. All persistence and Auth
addresses are replaced before Argus is imported. Never use this with a hosted DB.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values, load_dotenv

ROOT = Path(__file__).resolve().parents[5]
PRIVATE = ROOT / "temp/share-answer-qa"
load_dotenv(ROOT / ".env")
local = dotenv_values(PRIVATE / "supabase-local.env")
api_url = str(local["API_URL"])
database_url = str(local["DB_URL"])
assert urlparse(api_url).hostname == "127.0.0.1"
assert urlparse(api_url).port == 55431
assert urlparse(database_url).hostname == "127.0.0.1"
assert urlparse(database_url).port == 55432

overrides = {
    "SUPABASE_URL": api_url,
    "SUPABASE_PROJECT_URL": api_url,
    "SUPABASE_ANON_KEY": str(local["ANON_KEY"]),
    "SUPABASE_ANON_PUBLIC_KEY": str(local["ANON_KEY"]),
    "SUPABASE_SERVICE_ROLE_KEY": str(local["SERVICE_ROLE_KEY"]),
    "SUPABASE_JWT_SECRET": str(local["JWT_SECRET"]),
    "DATABASE_URL": database_url,
    "SUPABASE_POSTGRES_DIRECT_URL": database_url,
    "SUPABASE_POSTGRES_SESSION_POOLER_URL": database_url,
    "SUPABASE_POSTGRES_TRANSACTION_POOLER_URL": database_url,
    "ARGUS_WORKFLOW_DATABASE_URL": database_url,
    "APP_ENV": "development",
    "CUADRAO_PERSISTENCE_MODE": "supabase",
    "CUADRAO_CHECKPOINTER_MODE": "postgres",
    "ARGUS_DEV_MEMORY_FALLBACK": "false",
    "CUADRAO_MOCK_AUTH": "false",
    "NEXT_PUBLIC_MOCK_AUTH": "false",
    "ARGUS_MARKET_DATA_PROVIDER_MODE": "live_provider",
    "ARGUS_ASSET_PROVIDER_MODE": "live_provider",
    "ARGUS_RESEARCH_RAIL_ENABLED": "true",
    "CUADRAO_EVIDENCE_RECEIPT_SHARING_ENABLED": "true",
    "ARGUS_ENABLE_PERSONALIZATION_MEMORY": "false",
    "ARGUS_BACKTEST_JOBS_SHADOW_ENABLED": "false",
    "ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED": "false",
    "ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED": "false",
    "ARGUS_APP_ORIGIN": "http://127.0.0.1:3319",
    "CUADRAO_CORS_ALLOW_ORIGINS": "http://127.0.0.1:3319",
    "POSTHOG_PROJECT_TOKEN": "",
    "CUADRAO_APPROVAL_EMAIL_SMTP_PASSWORD": "",
}
os.environ.update(overrides)

import uvicorn  # noqa: E402
from argus.api.main import app  # noqa: E402


@app.middleware("http")
async def record_public_requests(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/v1/public/"):
        # Public identifiers may be published; no source or owner identifiers.
        record = {
            "path": request.url.path,
            "method": request.method,
            "authorization_present": "authorization" in request.headers,
            "cookie_present": "cookie" in request.headers,
            "status": response.status_code,
        }
        with (PRIVATE / "public-requests.jsonl").open("a") as output:
            output.write(json.dumps(record) + "\n")
    return response


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8319)
