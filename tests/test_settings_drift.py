"""Live staging settings compared with the manifest, without printing secrets."""

from __future__ import annotations

import scripts.ops.settings_drift as drift
from scripts.ops.staging_env import load_manifest


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


def test_run_reads_the_staging_service_and_does_not_write(monkeypatch) -> None:
    monkeypatch.setenv("RENDER_API_KEY", "read-only-token")
    name = load_manifest()["services"]["api"]["service_name"]
    reader = _Reader(name)
    lines: list[str] = []

    code = drift.run(["api"], client_factory=lambda _token: reader, out=lines.append)

    assert code == 1
    assert reader.reads == 1
    assert reader.puts == []
    assert "read-only-token" not in "\n".join(lines)
