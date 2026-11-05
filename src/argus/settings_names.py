"""Cuadrao setting names with the Argus names as a fallback.

A Cuadrao setting is read as ``CUADRAO_<NAME>`` first and ``ARGUS_<NAME>``
second. Hosted services and local files can move to the new name one at a
time; the old name keeps working until every writer has moved. Only setting
names change here: the Python package, database objects and code names stay.
"""

from __future__ import annotations

import os

from pydantic import AliasChoices

PREFIXES = ("CUADRAO_", "ARGUS_")


def setting_names(name: str) -> tuple[str, ...]:
    """The names to try, in order: ``CUADRAO_<name>`` then ``ARGUS_<name>``."""

    return tuple(prefix + name for prefix in PREFIXES)


def setting_value(name: str, default: str | None = None) -> str | None:
    """The first set name's value, Cuadrao before Argus; ``default`` when neither is set."""

    for candidate in setting_names(name):
        value = os.environ.get(candidate)
        if value is not None:
            return value
    return default


def setting_aliases(name: str) -> AliasChoices:
    """A pydantic-settings alias that reads ``CUADRAO_<name>`` before ``ARGUS_<name>``."""

    return AliasChoices(*setting_names(name))
