"""Live route check server: the chat route with capture wrappers.

Memory persistence and mock auth, with OpenRouter models and the `live_provider`
market-data and asset modes. Provider keys load in-process from the env file
named by ROUTE_CHECK_ENV_FILE, where values already set win; the file is never
written. For httpx requests to openrouter.ai or perplexity.ai it records the
request body (never headers) when the send returns or raises an ordinary
exception; a request cancelled by an asyncio timeout is not recorded. It also
records each receipt appended to OpenRouter's route receipt list, the result of
each research cost validation, each thread history load made through the chat
route and artifact naming modules, and each naming context and name that
artifact naming builds.
"""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve()
SOURCE_ROOT = Path(
    os.environ.get("ROUTE_CHECK_SOURCE_ROOT")
    or next(
        parent
        for parent in HERE.parents
        if (parent / "pyproject.toml").is_file() and (parent / "src" / "argus").is_dir()
    )
).resolve()
OUT = Path(os.environ["ROUTE_CHECK_OUT"]).resolve()
PORT = int(os.environ.get("ROUTE_CHECK_PORT", "8618"))
ENV_FILE = os.environ["ROUTE_CHECK_ENV_FILE"]
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(SOURCE_ROOT / "src"))

OVERRIDES = {
    "CUADRAO_PERSISTENCE_MODE": "memory",
    "CUADRAO_MOCK_AUTH": "true",
    "CUADRAO_CHECKPOINTER_MODE": "memory",
    "ARGUS_DEV_MEMORY_FALLBACK": "true",
    "ARGUS_MARKET_DATA_PROVIDER_MODE": "live_provider",
    "ARGUS_ASSET_PROVIDER_MODE": "live_provider",
    "ARGUS_BACKTEST_JOBS_SHADOW_ENABLED": "false",
    "ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED": "false",
    "ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED": "false",
    "ARGUS_ENABLE_PERSONALIZATION_MEMORY": "false",
    "ARGUS_ENABLE_MEMORY_SEMANTIC_RECALL": "false",
    "DATABASE_URL": "",
    "SUPABASE_URL": "",
    "SUPABASE_PROJECT_URL": "",
    "SUPABASE_SERVICE_ROLE_KEY": "",
    "SUPABASE_POSTGRES_DIRECT_URL": "",
    "SUPABASE_POSTGRES_SESSION_POOLER_URL": "",
    "SUPABASE_POSTGRES_TRANSACTION_POOLER_URL": "",
}
os.environ.update(OVERRIDES)

from dotenv import load_dotenv  # noqa: E402

# Explicit values above win: load_dotenv never overrides what is already set.
load_dotenv(ENV_FILE, override=False)

_LOCK = threading.Lock()


