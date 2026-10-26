"""Atomic workspace commands and saved projections."""

from __future__ import annotations

import hashlib
from uuid import UUID

from psycopg import Connection
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from argus.domain.business.access import ensure_owner_grant
from argus.domain.business.authority import authorize
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.country import business_country
from argus.domain.business.lifecycle import require_ownership_admission
from argus.domain.business.memberships import require_manager
from argus.domain.business.workspace import (
    BusinessDetails,
    SaveWorkspace,
    WorkspaceError,
    WorkspaceSnapshot,
    checked_key,
    command_payload,
)
from argus.domain.business.workspace_images import (
    DefaultAppearance,
    ImageAppearance,
    WorkspaceAsset,
    normalized_source,
    render,
)
from argus.domain.profile_images.objects import (
    ProfileImageObjects,
    ProfileImageStorageUnavailable,
)


def _actor(db: Connection, actor_id: str) -> None:
    row = db.execute(
        "select id from auth.users where id=%s and not coalesce(is_anonymous,false)"
        " and (banned_until is null or banned_until<=clock_timestamp()) for no key update",
        (actor_id,),
    ).fetchone()
    if row is None:
        raise WorkspaceError("business_record_not_found")
    require_ownership_admission(db, actor_id)


def _read(db: Connection, actor_id: str, space_id: str) -> WorkspaceSnapshot:
    authorize(
        db,
        TrustedActor(
            actor_id=UUID(actor_id), actor_kind="member", space_id=UUID(space_id)
        ),
    ).require("read")
    row = db.execute(
        "select name,country,currency,business_workspace_revision,business_provided_details,business_appearance"
        " from public.spaces where id=%s",
        (space_id,),
    ).fetchone()
    return WorkspaceSnapshot(
        space_id=space_id,
        name=row[0],
        country=row[1],
        currency=row[2],
        revision=row[3],
        details=BusinessDetails.model_validate(row[4]),
        appearance=row[5],
    )


def read_workspace(
    pool: ConnectionPool, actor_id: str, space_id: str
) -> WorkspaceSnapshot:
    with pool.connection() as db, db.transaction():
        return _read(db, actor_id, space_id)


def _previous(
    db: Connection, actor_id: str, operation: str, key: str, payload: dict
) -> str | None:
    checked_key(key)
    row = db.execute(
        "select payload,space_id::text from argus_private.business_workspace_commands"
        " where actor_id=%s and operation=%s and command_key=%s",
        (actor_id, operation, key),
    ).fetchone()
    if row is not None:
        if row[0] != payload:
            raise WorkspaceError("idempotency_conflict")
        return row[1]
    return None


def _remember(
    db: Connection, actor_id: str, operation: str, key: str, payload: dict, space_id: str
) -> None:
    db.execute(
        "insert into argus_private.business_workspace_commands"
        " (actor_id,operation,command_key,payload,space_id) values (%s,%s,%s,%s,%s)",
        (actor_id, operation, key, Jsonb(payload), space_id),
    )


def create_additional(
    pool: ConnectionPool, actor_id: str, name: str, country: str, key: str
) -> tuple[str, bool]:
    payload = {"name": name, "country": country}
    with pool.connection() as db, db.transaction():
        _actor(db, actor_id)
        previous = _previous(db, actor_id, "create", key, payload)
        if previous is not None:
            _read(db, actor_id, previous)
            return previous, False
        default = db.execute(
            "select id from public.spaces where current_owner_id=%s and kind='business' and business_legacy_default and closed_at is null",
            (actor_id,),
        ).fetchone()
        if default is None:
            raise WorkspaceError("business_default_required")
        row = db.execute(
            "insert into public.spaces"
            " (kind,name,created_by,current_owner_id,country,currency,business_legacy_default)"
            " values ('business',%s,%s,%s,%s,%s,false) returning id::text",
            (name, actor_id, actor_id, country, business_country(country).currency),
        ).fetchone()
        space_id = row[0]
        ensure_owner_grant(db, space_id, actor_id)
        _remember(db, actor_id, "create", key, payload, space_id)
        return space_id, True


