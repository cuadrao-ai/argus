from __future__ import annotations

import hashlib
import json
import ssl
from email import message_from_string
from unittest.mock import MagicMock

import pytest
from argus.api import state as api_state
from argus.api.main import app
from argus.api.schemas import Language
from argus.domain.access_approval_email import (
    ACCESS_WELCOME_CONTENT_VERSION,
    AccessWelcomeSendResult,
    build_access_welcome_email,
    send_access_welcome_email,
)
from fastapi.testclient import TestClient

client = TestClient(app)


class _StatefulApprovalGateway:
    def __init__(
        self,
        *,
        role: str | None = "requested",
        language: Language = "en",
        disabled: bool = False,
    ) -> None:
        self.role = role
        self.language = language
        self.disabled = disabled
        self.deliveries: dict[str, dict[str, str]] = {}
        self.events: list[str] = []
        self.complete_result: bool | None = None
        self.complete_error: Exception | None = None
        self.delivery_lookup_error: Exception | None = None
        self.claim_error: Exception | None = None
        self.claim_send_allowed = True
        self.claims: dict[str, dict[str, object]] = {}

    @staticmethod
    def _normalize(email: str) -> str:
        return email.strip().lower()

    def get_private_alpha_access_welcome_delivery(
        self,
        email: str,
    ) -> dict[str, str] | None:
        if self.delivery_lookup_error is not None:
            raise self.delivery_lookup_error
        return self.deliveries.get(self._normalize(email))

    def get_requested_private_alpha_access(self, email: str) -> dict[str, object] | None:
        if self.role != "requested" or self.disabled:
            return None
        return {
            "email": self._normalize(email),
            "role": self.role,
            "language": self.language,
            "disabled_at": None,
        }

    def claim_private_alpha_access_welcome(
        self,
        *,
        email: str,
        language: Language,
        content_version: str,
        subject: str,
    ) -> dict[str, object] | None:
        self.events.append("claim")
        if self.claim_error is not None:
            raise self.claim_error
        if self.role != "requested" or self.disabled or language != self.language:
            return None
        normalized = self._normalize(email)
        claim = self.claims.setdefault(
            normalized,
            {
                "recipient_email": normalized,
                "language": language,
                "content_version": content_version,
                "subject": subject,
                "claim_token": "11111111-1111-4111-8111-111111111111",
                "claimed_at": "2026-08-12T14:27:17Z",
                "send_allowed": self.claim_send_allowed,
            },
        )
        return claim

    def complete_private_alpha_access_welcome(
        self,
        *,
        email: str,
        language: Language,
        content_version: str,
        subject: str,
        provider_receipt: str,
        claim_token: str | None,
    ) -> bool:
        self.events.append("complete")
        if self.complete_error is not None:
            raise self.complete_error
        if self.complete_result is not None:
            return self.complete_result

        normalized = self._normalize(email)
        delivery = self.deliveries.get(normalized)
        claim = self.claims.get(normalized)
        if (
            self.role not in {"requested", "user"}
            or self.disabled
            or language != self.language
        ):
            return False

        def _matches(record: dict[str, object]) -> bool:
            return (
                record["language"] == language
                and record["content_version"] == content_version
                and record["subject"] == subject
            )

        if claim_token is None:
            # An open claim means a send is owed; only a finished grant replays.
            if claim is not None or self.role != "user":
                return False
            return delivery is not None and _matches(delivery)

        if claim is not None:
            if claim["claim_token"] != claim_token or not _matches(claim):
                return False
            self.deliveries[normalized] = {
                "recipient_email": normalized,
                "language": language,
                "content_version": content_version,
                "subject": subject,
                "provider_receipt": provider_receipt,
                "sent_at": "2026-08-12T14:27:17Z",
            }
            self.claims.pop(normalized)
            self.role = "user"
            return True

        if self.role != "user":
            return False
        return delivery is not None and _matches(delivery)


