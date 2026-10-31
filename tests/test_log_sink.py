"""Regression tests for Loguru diagnostic locals and ops token compare (#682)."""

from __future__ import annotations

import hmac
import importlib
import io
import subprocess
import sys
from types import ModuleType
from typing import Any

import anyio
import pytest
from argus.api.main import app
from argus.api.routers import ops
from argus.log_sink import configure_logging
from faker import Faker
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient
from loguru import logger

fake = Faker()

_SENTINEL_SECRET = "SENTINEL_LOCAL_SECRET_VALUE_682"
_OPS_SCRIPT_MODULES = (
    "scripts.ops.cleanup_expired_guest_workspaces",
    "scripts.ops.stale_backtest_jobs",
    "scripts.ops.release_expired_access_welcome_claims",
)


def _raise_with_sentinel() -> None:
    expected_header = _SENTINEL_SECRET
    authorization = "Bearer token-\u00e9"
    hmac.compare_digest(authorization, expected_header)


def _assert_handlers_are_safe() -> None:
    handlers = logger._core.handlers
    assert handlers
    for handler in handlers.values():
        formatter = handler._exception_formatter
        assert formatter._diagnose is False
        assert formatter._backtrace is False


def _latin1_ops_token() -> str:
    return f"{fake.hexify(text='^^^^^^^^')}-\u00e9"


def _asgi_get_with_raw_authorization(authorization: bytes) -> int:
    status_box: dict[str, int] = {}

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            status_box["status"] = int(message["status"])

    async def _run() -> None:
        await app(
            {
                "type": "http",
                "asgi": {"spec_version": "2.3", "version": "3.0"},
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": "/internal/readiness",
                "raw_path": b"/internal/readiness",
                "query_string": b"",
                "headers": [
                    (b"host", b"testserver"),
                    (b"authorization", authorization),
                ],
                "client": ("127.0.0.1", 123),
                "server": ("testserver", 80),
            },
            receive,
            send,
        )

    anyio.run(_run)
    return status_box["status"]


def test_logger_exception_does_not_render_local_values() -> None:
    stream = io.StringIO()
    configure_logging(sink=stream)
    try:
        try:
            _raise_with_sentinel()
        except TypeError:
            logger.exception("forced exception through logging path")
    finally:
        configure_logging()

    output = stream.getvalue()
    assert "forced exception through logging path" in output
    assert _SENTINEL_SECRET not in output


