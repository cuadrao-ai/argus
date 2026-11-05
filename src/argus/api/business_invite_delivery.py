"""The separately activated Business invite email hook; no Auth invitation token."""

from smtplib import (
    SMTPAuthenticationError,
    SMTPDataError,
    SMTPRecipientsRefused,
    SMTPSenderRefused,
)
from typing import Literal

from fastapi import Request
from loguru import logger

from argus.api.business_spaces import business_access, business_spaces
from argus.domain.business.access import AccessInvite, AccessList
from argus.domain.business.invite_email import send_invite_email
from argus.settings_names import setting_value


def _send_invite(
    request: Request,
    access: AccessList,
    invite: AccessInvite,
    space_id: str,
    owner_id: str,
) -> Literal["not_configured", "accepted", "failed", "uncertain"]:
    enabled = (setting_value("BUSINESS_INVITE_EMAIL_ENABLED") or "false").strip().lower()
    origin = (setting_value("APP_ORIGIN") or "").strip()
    if enabled not in {"true", "1", "yes", "on"} or not origin:
        return "not_configured"
    spaces = business_spaces()
    space = spaces.get(space_id) if spaces is not None else None
    owner = next((g for g in access.grants if g.grantee_id == owner_id), None)
    try:
        if space is None or owner is None:
            raise LookupError("Invite labels unavailable")
        send_invite_email(
            invite=invite,
            owner_name=owner.display_name,
            business_name=space.name,
            sign_in_origin=origin,
        )
    except Exception as error:
        logger.warning(
            "business_invite_email_failed",
            invite_id=invite.id,
            error=type(error).__name__,
        )
        return (
            "failed"
            if isinstance(
                error,
                (
                    SMTPAuthenticationError,
                    SMTPDataError,
                    SMTPRecipientsRefused,
                    SMTPSenderRefused,
                    ValueError,
                    LookupError,
                ),
            )
            else "uncertain"
        )
    return "accepted"


def deliver_invite(
    request: Request,
    access: AccessList,
    invite: AccessInvite,
    space_id: str,
    owner_id: str,
) -> Literal["not_configured", "accepted", "failed", "uncertain"]:
    return business_access().deliver_invitation(
        space_id,
        owner_id,
        invite.id,
        lambda: _send_invite(request, access, invite, space_id, owner_id),
    )
