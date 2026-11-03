"""The greeting name a new profile starts with."""

from __future__ import annotations

from argus.api.schemas import PREFERRED_NAME_MAX_LENGTH


def first_name_typed(display_name: object) -> str | None:
    """First word of the name typed at sign-up, or None when it can't be a name.

    A first word over the stored bound is left empty rather than cut mid-word.
    """

    if not isinstance(display_name, str):
        return None
    words = display_name.split()
    if not words or len(words[0]) > PREFERRED_NAME_MAX_LENGTH:
        return None
    return words[0]
