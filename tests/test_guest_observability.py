from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from argus.api.dependencies import current_user
from argus.api.guest_access import guest_account_context
from argus.api.guest_observability import (
    emit_first_guest_message_event,
    emit_guest_funnel_event,
)
from argus.api.main import app
from argus.api.schemas import OnboardingState, User
from argus.domain.guest_workspaces import GuestWorkspace
from argus.domain.usage_limits import MESSAGE_USAGE_RESOURCE
from argus.observability import sanitize_observability_attributes
from argus.observability.guest_funnel import (
    GUEST_FUNNEL_EVENT_MAP,
    build_guest_funnel_event,
)
from fastapi.testclient import TestClient

# Retired from PostHog by SPEC 0 package 0C-1. What is left is only what a later
# package renames at its call site (0C-3 and 0C-4).
APPROVED_GUEST_FUNNEL_EVENTS = {
    "first_useful_assistant_response_completed",
    "account_creation_completed",
    "existing_account_sign_in_completed",
}
REMOVED_GUEST_FUNNEL_EVENTS = {
    "guest_session_started",
    "starter_action_selected",
    "confirmation_reached",
    "first_simulation_admitted",
    "first_result_completed",
    "conversion_prompt_shown",
    "temporary_workspace_claimed",
    "guest_limit_reached",
    "guest_feedback_submitted",
    "guest_session_expired",
}

GUEST_USER_ID = "00000000-0000-0000-0000-000000000091"


def _guest_profile() -> User:
    now = datetime.now(timezone.utc)
    return User(
        id=GUEST_USER_ID,
        email=None,
        language="en",
        locale="en-US",
        is_admin=False,
        onboarding=OnboardingState(),
        created_at=now,
        updated_at=now,
    )


def _guest_context():
    profile = _guest_profile()
    return guest_account_context(
        GuestWorkspace(
            user_id=profile.id,
            conversation_id="conversation-1",
            status="active",
            created_at=profile.created_at,
            expires_at=profile.created_at.replace(year=profile.created_at.year + 1),
            claimed_by=None,
            claimed_at=None,
            updated_at=profile.updated_at,
        )
    )


def test_guest_funnel_event_contract_is_complete_and_uses_the_shared_envelope() -> None:
    assert set(GUEST_FUNNEL_EVENT_MAP) == APPROVED_GUEST_FUNNEL_EVENTS

    for kind in sorted(APPROVED_GUEST_FUNNEL_EVENTS):
        envelope = build_guest_funnel_event(
            kind,
            user_id="guest-user-1",
            language="es-419",
            surface="chat",
            terminal_outcome="completed",
        )

        assert envelope.schema_version == "argus_observability_event/v1"
        assert envelope.feature_area == "guest_acquisition"
        assert envelope.privacy_mode == "metadata_only"
        assert envelope.actor_hash
        assert envelope.actor_hash != "guest-user-1"
        assert envelope.provider is None
        assert envelope.model is None
        assert envelope.route_receipt_id is None
        assert envelope.attributes == {
            "language": "es-419",
            "product_event": kind,
            "surface": "chat",
            "terminal_outcome": "completed",
        }


def test_guest_funnel_sanitizer_removes_every_forbidden_property() -> None:
    sanitized = sanitize_observability_attributes(
        {
            "language": "en",
            "surface": "conversion_modal",
            "conversion_reason": "save_decision",
            "terminal_outcome": "shown",
            "prompt": "Buy $100,000 of AAPL from 2024-01-01",
            "assistant_prose": "Private response",
            "capital": 100_000,
            "start_date": "2024-01-01",
            "end_date": "2025-01-01",
            "email": "person@example.com",
            "display_name": "Private Person",
            "conversation_title": "Private title",
            "conversation_preview": "Private preview",
            "cookie": "session=secret",
            "authorization_header": "Bearer secret",
            "ip_address": "203.0.113.8",
            "url": "https://argus.test/chat?token=secret",
            "auth_material": {"session": "secret"},
            "model": "internal-model",
            "provider": "internal-provider",
        }
    )

    assert sanitized == {
        "language": "en",
        "surface": "conversion_modal",
        "conversion_reason": "save_decision",
        "terminal_outcome": "shown",
    }