class _FakeSMTP:
    def __init__(
        self,
        host: str,
        port: int,
        *,
        timeout: float,
        context: ssl.SSLContext,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.context = context
        self.login_args: tuple[str, str] | None = None
        self.mail_from: str | None = None
        self.recipient: str | None = None
        self.message: str | None = None
        self.data_receipt = b"Queued. resend-message-id"

    def __enter__(self) -> "_FakeSMTP":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def login(self, username: str, password: str) -> None:
        self.login_args = (username, password)

    def mail(self, sender: str) -> tuple[int, bytes]:
        self.mail_from = sender
        return 250, b"sender accepted"

    def rcpt(self, recipient: str) -> tuple[int, bytes]:
        self.recipient = recipient
        return 250, b"recipient accepted"

    def data(self, message: str) -> tuple[int, bytes]:
        self.message = message
        return 250, self.data_receipt


@pytest.mark.parametrize(
    (
        "language",
        "subject",
        "welcome_line",
        "product_line",
        "first_action",
        "cta_line",
        "button_label",
        "fallback_line",
        "support_line",
    ),
    [
        (
            "en",
            "Welcome to Argus",
            "Welcome to Argus. Your access has been granted.",
            "Argus is AI-powered investing and trading idea validation for everyone.",
            "Start by describing an investing idea in plain language and running "
            "your first historical test.",
            "Create your Argus account:",
            "Create your Argus account",
            "If the button does not work, open this link:",
            "Questions? Contact support@get-argus.com.",
        ),
        (
            "es-419",
            "Bienvenido a Argus",
            "Bienvenido a Argus. Tu acceso fue aprobado.",
            "Argus usa IA para validar ideas de inversión y trading para todos.",
            "Empieza por describir una idea de inversión en lenguaje sencillo y "
            "realizar tu primera prueba histórica.",
            "Crea tu cuenta de Argus:",
            "Crea tu cuenta de Argus",
            "Si el botón no funciona, abre este enlace:",
            "¿Tienes preguntas? Escribe a support@get-argus.com.",
        ),
    ],
)
def test_access_welcome_content_is_literal_bilingual_and_transactional(
    language: Language,
    subject: str,
    welcome_line: str,
    product_line: str,
    first_action: str,
    cta_line: str,
    button_label: str,
    fallback_line: str,
    support_line: str,
) -> None:
    signup_url = "https://app.example/?auth=signup"

    content = build_access_welcome_email(
        language=language,
        signup_url=signup_url,
    )

    assert content.subject == subject
    assert content.plain_text == (
        f"{welcome_line}\n\n"
        f"{product_line}\n\n"
        f"{first_action}\n\n"
        f"{cta_line}\n"
        f"{signup_url}\n\n"
        f"{support_line}"
    )
    for literal in (
        welcome_line,
        product_line,
        first_action,
        button_label,
        fallback_line,
        signup_url,
        support_line,
    ):
        assert literal in content.html
    assert content.plain_text.count(first_action) == 1
    assert content.html.count(first_action) == 1
    combined = f"{content.plain_text}\n{content.html}".lower()
    assert "unsubscribe" not in combined
    assert "cancelar la suscripción" not in combined
    assert "confirm your email" not in combined
    assert "confirma tu correo" not in combined
    assert "\u2014" not in combined


def test_access_welcome_html_uses_canonical_auth_email_shell() -> None:
    content = build_access_welcome_email(
        language="en",
        signup_url="https://app.example/?auth=signup",
    )

    canonical_fragments = (
        '<body style="margin:0;padding:0;background:#f4f4f4;">',
        'style="background:#f4f4f4;border-collapse:collapse;"',
        "max-width:600px;background:#ffffff;border:1px solid #c9c9cd;"
        "border-radius:20px;border-collapse:separate;overflow:hidden;",
        'style="background:#191c1f;padding:22px 28px;color:#ffffff;"',
        '<img src="https://arguschat.ai/icons/argus-192.png" width="36" '
        'height="36" alt="" style="display:block;width:36px;height:36px;'
        'border:0;outline:none;text-decoration:none;">',
        "font-family:'Space Grotesk',Arial,Helvetica,sans-serif;font-size:21px;"
        "font-weight:700;letter-spacing:0.12em;line-height:1;color:#ffffff;",
        "padding:32px 28px 28px;color:#191c1f;font-family:'Inter',Arial,"
        "Helvetica,sans-serif;font-size:16px;line-height:1.55;",
        "font-family:'Space Grotesk','Inter',Arial,Helvetica,sans-serif;"
        "font-size:28px;font-weight:500;letter-spacing:-0.01em;line-height:1.2;",
        "display:inline-block;background:#191c1f;color:#ffffff;"
        "text-decoration:none;font-weight:700;padding:13px 22px;"
        "border-radius:9999px;",
        '<a href="https://app.example/?auth=signup" style="color:#3036b3;">',
        "padding:20px 28px;border-top:1px solid #e1e1e4;color:#5f6368;"
        "font-family:'Inter',Arial,Helvetica,sans-serif;font-size:13px;"
        "line-height:1.5;",
    )
    for fragment in canonical_fragments:
        assert fragment in content.html

    assert content.html.index("Questions? Contact support@get-argus.com.") > (
        content.html.index("border-top:1px solid #e1e1e4")
    )


@pytest.mark.parametrize(
    ("language", "subject", "product_line", "first_action"),
    [
        (
            "en",
            "Welcome to Argus",
            "Argus is AI-powered investing and trading idea validation for everyone.",
            "Start by describing an investing idea in plain language and running "
            "your first historical test.",
        ),
        (
            "es-419",
            "Bienvenido a Argus",
            "Argus usa IA para validar ideas de inversión y trading para todos.",
            "Empieza por describir una idea de inversión en lenguaje sencillo y "
            "realizar tu primera prueba histórica.",
        ),
    ],
)
def test_access_welcome_sender_preserves_smtp_and_multipart_contract(
    monkeypatch: pytest.MonkeyPatch,
    language: Language,
    subject: str,
    product_line: str,
    first_action: str,
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
    monkeypatch.setattr(
        "argus.domain.resend_email.smtplib.SMTP_SSL",
        _smtp,
    )

    result = send_access_welcome_email(
        recipient=" Person@Example.COM ",
        language=language,
        signup_url="https://app.example/?auth=signup",
        claim_token="11111111-1111-4111-8111-111111111111",
    )

    assert result == AccessWelcomeSendResult(
        subject=subject,
        content_version="private-alpha-access-welcome/v1",
        provider_receipt="Queued. resend-message-id",
    )
    assert result.content_version == ACCESS_WELCOME_CONTENT_VERSION
    assert len(instances) == 1
    smtp = instances[0]
    assert (smtp.host, smtp.port) == ("smtp.resend.com", 465)
    assert smtp.login_args == ("resend", "re_test_password")
    assert smtp.context.verify_mode == ssl.CERT_REQUIRED
    assert smtp.context.check_hostname is True
    assert smtp.mail_from == "no-responder@mail.cuadrao.ai"
    assert smtp.recipient == "person@example.com"
    assert smtp.message is not None

    message = message_from_string(smtp.message)
    assert message["From"] == "Cuadrao <no-responder@mail.cuadrao.ai>"
    assert message["To"] == "person@example.com"
    assert str(message["Subject"]) == subject
    assert message["Resend-Idempotency-Key"].startswith("sha256:")
    assert "person@example.com" not in message["Resend-Idempotency-Key"]
    assert message.get_content_type() == "multipart/alternative"
    payloads = {
        part.get_content_type(): part.get_payload(decode=True).decode(
            part.get_content_charset() or "utf-8"
        )
        for part in message.walk()
        if part.get_content_maintype() != "multipart"
    }
    assert set(payloads) == {"text/plain", "text/html"}
    assert product_line in payloads["text/plain"]
    assert product_line in payloads["text/html"]
    assert payloads["text/plain"].count(first_action) == 1
    assert payloads["text/html"].count(first_action) == 1
    assert "support@get-argus.com" in payloads["text/plain"]
    assert "support@get-argus.com" in payloads["text/html"]
    assert "background:#191c1f" in payloads["text/html"]
    assert "border-radius:9999px" in payloads["text/html"]
    assert "https://app.example/?auth=signup" in payloads["text/plain"]
    assert "https://app.example/?auth=signup" in payloads["text/html"]
    assert "\u2014" not in payloads["text/plain"] + payloads["text/html"]


def test_access_welcome_hash_uses_only_stable_namespace_and_claim_token(
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
    monkeypatch.setattr(
        "argus.domain.resend_email.smtplib.SMTP_SSL",
        _smtp,
    )

    for recipient, language, signup_url, claim_token in (
        (
            "Person@Example.com",
            "en",
            "https://app.example/?auth=signup",
            "11111111-1111-4111-8111-abcdefabcdef",
        ),
        (
            " person@example.COM ",
            "es-419",
            "https://new.example/?auth=signup",
            " 11111111-1111-4111-8111-ABCDEFABCDEF ",
        ),
    ):
        send_access_welcome_email(
            recipient=recipient,
            language=language,
            signup_url=signup_url,
            claim_token=claim_token,
        )
    send_access_welcome_email(
        recipient="person@example.com",
        language="en",
        signup_url="https://app.example/?auth=signup",
        claim_token="22222222-2222-4222-8222-222222222222",
    )

    keys = [
        message_from_string(instance.message or "")["Resend-Idempotency-Key"]
        for instance in instances
    ]
    assert keys[0] == keys[1]
    assert keys[2] != keys[0]
    material = "\n".join(
        (
            "argus-access-welcome",
            "11111111-1111-4111-8111-abcdefabcdef",
        )
    )
    assert keys[0] == f"sha256:{hashlib.sha256(material.encode('utf-8')).hexdigest()}"


def test_access_welcome_receipt_is_bounded_to_256_characters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _smtp(
        host: str,
        port: int,
        *,
        timeout: float,
        context: ssl.SSLContext,
    ) -> _FakeSMTP:
        instance = _FakeSMTP(host, port, timeout=timeout, context=context)
        instance.data_receipt = b"x" * 300
        return instance

    monkeypatch.setenv("ARGUS_APPROVAL_EMAIL_SMTP_PASSWORD", "re_test_password")
    monkeypatch.setattr(
        "argus.domain.resend_email.smtplib.SMTP_SSL",
        _smtp,
    )

    result = send_access_welcome_email(
        recipient="person@example.com",
        language="en",
        signup_url="https://app.example/?auth=signup",
        claim_token="11111111-1111-4111-8111-111111111111",
    )

    assert result.provider_receipt == "x" * 256


def test_access_welcome_html_escapes_the_signup_url() -> None:
    unsafe_url = 'https://app.example/?next="><script>alert(1)</script>&auth=signup'

    content = build_access_welcome_email(language="en", signup_url=unsafe_url)

    assert "<script>alert(1)</script>" not in content.html
    assert (
        "https://app.example/?next=&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;"
        "&amp;auth=signup"
    ) in content.html


def test_internal_approval_two_requests_send_once_and_replay_durable_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.routers import ops

    gateway = _StatefulApprovalGateway(language="es-419")
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)
    monkeypatch.setenv("ARGUS_OPS_TOKEN", "ops-token")
    monkeypatch.setenv("ARGUS_APP_ORIGIN", "https://app.example/")
    send_count = 0

    def _send(**kwargs: object) -> AccessWelcomeSendResult:
        nonlocal send_count
        send_count += 1
        gateway.events.append("send")
        assert kwargs == {
            "recipient": "person@example.com",
            "language": "es-419",
            "signup_url": "https://app.example/?auth=signup",
            "claim_token": "11111111-1111-4111-8111-111111111111",
        }
        return AccessWelcomeSendResult(
            subject="Bienvenido a Argus",
            content_version="private-alpha-access-welcome/v1",
            provider_receipt="synthetic-provider-receipt",
        )

    monkeypatch.setattr(ops, "send_access_welcome_email", _send)

    first = client.post(
        "/internal/access-requests/approve",
        json={"email": " Person@Example.COM "},
        headers={"Authorization": "Bearer ops-token"},
    )
    second = client.post(
        "/internal/access-requests/approve",
        json={"email": "person@example.com"},
        headers={"Authorization": "Bearer ops-token"},
    )

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json() == {"approved": True}
    assert send_count == 1
    assert gateway.role == "user"
    assert len(gateway.deliveries) == 1
    assert gateway.events == ["claim", "send", "complete", "complete"]


def test_internal_approval_crash_window_reuses_claim_and_idempotency_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.routers import ops

    gateway = _StatefulApprovalGateway()
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)
    monkeypatch.setenv("ARGUS_OPS_TOKEN", "ops-token")
    monkeypatch.setenv("ARGUS_APP_ORIGIN", "https://app.example")
    observed_claim_tokens: list[object] = []

    def _send(**kwargs: object) -> AccessWelcomeSendResult:
        gateway.events.append("send")
        observed_claim_tokens.append(kwargs["claim_token"])
        if len(observed_claim_tokens) == 1:
            raise RuntimeError("synthetic crash-window failure")
        return AccessWelcomeSendResult(
            subject="Welcome to Argus",
            content_version="private-alpha-access-welcome/v1",
            provider_receipt="synthetic-provider-receipt",
        )

    monkeypatch.setattr(ops, "send_access_welcome_email", _send)

    first = client.post(
        "/internal/access-requests/approve",
        json={"email": "person@example.com"},
        headers={"Authorization": "Bearer ops-token"},
    )
    second = client.post(
        "/internal/access-requests/approve",
        json={"email": "person@example.com"},
        headers={"Authorization": "Bearer ops-token"},
    )

    assert first.status_code == 503
    assert second.status_code == 200
    assert second.json() == {"approved": True}
    assert observed_claim_tokens == [
        "11111111-1111-4111-8111-111111111111",
        "11111111-1111-4111-8111-111111111111",
    ]
    assert gateway.events == ["claim", "send", "claim", "send", "complete"]
    assert len(gateway.deliveries) == 1


def test_internal_approval_expired_pending_claim_fails_closed_without_smtp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.routers import ops

    gateway = _StatefulApprovalGateway()
    gateway.claim_send_allowed = False
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)
    monkeypatch.setenv("ARGUS_OPS_TOKEN", "ops-token")
    monkeypatch.setenv("ARGUS_APP_ORIGIN", "https://app.example")
    sender = MagicMock()
    monkeypatch.setattr(ops, "send_access_welcome_email", sender)

    response = client.post(
        "/internal/access-requests/approve",
        json={"email": "person@example.com"},
        headers={"Authorization": "Bearer ops-token"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Access request is not eligible for approval."
    sender.assert_not_called()
    assert gateway.events == ["claim"]


@pytest.mark.parametrize(
    ("claim_error", "expected_status"),
    [(None, 409), (RuntimeError("synthetic claim detail"), 503)],
)
def test_internal_approval_claim_revalidation_failure_never_sends(
    monkeypatch: pytest.MonkeyPatch,
    claim_error: Exception | None,
    expected_status: int,
) -> None:
    from argus.api.routers import ops

    gateway = _StatefulApprovalGateway()
    if claim_error is None:
        gateway.claim_private_alpha_access_welcome = MagicMock(return_value=None)
    else:
        gateway.claim_error = claim_error
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)
    monkeypatch.setenv("ARGUS_OPS_TOKEN", "ops-token")
    monkeypatch.setenv("ARGUS_APP_ORIGIN", "https://app.example")
    sender = MagicMock()
    monkeypatch.setattr(ops, "send_access_welcome_email", sender)

    response = client.post(
        "/internal/access-requests/approve",
        json={"email": "person@example.com"},
        headers={"Authorization": "Bearer ops-token"},
    )

    assert response.status_code == expected_status
    assert "synthetic claim detail" not in response.text
    sender.assert_not_called()
    assert "complete" not in gateway.events


def test_internal_approval_recorded_replay_never_calls_smtp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.routers import ops

    gateway = _StatefulApprovalGateway(role="user", language="en")
    gateway.deliveries["person@example.com"] = {
        "recipient_email": "person@example.com",
        "language": "en",
        "content_version": "private-alpha-access-welcome/v1",
        "subject": "Welcome to Argus",
        "provider_receipt": "synthetic-provider-receipt",
        "sent_at": "2026-08-12T14:27:17Z",
    }
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)
    monkeypatch.setenv("ARGUS_OPS_TOKEN", "ops-token")
    sender = MagicMock()
    monkeypatch.setattr(ops, "send_access_welcome_email", sender)

    response = client.post(
        "/internal/access-requests/approve",
        json={"email": "person@example.com"},
        headers={"Authorization": "Bearer ops-token"},
    )

    assert response.status_code == 200
    assert response.json() == {"approved": True}
    sender.assert_not_called()
    assert gateway.events == ["complete"]