def _log(name: str, record: dict[str, Any]) -> None:
    line = json.dumps({"ts": time.time(), **record}, ensure_ascii=False, default=str)
    with _LOCK, (OUT / f"{name}.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    for method in ("model_dump", "as_dict", "to_dict"):
        if callable(getattr(value, method, None)):
            return getattr(value, method)()
    return vars(value) if hasattr(value, "__dict__") else value


import httpx  # noqa: E402

_MODEL_HOSTS = ("openrouter.ai", "perplexity.ai")


def _request_record(request: httpx.Request) -> dict[str, Any] | None:
    host = request.url.host or ""
    if not any(host.endswith(model_host) for model_host in _MODEL_HOSTS):
        return None
    try:
        content = request.content
        body: Any = json.loads(content.decode("utf-8")) if content else None
    except Exception:  # noqa: BLE001
        body = {"unparsed_body": True}
    return {"host": host, "path": request.url.path, "body": body}


_sync_send = httpx.Client.send
_async_send = httpx.AsyncClient.send


def _logged_send(self: httpx.Client, request: httpx.Request, *args: Any, **kwargs: Any):
    record = _request_record(request)
    try:
        response = _sync_send(self, request, *args, **kwargs)
    except Exception as exc:
        if record is not None:
            _log("model_requests", {**record, "error": type(exc).__name__})
        raise
    if record is not None:
        _log("model_requests", {**record, "status": response.status_code})
    return response


async def _logged_async_send(
    self: httpx.AsyncClient, request: httpx.Request, *args: Any, **kwargs: Any
):
    record = _request_record(request)
    try:
        response = await _async_send(self, request, *args, **kwargs)
    except Exception as exc:
        if record is not None:
            _log("model_requests", {**record, "error": type(exc).__name__})
        raise
    if record is not None:
        _log("model_requests", {**record, "status": response.status_code})
    return response


httpx.Client.send = _logged_send  # type: ignore[method-assign]
httpx.AsyncClient.send = _logged_async_send  # type: ignore[method-assign]

import argus.api.artifact_naming as artifact_naming  # noqa: E402
import argus.api.routers.agent as agent_router  # noqa: E402
import argus.domain.research.perplexity_agent as perplexity_agent  # noqa: E402
import argus.llm.openrouter as openrouter  # noqa: E402


class _LoggedReceipts(list):
    def append(self, item: Any) -> None:
        _log("receipts", {"receipt": _plain(item)})
        super().append(item)


openrouter._ROUTE_RECEIPTS = _LoggedReceipts(openrouter._ROUTE_RECEIPTS)

_price_research = perplexity_agent.validated_research_cost_usd


def _logged_research_price(*args: Any, **kwargs: Any) -> Any:
    value = _price_research(*args, **kwargs)
    _log("research_costs", {"cost_usd": value})
    return value


perplexity_agent.validated_research_cost_usd = _logged_research_price


def _capture_history(module: Any, reader: str) -> None:
    original = module.load_runtime_thread_history

    def wrapper(**kwargs: Any) -> Any:
        history = original(**kwargs)
        _log(
            "thread_history",
            {
                "reader": reader,
                "conversation_id": kwargs.get("conversation_id"),
                "history": [{"role": item.role, "content": item.content} for item in history],
            },
        )
        return history

    module.load_runtime_thread_history = wrapper


_capture_history(agent_router, "chat_route")
_capture_history(artifact_naming, "artifact_naming")

_context_from_messages = artifact_naming._conversation_title_context_from_messages
_context_from_run = artifact_naming._conversation_title_context_from_run
_suggest_name = artifact_naming.suggest_entity_name


def _logged_context_from_messages(**kwargs: Any) -> str:
    context = _context_from_messages(**kwargs)
    _log(
        "naming_input",
        {
            "source": "messages",
            "conversation_id": kwargs.get("conversation_id"),
            "assistant_message": kwargs.get("assistant_message"),
            "context": context,
        },
    )
    return context


def _logged_context_from_run(run: Any) -> str:
    context = _context_from_run(run)
    _log("naming_input", {"source": "run", "run_id": getattr(run, "id", None), "context": context})
    return context


def _logged_suggest_name(**kwargs: Any) -> Any:
    name = _suggest_name(**kwargs)
    _log(
        "naming_output",
        {"entity_type": kwargs.get("entity_type"), "language": kwargs.get("language"), "name": name},
    )
    return name


artifact_naming._conversation_title_context_from_messages = _logged_context_from_messages
artifact_naming._conversation_title_context_from_run = _logged_context_from_run
artifact_naming.suggest_entity_name = _logged_suggest_name

from argus.api.main import app  # noqa: E402

if __name__ == "__main__":
    import uvicorn

    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=SOURCE_ROOT, text=True
    ).strip()
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain", "--", "src", "web"], cwd=SOURCE_ROOT, text=True
    ).strip()
    (OUT / "server.json").write_text(
        json.dumps(
            {
                "source_head": head,
                "working_tree_changes_under_src_or_web": bool(dirty),
                "port": PORT,
                "overrides": sorted(OVERRIDES),
                "env_file": "canonical integration .env, loaded in-process, not committed",
            },
            indent=2,
        )
    )
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
