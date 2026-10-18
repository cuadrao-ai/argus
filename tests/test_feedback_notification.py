from __future__ import annotations

import ssl
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from email import message_from_string
from unittest.mock import MagicMock, patch

import pytest
from argus.api import feedback_notification
from argus.api import state as api_state
from argus.api.feedback_notification import (
    FEEDBACK_NOTIFICATION_RECIPIENT,
    build_feedback_notification,
    notify_feedback_submitted,
)
from argus.api.main import app
from argus.api.schemas import OnboardingState, User
from argus.domain.guest_workspaces import GuestWorkspace
from argus.domain.resend_email import SUPPORT_EMAIL_ADDRESS
from argus.domain.store import utcnow
from argus.domain.supabase_gateway import QuotaExceededError, SupabaseGateway
from fastapi.testclient import TestClient
from test_access_approval_email import _FakeSMTP  # noqa: E402

client = TestClient(app)

USER_ID = "00000000-0000-4000-8000-00000000fb01"
ACCOUNT_ROUTES = ("memory", "registered", "guest")
EXPECTED_ACCOUNT_KIND = {
    "memory": "registered",
    "registered": "registered",
    "guest": "guest",
}
ASK_PAYLOAD = {
    "type": "general",
    "message": "neutral rating with tags",
    "context": {
        "source": "feedback_ask",
        "surface": "chat",
        "conversation_id": "conversation-1",
        "message_id": "result-message-1",
        "message_kind": "strategy_result",
        "result_run_id": "run-1",
        "evidence_artifact_id": "evidence-1",
        "rating": "neutral",
        "tags": [],
        "email": "person@example.com",
        "transcript": "Test buy and hold on AAPL",
    },
}
# The ask's pointers survive; contact details and conversation text never do.
SANITIZED_ASK_CONTEXT = {
    "source": "feedback_ask",
    "surface": "chat",
    "conversation_id": "conversation-1",
    "message_id": "result-message-1",
    "message_kind": "strategy_result",
    "result_run_id": "run-1",
    "evidence_artifact_id": "evidence-1",
    "rating": "neutral",
}


def _profile(email: str | None) -> User:
    now = utcnow()
    return User(
        id=USER_ID,
        email=email,
        username=None,
        display_name=None,
        language="en",
        locale="en-US",
        is_admin=False,
        onboarding=OnboardingState(),
        created_at=now,
        updated_at=now,
    )


@contextmanager
def _feedback_route(
    route: str,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[MagicMock | None, dict[str, str]]]:
    """Enter one of the three places POST /feedback saves a submission."""

    if route == "memory":
        with patch.object(api_state, "supabase_gateway", None):
            yield None, {}
        return

    gateway = MagicMock(spec=SupabaseGateway)
    headers: dict[str, str] = {}
    if route == "registered":
        profile = _profile("person@example.com")
        gateway.get_or_create_mock_user.return_value = profile
        gateway.get_auth_user_from_token.return_value = {
            "id": profile.id,
            "email": profile.email,
        }
        gateway.private_alpha_email_allowed.return_value = True
    else:
        monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
        monkeypatch.setenv("ARGUS_MOCK_AUTH", "false")
        monkeypatch.setenv("ARGUS_GUEST_ACCESS_ENABLED", "true")
        monkeypatch.setenv("NEXT_PUBLIC_GUEST_ACCESS_ENABLED", "true")
        profile = _profile(None)
        gateway.get_auth_user_from_token.return_value = {
            "id": USER_ID,
            "email": None,
            "is_anonymous": True,
            "user_metadata": {"language": "en"},
        }
        gateway.get_or_create_profile_for_auth_user.return_value = profile
        gateway.get_active_guest_workspace.return_value = GuestWorkspace(
            user_id=profile.id,
            conversation_id=None,
            status="active",
            created_at=profile.created_at,
            expires_at=profile.created_at + timedelta(days=7),
            claimed_by=None,
            claimed_at=None,
            updated_at=profile.created_at,
        )
        gateway.create_feedback_settling_usage.return_value = {
            "decision": "accepted",
            "replayed": False,
        }
        headers = {"Authorization": "Bearer existing-guest-token"}
    gateway.get_user.return_value = profile
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        patch("argus.api.dependencies.auth_session_is_active", return_value=True),
    ):
        yield gateway, headers


def _saved(route: str, gateway: MagicMock | None, rows_before: int) -> bool:
    if route == "memory":
        return [row["message"] for row in api_state.store.feedback[rows_before:]] == [
            ASK_PAYLOAD["message"]
        ]
    assert gateway is not None
    writer = (
        gateway.create_feedback_settling_usage
        if route == "guest"
        else gateway.create_feedback
    )
    return writer.call_count == 1


def test_notification_carries_the_submission_with_header_safe_escaped_text() -> None:
    message = "Line one\r\nLine <two> & more " + "x" * 120

    notification = build_feedback_notification(
        feedback_type="general",
        message=message,
        context={
            "source": "feedback_ask",
            "rating": "neutral",
            "tags": ["slow", "style"],
        },
        account_kind="guest",
        language="es-419",
    )

    excerpt = notification.subject.removeprefix("Argus feedback (general): ")
    assert excerpt == " ".join(message.split())[:80]
    assert "\r" not in notification.subject and "\n" not in notification.subject
    for line in (
        "Type: general",
        "Account: guest",
        "Language: es-419",
        message,
        "  source: feedback_ask",
        "  rating: neutral",
        "  tags: slow, style",
    ):
        assert line in notification.plain_text
    assert "Line &lt;two&gt; &amp; more" in notification.html
    assert "<two>" not in notification.html
    assert "—" not in notification.subject + notification.plain_text


