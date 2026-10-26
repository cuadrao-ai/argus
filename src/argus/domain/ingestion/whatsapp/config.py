"""WhatsApp settings, read from ``CUADRAO_WHATSAPP_*``.

Each setting also reads its older ``ARGUS_WHATSAPP_*`` name, and the Cuadrao
name wins when both are set. The app origin reads ``CUADRAO_APP_ORIGIN`` then
``ARGUS_APP_ORIGIN``.

Intake is off unless ``CUADRAO_WHATSAPP_INTAKE_ENABLED`` is a true value and
every credential it needs is present. Outbound replies are a second switch,
``CUADRAO_WHATSAPP_OUTBOUND_ENABLED``, so intake can be proven without sending.
"""

from __future__ import annotations

from typing import Annotated

from loguru import logger
from pydantic import AliasChoices, BeforeValidator, Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from argus.api.financial_accounts import TRUE_VALUES


def _flag(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return value is not None and str(value).strip().lower() in TRUE_VALUES


def _blank_to_none(value: object) -> object:
    if isinstance(value, str) and not value.strip():
        return None
    return value.strip() if isinstance(value, str) else value


Flag = Annotated[bool, BeforeValidator(_flag)]
Optional = Annotated[str | None, BeforeValidator(_blank_to_none)]
Secret = Annotated[SecretStr | None, BeforeValidator(_blank_to_none)]


def _names(name: str) -> AliasChoices:
    return AliasChoices(f"CUADRAO_WHATSAPP_{name}", f"ARGUS_WHATSAPP_{name}")


class WhatsAppSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)

    diagnostic_enabled: Flag = Field(
        default=False, validation_alias="CUADRAO_WHATSAPP_DIAGNOSTIC_ENABLED"
    )
    intake_enabled: Flag = Field(default=False, validation_alias=_names("INTAKE_ENABLED"))
    # The Business agent over WhatsApp. Off by default: WhatsApp is receipt
    # intake only until this is turned on.
    agent_enabled: Flag = Field(default=False, validation_alias=_names("AGENT_ENABLED"))
    outbound_enabled: Flag = Field(
        default=False, validation_alias=_names("OUTBOUND_ENABLED")
    )
    verify_token: Secret = Field(default=None, validation_alias=_names("VERIFY_TOKEN"))
    app_secret: Secret = Field(default=None, validation_alias=_names("APP_SECRET"))
    access_token: Secret = Field(default=None, validation_alias=_names("ACCESS_TOKEN"))
    sender_key: Secret = Field(default=None, validation_alias=_names("SENDER_KEY"))
    phone_number_id: Optional = Field(
        default=None,
        validation_alias=AliasChoices(
            "CUADRAO_WHATSAPP_NUMBER_ID",
            "CUADRAO_WHATSAPP_PHONE_NUMBER_ID",
            "ARGUS_WHATSAPP_PHONE_NUMBER_ID",
        ),
    )
    display_phone_number: Optional = Field(
        default=None, validation_alias=_names("DISPLAY_PHONE_NUMBER")
    )
    graph_api_version: str = Field(
        default="v23.0", validation_alias=_names("GRAPH_API_VERSION")
    )
    app_origin: Optional = Field(
        default=None,
        validation_alias=AliasChoices("CUADRAO_APP_ORIGIN", "ARGUS_APP_ORIGIN"),
    )
    reply_group_wait_seconds: int = Field(
        default=120, ge=1, le=3600, validation_alias=_names("REPLY_GROUP_WAIT_SECONDS")
    )
    reply_daily_limit: int = Field(
        default=10, ge=1, le=100, validation_alias=_names("REPLY_DAILY_LIMIT")
    )

    @property
    def intake_ready(self) -> bool:
        return self.intake_enabled and None not in (
            self.verify_token,
            self.app_secret,
            self.access_token,
            self.sender_key,
            self.phone_number_id,
        )

    @property
    def wa_me_number(self) -> str | None:
        digits = "".join(ch for ch in self.display_phone_number or "" if ch.isdigit())
        return digits or None


def _version_ok(version: str) -> bool:
    major, dot, minor = version.removeprefix("v").partition(".")
    return version.startswith("v") and major.isdigit() and (not dot or minor.isdigit())


_warned: set[str] = set()


def _warn_once(message: str) -> None:
    if message not in _warned:
        _warned.add(message)
        logger.warning(message)


def load_whatsapp_settings() -> WhatsAppSettings:
    """Current settings, or an all-off snapshot when they cannot be read."""

    try:
        settings = WhatsAppSettings()
    except ValidationError:
        _warn_once("WhatsApp settings are invalid; intake stays off")
        return WhatsAppSettings.model_construct(intake_enabled=False)
    if not _version_ok(settings.graph_api_version):
        _warn_once("WhatsApp Graph API version is malformed; intake stays off")
        return WhatsAppSettings.model_construct(intake_enabled=False)
    if settings.intake_enabled and not settings.intake_ready:
        _warn_once("WhatsApp intake is enabled without its credentials; it stays off")
    return settings
