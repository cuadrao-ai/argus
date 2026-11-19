"""Live staging settings compared with the manifest, without printing secrets."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

import pytest
from faker import Faker
from loguru import logger

import scripts.ops.settings_drift as drift
from scripts.ops.staging_env import load_manifest


@pytest.mark.parametrize("service", ["api", "web", "documents_worker"])
def test_documented_command_help_runs_from_repo_root(
    service: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = Path(__file__).resolve().parents[1]
    runbook = (root / "docs/PRIVATE_LAUNCH_RUNBOOK.md").read_text()
    command = next(
        line
        for line in runbook.splitlines()
        if "settings_drift" in line and line.endswith(f" {service}")
    )
    argv = shlex.split(command)
    assert argv.pop(0) == "RENDER_API_KEY=..."
    monkeypatch.delenv("PYTHONPATH", raising=False)
    monkeypatch.delenv("RENDER_API_KEY", raising=False)

    result = subprocess.run(
        [*argv, "--help"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--token-env" in result.stdout


def _service() -> dict:
    return {
        "entries": [
            {
                "name": "CUADRAO_BUSINESS_NOTIFICATIONS_ENABLED",
                "kind": "plain",
                "value": "false",
            },
            {"name": "CUADRAO_OPS_TOKEN", "kind": "secret"},
            {"name": "CUADRAO_OPTIONAL_SECRET", "kind": "secret", "optional": True},
        ],
        "remove": [],
        "hold": [{"name": "CUADRAO_HELD"}],
    }


def test_plain_value_drift_is_reported_and_a_secret_value_is_not() -> None:
    lines = drift.compare(
        _service(),
        {
            "CUADRAO_BUSINESS_NOTIFICATIONS_ENABLED": "true",
            "CUADRAO_OPS_TOKEN": "super-secret-value",
            "CUADRAO_HELD": "leave-me",
            "CUADRAO_EXTRA": "extra-value",
        },
    )

    assert lines == [
        "drift CUADRAO_BUSINESS_NOTIFICATIONS_ENABLED expected=false actual=true",
        "ok CUADRAO_OPS_TOKEN present",
        "ok CUADRAO_OPTIONAL_SECRET absent",
        "drift CUADRAO_EXTRA extra",
    ]
    rendered = "\n".join(lines)
    assert "super-secret-value" not in rendered
    assert "leave-me" not in rendered
    assert "extra-value" not in rendered


def test_a_matching_service_has_no_drift() -> None:
    lines = drift.compare(
        _service(),
        {
            "CUADRAO_BUSINESS_NOTIFICATIONS_ENABLED": "false",
            "CUADRAO_OPS_TOKEN": "present",
        },
    )

    assert drift.drifted(lines) is False
    assert "ok CUADRAO_BUSINESS_NOTIFICATIONS_ENABLED=false" in lines


def test_run_refuses_to_call_without_a_token(monkeypatch) -> None:
    monkeypatch.delenv("RENDER_API_KEY", raising=False)

    assert drift.run(["api"], out=lambda _line: None) == 2


class _Reader:
    def __init__(self, name: str) -> None:
        self.name = name
        self.puts: list[object] = []
        self.reads = 0

    def service_name(self, _service_id: str) -> str:
        return self.name

    def list_env(self, _service_id: str) -> dict[str, str]:
        self.reads += 1
        return {}

    def put_env(self, service_id: str, env: dict[str, str]) -> None:
        self.puts.append((service_id, env))


@pytest.mark.parametrize("service", ["api", "web", "documents_worker"])
def test_run_reads_the_staging_service_and_does_not_write(monkeypatch, service) -> None:
    monkeypatch.setenv("RENDER_API_KEY", "read-only-token")
    name = load_manifest()["services"][service].get(
        "service_name", "cuadrao-documents-worker-staging"
    )
    reader = _Reader(name)
    lines: list[str] = []

    code = drift.run([service], client_factory=lambda _token: reader, out=lines.append)

    assert code == 1
    assert reader.reads == 1
    assert reader.puts == []
    assert "read-only-token" not in "\n".join(lines)


@pytest.mark.parametrize("use_callback", [False, True])
def test_run_redacts_token_from_plain_values(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    faker: Faker,
    use_callback: bool,
) -> None:
    token = faker.pystr()
    monkeypatch.setenv("CUSTOM_DRIFT_TOKEN", token)
    service = _service()
    monkeypatch.setattr(drift, "load_manifest", lambda: {"services": {"api": service}})
    monkeypatch.setattr(drift, "staging_services", lambda manifest: manifest["services"])
    monkeypatch.setattr(
        drift,
        "read_live",
        lambda _client, _service: {"CUADRAO_BUSINESS_NOTIFICATIONS_ENABLED": token},
    )
    tokens: list[str] = []
    lines: list[str] = []
    kwargs = {"out": lines.append} if use_callback else {}

    code = drift.run(
        ["api", "--token-env", "CUSTOM_DRIFT_TOKEN"],
        client_factory=tokens.append,
        **kwargs,
    )

    captured = capsys.readouterr()
    output = "\n".join(lines) + captured.out + captured.err
    assert code == 1
    assert tokens == [token]
    assert token not in output
    assert "actual=<redacted>" in output


@pytest.mark.parametrize("failure", ["load_manifest", "client_factory", "read_live"])
def test_run_diagnostics_do_not_disclose_token(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    faker: Faker,
    failure: str,
) -> None:
    token = faker.pystr()
    monkeypatch.setenv("RENDER_API_KEY", token)
    errors: list[str] = []

    def fail(*_args: object) -> None:
        raise drift.RenderError(f"request rejected with Authorization: Bearer {token}")

    factory = fail if failure == "client_factory" else lambda _token: object()
    if failure != "client_factory":
        monkeypatch.setattr(drift, failure, fail)
    sink = logger.add(errors.append, format="{message}")
    try:
        code = drift.run(["api"], client_factory=factory)
    finally:
        logger.remove(sink)

    captured = capsys.readouterr()
    output = "\n".join(errors) + captured.out + captured.err
    assert code == 2
    assert token not in output
    assert errors


@pytest.mark.parametrize("use_callback", [False, True])
@pytest.mark.parametrize("scope", [{}, {"local_only": True}, {"production_only": True}])
def test_run_redacts_every_manifest_secret_from_every_report_line(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    faker: Faker,
    use_callback: bool,
    scope: dict[str, bool],
) -> None:
    token, secret, generated = (faker.unique.pystr() for _ in range(3))
    monkeypatch.setenv("RENDER_API_KEY", token)
    service = _service()
    service["entries"].extend(
        [
            {"name": "CUADRAO_OPAQUE", "kind": "secret", **scope},
            {"name": "CUADRAO_GENERATED", "kind": "generated", **scope},
            {"name": "CUADRAO_EMPTY", "kind": "secret"},
            {"name": "CUADRAO_MISSING", "kind": "secret"},
            {"name": "CUADRAO_COMBINED", "kind": "plain", "value": "false"},
            {"name": "CUADRAO_MATCHING", "kind": "plain", "value": generated},
        ]
    )
    live = {
        "CUADRAO_BUSINESS_NOTIFICATIONS_ENABLED": secret,
        "CUADRAO_OPAQUE": secret,
        "CUADRAO_GENERATED": generated,
        "CUADRAO_EMPTY": "",
        "CUADRAO_COMBINED": f"{token}/{secret}/{generated}",
        "CUADRAO_MATCHING": generated,
    }
    monkeypatch.setattr(drift, "load_manifest", lambda: {"services": {"api": service}})
    monkeypatch.setattr(drift, "staging_services", lambda manifest: manifest["services"])
    monkeypatch.setattr(drift, "read_live", lambda _client, _service: live)
    lines: list[str] = []
    kwargs = {"out": lines.append} if use_callback else {}

    code = drift.run(["api"], client_factory=lambda _token: object(), **kwargs)

    captured = capsys.readouterr()
    output = "\n".join(lines) + captured.out + captured.err
    assert code == 1
    assert all(value not in output for value in (token, secret, generated))
    assert (
        "CUADRAO_BUSINESS_NOTIFICATIONS_ENABLED expected=false actual=<redacted>"
        in output
    )
    assert (
        "CUADRAO_COMBINED expected=false actual=<redacted>/<redacted>/<redacted>"
        in output
    )
    assert "ok CUADRAO_MATCHING=<redacted>" in output


@pytest.mark.parametrize("idle_poll, expected_code", [("60", 0), ("5", 1)])
def test_worker_drift_compares_staging_rules_and_redacts_secrets(
    monkeypatch: pytest.MonkeyPatch,
    faker: Faker,
    idle_poll: str,
    expected_code: int,
) -> None:
    service = load_manifest()["services"]["documents_worker"]
    token = faker.unique.pystr()
    live = {
        e["name"]: str(e.get("value", faker.unique.pystr()))
        for e in drift.staging_entries(service)
    }
    live["CUADRAO_DOCUMENT_JOBS_IDLE_POLL_SECONDS"] = idle_poll
    monkeypatch.setenv("RENDER_API_KEY", token)
    reader = _Reader("cuadrao-documents-worker-staging")
    monkeypatch.setattr(reader, "list_env", lambda _id: live)
    lines: list[str] = []
    code = drift.run(
        ["documents_worker"], client_factory=lambda _token: reader, out=lines.append
    )
    assert code == expected_code
    assert reader.puts == []
    text = "\n".join(lines)
    assert token not in text
    assert "ok CUADRAO_OPENROUTER_API_KEY_STG present" in text
    assert "CUADRAO_OPENROUTER_API_KEY_PROD" not in text
    for entry in drift.staging_entries(service):
        if entry["kind"] != "plain":
            assert live[entry["name"]] not in text
    if expected_code:
        assert (
            "drift CUADRAO_DOCUMENT_JOBS_IDLE_POLL_SECONDS expected=60 actual=5" in lines
        )
