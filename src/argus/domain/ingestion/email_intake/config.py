"""Email receiving settings. Only the Business receiving credential is read."""

from __future__ import annotations

from typing import Annotated

from pydantic import BeforeValidator, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from argus.domain.ingestion.documents.config import enabled_flag


class EmailIntakeSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    capture_enabled: Annotated[bool, BeforeValidator(enabled_flag)] = Field(
        default=False, validation_alias="ARGUS_BUSINESS_EMAIL_CAPTURE_ENABLED"
    )
    receiving_enabled: Annotated[bool, BeforeValidator(enabled_flag)] = Field(
        default=False, validation_alias="ARGUS_BUSINESS_EMAIL_INTAKE_ENABLED"
    )
    api_key: SecretStr = Field(
        default=SecretStr(""), validation_alias="RESEND_BUSINESS_API_KEY"
    )
    webhook_secret: SecretStr = Field(
        default=SecretStr(""), validation_alias="ARGUS_RESEND_WEBHOOK_SECRET"
    )
    # The inbound domain whose addresses route to Businesses, e.g. recibos.example.com.
    receiving_domain: str = Field(
        default="", validation_alias="ARGUS_BUSINESS_EMAIL_DOMAIN"
    )
