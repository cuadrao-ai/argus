"""The account deletion sweep entry point (Lane 6), run by scheduled_maintenance."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from scripts.ops import resume_account_deletions as sweep

ENV = {
    "DATABASE_URL": "postgresql://ops@db.example.supabase.co:5432/postgres",
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "service-role",
}


def test_refuses_without_an_explicit_target(monkeypatch) -> None:  # noqa: ANN001
    for key in ENV:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("SUPABASE_PROJECT_URL", raising=False)
    with pytest.raises(SystemExit) as exited:
        sweep.main([])
    assert exited.value.code == 2


@pytest.mark.parametrize(
    ("result", "code"),
    [
        ({"resumed": 2, "done": 1, "pending": 1, "failed": 0, "busy": 1}, 0),
        ({"resumed": 1, "done": 0, "pending": 0, "failed": 1, "busy": 0}, 1),
    ],
)
def test_resumes_through_the_command_and_fails_only_on_errors(
    monkeypatch,
    capsys,
    result,
    code,  # noqa: ANN001
) -> None:
    from argus.api import account_deletion_runtime
    from argus.domain import supabase_gateway

    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
    service = MagicMock()
    service.resume_pending.return_value = result
    built = {}

    def build(**kwargs):  # noqa: ANN003, ANN202
        built.update(kwargs)
        return service

    monkeypatch.setattr(account_deletion_runtime, "build_service", build)
    monkeypatch.setattr(
        supabase_gateway.SupabaseGateway, "from_env", classmethod(lambda cls: MagicMock())
    )
    assert sweep.main(["--limit", "7"]) == code
    service.resume_pending.assert_called_once_with(limit=7)
    assert built["database_url"] == ENV["DATABASE_URL"]
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1]) == result