@pytest.mark.parametrize(
    ("role", "disabled"),
    [(None, False), ("requested", True), ("admin", False), ("developer", False)],
)
def test_internal_approval_delivery_cannot_approve_ineligible_allowlist_row(
    monkeypatch: pytest.MonkeyPatch,
    role: str | None,
    disabled: bool,
) -> None:
    from argus.api.routers import ops

    gateway = _StatefulApprovalGateway(role=role, disabled=disabled)
    gateway.deliveries["person@example.com"] = {
        "recipient_email": "person@example.com",
        "language": "en",
        "content_version": "private-alpha-access-welcome/v1",
        "subject": "Welcome to Argus",
        "provider_receipt": "synthetic-provider-receipt",
        "sent_at": "2026-08-12T14:27:17Z",
    }
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)
    monkeypatch.setenv("ARGUS_OPS_TOKEN", "ops-token")
    sender = MagicMock()
    monkeypatch.setattr(ops, "send_access_welcome_email", sender)

    response = client.post(
        "/internal/access-requests/approve",
        json={"email": "person@example.com"},
        headers={"Authorization": "Bearer ops-token"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == ("Access request is not eligible for approval.")
    sender.assert_not_called()


def test_internal_approval_missing_smtp_secret_never_transitions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = _StatefulApprovalGateway()
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)
    monkeypatch.setenv("ARGUS_OPS_TOKEN", "ops-token")
    monkeypatch.setenv("ARGUS_APP_ORIGIN", "https://app.example")
    monkeypatch.delenv("ARGUS_APPROVAL_EMAIL_SMTP_PASSWORD", raising=False)

    response = client.post(
        "/internal/access-requests/approve",
        json={"email": "person@example.com"},
        headers={"Authorization": "Bearer ops-token"},
    )

    assert response.status_code == 503
    assert "ARGUS_APPROVAL_EMAIL_SMTP_PASSWORD" not in response.text
    assert "complete" not in gateway.events


def test_internal_approval_smtp_failure_never_transitions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.routers import ops

    gateway = _StatefulApprovalGateway()
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)
    monkeypatch.setenv("ARGUS_OPS_TOKEN", "ops-token")
    monkeypatch.setenv("ARGUS_APP_ORIGIN", "https://app.example")
    monkeypatch.setenv("ARGUS_APPROVAL_EMAIL_SMTP_PASSWORD", "re_test_password")
    monkeypatch.setattr(
        ops,
        "send_access_welcome_email",
        MagicMock(side_effect=RuntimeError("smtp unavailable")),
    )

    response = client.post(
        "/internal/access-requests/approve",
        json={"email": "person@example.com"},
        headers={"Authorization": "Bearer ops-token"},
    )

    assert response.status_code == 503
    assert "smtp unavailable" not in response.text
    assert "complete" not in gateway.events


