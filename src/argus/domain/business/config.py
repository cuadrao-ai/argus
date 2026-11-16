"""Independent Business feature settings."""

from __future__ import annotations

from typing import Annotated

from pydantic import BeforeValidator, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from argus.domain.ingestion.documents.config import enabled_flag
from argus.settings_names import setting_aliases


class BusinessChatSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)
    enabled: Annotated[bool, BeforeValidator(enabled_flag)] = Field(
        default=False, validation_alias=setting_aliases("BUSINESS_CHAT_ENABLED")
    )


def business_chat_enabled() -> bool:
    """Off until Business turns have their own tool
    restrictions; reading and deleting Business chats never depends on it."""

    try:
        return BusinessChatSettings().enabled
    except ValidationError:
        return False


class BusinessBankMatchingSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)
    enabled: Annotated[bool, BeforeValidator(enabled_flag)] = Field(
        default=False, validation_alias=setting_aliases("BUSINESS_BANK_MATCHING_ENABLED")
    )


def business_bank_matching_enabled() -> bool:
    """Off hides the statement import routes."""

    try:
        return BusinessBankMatchingSettings().enabled
    except ValidationError:
        return False


class BusinessSettlementSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)
    enabled: Annotated[bool, BeforeValidator(enabled_flag)] = Field(
        default=False, validation_alias="CUADRAO_BUSINESS_SETTLEMENT_ENABLED"
    )


def business_settlement_enabled() -> bool:
    """Por cobrar and Por pagar: marking a document cobrado or pagado and the
    lists of what is still open. Off, the default: the month close carries no
    settlement state, an open document never holds the month, and the routes
    that only serve settlement refuse. Stored settlements stay as they are."""

    try:
        return BusinessSettlementSettings().enabled
    except ValidationError:
        return False


class BusinessInviteAdmissionSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)
    enabled: Annotated[bool, BeforeValidator(enabled_flag)] = Field(
        default=False, validation_alias="CUADRAO_BUSINESS_INVITE_ADMISSION_ENABLED"
    )


def business_invite_admission_enabled() -> bool:
    """Off, the default: only the allowlist and open sign-up admit an email,
    and the standing check on Business routes is inert. On: a live Business
    invitation or grant admits its email too, and an account admitted only
    that way cannot start a Business, invite anyone or take one over."""

    try:
        return BusinessInviteAdmissionSettings().enabled
    except ValidationError:
        return False