def save_workspace(
    pool: ConnectionPool,
    actor_id: str,
    space_id: str,
    command: SaveWorkspace,
    key: str,
    objects: ProfileImageObjects | None = None,
) -> WorkspaceSnapshot:
    payload = {"space_id": space_id, **command_payload(command)}
    with pool.connection() as db, db.transaction():
        _actor(db, actor_id)
        require_manager(db, space_id, actor_id)
        current = _read(db, actor_id, space_id)
        if _previous(db, actor_id, "save", key, payload) is not None:
            return current
        if current.revision != command.expected_revision:
            raise WorkspaceError("business_workspace_stale")
        details = current.details
        if "details" in command.model_fields_set:
            details = (
                BusinessDetails.model_validate(
                    {
                        **current.details.model_dump(),
                        **command.details.model_dump(exclude_unset=True),
                    }
                )
                if command.details is not None
                else BusinessDetails()
            )
        name = command.name or current.name
        appearance = current.appearance
        if "appearance" in command.model_fields_set:
            appearance = command.appearance or DefaultAppearance()
            if isinstance(appearance, ImageAppearance):
                asset = _asset(db, space_id, appearance.asset_id)
                if objects is None:
                    raise ProfileImageStorageUnavailable("objects_unavailable")
                render(objects, asset, appearance.crop)
        if (
            name != current.name
            or details != current.details
            or appearance != current.appearance
        ):
            db.execute(
                "update public.spaces set name=%s,business_provided_details=%s,business_appearance=%s where id=%s",
                (
                    name,
                    Jsonb(details.model_dump()),
                    Jsonb(appearance.model_dump(mode="json")),
                    space_id,
                ),
            )
        _remember(db, actor_id, "save", key, payload, space_id)
        return _read(db, actor_id, space_id)


def _asset(db: Connection, space_id: str, asset_id: str) -> WorkspaceAsset:
    row = db.execute(
        "select id::text,space_id::text,sha256,width,height from argus_private.business_workspace_assets where id=%s and space_id=%s",
        (asset_id, space_id),
    ).fetchone()
    if row is None:
        raise WorkspaceError("business_image_not_found")
    return WorkspaceAsset(*row)


def workspace_asset(
    pool: ConnectionPool, actor_id: str, space_id: str, asset_id: str
) -> WorkspaceAsset:
    with pool.connection() as db, db.transaction():
        _read(db, actor_id, space_id)
        return _asset(db, space_id, asset_id)


def upload_workspace_image(
    pool: ConnectionPool,
    actor_id: str,
    space_id: str,
    content: bytes,
    media_type: str,
    key: str,
    objects: ProfileImageObjects,
) -> WorkspaceAsset:
    with pool.connection() as db, db.transaction():
        _actor(db, actor_id)
        require_manager(db, space_id, actor_id)
        stored, width, height = normalized_source(content, media_type)
        digest = hashlib.sha256(stored).hexdigest()
        payload = {"space_id": space_id, "sha256": digest}
        previous = _previous(db, actor_id, "upload", key, payload)
        row = db.execute(
            "select id::text from argus_private.business_workspace_assets where space_id=%s and sha256=%s",
            (space_id, digest),
        ).fetchone()
        if previous is not None:
            if row is None:
                raise WorkspaceError("business_image_not_found")
            return _asset(db, space_id, row[0])
        objects.put(
            f"business/{space_id}/identity/{digest}-source.webp", stored, "image/webp"
        )
        if row is None:
            row = db.execute(
                "insert into argus_private.business_workspace_assets(space_id,sha256,width,height) values(%s,%s,%s,%s) returning id::text",
                (space_id, digest, width, height),
            ).fetchone()
        _remember(db, actor_id, "upload", key, payload, space_id)
        return _asset(db, space_id, row[0])
