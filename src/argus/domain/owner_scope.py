"""Whose records a read or write sees: the person's Personal records or one Business space.

A root row (account, source connection, import event, conversation) stores
``owner_space_id``. Null is Personal; a Business row stores its space id. The
rule lives only here: ``sql_predicate``, ``sql_named_predicate`` and
``sql_named_join_predicate`` for SQL, ``postgrest_scoped`` for PostgREST, and
``holds`` for the in-memory twins. Every scoped reader and writer takes
``scope`` as a required keyword: a caller states which side it means.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class Personal:
    pass


@dataclass(frozen=True)
class BusinessSpace:
    space_id: str


OwnerScope = Personal | BusinessSpace
PERSONAL = Personal()


def surface_of(stored_space_id: object) -> Literal["personal", "business"]:
    """The chat surface a stored ``owner_space_id`` belongs to."""

    return "personal" if stored_space_id is None else "business"


def space_id(scope: OwnerScope) -> str | None:
    """The value a row in this scope stores in ``owner_space_id``."""

    return scope.space_id if isinstance(scope, BusinessSpace) else None


def scope_of(stored_space_id: object) -> OwnerScope:
    """The scope a stored ``owner_space_id`` names."""

    return PERSONAL if stored_space_id is None else BusinessSpace(str(stored_space_id))


def holds(scope: OwnerScope, stored_space_id: object) -> bool:
    """Whether a row storing ``stored_space_id`` belongs to ``scope``."""

    return scope_of(stored_space_id) == scope


def sql_predicate(scope: OwnerScope, column: str) -> tuple[str, tuple[str, ...]]:
    """``(condition, params)`` keeping rows of ``scope``; ``column`` is a code constant."""

    if isinstance(scope, BusinessSpace):
        return f"{column} = %s", (scope.space_id,)
    return f"{column} is null", ()


SCOPE_PARAMETER = "owner_space_id"


def sql_named_predicate(scope: OwnerScope, column: str) -> str:
    """The same rule for SQL that binds by name; bind ``SCOPE_PARAMETER`` to ``space_id``.

    Use it where the rows are found by scanning the owner's rows: ``is null``
    keeps the owner's indexes usable.
    """

    if isinstance(scope, BusinessSpace):
        return f"{column} = %({SCOPE_PARAMETER})s::uuid"
    return f"{column} is null"


def sql_named_join_predicate(column: str) -> str:
    """One text for both sides, for SQL built once for either side.

    Bind ``SCOPE_PARAMETER`` to ``space_id``. Postgres cannot use an index for
    ``is not distinct from``, so use it only where another condition already
    bounds the rows: a join by id, or the owner's ``user_id`` index, as in the
    search reader's owner scans. A full scan needs ``sql_named_predicate``.
    """

    return f"{column} is not distinct from %({SCOPE_PARAMETER})s::uuid"


def postgrest_scoped(query: Any, scope: OwnerScope, column: str) -> Any:
    """The same rule as a PostgREST filter on ``query``."""

    if isinstance(scope, BusinessSpace):
        return query.eq(column, scope.space_id)
    return query.is_(column, "null")