def test_internal_approval_missing_app_origin_never_sends_or_transitions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.routers import ops

    gateway = _StatefulApprovalGateway()
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)
    monkeypatch.setenv("ARGUS_OPS_TOKEN", "ops-token")
    monkeypatch.delenv("ARGUS_APP_ORIGIN", raising=False)
    sender = MagicMock()
    monkeypatch.setattr(ops, "send_access_welcome_email", sender)

    response = client.post(
        "/internal/access-requests/approve",
        json={"email": "person@example.com"},
        headers={"Authorization": "Bearer ops-token"},
    )

    assert response.status_code == 503
    sender.assert_not_called()
    assert "complete" not in gateway.events


def test_internal_approval_missing_or_disabled_request_does_not_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.routers import ops

    gateway = _StatefulApprovalGateway(role=None)
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)
    monkeypatch.setenv("ARGUS_OPS_TOKEN", "ops-token")
    sender = MagicMock()
    monkeypatch.setattr(ops, "send_access_welcome_email", sender)

    response = client.post(
        "/internal/access-requests/approve",
        json={"email": "person@example.com"},
        headers={"Authorization": "Bearer ops-token"},
    )

    assert response.status_code == 409
    sender.assert_not_called()
    assert "complete" not in gateway.events


@pytest.mark.parametrize(
    ("complete_result", "complete_error", "expected_status", "expected_detail"),
    [
        (False, None, 409, "Access request is not eligible for approval."),
        (
            None,
            RuntimeError("synthetic provider detail"),
            503,
            "Approval is unavailable.",
        ),
    ],
)
def test_internal_approval_completion_failure_is_generic(
    monkeypatch: pytest.MonkeyPatch,
    complete_result: bool | None,
    complete_error: Exception | None,
    expected_status: int,
    expected_detail: str,
) -> None:
    from argus.api.routers import ops

    gateway = _StatefulApprovalGateway()
    gateway.complete_result = complete_result
    gateway.complete_error = complete_error
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)
    monkeypatch.setenv("ARGUS_OPS_TOKEN", "ops-token")
    monkeypatch.setenv("ARGUS_APP_ORIGIN", "https://app.example")
    sender = MagicMock(
        return_value=AccessWelcomeSendResult(
            subject="Welcome to Argus",
            content_version="private-alpha-access-welcome/v1",
            provider_receipt="synthetic-provider-receipt",
        )
    )
    monkeypatch.setattr(ops, "send_access_welcome_email", sender)

    response = client.post(
        "/internal/access-requests/approve",
        json={"email": "person@example.com"},
        headers={"Authorization": "Bearer ops-token"},
    )

    assert response.status_code == expected_status
    assert response.json()["detail"] == expected_detail
    assert "synthetic provider detail" not in response.text
    sender.assert_called_once()
    assert gateway.events == ["claim", "complete"]


