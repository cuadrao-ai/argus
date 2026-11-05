"""Render the canonical shared account template and deliver one invite window."""

from __future__ import annotations

import html
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from argus.domain.business.access import AccessInvite, normalize_email
from argus.domain.resend_email import send_resend_email

_MONTHS = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


@dataclass(frozen=True)
class InviteEmail:
    subject: str
    html: str
    text: str


def _origin(value: str) -> str:
    parsed = urlsplit(value)
    port = parsed.port
    if (
        (port is not None and port == 0)
        or parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or any(c.isspace() for c in value)
    ):
        raise ValueError("Email origin must be HTTPS without credentials or a path")
    return value.rstrip("/")


def spanish_expiry_date(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("Invite expiry must include a timezone")
    local = value.astimezone(ZoneInfo("America/Santo_Domingo"))
    return f"{local.day} de {_MONTHS[local.month - 1]} de {local.year}"


def render_invite_email(
    *,
    owner_name: str,
    business_name: str,
    expires_at: datetime,
    sign_in_origin: str,
    asset_origin: str | None = None,
) -> InviteEmail:
    for value in (owner_name, business_name):
        if not value.strip() or any(c in value for c in "\r\n"):
            raise ValueError("Invite names must be nonempty single-line values")
    artifact = json.loads(
        Path(__file__).with_name("business_invite_email.generated.json").read_text()
    )
    values = {
        "ownerName": owner_name,
        "businessName": business_name,
        "expiresDate": spanish_expiry_date(expires_at),
        "signInUrl": _origin(sign_in_origin) + "/",
        "assetOrigin": _origin(
            asset_origin
            or os.getenv("CUADRAO_EMAIL_ASSET_ORIGIN")
            or "https://cuadrao.ai"
        ),
    }
    replacements = {token: values[key] for key, token in artifact["tokens"].items()}
    pattern = re.compile("|".join(re.escape(token) for token in replacements))

    def substitute(field: str) -> str:
        return pattern.sub(
            lambda match: html.escape(replacements[match[0]], quote=True)
            if field == "html"
            else replacements[match[0]],
            artifact[field],
        )

    return InviteEmail(
        subject=substitute("subject"), html=substitute("html"), text=substitute("text")
    )


def send_invite_email(
    *, invite: AccessInvite, owner_name: str, business_name: str, sign_in_origin: str
) -> str:
    message = render_invite_email(
        owner_name=owner_name,
        business_name=business_name,
        expires_at=invite.expires_at,
        sign_in_origin=sign_in_origin,
    )
    return send_resend_email(
        recipient=normalize_email(invite.email),
        subject=message.subject,
        plain_text=message.text,
        html=message.html,
        idempotency_key=f"business-invite:{invite.id}:{invite.expires_at.isoformat()}",
    )
