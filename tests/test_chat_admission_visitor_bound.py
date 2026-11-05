"""Visitor-day bound at chat admission: replay always resolves first.

A retry of an already-admitted run must return its existing job — the
visitor limit only gates fresh reservations.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from argus.api.chat import backtest_admission_flow as flow
from argus.api.chat.backtest_jobs import BacktestJobShadowContext


def _context() -> BacktestJobShadowContext:
    context = BacktestJobShadowContext(
        user_id="00000000-0000-0000-0000-000000000051",
        conversation_id="00000000-0000-0000-0000-000000000052",
        account_kind="guest",
        idempotency_key="guest-sim-retry",
        request_id="req-1",
        allowance_limits=[
            {
                "period": "guest_session",
                "limit": 2,
                "period_start": "2026-07-28T00:00:00+00:00",
                "period_end": "2026-08-04T00:00:00+00:00",
            }
        ],
        visitor_key="visitor:test-digest",
    )
    return context


def _gateway(*, reservation: dict[str, Any] | None, decision: str) -> MagicMock:
    gateway = MagicMock()
    gateway.get_backtest_job_reservation.return_value = reservation
    gateway.admit_backtest_job.return_value = {
        "decision": decision,
        "job": {"id": "job-1", "status": "queued"},
    }
    return gateway


def _admit(gateway: MagicMock) -> flow.ChatAdmissionResult:
    return flow.admit_durable_chat_job(
        gateway=gateway,
        context=_context(),
        identity_hash=f"sha256:{'a' * 64}",
        payload_digest=f"sha256:{'b' * 64}",
        launch_payload={"kind": "proof"},
        reconcile_blockers=lambda **kwargs: False,
    )


def test_exhausted_visitor_with_existing_reservation_replays(monkeypatch) -> None:
    monkeypatch.setattr(flow, "visitor_within_limits", lambda *a, **k: False)
    gateway = _gateway(reservation={"id": "job-1"}, decision="replay")

    result = _admit(gateway)

    assert result.decision == "replay"
    gateway.admit_backtest_job.assert_called_once()


def test_replay_ignores_a_transient_first_simulation_counter_failure(
    monkeypatch,
) -> None:
    gateway = _gateway(reservation={"id": "job-1"}, decision="replay")
    gateway.list_current_usage_counters.side_effect = RuntimeError

    result = _admit(gateway)

    assert result.decision == "replay"
    gateway.admit_backtest_job.assert_called_once()
    gateway.list_current_usage_counters.assert_not_called()


def test_exhausted_visitor_without_reservation_requires_conversion(
    monkeypatch,
) -> None:
    monkeypatch.setattr(flow, "visitor_within_limits", lambda *a, **k: False)
    gateway = _gateway(reservation=None, decision="admitted")

    result = _admit(gateway)

    assert result.decision == "conversion_required"
    gateway.admit_backtest_job.assert_not_called()


def test_fresh_admission_charges_the_visitor_once(monkeypatch) -> None:
    monkeypatch.setattr(flow, "visitor_within_limits", lambda *a, **k: True)
    charges: list[str] = []
    monkeypatch.setattr(
        flow,
        "settle_visitor_usage",
        lambda *a, **k: charges.append(k["visitor_key"]),
    )
    gateway = _gateway(reservation=None, decision="admitted")

    result = _admit(gateway)

    assert result.decision == "admitted"
    assert charges == ["visitor:test-digest"]
    assert (
        gateway.admit_backtest_job.call_args.kwargs["execution_metadata"][
            "openrouter_traffic_class"
        ]
        == "guest"
    )


def test_replay_decision_never_charges_the_visitor(monkeypatch) -> None:
    monkeypatch.setattr(flow, "visitor_within_limits", lambda *a, **k: True)
    charges: list[str] = []
    monkeypatch.setattr(
        flow,
        "settle_visitor_usage",
        lambda *a, **k: charges.append(k["visitor_key"]),
    )
    gateway = _gateway(reservation={"id": "job-1"}, decision="replay")

    result = _admit(gateway)

    assert result.decision == "replay"
    assert charges == []


def test_fresh_admission_sends_no_retired_funnel_event(monkeypatch) -> None:
    """first_simulation_admitted was retired by SPEC 0 package 0C-1; admission
    no longer reads the guest-session counter for it or sends anything."""
    monkeypatch.setattr(flow, "visitor_within_limits", lambda *a, **k: True)
    monkeypatch.setattr(flow, "settle_visitor_usage", lambda *a, **k: None)
    posts: list[object] = []
    monkeypatch.setenv("POSTHOG_PROJECT_TOKEN", "ph_project_token")
    monkeypatch.setenv("POSTHOG_REGION", "us")
    monkeypatch.setattr(
        "argus.observability.envelope.httpx.post",
        lambda *args, **kwargs: posts.append((args, kwargs)),
    )

    gateway = _gateway(reservation=None, decision="admitted")
    _admit(gateway)

    assert posts == []
    gateway.list_current_usage_counters.assert_not_called()
