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


class BusinessTypedNotesSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)
    enabled: Annotated[bool, BeforeValidator(enabled_flag)] = Field(
        default=False, validation_alias="CUADRAO_BUSINESS_TYPED_NOTES_ENABLED"
    )


def business_typed_notes_enabled() -> bool:
    """Nota escrita: a document typed in Agregar, with no file. Off, the
    default: the capture route refuses a note that starts a draft. Notes
    already saved stay as they are, and a note added to an existing draft
    still saves."""

    try:
        return BusinessTypedNotesSettings().enabled
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


class EcfChecksPanelSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)
    enabled: Annotated[bool, BeforeValidator(enabled_flag)] = Field(
        default=False, validation_alias="CUADRAO_ECF_CHECKS_PANEL_ENABLED"
    )


def ecf_checks_panel_enabled() -> bool:
    """The e-CF checks card in review. Off, the default: the dossier says
    review does not show it. The checks still run, the QR still corrects the
    read, and a field the XML disputes is still marked."""

    try:
        return EcfChecksPanelSettings().enabled
    except ValidationError:
        return False