def test_internal_approval_delivery_lookup_failure_is_generic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.routers import ops

    gateway = _StatefulApprovalGateway()
    gateway.delivery_lookup_error = RuntimeError("synthetic database detail")
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)
    monkeypatch.setenv("ARGUS_OPS_TOKEN", "ops-token")
    sender = MagicMock()
    monkeypatch.setattr(ops, "send_access_welcome_email", sender)

    response = client.post(
        "/internal/access-requests/approve",
        json={"email": "person@example.com"},
        headers={"Authorization": "Bearer ops-token"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Approval is unavailable."
    assert "synthetic database detail" not in response.text
    sender.assert_not_called()


def test_internal_approval_invalid_ops_token_is_route_indistinguishable_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = MagicMock()
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)
    monkeypatch.setenv("ARGUS_OPS_TOKEN", "ops-token")

    response = client.post(
        "/internal/access-requests/approve",
        json={"email": "person@example.com"},
        headers={"Authorization": "Bearer wrong-token"},
    )

    assert response.status_code == 404
    gateway.get_requested_private_alpha_access.assert_not_called()


def test_internal_canary_denial_signal_requires_ops_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = MagicMock()
    gateway.private_alpha_email_allowed.return_value = False
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)
    monkeypatch.setenv("ARGUS_OPS_TOKEN", "ops-token")

    missing = client.post(
        "/internal/canary/requested-signup-denial",
        json={"email": "person@example.com"},
    )
    wrong = client.post(
        "/internal/canary/requested-signup-denial",
        json={"email": "person@example.com"},
        headers={"Authorization": "Bearer wrong-token"},
    )
    authorized = client.post(
        "/internal/canary/requested-signup-denial",
        json={"email": "person@example.com"},
        headers={"Authorization": "Bearer ops-token"},
    )

    assert missing.status_code == wrong.status_code == 404
    assert authorized.status_code == 200
    assert authorized.json() == {"denied": True}
    gateway.private_alpha_email_allowed.assert_called_once_with("person@example.com")


