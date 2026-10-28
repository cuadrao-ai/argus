"""Tell an existing account owner that someone tried to sign up with their email.

Signup answers a duplicate exactly like a new account, so only the mailbox
owner learns the account exists.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from argus.api.schemas import Language
from argus.domain import resend_email
from argus.domain.business.transfer_mail import _origin
from argus.settings_names import setting_value

_ARTIFACT = Path(__file__).with_name("existing_account_email.generated.json")


def render_existing_account_email(
    *, language: Language, app_origin: str, asset_origin: str
) -> dict[str, str]:
    artifact = json.loads(_ARTIFACT.read_text())
    if artifact["schemaVersion"] != 1:
        raise ValueError("Unsupported existing account email artifact")
    values = {
        "signInUrl": f"{_origin(app_origin)}/?auth=login",
        "assetOrigin": _origin(asset_origin),
    }
    template = artifact["templates"][language]
    rendered = {}
    for field in ("subject", "html", "text"):
        value = template[field]
        for key, token in artifact["tokens"].items():
            if field == "html":
                value = value.replace(
                    html.escape(token, quote=True), html.escape(values[key], quote=True)
                )
            else:
                value = value.replace(token, values[key])
        rendered[field] = value
    return rendered


def _idempotency_key(recipient: str, sent_at: datetime) -> str:
    hour = sent_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H")
    digest = hashlib.sha256(recipient.encode("utf-8")).hexdigest()
    return f"existing-account:{digest}:{hour}"


def send_existing_account_notice(
    *, recipient: str, language: Language, sent_at: datetime | None = None
) -> None:
    """Send at most one notice per address per hour; never raise to the caller."""

    try:
        app_origin = setting_value("APP_ORIGIN")
        if not app_origin:
            raise LookupError("App origin is unavailable.")
        message = render_existing_account_email(
            language=language,
            app_origin=app_origin,
            asset_origin=os.getenv("CUADRAO_EMAIL_ASSET_ORIGIN") or "https://cuadrao.ai",
        )
        normalized = recipient.strip().lower()
        resend_email.send_resend_email(
            recipient=normalized,
            subject=message["subject"],
            plain_text=message["text"],
            html=message["html"],
            idempotency_key=_idempotency_key(
                normalized, sent_at or datetime.now(timezone.utc)
            ),
        )
        logger.info("existing_account_notice_sent")
    except Exception as error:
        logger.warning("existing_account_notice_failed", error=type(error).__name__)
