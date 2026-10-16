from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from unittest.mock import AsyncMock, Mock

import pytest
from argus.api import app_setup
from argus.api import state as api_state
from argus.domain import supabase_gateway
from faker import Faker
from fastapi import FastAPI
from fastapi.testclient import TestClient
from loguru import logger

FLAGS = ("NEXT_PUBLIC_MOCK_AUTH", "ARGUS_MOCK_AUTH", "ARGUS_DEV_ENDPOINTS_ENABLED")
ENV_NAMES = ("APP_ENV", "ENVIRONMENT", "ARGUS_ENV", "ARGUS_APP_ENV")
LOCAL_ENVS = ("local", "development", "dev", "test", "local-smoke")
fake = Faker()


@pytest.fixture
def startup(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[FastAPI, Mock, list[str]]]:
    for name in (*FLAGS, *ENV_NAMES, "RENDER", "RENDER_SERVICE_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(api_state, "PERSISTENCE_MODE", "memory")
    monkeypatch.setattr(api_state, "CHECKPOINTER_MODE", "memory")
    checkpointer = Mock()
    monkeypatch.setattr(api_state, "build_agent_runtime_checkpointer", checkpointer)
    monkeypatch.setattr(app_setup, "validate_hosted_openrouter_configuration", Mock())
    for module, stem in (
        ("personalization_memory", "personalization_memory"),
        ("financial_accounts", "financial_accounts"),
        ("ingestion", "ingestion"),
        ("households", "households"),
        ("apple_sign_in", "apple_sign_in"),
    ):
        for prefix in ("start", "stop"):
            monkeypatch.setattr(f"argus.api.{module}.{prefix}_{stem}", Mock())
    for module, stem in (("email_intake", "email_intake"), ("whatsapp_worker", "worker")):
        monkeypatch.setattr(f"argus.api.{module}.start_{stem}", Mock())
        monkeypatch.setattr(f"argus.api.{module}.stop_{stem}", AsyncMock())
    monkeypatch.setattr("argus.api.whatsapp.drain_whatsapp", AsyncMock())
    records: list[str] = []
    sink = logger.add(lambda message: records.append(message.record["message"]))
    try:
        yield FastAPI(lifespan=app_setup.lifespan), checkpointer, records
    finally:
        logger.remove(sink)


@pytest.mark.parametrize("flag", FLAGS)
@pytest.mark.parametrize("env_name", ENV_NAMES)
@pytest.mark.parametrize("environment", ("production", "prod", "staging", "preview"))
def test_hosted_flags_refuse_startup_before_resources(
    startup, monkeypatch: pytest.MonkeyPatch, flag: str, env_name: str, environment: str
) -> None:
    app, checkpointer, records = startup
    monkeypatch.setenv(env_name, environment)
    monkeypatch.setenv(flag, " TrUe ")
    with pytest.raises(RuntimeError, match=flag):
        with TestClient(app):
            pass
    checkpointer.assert_not_called()
    assert any("startup_config_refused" in line and flag in line for line in records)


@pytest.mark.parametrize("environment", (None, "", "unknown", "private-alpha"))
@pytest.mark.parametrize("flag", FLAGS)
def test_flags_require_an_explicit_local_environment(
    startup, monkeypatch: pytest.MonkeyPatch, environment: str | None, flag: str
) -> None:
    app, checkpointer, _ = startup
    if environment is not None:
        monkeypatch.setenv("APP_ENV", environment)
    monkeypatch.setenv(flag, "true")
    with pytest.raises(RuntimeError, match=flag):
        with TestClient(app):
            pass
    checkpointer.assert_not_called()


@pytest.mark.parametrize("environment", LOCAL_ENVS)
@pytest.mark.parametrize("flag", FLAGS)
def test_local_flags_preserve_startup(
    startup, monkeypatch: pytest.MonkeyPatch, environment: str, flag: str
) -> None:
    app, checkpointer, records = startup
    monkeypatch.setenv("APP_ENV", environment)
    monkeypatch.setenv(flag, "true")
    with TestClient(app):
        pass
    checkpointer.assert_called_once()
    assert not any("startup_config_refused" in line for line in records)


@pytest.mark.parametrize(
    ("name", "value"),
    (("ENVIRONMENT", "staging"), ("RENDER", "true"), ("RENDER_SERVICE_ID", "srv-test")),
)
@pytest.mark.parametrize("local_environment", ("test", "local-smoke"))
def test_hosted_markers_override_a_local_label(
    startup,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
    local_environment: str,
) -> None:
    app, checkpointer, _ = startup
    monkeypatch.setenv("APP_ENV", local_environment)
    monkeypatch.setenv(name, value)
    monkeypatch.setenv("ARGUS_MOCK_AUTH", "true")
    with pytest.raises(RuntimeError, match="ARGUS_MOCK_AUTH"):
        with TestClient(app):
            pass
    checkpointer.assert_not_called()


def test_hosted_startup_without_bypasses_succeeds(startup, monkeypatch) -> None:
    app, checkpointer, _ = startup
    monkeypatch.setenv("APP_ENV", "staging")
    for flag in FLAGS:
        monkeypatch.setenv(flag, "false")
    with TestClient(app):
        pass
    checkpointer.assert_called_once()


@pytest.fixture
def gateway_config(monkeypatch: pytest.MonkeyPatch) -> tuple[Mock, Mock, str]:
    service_key = fake.pystr(min_chars=32, max_chars=32)
    monkeypatch.setenv("SUPABASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", service_key)
    monkeypatch.setenv("DATABASE_URL", "postgresql://test@127.0.0.1:9/test")
    for name in ("SUPABASE_ANON_KEY", "SUPABASE_ANON_PUBLIC_KEY"):
        monkeypatch.delenv(name, raising=False)
    client, auth = Mock(), Mock()
    monkeypatch.setattr(supabase_gateway, "create_client", client)
    monkeypatch.setattr(supabase_gateway, "_auth_client_factory", auth)
    monkeypatch.setattr(supabase_gateway, "history_reader_for_database_url", Mock())
    return client, auth, service_key


@pytest.mark.parametrize("missing", ("", " \t "))
def test_gateway_refuses_missing_anon_before_constructing_clients(
    gateway_config, monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    client, auth, service_key = gateway_config
    monkeypatch.setenv("SUPABASE_ANON_KEY", missing)
    monkeypatch.setenv("SUPABASE_ANON_PUBLIC_KEY", missing)
    records: list[str] = []
    sink = logger.add(lambda message: records.append(message.record["message"]))
    try:
        with pytest.raises(RuntimeError, match="SUPABASE_ANON_KEY") as refused:
            supabase_gateway.SupabaseGateway.from_env()
    finally:
        logger.remove(sink)
    client.assert_not_called()
    auth.assert_not_called()
    assert any("startup_config_refused" in line for line in records)
    assert service_key not in str(refused.value) + "".join(records)


@pytest.mark.parametrize("name", ("SUPABASE_ANON_KEY", "SUPABASE_ANON_PUBLIC_KEY"))
def test_gateway_auth_uses_only_the_explicit_public_key(
    gateway_config, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    client, auth, service_key = gateway_config
    public_key = fake.pystr(min_chars=32, max_chars=32)
    monkeypatch.setenv("SUPABASE_ANON_KEY", " ")
    monkeypatch.setenv(name, public_key)
    supabase_gateway.SupabaseGateway.from_env()
    assert client.call_args.args[1] == service_key
    auth.assert_called_once_with("http://127.0.0.1:9", public_key)


def _startup_process(config: dict[str, str]) -> subprocess.CompletedProcess[str]:
    environment = {
        "PATH": os.defpath,
        "PYTHONPATH": os.pathsep.join(sys.path),
        "APP_ENV": "staging",
        "ARGUS_PERSISTENCE_MODE": "memory",
        "ARGUS_CHECKPOINTER_MODE": "memory",
        **config,
    }
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "import asyncio; import argus.env; "
            "argus.env.load_project_dotenv = lambda: False; "
            "from argus.api.main import app; "
            "asyncio.run(app.router.lifespan_context(app).__aenter__())",
        ],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.mark.parametrize("flag", FLAGS)
def test_process_exits_nonzero_for_hosted_bypass(flag: str) -> None:
    result = _startup_process({flag: "true"})
    assert result.returncode != 0
    assert "startup_config_refused" in result.stderr
    assert flag in result.stderr


def test_process_starts_for_local_smoke_configuration() -> None:
    result = _startup_process(
        {
            "APP_ENV": "local-smoke",
            "ARGUS_MOCK_AUTH": "true",
            "NEXT_PUBLIC_MOCK_AUTH": "true",
        }
    )
    assert result.returncode == 0, result.stderr
    assert "startup_config_refused" not in result.stderr


def test_process_exits_nonzero_without_public_key_in_supabase_mode() -> None:
    service_key = fake.pystr(min_chars=32, max_chars=32)
    result = _startup_process(
        {
            "ARGUS_PERSISTENCE_MODE": "supabase",
            "SUPABASE_URL": "http://127.0.0.1:9",
            "SUPABASE_SERVICE_ROLE_KEY": service_key,
            "DATABASE_URL": "postgresql://test@127.0.0.1:9/test",
        }
    )
    assert result.returncode != 0
    assert "startup_config_refused{reason=missing_SUPABASE_ANON_KEY}" in result.stderr
    assert service_key not in result.stdout + result.stderr
