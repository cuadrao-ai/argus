"""Saved Business identity and user-provided contact details."""

from __future__ import annotations

import re
from typing import Annotated, get_args
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from pydantic_core import PydanticCustomError

from argus.domain.business.phone import PhoneRefusal, PhoneRefused, display_phone
from argus.domain.business.workspace_images import Appearance, DefaultAppearance


class WorkspaceError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class BusinessDetails(BaseModel):
    """The saved details. A row saved before a rule existed may not pass it."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    address: str = Field(default="", max_length=200)
    province: str = Field(default="", max_length=80)
    municipality: str = Field(default="", max_length=80)
    email: str = Field(default="", max_length=254)
    phone: str = Field(default="", max_length=40)
    website: str = Field(default="", max_length=2048)
    description: str = Field(default="", max_length=280)

    @field_validator("*", mode="before")
    @classmethod
    def clear_null(cls, value: object) -> object:
        return "" if value is None else value

    @field_validator("phone")
    @classmethod
    def phone_format(cls, value: str) -> str:
        """A valid phone reads in its one form. Text from before the rule reads as saved."""
        try:
            return display_phone(value)
        except PhoneRefused:
            return value


PHONE_REFUSAL_CODES = frozenset(
    f"invalid_business_phone_{reason}" for reason in get_args(PhoneRefusal)
)


def _refused(code: str) -> PydanticCustomError:
    return PydanticCustomError(code, code)


class BusinessDetailsInput(BusinessDetails):
    """Details a person typed. The only owner of the email, website and phone rules."""

    @field_validator("email")
    @classmethod
    def email_format(cls, value: str) -> str:
        if value and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise _refused("invalid_business_email")
        return value

    @field_validator("phone")
    @classmethod
    def phone_format(cls, value: str) -> str:
        """A phone is saved as +1 809 555 0142. An empty one clears the field."""
        if not value:
            return value
        try:
            return display_phone(value)
        except PhoneRefused as refused:
            raise _refused(f"invalid_business_phone_{refused.reason}") from None

    @field_validator("website", mode="before")
    @classmethod
    def website_format(cls, value: object) -> object:
        if not isinstance(value, str) or not value.strip():
            return value
        value = value.strip()
        if not re.match(r"^[a-z][a-z0-9+.-]*:", value, re.I):
            value = "https://" + value
        try:
            url = urlsplit(value)
            valid = (
                url.scheme in {"http", "https"}
                and "." in (url.hostname or "")
                and not re.search(r"\s", value)
                and not url.username
                and not url.password
                and "@" not in url.netloc
            )
            _ = url.port
        except ValueError:
            valid = False
        if not valid:
            raise _refused("invalid_business_website")
        return value


class SaveWorkspace(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_revision: int = Field(ge=0, strict=True)
    name: (
        Annotated[
            str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)
        ]
        | None
    ) = None
    details: BusinessDetailsInput | None = None
    appearance: Appearance | None = None

    @field_validator("name", mode="before")
    @classmethod
    def name_cannot_clear(cls, value: object) -> object:
        if value is None:
            raise ValueError("business_name_required")
        return value


class WorkspaceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    space_id: str
    name: str
    country: str
    currency: str
    revision: int
    details: BusinessDetails
    appearance: Appearance = DefaultAppearance()


def command_payload(command: SaveWorkspace) -> dict:
    return command.model_dump(mode="json", exclude_unset=True)


def checked_key(key: str) -> str:
    if not key.strip() or not 1 <= len(key) <= 200:
        raise WorkspaceError("invalid_idempotency_key")
    return key
