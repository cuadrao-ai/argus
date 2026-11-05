"""The operator-only force-complete entry point (Lane 6)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from argus.domain.account_deletion.service import (
    AccountDeletionIncomplete,
    AccountDeletionRejected,
    DeletionOutcome,
)

from scripts.ops import force_account_deletion_step as force

ENV = {
    "DATABASE_URL": "postgresql://ops@db.example.supabase.co:5432/postgres",
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "service-role",
}
USER = "00000000-0000-4000-8000-000000000001"
ARGS = ["--user-id", USER, "--step", "apple", "--operator", "lucas"]


@pytest.fixture
def service(monkeypatch):  # noqa: ANN001, ANN201
    from argus.api import account_deletion_runtime
    from argus.domain import supabase_gateway

    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
    built = MagicMock()
    monkeypatch.setattr(account_deletion_runtime, "build_service", lambda **_: built)
    monkeypatch.setattr(
        supabase_gateway.SupabaseGateway, "from_env", classmethod(lambda cls: MagicMock())
    )
    return built


PLAN = {"step": "apple", "pending_days": 8, "last_error": "invalid_request"}


def _last(capsys) -> dict:  # noqa: ANN001
    return json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def test_a_dry_run_by_default_changes_nothing(service, capsys) -> None:  # noqa: ANN001
    """Note 2: without --confirm it only reports the plan."""
    service.force_complete_step.return_value = {
        **PLAN,
        "dry_run": True,
        "forced": False,
    }
    assert force.main([*ARGS, "--reason", "Apple invalid_request for 7 days"]) == 0
    service.force_complete_step.assert_called_once_with(
        user_id=USER,
        step="apple",
        reason="Apple invalid_request for 7 days",
        operator="lucas",
        confirm=False,
    )
    service.delete_account.assert_not_called()
    assert _last(capsys)["dry_run"] is True


def test_confirm_forces_the_step_then_resumes_the_run(service, capsys) -> None:  # noqa: ANN001
    service.force_complete_step.return_value = {
        **PLAN,
        "dry_run": False,
        "revoke_attempt": "invalid_request",
        "forced": True,
    }
    service.delete_account.return_value = DeletionOutcome(status="done", counts={})
    args = [*ARGS, "--reason", "Apple invalid_request for 7 days", "--confirm"]
    assert force.main(args) == 0
    assert service.force_complete_step.call_args.kwargs["confirm"] is True
    service.delete_account.assert_called_once_with(user_id=USER, origin="force")
    assert _last(capsys) == {"forced": True, "status": "done"}


def test_a_revoke_that_now_succeeds_is_not_forced(service, capsys) -> None:  # noqa: ANN001
    service.force_complete_step.return_value = {
        **PLAN,
        "dry_run": False,
        "revoke_attempt": "completed",
        "forced": False,
    }
    service.delete_account.return_value = DeletionOutcome(status="done", counts={})
    assert force.main([*ARGS, "--reason", "app removed", "--confirm"]) == 0
    assert _last(capsys) == {"forced": False, "status": "done"}


def test_a_step_pending_under_7_days_is_refused(service, capsys) -> None:  # noqa: ANN001
    service.force_complete_step.side_effect = AccountDeletionRejected(
        "step_pending_under_7_days"
    )
    assert force.main([*ARGS, "--reason", "app removed", "--confirm"]) == 1
    service.delete_account.assert_not_called()
    assert _last(capsys) == {"forced": False, "reason": "step_pending_under_7_days"}


def test_still_pending_elsewhere_is_reported(service, capsys) -> None:  # noqa: ANN001
    service.force_complete_step.return_value = {**PLAN, "forced": True}
    service.delete_account.side_effect = AccountDeletionIncomplete(
        "third_party_pending", ["plaid"]
    )
    assert force.main([*ARGS, "--reason", "app removed", "--confirm"]) == 0
    assert _last(capsys)["pending"] == ["plaid"]


def test_refuses_an_email_in_the_reason_and_unknown_steps(service) -> None:  # noqa: ANN001
    with pytest.raises(SystemExit) as exited:
        force.main([*ARGS, "--reason", "asked by someone@example.com"])
    assert exited.value.code == 2
    with pytest.raises(SystemExit):
        force.main(
            ["--user-id", USER, "--step", "storage", "--operator", "x", "--reason", "y"]
        )
    service.force_complete_step.assert_not_called()


def test_no_run_waiting_is_a_failure(service, capsys) -> None:  # noqa: ANN001
    service.force_complete_step.side_effect = AccountDeletionRejected(
        "no_run_awaiting_third_parties"
    )
    assert force.main([*ARGS, "--reason", "app removed", "--confirm"]) == 1
    service.delete_account.assert_not_called()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("DATABASE_URL", ""),
        ("DATABASE_URL", "not-a-url"),
        ("SUPABASE_URL", ""),
        ("SUPABASE_SERVICE_ROLE_KEY", ""),
    ],
)
def test_refused_target_never_constructs_the_deletion_service(
    monkeypatch,
    name,
    value,
) -> None:
    from argus.api import account_deletion_runtime

    for key, configured in ENV.items():
        monkeypatch.setenv(key, configured)
    monkeypatch.delenv("SUPABASE_PROJECT_URL", raising=False)
    monkeypatch.setenv(name, value)
    build = MagicMock()
    monkeypatch.setattr(account_deletion_runtime, "build_service", build)
    with pytest.raises(SystemExit) as exited:
        force.main([*ARGS, "--reason", "synthetic provider unavailable", "--confirm"])
    assert exited.value.code == 2
    build.assert_not_called()
