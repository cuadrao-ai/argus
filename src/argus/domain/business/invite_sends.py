"""How often one Business invitation email may be sent: the limits and the one rule."""

from __future__ import annotations

from datetime import datetime, timedelta
from math import ceil
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from argus.settings_names import setting_aliases

ResendRefusal = Literal[
    "business_invite_resend_cooldown",
    "business_invite_send_cap_reached",
    "business_invite_daily_cap_reached",
]
DAILY_WINDOW = timedelta(days=1)


class InviteSendLimits(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)
    cooldown_seconds: int = Field(
        default=60,
        ge=0,
        validation_alias=setting_aliases("BUSINESS_INVITE_RESEND_COOLDOWN_SECONDS"),
    )
    sends_per_invite: int = Field(
        default=5,
        ge=1,
        validation_alias=setting_aliases("BUSINESS_INVITE_SENDS_PER_INVITE"),
    )
    resends_per_day: int = Field(
        default=20,
        ge=0,
        validation_alias=setting_aliases("BUSINESS_INVITE_RESENDS_PER_DAY"),
    )


def resend_wait_seconds(
    last_sent_at: datetime | None, now: datetime, limits: InviteSendLimits
) -> int:
    """Whole seconds until the cooldown after the last send is over."""

    if last_sent_at is None:
        return 0
    left = limits.cooldown_seconds - (now - last_sent_at).total_seconds()
    return max(0, ceil(left))


def resend_refusal(
    *,
    invite_sends: int,
    last_sent_at: datetime | None,
    business_resends_today: int,
    now: datetime,
    limits: InviteSendLimits,
) -> tuple[ResendRefusal, int] | None:
    """Why a resend may not go out now, with the seconds to wait when waiting helps."""

    if invite_sends >= limits.sends_per_invite:
        return "business_invite_send_cap_reached", 0
    if business_resends_today >= limits.resends_per_day:
        return "business_invite_daily_cap_reached", 0
    wait = resend_wait_seconds(last_sent_at, now, limits)
    return ("business_invite_resend_cooldown", wait) if wait else None
