"""Stored household records and wire schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Permission = Literal["view", "edit"]
HouseholdStatus = Literal["active", "closed"]
MemberRole = Literal["admin", "member"]


class CreateHouseholdRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=80)
    display_name: str = Field(default="Member", min_length=1, max_length=60)


class AcceptInvitationRequest(BaseModel):
    """The token from the link or QR, or the typed code. Exactly one."""

    model_config = ConfigDict(extra="forbid")

    token: str | None = Field(default=None, min_length=8, max_length=200)
    code: str | None = Field(default=None, min_length=4, max_length=32)
    display_name: str = Field(default="Member", min_length=1, max_length=60)

    @model_validator(mode="after")
    def _one_secret(self) -> AcceptInvitationRequest:
        if (self.token is None) == (self.code is None):
            raise ValueError("Send exactly one of token or code.")
        return self


class VersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)


class TransferAdminRequest(VersionRequest):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=80)


class CreateAccountGrantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str = Field(min_length=1, max_length=80)
    permission: Permission = "view"
    recipient_membership_id: str = Field(min_length=1, max_length=80)
    expected_version: int = Field(ge=1)


class UpdateAccountGrantRequest(VersionRequest):
    model_config = ConfigDict(extra="forbid")

    permission: Permission


class MemberRecord(BaseModel):
    membership_id: str
    display_name: str
    is_self: bool = False
    is_admin: bool = False
    user_id: str
    role: MemberRole
    joined_at: datetime


class Recipient(BaseModel):
    membership_id: str
    permission: Permission = "view"


class AccountShare(BaseModel):
    account_id: str
    recipients: list[Recipient]


class ReplaceAccountGrantsRequest(VersionRequest):
    recipients: list[Recipient] = Field(max_length=1000)


class InvitationMetadata(BaseModel):
    id: str
    expires_at: datetime
    state: Literal["pending", "accepted", "revoked", "expired"]
    token: None = None


class InvitationPreview(BaseModel):
    name: str | None
    expires_at: datetime
    available: bool


class AcceptanceResult(BaseModel):
    household_id: str
    membership_id: str
    state: Literal["active", "departed"]


class CommandResult(BaseModel):
    household_id: str
    membership_id: str | None = None
    state: Literal["active", "departed"]
    replayed: bool
    invitation: InvitationCreated | None = None


class HouseholdRecord(BaseModel):
    version: int
    membership_id: str | None = None
    admin_membership_id: str | None = None
    invitations: list[InvitationMetadata] = Field(default_factory=list)
    shares: list[AccountShare] = Field(default_factory=list)
    id: str
    name: str | None
    status: HouseholdStatus
    admin_user_id: str | None
    created_by: str | None
    created_at: datetime
    closed_at: datetime | None
    members: list[MemberRecord]


class InvitationCreated(BaseModel):
    """Token, code and link are returned once; a replay carries none of them."""

    id: str
    household_id: str
    expires_at: datetime
    token: str | None
    state: str = "pending"
    code: str | None = None
    link: str | None = None


class AccountGrantRecord(BaseModel):
    id: str
    household_id: str
    account_id: str
    owner_user_id: str
    owner_membership_id: str
    recipient_membership_id: str
    permission: Permission
    created_at: datetime
    revoked_at: datetime | None = None


class SharedAccountView(BaseModel):
    grant_id: str
    account_id: str
    owner_user_id: str
    permission: Permission
    type: str
    currency: str
    nickname: str | None
    archived: bool
    ownership_share_bps: int


class OwnedAccountRef(BaseModel):
    """Minimal account facts needed to validate and project a grant."""

    id: str
    user_id: str
    type: str
    currency: str
    nickname: str | None
    archived: bool
    ownership_share_bps: int


CommandResult.model_rebuild()
