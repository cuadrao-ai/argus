from __future__ import annotations

import pytest
from argus.observability import EventCaptureResult
from argus.observability.product_events import (
    _PRODUCT_EVENT_MAP,
    build_product_event,
    capture_product_event,
)


def test_retired_product_events_keep_only_the_kinds_awaiting_rename() -> None:
    """SPEC 0 0C-1: every other product event is gone. These three stay only at
    the call sites 0C-4 and 0C-8 replace with analytics events."""
    cases = {
        "decision_capture": ("decision_saved", "completed", "decision_capture"),
        "receipt_created": ("storage", "completed", "evidence_capture"),
        "account_registration_completed": ("storage", "completed", "guest_acquisition"),
    }
    assert set(_PRODUCT_EVENT_MAP) == set(cases)

    for kind, expected in cases.items():
        envelope = build_product_event(
            kind,
            user_id="user-1",
            conversation_id="conversation-1",
            attributes={"raw_prompt": "do not keep", "safe_count": 1},
        )

        assert (
            envelope.event_type,
            envelope.event_action,
            envelope.feature_area,
        ) == expected
        assert envelope.actor_hash is not None
        assert envelope.actor_hash != "user-1"
        assert envelope.attributes == {"safe_count": 1, "product_event": kind}


@pytest.mark.parametrize("kind", sorted(_PRODUCT_EVENT_MAP))
def test_retired_product_events_stop_at_the_sink(monkeypatch, kind: str) -> None:
    posts: list[object] = []
    monkeypatch.setenv("POSTHOG_PROJECT_TOKEN", "ph_project_token")
    monkeypatch.setenv("POSTHOG_REGION", "us")
    monkeypatch.setattr(
        "argus.observability.envelope.httpx.post",
        lambda *args, **kwargs: posts.append((args, kwargs)),
    )

    result = capture_product_event(kind, user_id="user-1", status="completed")

    assert result.status == "suppressed"
    assert result.reason == "not_an_analytics_event"
    assert posts == []


@pytest.mark.parametrize(
    "kind",
    [
        "evidence_capture",
        "recall_usage",
        "continuity_mismatch",
        "compare_started",
        "next_experiments_offered",
        "next_experiment_selected",
        "eval_readiness",
        "receipt_revoked",
        "receipt_viewed",
        "not_a_registered_product_event",
    ],
)
def test_capture_product_event_unknown_kind_fails_open(monkeypatch, kind: str) -> None:
    captured = []

    def fake_capture(envelope):  # noqa: ANN001
        captured.append(envelope)
        return EventCaptureResult(
            status="captured",
            reason=None,
            event_id=envelope.event_id,
            destination="posthog",
        )

    monkeypatch.setattr("argus.observability.product_events.capture_event", fake_capture)

    result = capture_product_event(kind, user_id="user-1", conversation_id="c-1")

    assert result.status == "failed"
    assert result.reason == "unknown_product_event_kind"
    assert captured == []
