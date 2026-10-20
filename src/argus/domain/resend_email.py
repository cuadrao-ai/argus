from __future__ import annotations

import json
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from importlib.resources import files

SMTP_PASSWORD_ENV = "ARGUS_APPROVAL_EMAIL_SMTP_PASSWORD"
# Owned by argus_display_contract/support_contact.json, which the web build also reads.
SUPPORT_EMAIL_ADDRESS: str = json.loads(
    files("argus_display_contract").joinpath("support_contact.json").read_text()
)["email"]

_SMTP_HOST = "smtp.resend.com"
_SMTP_PORT = 465
_SMTP_USERNAME = "resend"
_SMTP_TIMEOUT_SECONDS = 10.0
_SENDER_ADDRESS = "no-responder@mail.cuadrao.ai"
_SENDER_HEADER = "Cuadrao <no-responder@mail.cuadrao.ai>"


def _require_accepted(code: int) -> None:
    if code not in {250, 251}:
        raise RuntimeError("Resend SMTP delivery was not accepted.")


def send_resend_email(
    *,
    recipient: str,
    subject: str,
    plain_text: str,
    html: str,
    idempotency_key: str | None = None,
) -> str:
    """Deliver one message through Resend SMTP and return the provider receipt."""

    password = (os.getenv(SMTP_PASSWORD_ENV) or "").strip()
    if not password:
        raise RuntimeError("Resend SMTP configuration is unavailable.")

    message = MIMEMultipart("alternative")
    message["From"] = _SENDER_HEADER
    message["Reply-To"] = "hola@cuadrao.ai"
    message["To"] = recipient
    message["Subject"] = subject
    if idempotency_key is not None:
        message["Resend-Idempotency-Key"] = idempotency_key
    message.attach(MIMEText(plain_text, "plain", "utf-8"))
    message.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP_SSL(
        _SMTP_HOST,
        _SMTP_PORT,
        timeout=_SMTP_TIMEOUT_SECONDS,
        context=ssl.create_default_context(),
    ) as smtp:
        smtp.login(_SMTP_USERNAME, password)
        mail_code, _ = smtp.mail(_SENDER_ADDRESS)
        _require_accepted(mail_code)
        recipient_code, _ = smtp.rcpt(recipient)
        _require_accepted(recipient_code)
        data_code, raw_receipt = smtp.data(message.as_string())
        _require_accepted(data_code)

    return raw_receipt.decode("utf-8", errors="replace").strip()