def test_non_ascii_ops_authorization_is_rejected_without_exception_log(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records: list[str] = []
    sink_id = logger.add(lambda message: records.append(str(message)), level="ERROR")
    monkeypatch.setenv("CUADRAO_OPS_TOKEN", fake.uuid4())
    try:
        response = TestClient(app, raise_server_exceptions=False).get(
            "/internal/readiness",
            headers={"Authorization": "Bearer token-\u00e9".encode("latin-1")},
        )
    finally:
        logger.remove(sink_id)

    assert response.status_code == 404
    assert all("Unexpected API failure" not in record for record in records)


def test_latin1_ops_token_matches_and_wrong_token_is_quiet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _latin1_ops_token()

    async def _ready_checks(request: Request, *, force: bool) -> dict[str, Any]:
        del request, force
        return {"status": "ready", "checks": []}

    records: list[str] = []
    sink_id = logger.add(lambda message: records.append(str(message)), level="ERROR")
    monkeypatch.setenv("CUADRAO_OPS_TOKEN", token)
    monkeypatch.setattr(ops, "run_readiness_checks", _ready_checks)
    TestClient(app, raise_server_exceptions=False)
    try:
        matched_status = _asgi_get_with_raw_authorization(
            f"Bearer {token}".encode("latin-1")
        )
        rejected_status = _asgi_get_with_raw_authorization(
            "Bearer wrong-\u00e9".encode("latin-1")
        )
    finally:
        logger.remove(sink_id)

    assert matched_status == 200
    assert rejected_status == 404
    assert all("Unexpected API failure" not in record for record in records)


def test_non_latin1_ops_authorization_is_rejected_without_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CUADRAO_OPS_TOKEN", "ascii-token")
    with pytest.raises(HTTPException) as exc_info:
        ops._require_ops_token("Bearer snowman-\u2603")
    assert exc_info.value.status_code == 404


def test_argus_package_import_installs_safe_handler() -> None:
    logger.remove()
    logger.add(sys.stderr)
    import argus

    importlib.reload(argus)
    _assert_handlers_are_safe()


def test_perplexity_client_import_uses_package_logging_owner() -> None:
    logger.remove()
    logger.add(sys.stderr)
    import argus

    importlib.reload(argus)
    from argus.domain.research.perplexity_agent import PerplexityAgentClient

    assert PerplexityAgentClient is not None
    _assert_handlers_are_safe()


def test_memory_import_installs_safe_handler_without_observability() -> None:
    script = """
import sys
import argus.memory
from loguru import logger
blocked = sorted(
    name for name in sys.modules
    if name == "argus.observability" or name.startswith("argus.observability.")
)
if blocked:
    raise SystemExit("loaded " + ",".join(blocked))
handlers = logger._core.handlers
if not handlers:
    raise SystemExit("no handlers")
for handler in handlers.values():
    formatter = handler._exception_formatter
    if formatter._diagnose or formatter._backtrace:
        raise SystemExit("unsafe handler")
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_api_app_import_installs_safe_handler() -> None:
    from argus.api import app_setup

    importlib.reload(app_setup)
    _assert_handlers_are_safe()


def test_workflows_main_import_installs_safe_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeRetry:
        def __init__(self, **kwargs: object) -> None:
            del kwargs

    class FakeWorkflows:
        def __init__(self, **kwargs: object) -> None:
            del kwargs

        def task(self, fn: object | None = None, **kwargs: object):
            del kwargs

            def decorate(inner: object) -> object:
                return inner

            if fn is not None:
                return decorate(fn)
            return decorate

        def start(self) -> None:
            return None

    fake_render_sdk = ModuleType("render_sdk")
    fake_render_sdk.Retry = FakeRetry
    fake_render_sdk.Workflows = FakeWorkflows
    fake_backtest_job = ModuleType("workflows.backtest_job")
    fake_backtest_job.PostgresBacktestJobGateway = object
    fake_backtest_job.capacity_probe_should_raise = lambda result: False
    fake_backtest_job.run_backtest_job = lambda *args, **kwargs: {}
    fake_proof = ModuleType("workflows.proof")
    fake_proof.PostgresProofJobGateway = object
    fake_proof.run_workflow_proof = lambda *args, **kwargs: {}
    monkeypatch.setitem(sys.modules, "render_sdk", fake_render_sdk)
    monkeypatch.setitem(sys.modules, "workflows.backtest_job", fake_backtest_job)
    monkeypatch.setitem(sys.modules, "workflows.proof", fake_proof)
    logger.remove()
    logger.add(sys.stderr)
    sys.modules.pop("workflows.main", None)
    importlib.import_module("workflows.main")
    _assert_handlers_are_safe()


def test_backtest_job_import_installs_safe_handler() -> None:
    import workflows.backtest_job as backtest_job

    logger.remove()
    logger.add(sys.stderr)
    importlib.reload(backtest_job)
    _assert_handlers_are_safe()


@pytest.mark.parametrize("module_name", _OPS_SCRIPT_MODULES)
def test_ops_script_entrypoint_installs_safe_handler(
    module_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.ops.destructive_database_target import DestructiveDatabaseTargetError

    module = importlib.import_module(module_name)
    calls: list[bool] = []
    real_configure = configure_logging

    def _configure(*args: object, **kwargs: object) -> None:
        calls.append(True)
        real_configure(*args, **kwargs)

    monkeypatch.setattr(
        "argus.log_sink.configure_logging",
        _configure,
    )
    monkeypatch.setattr(
        module,
        "resolve_destructive_database_target",
        lambda: (_ for _ in ()).throw(DestructiveDatabaseTargetError("missing")),
    )
    with pytest.raises(SystemExit):
        module.main([])
    assert calls
    _assert_handlers_are_safe()
