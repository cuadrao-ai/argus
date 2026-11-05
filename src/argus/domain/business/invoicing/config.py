from typing import Annotated

from pydantic import BeforeValidator, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from argus.domain.ingestion.documents.config import enabled_flag


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    enabled: Annotated[bool, BeforeValidator(enabled_flag)] = Field(
        default=False, validation_alias="CUADRAO_BUSINESS_INVOICING_ENABLED"
    )