@pytest.mark.parametrize("public_access_enabled", [True, False])
def test_internal_canary_denies_disabled_email_in_public_and_rollback_modes(
    monkeypatch: pytest.MonkeyPatch,
    public_access_enabled: bool,
) -> None:
    gateway = MagicMock()
    gateway.private_alpha_email_disabled.return_value = True
    gateway.private_alpha_email_allowed.return_value = False
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)
    monkeypatch.setenv("ARGUS_OPS_TOKEN", "ops-token")
    monkeypatch.setenv(
        "ARGUS_PUBLIC_ACCOUNT_ACCESS_ENABLED",
        "true" if public_access_enabled else "false",
    )

    response = client.post(
        "/internal/canary/requested-signup-denial",
        json={"email": "disabled@example.com"},
        headers={"Authorization": "Bearer ops-token"},
    )

    assert response.status_code == 200
    assert response.json() == {"denied": True}
    if public_access_enabled:
        gateway.private_alpha_email_disabled.assert_called_once_with(
            "disabled@example.com"
        )
        gateway.private_alpha_email_allowed.assert_not_called()
    else:
        gateway.private_alpha_email_allowed.assert_called_once_with(
            "disabled@example.com"
        )
        gateway.private_alpha_email_disabled.assert_not_called()


@pytest.mark.parametrize("authorization", [None, "Bearer wrong-token"])
@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"{",
        json.dumps({"email": "not-an-email"}).encode(),
        json.dumps({"email": f"{'a' * 321}@example.com"}).encode(),
        json.dumps({"email": "person@example.com"}).encode(),
    ],
)
def test_internal_approval_checks_ops_auth_before_parsing_any_body(
    monkeypatch: pytest.MonkeyPatch,
    authorization: str | None,
    body: bytes,
) -> None:
    from argus.api.routers import ops

    gateway = MagicMock()
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)
    monkeypatch.setenv("ARGUS_OPS_TOKEN", "ops-token")
    sender = MagicMock()
    monkeypatch.setattr(ops, "send_access_welcome_email", sender)
    headers = {"Content-Type": "application/json"}
    if authorization is not None:
        headers["Authorization"] = authorization

    response = client.post(
        "/internal/access-requests/approve",
        content=body,
        headers=headers,
    )

    assert response.status_code == 404
    gateway.get_requested_private_alpha_access.assert_not_called()
    sender.assert_not_called()
