"""The HTTP face of the Business list version: ETag out, If-None-Match in."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

from fastapi import Response

from argus.api.business import BusinessContext
from argus.domain.business.list_version import list_version, records_mark
from argus.domain.business.transactions import GrantImportStore


def _person(context: BusinessContext) -> str:
    return str(context.scope.actor_id or context.scope.person_id)


def _version(context: BusinessContext, mark: str) -> str:
    record = context.record_context
    return list_version(
        mark,
        space_id=str(context.scope.owner.space_id),
        person_id=_person(context),
        capabilities=record.capabilities if record else (),
    )


def stored_version(context: BusinessContext) -> str | None:
    """The version from the stored records, read before the list is built so a
    write that lands meanwhile shows as a change on the next check. None for
    the in-memory app, which has no records to ask."""

    store = context.service.imports.store
    if not isinstance(store, GrantImportStore):
        return None
    mark = records_mark(
        store.authority.pool,
        space_id=str(context.scope.owner.space_id),
        person_id=_person(context),
    )
    return _version(context, mark)


def answer_version(context: BusinessContext, answer: dict[str, Any]) -> str:
    """The in-memory app's version: the answer itself, since it keeps no
    change marks. It saves the bytes, not the work."""

    body = json.dumps(answer, sort_keys=True, default=str)
    return _version(context, sha256(body.encode()).hexdigest())


def etag(version: str) -> str:
    return f'"{version}"'


def unchanged(held: str | None, version: str) -> bool:
    """Whether the caller already holds this version. A proxy that compressed
    the earlier answer may have marked its ETag weak."""

    return (held or "").strip().removeprefix("W/") == etag(version)


def not_modified(version: str) -> Response:
    return Response(status_code=304, headers={"ETag": etag(version)})
