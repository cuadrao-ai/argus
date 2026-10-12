"""Document extraction settings.

``CUADRAO_DOCUMENT_EXTRACTION_ENABLED`` (or the older ``ARGUS_`` name) uses the same true-value set as the
other default-off surfaces. Anything else, including a blank or unrecognized
value, leaves extraction off. A setting that cannot be read leaves the
document surface off and is logged; it never raises into ingestion startup
or a document route.
"""

from __future__ import annotations

from typing import Annotated

from loguru import logger
from pydantic import BeforeValidator, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from argus.api.financial_accounts import TRUE_VALUES
from argus.settings_names import setting_aliases, setting_value

# The bucket in 20261008100000 repeats both, checked by a real-Postgres test.
SOURCE_MAX_BYTES = 10 * 1024 * 1024
# Each accepted source type and the suffix its download is named with.
SOURCE_MEDIA_TYPES = {
    "application/pdf": "pdf",
    "image/jpeg": "jpg",
    "image/png": "png",
    "text/plain": "txt",
    "text/csv": "csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "message/rfc822": "eml",
}
_MAX_PAGES = 8
_RECOGNIZED_OFF = frozenset({"0", "false", "no", "off"})
_warned_flags: set[str] = set()
_warned_invalid = False


def enabled_flag(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in TRUE_VALUES


class DocumentExtractionSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)
    enabled: Annotated[bool, BeforeValidator(enabled_flag)] = Field(
        default=False, validation_alias=setting_aliases("DOCUMENT_EXTRACTION_ENABLED")
    )
    max_bytes: int = Field(
        default=SOURCE_MAX_BYTES,
        ge=1,
        le=SOURCE_MAX_BYTES,
        validation_alias=setting_aliases("DOCUMENT_EXTRACTION_MAX_BYTES"),
    )
    max_pages: int = Field(
        default=_MAX_PAGES,
        ge=1,
        le=_MAX_PAGES,
        validation_alias=setting_aliases("DOCUMENT_EXTRACTION_MAX_PAGES"),
    )


def _disabled_document_extraction_settings() -> DocumentExtractionSettings:
    return DocumentExtractionSettings.model_construct(
        enabled=False,
        max_bytes=SOURCE_MAX_BYTES,
        max_pages=_MAX_PAGES,
    )


def _warn_unusable_flag() -> None:
    raw = setting_value("DOCUMENT_EXTRACTION_ENABLED")
    if raw is None:
        return
    normalized = raw.strip().lower()
    if normalized in TRUE_VALUES or normalized in _RECOGNIZED_OFF:
        return
    if normalized in _warned_flags:
        return
    _warned_flags.add(normalized)
    logger.warning(
        "Document extraction flag is blank or unrecognized; document surface stays off"
    )


def load_document_extraction_settings() -> DocumentExtractionSettings:
    """Read document settings, or a disabled snapshot when they cannot be read."""

    global _warned_invalid
    _warn_unusable_flag()
    try:
        return DocumentExtractionSettings()
    except ValidationError:
        if not _warned_invalid:
            _warned_invalid = True
            logger.warning(
                "Document extraction settings are invalid; document surface stays off",
                failure_mode="ValidationError",
            )
        return _disabled_document_extraction_settings()


class DocumentJobSettings(BaseSettings):
    """Durable preparation jobs (#823). Off keeps FastAPI background tasks."""

    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)
    enabled: Annotated[bool, BeforeValidator(enabled_flag)] = Field(
        default=False, validation_alias=setting_aliases("DOCUMENT_JOBS_ENABLED")
    )
    workflow_task: str = Field(
        default="", validation_alias=setting_aliases("DOCUMENT_JOBS_WORKFLOW_TASK")
    )
    sweep_seconds: float = Field(
        default=30.0,
        gt=0,
        le=3600,
        validation_alias=setting_aliases("DOCUMENT_JOBS_SWEEP_SECONDS"),
    )


def load_document_job_settings() -> DocumentJobSettings:
    """Read job settings, or jobs off when they cannot be read."""

    try:
        return DocumentJobSettings()
    except ValidationError:
        logger.warning(
            "Document job settings are invalid; preparation stays on background tasks",
            failure_mode="ValidationError",
        )
        return DocumentJobSettings.model_construct(
            enabled=False, workflow_task="", sweep_seconds=30.0
        )
