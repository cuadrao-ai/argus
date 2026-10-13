"""Email receiving settings. Only the Business receiving credential is read."""

from __future__ import annotations

from typing import Annotated

from pydantic import BeforeValidator, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from argus.domain.ingestion.documents.config import enabled_flag
from argus.settings_names import setting_aliases


class EmailIntakeSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)
    capture_enabled: Annotated[bool, BeforeValidator(enabled_flag)] = Field(
        default=False, validation_alias=setting_aliases("BUSINESS_EMAIL_CAPTURE_ENABLED")
    )
    receiving_enabled: Annotated[bool, BeforeValidator(enabled_flag)] = Field(
        default=False, validation_alias=setting_aliases("BUSINESS_EMAIL_INTAKE_ENABLED")
    )
    api_key: SecretStr = Field(
        default=SecretStr(""), validation_alias="RESEND_BUSINESS_API_KEY"
    )
    webhook_secret: SecretStr = Field(
        default=SecretStr(""), validation_alias=setting_aliases("RESEND_WEBHOOK_SECRET")
    )
    # The inbound domain whose addresses route to Businesses, e.g. recibos.example.com.
    receiving_domain: str = Field(
        default="", validation_alias=setting_aliases("BUSINESS_EMAIL_DOMAIN")
    )

    @field_validator("api_key", "webhook_secret", mode="before")
    @classmethod
    def _trimmed(cls, value: object) -> object:
        # A credential pasted with a stray newline or spaces is the credential;
        # one made only of whitespace is absent.
        if isinstance(value, SecretStr):
            value = value.get_secret_value()
        return value.strip() if isinstance(value, str) else value
