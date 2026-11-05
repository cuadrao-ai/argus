"""Wire schemas for beta invites, the founder group link, and beta access."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

InviteKind = Literal["beta", "household", "group_link"]
InviteState = Literal["pending", "accepted", "revoked", "expired"]


class InviteSecretRequest(BaseModel):
    """A code typed by hand, or the token from a link or QR. Exactly one."""

    model_config = ConfigDict(extra="forbid")

    token: str | None = Field(default=None, min_length=8, max_length=200)
    code: str | None = Field(default=None, min_length=4, max_length=32)

    @model_validator(mode="after")
    def _one_secret(self) -> InviteSecretRequest:
        if (self.token is None) == (self.code is None):
            raise ValueError("Send exactly one of token or code.")
        return self


class CreateBetaInviteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateGroupLinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_label: str = Field(min_length=1, max_length=80)
    cap: int = Field(ge=1, le=10000)
    expires_at: datetime

    @field_validator("source_label")
    @classmethod
    def _label_has_text(cls, value: str) -> str:
        # Every group link names its source; a blank label is a 422, not a 500.
        stripped = value.strip()
        if not stripped:
            raise ValueError("The source label cannot be blank.")
        return stripped


class QuotaGrantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=80)
    extra: int = Field(ge=1, le=1000)


class InviteQuota(BaseModel):
    limit: int
    used: int
    remaining: int


class BetaInviteCreated(BaseModel):
    """Secrets are returned once. A replay returns the same id with no secrets."""

    id: str
    kind: Literal["beta", "group_link"]
    expires_at: datetime
    token: str | None = None
    code: str | None = None
    link: str | None = None
    source_label: str | None = None
    cap: int | None = None
    replayed: bool = False


class BetaInviteCreatedResponse(BaseModel):
    invitation: BetaInviteCreated
    quota: InviteQuota | None = None


class SentInvite(BaseModel):
    """One invite the caller sent. accepted_at drives the "accepted" notice."""

    id: str
    kind: Literal["beta", "household"]
    invitation_id: str | None
    state: InviteState
    sent_at: datetime
    expires_at: datetime | None
    accepted_at: datetime | None


class SentInvitesResponse(BaseModel):
    quota: InviteQuota
    invitations: list[SentInvite]


class InvitePreview(BaseModel):
    kind: InviteKind
    available: bool
    expires_at: datetime
    household_name: str | None = None


class RedeemResult(BaseModel):
    admitted: bool
    outcome: Literal["admitted", "already_admitted"]
    kind: Literal["beta", "group_link"]
    replayed: bool = False


class BetaAccess(BaseModel):
    gate_enabled: bool
    admitted: bool
    waitlist_url: str | None = None
    testflight_url: str | None = None


class GroupLinkView(BaseModel):
    id: str
    source_label: str
    cap: int
    redeemed: int
    overflow: int
    expires_at: datetime
    revoked_at: datetime | None
    state: Literal["open", "full", "expired", "revoked"]


class GroupLinkListResponse(BaseModel):
    links: list[GroupLinkView]


class QuotaGrantResult(BaseModel):
    id: str
    user_id: str
    extra: int
    replayed: bool = False


class KindNumbers(BaseModel):
    """The three network numbers for one kind of invite."""

    sent: int
    senders: int
    sent_per_sender: float | None
    accepted: int
    accepted_share: float | None
    invitees_who_invited: int
    invitees_who_invited_share: float | None


class GroupLinkNumbers(BaseModel):
    id: str
    source_label: str
    cap: int
    redeemed: int
    overflow: int
    invitees_who_invited: int
    invitees_who_invited_share: float | None


class NetworkNumbers(BaseModel):
    beta: KindNumbers
    household: KindNumbers
    group_links: list[GroupLinkNumbers]
