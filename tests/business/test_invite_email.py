from datetime import datetime, timezone
from email import message_from_string
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from argus.domain.business.access import AccessInvite
from argus.domain.business.invite_email import (
    render_invite_email,
    send_invite_email,
    spanish_expiry_date,
)

EXPIRY = datetime(2026, 10, 25, 3, tzinfo=timezone.utc)


def render(**overrides):
    return render_invite_email(
        **dict(
            owner_name="Lucía",
            business_name="Colmado",
            expires_at=EXPIRY,
            sign_in_origin="https://app.example.test",
            **overrides,
        )
    )


def test_shared_html_and_plain_snapshots():
    mail = render()
    snapshots = Path(__file__).with_name("invite_email_snapshots")
    assert mail.html == (snapshots / "invite.html").read_text()
    assert mail.text == (snapshots / "invite.txt").read_text()
    assert mail.subject == "Lucía te invitó a Colmado en Cuadrao"
    assert "Vence el 24 de octubre de 2026." in mail.html
    assert "Saludos,<br>Cuadrao" in mail.html
    assert "Saludos,\nCuadrao" in mail.text
    assert "https://app.example.test/" in mail.html
    assert "token" not in mail.html


def test_values_are_escaped_once_and_never_reinterpolated():
    mail = render_invite_email(
        owner_name="<img src=x> __CUADRAO_BUSINESS_NAME__",
        business_name='Shop & "Family"',
        expires_at=EXPIRY,
        sign_in_origin="https://app.example.test",
    )
    assert "<img src=x>" not in mail.html
    assert "&lt;img src=x&gt; __CUADRAO_BUSINESS_NAME__" in mail.html
    assert "Shop &amp; &quot;Family&quot;" in mail.html
    assert "<img src=x> __CUADRAO_BUSINESS_NAME__" in mail.text
    assert 'Shop & "Family"' in mail.text


@pytest.mark.parametrize(
    "origin",
    [
        "http://example.test",
        "https://user:pass@example.test",
        "https://example.test/login",
        "https://example.test/?token=x",
        "https://example.test/#token",
        "https://example.test/\n",
    ],
)
def test_rejects_unsafe_origins(origin):
    with pytest.raises(ValueError):
        render_invite_email(
            owner_name="Owner",
            business_name="Shop",
            expires_at=EXPIRY,
            sign_in_origin=origin,
        )
    with pytest.raises(ValueError):
        render_invite_email(
            owner_name="Owner",
            business_name="Shop",
            expires_at=EXPIRY,
            sign_in_origin="https://app.example.test",
            asset_origin=origin,
        )


@pytest.mark.parametrize(
    "name", ["", "  ", "Name\rBcc: other@example.test", "Name\nInjected"]
)
def test_rejects_header_injection(name):
    with pytest.raises(ValueError):
        render_invite_email(
            owner_name=name,
            business_name="Shop",
            expires_at=EXPIRY,
            sign_in_origin="https://app.example.test",
        )


def test_santo_domingo_date_boundary():
    assert spanish_expiry_date(EXPIRY) == "24 de octubre de 2026"
    assert spanish_expiry_date(EXPIRY.replace(hour=4)) == "25 de octubre de 2026"
    with pytest.raises(ValueError):
        spanish_expiry_date(EXPIRY.replace(tzinfo=None))


def test_actual_transport_mime_recipient_and_window_idempotency(monkeypatch):
    from argus.domain import resend_email

    smtp = MagicMock()
    smtp.mail.return_value = smtp.rcpt.return_value = (250, b"ok")
    smtp.data.return_value = (250, b"synthetic-receipt")
    factory = MagicMock()
    factory.return_value.__enter__.return_value = smtp
    monkeypatch.setattr(resend_email.smtplib, "SMTP_SSL", factory)
    monkeypatch.setenv(resend_email.SMTP_PASSWORD_ENV, "synthetic-password")
    invite = AccessInvite("id-one", "person@example.test", EXPIRY, EXPIRY)
    kwargs = dict(
        invite=invite,
        owner_name="Lucía",
        business_name="Colmado",
        sign_in_origin="https://app.example.test",
    )
    assert send_invite_email(**kwargs) == "synthetic-receipt"
    assert send_invite_email(**kwargs) == "synthetic-receipt"
    first, second = [
        message_from_string(call.args[0]) for call in smtp.data.call_args_list
    ]
    assert first["To"] == "person@example.test"
    assert first["From"] == "Cuadrao <no-responder@mail.cuadrao.ai>"
    assert first["Reply-To"] == "hola@cuadrao.ai"
    smtp.mail.assert_called_with("no-responder@mail.cuadrao.ai")
    assert first["Resend-Idempotency-Key"] == second["Resend-Idempotency-Key"]
    assert first["Subject"]
    assert [part.get_content_type() for part in first.get_payload()] == [
        "text/plain",
        "text/html",
    ]


def test_missing_transport_configuration_is_an_error(monkeypatch):
    monkeypatch.setenv("ARGUS_APPROVAL_EMAIL_SMTP_PASSWORD", "")
    with pytest.raises(RuntimeError, match="configuration"):
        send_invite_email(
            invite=AccessInvite("id", "person@example.test", EXPIRY, EXPIRY),
            owner_name="Lucía",
            business_name="Colmado",
            sign_in_origin="https://app.example.test",
        )


@pytest.mark.parametrize(
    "address",
    [
        "",
        "  ",
        "Cuadrao LLC",
        "Cuadrao LLC, ",
        "Street\nBcc: person@example.test",
        "Cuadrao LLC, 1209 Mountain Road Pl NE Ste N, Albuquerque NM 87110, EE. UU.",
    ],
)
def test_invite_mail_ignores_a_configured_postal_address(address, monkeypatch):
    monkeypatch.setenv("MARKETING_POSTAL_ADDRESS", address)
    mail = render()
    assert ">Cuadrao LLC</p>" in mail.html
    assert mail.text.rstrip().endswith("Cuadrao LLC")
    assert "Cuadrao LLC," not in mail.html
    assert "1209 Mountain" not in mail.text
    assert "Salir de la lista" not in mail.html + mail.text


def test_invite_mail_renders_cuadrao_llc_when_postal_address_is_unset(monkeypatch):
    monkeypatch.delenv("MARKETING_POSTAL_ADDRESS", raising=False)
    mail = render()
    assert ">Cuadrao LLC</p>" in mail.html
    assert mail.text.rstrip().endswith("Cuadrao LLC")
    assert "Cuadrao LLC," not in mail.html
    assert "Cuadrao LLC," not in mail.text
    assert "Salir de la lista" not in mail.html + mail.text
