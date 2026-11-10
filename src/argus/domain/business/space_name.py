"""Whether a Business has a name its owner gave it."""

from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator

# Founder-approved October 8: the name a space starts with until renamed.
DEFAULT_SPACE_NAMES = {"es": "Mi negocio", "en": "My business"}


def default_space_name(language: str | None) -> str:
    """English when the person's language is English, else Spanish."""

    return DEFAULT_SPACE_NAMES["en" if language == "en" else "es"]


def given_name(name: str | None) -> str | None:
    """The name the owner gave the Business; None while it keeps a starting name."""

    return None if name is None or name in DEFAULT_SPACE_NAMES.values() else name


def spanish_name(name: str) -> str:
    """The Business as a Spanish message names it."""

    return given_name(name) or DEFAULT_SPACE_NAMES["es"]


def typed_name(stored: str, typed: str | None) -> str | None:
    """A typed confirmation of ``stored``. An unnamed Business answers to its
    starting name in either language, since each reader shows its own."""

    if given_name(stored) is None and typed in DEFAULT_SPACE_NAMES.values():
        return stored
    return typed


#: A Business name on the wire: null until the owner names the Business.
GivenName = Annotated[str | None, AfterValidator(given_name)]
