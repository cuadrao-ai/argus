from __future__ import annotations

import re
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml
from argus.api.guest_access import (
    AccountContext,
    guest_capabilities,
    registered_account_context,
)
from argus.api.main import app
from argus.domain import backtest_admission, usage_limits
from argus.domain.backtest_admission_gateway import admit_backtest_job
from argus.domain.store import AlphaStore, utcnow
from argus.domain.usage_limits import (
    GUEST_FEEDBACK_ALLOWANCE,
    GUEST_SIMULATION_ALLOWANCE,
    SIMULATION_USAGE_RESOURCE,
    allowance_windows,
    settle_memory_usage,
)


def _guest_context() -> AccountContext:
    return AccountContext(
        kind="guest",
        user_id="00000000-0000-0000-0000-000000000051",
        expires_at=utcnow() + timedelta(days=7),
        capabilities=guest_capabilities(),
    )


def test_guest_lifetime_windows_use_fixed_workspace_bounds() -> None:
    account = _guest_context()
    assert account.expires_at is not None
    expected_start = account.expires_at - timedelta(days=7)

    assert allowance_windows(account, "backtest_runs") == [
        {
            "period": "guest_session",
            "limit": GUEST_SIMULATION_ALLOWANCE,
            "period_start": expected_start,
            "period_end": account.expires_at,
        }
    ]
    assert allowance_windows(account, "feedback")[0]["limit"] == (
        GUEST_FEEDBACK_ALLOWANCE
    )


def test_conversation_has_no_allowance_window() -> None:
    # Conversation is compute: no account kind carries a window for it.
    for account in (
        _guest_context(),
        registered_account_context("00000000-0000-0000-0000-000000000054"),
    ):
        with pytest.raises(ValueError, match="chat_messages"):
            allowance_windows(account, "chat_messages")


def test_registered_allowance_windows_remain_hour_and_day() -> None:
    account = registered_account_context("00000000-0000-0000-0000-000000000052")

    assert allowance_windows(account, "backtest_runs") == [
        {"period": "hour", "limit": 10},
        {"period": "day", "limit": 50},
    ]
    assert allowance_windows(account, "feedback") == [
        {"period": "day", "limit": 50},
        {"period": "hour", "limit": 20},
    ]


def test_backtest_gateway_passes_guest_window_to_existing_atomic_owner() -> None:
    client = MagicMock()
    client.rpc.return_value.execute.return_value.data = {
        "decision": "conversion_required"
    }
    windows = allowance_windows(_guest_context(), "backtest_runs")

    outcome = admit_backtest_job(
        client,
        user_id="00000000-0000-0000-0000-000000000051",
        operation_scope="chat.run_backtest",
        idempotency_key="guest-simulation",
        identity_hash=f"sha256:{'a' * 64}",
        payload_hash=f"sha256:{'b' * 64}",
        launch_payload={"kind": "proof"},
        initial_status="queued",
        allowance_limits=windows,
    )

    assert outcome == {"decision": "conversion_required"}
    assert client.rpc.call_args.args[0] == "admit_backtest_job"
    assert client.rpc.call_args.args[1]["p_allowance_limits"] == [
        {
            "period": "guest_session",
            "limit": 2,
            "period_start": windows[0]["period_start"].isoformat(),
            "period_end": windows[0]["period_end"].isoformat(),
        }
    ]


def test_memory_settlement_accepts_guest_dict_window_with_fixed_bounds() -> None:
    account = _guest_context()
    assert account.expires_at is not None
    counters: dict[tuple[str, str, str], dict[str, object]] = {}
    windows = allowance_windows(account, "feedback")

    settle_memory_usage(
        counters,
        user_id=account.user_id,
        resource="feedback",
        limits=windows,
        at=utcnow(),
    )

    row = counters[(account.user_id, "feedback", "guest_session")]
    assert row == {
        "period_start": account.expires_at - timedelta(days=7),
        "period_end": account.expires_at,
        "used_count": 1,
        "limit_count": GUEST_FEEDBACK_ALLOWANCE,
    }