def test_browser_guest_event_endpoint_is_gone() -> None:
    """The browser sends no analytics of its own (SPEC 0, 0C-1)."""
    app.dependency_overrides[current_user] = _guest_profile
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/analytics/guest-events",
                json={
                    "event": "conversion_prompt_shown",
                    "language": "en",
                    "surface": "conversion_modal",
                    "conversion_reason": "save_decision",
                    "terminal_outcome": "shown",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_first_useful_response_emits_only_at_the_first_settled_unit() -> None:
    account = _guest_context()
    with (
        patch(
            "argus.api.guest_observability.current_guest_usage_count",
            side_effect=[1, 2],
        ),
        patch("argus.api.guest_observability.capture_guest_funnel_event") as capture,
    ):
        emit_first_guest_message_event(
            account=account,
            user_id=GUEST_USER_ID,
            conversation_id="conversation-1",
            message_id="message-1",
            language="en",
        )
        emit_first_guest_message_event(
            account=account,
            user_id=GUEST_USER_ID,
            conversation_id="conversation-1",
            message_id="message-2",
            language="en",
        )

    capture.assert_called_once_with(
        "first_useful_assistant_response_completed",
        user_id=GUEST_USER_ID,
        conversation_id="conversation-1",
        message_id="message-1",
        language="en",
        surface="chat",
        product_capability="chat",
        terminal_outcome="completed",
    )


def test_registered_context_never_emits_a_guest_event() -> None:
    from argus.api.guest_access import registered_account_context

    with patch("argus.api.guest_observability.capture_guest_funnel_event") as capture:
        emit_guest_funnel_event(
            account=registered_account_context("registered-user"),
            kind="first_useful_assistant_response_completed",
            user_id="registered-user",
            surface="chat",
            product_capability="chat",
            terminal_outcome="completed",
        )

    capture.assert_not_called()


@pytest.mark.parametrize(
    ("relative_path", "events"),
    [
        (
            "src/argus/api/routers/auth.py",
            {
                "account_creation_completed",
                "existing_account_sign_in_completed",
            },
        ),
        (
            "src/argus/api/guest_observability.py",
            {"first_useful_assistant_response_completed"},
        ),
        ("src/argus/api/chat/backtest_admission_flow.py", set()),
        ("src/argus/api/routers/feedback.py", set()),
        ("src/argus/domain/guest_cleanup.py", set()),
    ],
)
def test_server_owners_emit_only_the_guest_events_awaiting_rename(
    relative_path: str,
    events: set[str],
) -> None:
    source = (Path(__file__).parents[1] / relative_path).read_text()

    for event in events:
        assert f'"{event}"' in source
    for event in REMOVED_GUEST_FUNNEL_EVENTS:
        # An emit names its kind first or as ``kind=``; the same word may
        # still appear elsewhere (``guest_session_expired`` is an error code).
        assert not re.search(rf'(?:_event\(\s*|kind=)"{event}"', source), event


def test_first_message_reader_uses_guest_session_counter_truth() -> None:
    account = _guest_context()
    with patch(
        "argus.api.guest_observability.current_guest_usage_count",
        return_value=1,
    ) as count:
        emit_first_guest_message_event(
            account=account,
            user_id=GUEST_USER_ID,
            conversation_id="conversation-1",
            message_id="message-1",
            language="en",
        )

    count.assert_called_once_with(
        account=account,
        user_id=GUEST_USER_ID,
        resource=MESSAGE_USAGE_RESOURCE,
    )


def test_checked_openapi_no_longer_has_the_guest_browser_event_contract() -> None:
    checked = (Path(__file__).parents[1] / "docs/api/openapi.yaml").read_text(
        encoding="utf-8"
    )
    generated = app.openapi()

    assert "/api/v1/analytics/guest-events" not in generated["paths"]
    assert "GuestFunnelClientEventRequest" not in generated["components"]["schemas"]
    assert "/api/v1/analytics/guest-events:" not in checked
    assert "GuestFunnelClientEventRequest:" not in checked