def test_notification_goes_to_support_through_the_shared_resend_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instances: list[_FakeSMTP] = []

    def _smtp(
        host: str,
        port: int,
        *,
        timeout: float,
        context: ssl.SSLContext,
    ) -> _FakeSMTP:
        instance = _FakeSMTP(host, port, timeout=timeout, context=context)
        instances.append(instance)
        return instance

    monkeypatch.setenv("ARGUS_APPROVAL_EMAIL_SMTP_PASSWORD", "re_test_password")
    monkeypatch.setattr("argus.domain.resend_email.smtplib.SMTP_SSL", _smtp)

    notify_feedback_submitted(
        feedback_type="bug",
        message="Search is slow",
        context={"surface": "chat"},
        account_kind="registered",
        language="en",
    )

    [smtp] = instances
    # The recipient is the API's one support address, the one the access email shows.
    assert (
        FEEDBACK_NOTIFICATION_RECIPIENT
        == SUPPORT_EMAIL_ADDRESS
        == "support@get-argus.com"
    )
    assert (smtp.host, smtp.port) == ("smtp.resend.com", 465)
    assert smtp.login_args == ("resend", "re_test_password")
    assert smtp.mail_from == "no-responder@mail.cuadrao.ai"
    assert smtp.recipient == FEEDBACK_NOTIFICATION_RECIPIENT
    sent = message_from_string(smtp.message or "")
    assert sent["From"] == "Cuadrao <no-responder@mail.cuadrao.ai>"
    assert sent["To"] == FEEDBACK_NOTIFICATION_RECIPIENT
    assert str(sent["Subject"]) == "Argus feedback (bug): Search is slow"
    assert sent["Resend-Idempotency-Key"] is None


@pytest.mark.parametrize("failure", ["missing_credential", "smtp_error"])
def test_a_failed_notification_is_logged_without_the_message_and_never_raised(
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    if failure == "smtp_error":
        monkeypatch.setenv("ARGUS_APPROVAL_EMAIL_SMTP_PASSWORD", "re_test_password")
        monkeypatch.setattr(
            "argus.domain.resend_email.smtplib.SMTP_SSL",
            MagicMock(side_effect=OSError("connection refused")),
        )

    with patch.object(feedback_notification.logger, "warning") as warning:
        notify_feedback_submitted(
            feedback_type="general",
            message="words only the founder should read",
            context={"source": "feedback_ask"},
            account_kind="guest",
            language="en",
        )

    warning.assert_called_once()
    assert "words only the founder should read" not in repr(warning.call_args)


@pytest.mark.parametrize("route", ACCOUNT_ROUTES)
def test_each_accepted_submission_schedules_one_notification_of_the_saved_row(
    monkeypatch: pytest.MonkeyPatch,
    route: str,
) -> None:
    notify = MagicMock()
    monkeypatch.setattr("argus.api.routers.feedback.notify_feedback_submitted", notify)
    rows_before = len(api_state.store.feedback)

    with _feedback_route(route, monkeypatch) as (gateway, headers):
        response = client.post("/api/v1/feedback", json=ASK_PAYLOAD, headers=headers)

        assert response.status_code == 200
        assert _saved(route, gateway, rows_before)
    notify.assert_called_once()
    kwargs = notify.call_args.kwargs
    assert kwargs["feedback_type"] == ASK_PAYLOAD["type"]
    assert kwargs["message"] == ASK_PAYLOAD["message"]
    assert kwargs["context"] == SANITIZED_ASK_CONTEXT
    assert kwargs["account_kind"] == EXPECTED_ACCOUNT_KIND[route]
    assert "person@example.com" not in repr(kwargs)


@pytest.mark.parametrize("route", ACCOUNT_ROUTES)
def test_a_failed_email_still_saves_the_feedback(
    monkeypatch: pytest.MonkeyPatch,
    route: str,
) -> None:
    sender = MagicMock(side_effect=RuntimeError("Resend SMTP delivery was not accepted."))
    monkeypatch.setattr("argus.api.feedback_notification.send_resend_email", sender)
    rows_before = len(api_state.store.feedback)

    with _feedback_route(route, monkeypatch) as (gateway, headers):
        response = client.post("/api/v1/feedback", json=ASK_PAYLOAD, headers=headers)

        assert response.status_code == 200
        assert response.json() == {"success": True}
        assert _saved(route, gateway, rows_before)
    sender.assert_called_once()


@pytest.mark.parametrize(
    ("route", "status_code"),
    [("registered", 429), ("guest", 403)],
)
def test_a_rejected_submission_sends_no_notification(
    monkeypatch: pytest.MonkeyPatch,
    route: str,
    status_code: int,
) -> None:
    notify = MagicMock()
    monkeypatch.setattr("argus.api.routers.feedback.notify_feedback_submitted", notify)

    with _feedback_route(route, monkeypatch) as (gateway, headers):
        assert gateway is not None
        gateway.check_and_increment_usage_limits.side_effect = QuotaExceededError(
            "Quota exceeded for feedback (hour)"
        )
        gateway.create_feedback_settling_usage.return_value = {
            "decision": "conversion_required"
        }
        response = client.post("/api/v1/feedback", json=ASK_PAYLOAD, headers=headers)

    assert response.status_code == status_code
    notify.assert_not_called()