def test_memory_guest_simulation_admission_charges_once_and_replays_zero() -> None:
    account = _guest_context()
    store = AlphaStore()
    windows = allowance_windows(account, SIMULATION_USAGE_RESOURCE)
    common = {
        "store": store,
        "user_id": account.user_id,
        "operation_scope": backtest_admission.DIRECT_RUN_SCOPE,
        "identity_hash": f"sha256:{'a' * 64}",
        "payload_hash": f"sha256:{'b' * 64}",
        "launch_payload": {"kind": "proof"},
        "initial_status": "succeeded",
        "allowance_limits": windows,
    }

    first = backtest_admission.admit_backtest_job_memory(
        idempotency_key="guest-first",
        **common,
    )
    replay = backtest_admission.admit_backtest_job_memory(
        idempotency_key="guest-first",
        **common,
    )
    second = backtest_admission.admit_backtest_job_memory(
        idempotency_key="guest-second",
        **common,
    )
    third = backtest_admission.admit_backtest_job_memory(
        idempotency_key="guest-third",
        **common,
    )

    assert first.kind == "admitted"
    assert replay.kind == "replay"
    assert second.kind == "admitted"
    assert third.kind == "conversion_required"
    row = store.usage_counters[
        (account.user_id, SIMULATION_USAGE_RESOURCE, "guest_session")
    ]
    assert row["used_count"] == 2
    assert len(store.backtest_jobs) == 2


def test_memory_registered_dict_windows_keep_hour_and_day_accounting() -> None:
    account = registered_account_context("00000000-0000-0000-0000-000000000053")
    counters: dict[tuple[str, str, str], dict[str, object]] = {}
    now = utcnow()

    settle_memory_usage(
        counters,
        user_id=account.user_id,
        resource="feedback",
        limits=allowance_windows(account, "feedback"),
        at=now,
    )

    assert counters[(account.user_id, "feedback", "hour")]["used_count"] == 1
    assert counters[(account.user_id, "feedback", "day")]["used_count"] == 1


def test_guest_summary_policy_matches_python_openapi_typescript_and_sql() -> None:
    root = Path(__file__).resolve().parents[1]
    policy = {
        "conversation_limit": getattr(
            usage_limits,
            "GUEST_CONVERSATION_ALLOWANCE",
            None,
        ),
        "simulation_limit": usage_limits.GUEST_SIMULATION_ALLOWANCE,
        "feedback_limit": usage_limits.GUEST_FEEDBACK_ALLOWANCE,
    }
    assert policy == {
        "conversation_limit": 1,
        "simulation_limit": 2,
        "feedback_limit": 5,
    }

    generated = app.openapi()["components"]["schemas"]["GuestAccountSummary"]
    checked = yaml.safe_load(
        (root / "docs" / "api" / "openapi.yaml").read_text(encoding="utf-8")
    )["components"]["schemas"]["GuestAccountSummary"]
    for schema in (generated, checked):
        for field in policy:
            field_schema = schema["properties"][field]
            assert field_schema["type"] == "integer"
            assert field_schema["minimum"] == 1
            assert field_schema["maximum"] == 2_147_483_647
            assert "const" not in field_schema

    typescript = (root / "web" / "lib" / "guest-account.ts").read_text(encoding="utf-8")
    for field in policy:
        assert re.search(rf"\b{field}: number;", typescript)

    migration = (
        root
        / "supabase"
        / "migrations_archive"
        / "20260802090000_raise_guest_simulation_allowance.sql"
    ).read_text(encoding="utf-8")
    # The immutable migration still names chat_messages; that row is retired
    # history now that conversation is compute and settles nothing.
    sql_policy = {
        resource: int(limit)
        for resource, limit in re.findall(
            r"when '(backtest_runs|feedback)' then (\d+)",
            migration,
        )
    }
    assert sql_policy == {
        "backtest_runs": usage_limits.GUEST_SIMULATION_ALLOWANCE,
        "feedback": usage_limits.GUEST_FEEDBACK_ALLOWANCE,
    }
