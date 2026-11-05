"""``GET /me/usage`` keyed by operation class.

Compute is free and reports no window. Grounding projects the retrieval meter
the live rail claims. Execution projects the simulation counters admission
charges, including both guest bounds, so availability here is availability at
admission (#546).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from argus.api.chat import discovery_evidence, research_evidence
from argus.api.routers import profile as profile_router
from argus.domain.guest_workspaces import GuestWorkspace

from tests.test_allowance_accounting import (
    USER_ID,
    _configure_guest_account,
    _FakeVisitorClient,
    client,
    mock_gateway,
)

__all__ = ["mock_gateway"]


def _usage_row(
    resource: str,
    period: str,
    used: int,
    limit: int,
    period_end: str,
) -> dict[str, Any]:
    return {
        "resource": resource,
        "period": period,
        "limit_count": limit,
        "used_count": used,
        "period_end": period_end,
    }


UNBOUNDED_ALLOWANCE = {
    "hour": None,
    "day": None,
    "guest_session": None,
    "available_now": True,
    "limiting_window": None,
}


@pytest.fixture
def research_rail_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARGUS_RESEARCH_RAIL_ENABLED", "true")


def _mock_usage_rows(
    mock_gateway,
    *,
    hour_rows: list[dict[str, Any]],
    day_rows: list[dict[str, Any]],
    resources: set[str] = frozenset({"backtest_runs"}),
) -> None:
    def _list(*, user_id: str, resources: tuple, period: str, at: Any):
        assert user_id == USER_ID
        assert set(resources) == set(expected_resources)
        return hour_rows if period == "hour" else day_rows

    expected_resources = resources
    mock_gateway.list_current_usage_counters.side_effect = _list


def test_me_usage_keys_allowances_by_operation_class(mock_gateway, research_rail_on):
    _mock_usage_rows(
        mock_gateway,
        hour_rows=[_usage_row("backtest_runs", "hour", 1, 10, "2026-07-21T15:00:00Z")],
        day_rows=[_usage_row("backtest_runs", "day", 4, 50, "2026-07-22T00:00:00Z")],
    )

    response = client.get(
        "/api/v1/me/usage", headers={"Authorization": "Bearer test-token"}
    )

    assert response.status_code == 200
    allowances = response.json()["allowances"]
    # The two deprecated aliases ride along for stale bundles; see the alias
    # test below for their derivation.
    assert set(allowances) == {
        "compute",
        "grounding",
        "execution",
        "messages",
        "backtests",
    }
    assert allowances["compute"] == UNBOUNDED_ALLOWANCE
    # Rail on, a signed-in account has no research window of its own.
    assert allowances["grounding"] == UNBOUNDED_ALLOWANCE

    execution = allowances["execution"]
    assert execution["hour"] == {
        "limit": 10,
        "used": 1,
        "remaining": 9,
        "period_end": "2026-07-21T15:00:00Z",
    }
    assert execution["day"] == {
        "limit": 50,
        "used": 4,
        "remaining": 46,
        "period_end": "2026-07-22T00:00:00Z",
    }
    assert execution["guest_session"] is None
    assert execution["available_now"] is True
    assert execution["limiting_window"] == "hour"


def test_me_usage_rail_off_projects_the_discovery_meter_as_grounding(
    mock_gateway, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv("ARGUS_RESEARCH_RAIL_ENABLED", raising=False)
    _mock_usage_rows(
        mock_gateway,
        hour_rows=[
            _usage_row("discovery_searches", "hour", 3, 10, "2026-07-21T15:00:00Z"),
        ],
        day_rows=[
            _usage_row("discovery_searches", "day", 20, 25, "2026-07-22T00:00:00Z"),
        ],
        resources={"backtest_runs", "discovery_searches"},
    )

    response = client.get(
        "/api/v1/me/usage", headers={"Authorization": "Bearer test-token"}
    )

    assert response.status_code == 200
    grounding = response.json()["allowances"]["grounding"]
    assert grounding["hour"]["remaining"] == 7
    assert grounding["day"]["remaining"] == 5
    assert grounding["available_now"] is True
    assert grounding["limiting_window"] == "day"


def test_me_usage_missing_rows_read_zero_without_creating_counters(
    mock_gateway, research_rail_on
):
    _mock_usage_rows(mock_gateway, hour_rows=[], day_rows=[])

    response = client.get(
        "/api/v1/me/usage", headers={"Authorization": "Bearer test-token"}
    )

    assert response.status_code == 200
    execution = response.json()["allowances"]["execution"]
    assert execution["hour"]["used"] == 0
    assert execution["hour"]["limit"] == 10
    assert execution["hour"]["remaining"] == 10
    assert execution["day"]["used"] == 0
    assert execution["day"]["limit"] == 50
    assert execution["day"]["remaining"] == 50
    assert execution["available_now"] is True
    assert execution["hour"]["period_end"] <= execution["day"]["period_end"]
    mock_gateway.check_and_increment_usage_limits.assert_not_called()


def test_me_usage_hourly_limited_while_daily_available(mock_gateway, research_rail_on):
    _mock_usage_rows(
        mock_gateway,
        hour_rows=[
            _usage_row("backtest_runs", "hour", 10, 10, "2026-07-21T15:00:00Z"),
        ],
        day_rows=[
            _usage_row("backtest_runs", "day", 20, 50, "2026-07-22T00:00:00Z"),
        ],
    )

    response = client.get(
        "/api/v1/me/usage", headers={"Authorization": "Bearer test-token"}
    )

    assert response.status_code == 200
    execution = response.json()["allowances"]["execution"]
    assert execution["hour"]["remaining"] == 0
    assert execution["day"]["remaining"] == 30
    assert execution["available_now"] is False
    assert execution["limiting_window"] == "hour"


def test_me_usage_daily_exhaustion_limits_across_fresh_hourly_window(
    mock_gateway, research_rail_on
):
    _mock_usage_rows(
        mock_gateway,
        hour_rows=[],
        day_rows=[
            _usage_row("backtest_runs", "day", 50, 50, "2026-07-22T00:00:00Z"),
        ],
    )

    response = client.get(
        "/api/v1/me/usage", headers={"Authorization": "Bearer test-token"}
    )

    assert response.status_code == 200
    execution = response.json()["allowances"]["execution"]
    assert execution["hour"]["used"] == 0
    assert execution["day"]["remaining"] == 0
    assert execution["available_now"] is False
    assert execution["limiting_window"] == "day"


def test_me_usage_used_beyond_limit_clamps_remaining_to_zero(
    mock_gateway, research_rail_on
):
    _mock_usage_rows(
        mock_gateway,
        hour_rows=[],
        day_rows=[
            _usage_row("backtest_runs", "day", 53, 50, "2026-07-22T00:00:00Z"),
        ],
    )

    response = client.get(
        "/api/v1/me/usage", headers={"Authorization": "Bearer test-token"}
    )

    assert response.status_code == 200
    execution = response.json()["allowances"]["execution"]
    assert execution["day"]["used"] == 53
    assert execution["day"]["remaining"] == 0
    assert execution["available_now"] is False


def _configure_guest_usage(
    mock_gateway,
    monkeypatch: pytest.MonkeyPatch,
    *,
    visitor_used: dict[str, int],
    workspace_simulations_used: int,
    expires_at: datetime | None = None,
) -> GuestWorkspace:
    monkeypatch.setenv("CUADRAO_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_GUEST_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    workspace = _configure_guest_account(mock_gateway)
    if expires_at is not None:
        workspace = workspace.model_copy(update={"expires_at": expires_at})
        mock_gateway.get_active_guest_workspace.return_value = workspace
    # Visitor-keyed day windows survive a renewed workspace...
    mock_gateway.client = _FakeVisitorClient(visitor_used)

    # ...and the workspace-lifetime window is the one admission also holds.
    def _list(*, user_id, resources, period, at, period_start=None):
        assert user_id == workspace.user_id
        assert period == "guest_session"
        assert set(resources) == {"backtest_runs"}
        assert period_start == workspace.expires_at - timedelta(days=7)
        if workspace_simulations_used == 0:
            return []
        return [
            {
                "resource": "backtest_runs",
                "limit_count": 2,
                "used_count": workspace_simulations_used,
                "period_end": workspace.expires_at.isoformat(),
            }
        ]

    mock_gateway.list_current_usage_counters.side_effect = _list
    return workspace


def test_guest_me_usage_keys_allowances_by_operation_class(
    mock_gateway,
    monkeypatch: pytest.MonkeyPatch,
    research_rail_on,
):
    workspace = _configure_guest_usage(
        mock_gateway,
        monkeypatch,
        visitor_used={"research_searches": 1, "backtest_runs": 1},
        workspace_simulations_used=1,
    )

    response = client.get(
        "/api/v1/me/usage", headers={"Authorization": "Bearer guest-token"}
    )

    assert response.status_code == 200
    allowances = response.json()["allowances"]
    assert allowances["compute"] == UNBOUNDED_ALLOWANCE

    grounding = allowances["grounding"]
    assert grounding["hour"] is None
    assert grounding["guest_session"] is None
    assert grounding["day"]["limit"] == 3
    assert grounding["day"]["used"] == 1
    assert grounding["day"]["remaining"] == 2
    assert grounding["available_now"] is True
    assert grounding["limiting_window"] == "day"

    execution = allowances["execution"]
    assert execution["hour"] is None
    assert execution["day"] == {
        "limit": 2,
        "used": 1,
        "remaining": 1,
        "period_end": execution["day"]["period_end"],
    }
    assert execution["guest_session"] == {
        "limit": 2,
        "used": 1,
        "remaining": 1,
        "period_end": workspace.expires_at.isoformat().replace("+00:00", "Z"),
    }
    assert execution["available_now"] is True


def test_guest_me_usage_rail_off_projects_the_discovery_allowance(
    mock_gateway, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv("ARGUS_RESEARCH_RAIL_ENABLED", raising=False)
    _configure_guest_usage(
        mock_gateway,
        monkeypatch,
        visitor_used={"discovery_searches": 2},
        workspace_simulations_used=0,
    )

    response = client.get(
        "/api/v1/me/usage", headers={"Authorization": "Bearer guest-token"}
    )

    assert response.status_code == 200
    grounding = response.json()["allowances"]["grounding"]
    assert grounding["day"]["limit"] == 2
    assert grounding["day"]["remaining"] == 0
    assert grounding["available_now"] is False
    assert grounding["limiting_window"] == "day"


@pytest.mark.parametrize(
    ("day_used", "workspace_used", "available_now", "limiting_window"),
    [
        # Fresh on both clocks: the coarser window names the reset that holds.
        (0, 0, True, "guest_session"),
        (1, 1, True, "guest_session"),
        # #546: the workspace is spent although the visitor day reset.
        (0, 2, False, "guest_session"),
        # The day is spent while the workspace still has one.
        (2, 1, False, "day"),
        # Both spent: midnight would not unblock, so the expiry is the truth.
        (2, 2, False, "guest_session"),
    ],
)
def test_guest_execution_availability_holds_every_enforced_bound(
    mock_gateway,
    monkeypatch: pytest.MonkeyPatch,
    research_rail_on,
    day_used: int,
    workspace_used: int,
    available_now: bool,
    limiting_window: str,
):
    workspace = _configure_guest_usage(
        mock_gateway,
        monkeypatch,
        visitor_used={"backtest_runs": day_used},
        workspace_simulations_used=workspace_used,
    )

    response = client.get(
        "/api/v1/me/usage", headers={"Authorization": "Bearer guest-token"}
    )

    assert response.status_code == 200
    execution = response.json()["allowances"]["execution"]
    assert execution["day"]["remaining"] == 2 - day_used
    assert execution["guest_session"]["remaining"] == 2 - workspace_used
    assert execution["guest_session"]["period_end"] == (
        workspace.expires_at.isoformat().replace("+00:00", "Z")
    )
    assert execution["available_now"] is available_now
    assert execution["limiting_window"] == limiting_window


@pytest.mark.parametrize("account", ["registered", "guest"])
def test_deprecated_aliases_mirror_the_classes_for_stale_bundles(
    mock_gateway,
    monkeypatch: pytest.MonkeyPatch,
    research_rail_on,
    account: str,
):
    # Deployed bundles read messages and backtests until they reload; both
    # derive from the classes, so a stale tab sees the same truth.
    if account == "guest":
        _configure_guest_usage(
            mock_gateway,
            monkeypatch,
            visitor_used={"backtest_runs": 2},
            workspace_simulations_used=1,
        )
        headers = {"Authorization": "Bearer guest-token"}
    else:
        _mock_usage_rows(mock_gateway, hour_rows=[], day_rows=[])
        headers = {"Authorization": "Bearer test-token"}

    response = client.get("/api/v1/me/usage", headers=headers)

    assert response.status_code == 200
    allowances = response.json()["allowances"]
    assert allowances["messages"] == allowances["compute"] == UNBOUNDED_ALLOWANCE
    assert allowances["backtests"] == allowances["execution"]


@pytest.mark.parametrize(
    ("expiry_offset", "limiting_window"),
    [
        # Workspace expires this afternoon: the visitor day still holds past
        # the renewal, so it names the later reset.
        (timedelta(hours=2), "day"),
        # Workspace outlives midnight: its expiry is the reset that holds.
        (timedelta(days=3), "guest_session"),
    ],
)
def test_guest_execution_tie_names_the_window_that_resets_later(
    mock_gateway,
    monkeypatch: pytest.MonkeyPatch,
    research_rail_on,
    expiry_offset: timedelta,
    limiting_window: str,
):
    frozen = datetime(2026, 9, 8, 10, 0, tzinfo=timezone.utc)

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return frozen if tz is not None else frozen.replace(tzinfo=None)

    monkeypatch.setattr(profile_router, "datetime", _FrozenDatetime)
    _configure_guest_usage(
        mock_gateway,
        monkeypatch,
        visitor_used={"backtest_runs": 2},
        workspace_simulations_used=2,
        expires_at=frozen + expiry_offset,
    )

    response = client.get(
        "/api/v1/me/usage", headers={"Authorization": "Bearer guest-token"}
    )

    assert response.status_code == 200
    execution = response.json()["allowances"]["execution"]
    assert execution["day"]["remaining"] == 0
    assert execution["guest_session"]["remaining"] == 0
    assert execution["available_now"] is False
    assert execution["limiting_window"] == limiting_window


@pytest.mark.parametrize("rail_on", [True, False])
def test_grounding_projection_names_the_meter_the_rail_charges(
    monkeypatch: pytest.MonkeyPatch, rail_on: bool
):
    # One owner per rail: the projection reads the same descriptor the
    # claim and the discovery charge read, so they cannot drift apart.
    if rail_on:
        monkeypatch.setenv("ARGUS_RESEARCH_RAIL_ENABLED", "true")
    else:
        monkeypatch.delenv("ARGUS_RESEARCH_RAIL_ENABLED", raising=False)
    for is_guest in (True, False):
        expected = (
            research_evidence.research_meter(is_guest=is_guest)
            if rail_on
            else discovery_evidence.discovery_meter(is_guest=is_guest)
        )
        assert research_evidence.grounding_meter(is_guest=is_guest) == expected
    assert research_evidence.research_meter(is_guest=True).resource == (
        research_evidence.RESEARCH_USAGE_RESOURCE
    )
    assert research_evidence.research_meter(is_guest=False).limits == []
