"""The process's Business space store, built beside the ingestion hub.

Postgres in ``supabase`` persistence, in memory otherwise. The Business routes
and WhatsApp intake read it through ``business_spaces`` and resolve a person's
space only with ``resolve_business_scope``.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

from argus.api import state as api_state
from argus.api.dependencies import problem
from argus.api.documents import NO_STORE
from argus.api.profile_images import picture_urls
from argus.domain.business.access import (
    AccessStore,
    InMemoryAccessStore,
    PostgresAccessStore,
)
from argus.domain.business.search_memory import (
    InMemorySearchMemory,
    PostgresSearchMemory,
    SearchMemory,
)
from argus.domain.business.spaces import (
    InMemorySpaceStore,
    PostgresSpaceStore,
    Space,
    SpaceStore,
)

_spaces: SpaceStore | None = None
_access: AccessStore | None = None
_search_memory: SearchMemory | None = None


def space_missing_problem(request: Request) -> HTTPException:
    return problem(
        request,
        status_code=404,
        code="business_space_missing",
        title="Not Found",
        detail="Start your business space first.",
        headers=NO_STORE,
    )


def business_spaces() -> SpaceStore | None:
    return _spaces


def space_payload(space: Space) -> dict[str, Any]:
    """The space as every Business route answers it, logo included."""

    return {
        "id": space.id,
        "name": space.name,
        "country": space.country,
        "currency": space.currency,
        "logo_url": picture_urls("business", [space.id])[space.id],
    }


def configure_business_spaces(store: SpaceStore | None) -> None:
    global _spaces
    _spaces = store


def business_access() -> AccessStore | None:
    return _access


def configure_business_access(store: AccessStore | None) -> None:
    global _access
    _access = store


def business_search_memory() -> SearchMemory | None:
    return _search_memory


def configure_business_search_memory(store: SearchMemory | None) -> None:
    global _search_memory
    _search_memory = store


def accept_business_invites(user_id: str) -> None:
    """Compatibility hook. Reading an account never accepts an invitation."""
    return None


def start_business_spaces(app: object) -> None:
    if api_state.PERSISTENCE_MODE != "supabase":
        access = InMemoryAccessStore()
        configure_business_spaces(InMemorySpaceStore(access))
        configure_business_access(access)
        configure_business_search_memory(InMemorySearchMemory())
        return
    pool = getattr(getattr(app, "state", None), "financial_accounts_pool", None)
    configure_business_spaces(PostgresSpaceStore(pool) if pool is not None else None)
    configure_business_access(PostgresAccessStore(pool) if pool is not None else None)
    configure_business_search_memory(
        PostgresSearchMemory(pool) if pool is not None else None
    )
