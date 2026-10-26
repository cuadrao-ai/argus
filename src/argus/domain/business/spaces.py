"""Business spaces, with a stable legacy default and explicit additional creation."""

from __future__ import annotations

import hashlib
import threading
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Protocol

from psycopg_pool import ConnectionPool

from argus.domain.business.access import ensure_owner_grant
from argus.domain.business.country import (
    COUNTRIES,
    DEFAULT_COUNTRY,
    business_country,
)
from argus.domain.business.lifecycle import (
    BusinessLifecycleError,
    require_ownership_admission,
)
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

# Founder-approved October 8: the name a space starts with until renamed.
DEFAULT_SPACE_NAMES = {"es": "Mi negocio", "en": "My business"}
MAX_NAME_LENGTH = 80


@dataclass(frozen=True)
class Space:
    id: str
    name: str
    custodian_id: str
    name_prompt_seen: bool = False
    country: str = DEFAULT_COUNTRY
    currency: str = COUNTRIES[DEFAULT_COUNTRY].currency

    @property
    def name_required(self) -> bool:
        return self.name in DEFAULT_SPACE_NAMES.values()


def default_space_name(language: str | None) -> str:
    """English when the person's language is English, else Spanish."""

    return DEFAULT_SPACE_NAMES["en" if language == "en" else "es"]


class SpaceStore(Protocol):
    def open_space(self, person_id: str) -> Space | None: ...

    def get(self, space_id: str) -> Space | None:
        """An open Business space by id, for a grant that names it."""
        ...

    def create(
        self, person_id: str, name: str, country: str = DEFAULT_COUNTRY
    ) -> tuple[Space, bool]:
        """The person's open space, created with ``name`` and ``country`` when
        there is none.

        Returns ``(space, created)``. Concurrent calls converge on one space.
        """
        ...

    def create_additional(
        self, person_id: str, name: str, country: str, key: str
    ) -> tuple[Space, bool]: ...

    def read_workspace(self, person_id: str, space_id: str) -> WorkspaceSnapshot: ...

    def save_workspace(
        self,
        person_id: str,
        space_id: str,
        command: SaveWorkspace,
        key: str,
        objects: ProfileImageObjects | None = None,
    ) -> WorkspaceSnapshot: ...

    def workspace_asset(
        self, person_id: str, space_id: str, asset_id: str
    ) -> WorkspaceAsset: ...

    def upload_workspace_image(
        self,
        person_id: str,
        space_id: str,
        content: bytes,
        media_type: str,
        key: str,
        objects: ProfileImageObjects,
    ) -> WorkspaceAsset: ...

    def claim_naming_visit(self, person_id: str, space_id: str) -> bool: ...

    def rename(
        self, person_id: str, name: str, space_id: str | None = None
    ) -> Space | None: ...

    def consent_accepted_at(self, person_id: str, version: str) -> datetime | None:
        """When the person accepted this wording of the Business consent screen."""
        ...

    def accept_consent(self, person_id: str, space_id: str, version: str) -> datetime:
        """Records the acceptance once per wording, naming the Business the
        person works in, and returns the first acceptance time."""
        ...


class PostgresSpaceStore:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def open_space(self, person_id: str) -> Space | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                "select id::text, name, created_by::text, business_name_prompt_seen_at is not null,"
                " country, currency from public.spaces"
                " where id = public.business_space_of(%s)",
                (person_id,),
            ).fetchone()
        return Space(*row) if row else None

    def get(self, space_id: str) -> Space | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                "select id::text, name, created_by::text, business_name_prompt_seen_at is not null,"
                " country, currency from public.spaces"
                " where id = %s and kind = 'business' and closed_at is null",
                (space_id,),
            ).fetchone()
        return Space(*row) if row else None

    def create(
        self, person_id: str, name: str, country: str = DEFAULT_COUNTRY
    ) -> tuple[Space, bool]:
        with self._pool.connection() as connection, connection.transaction():
            user = connection.execute(
                "select id from auth.users where id=%s for no key update", (person_id,)
            ).fetchone()
            if user is None:
                raise BusinessLifecycleError("business_record_not_found")
            require_ownership_admission(connection, person_id)
            created = connection.execute(
                "insert into public.spaces (kind, name, created_by, current_owner_id, country, currency)"
                " values ('business', %s, %s, %s, %s, %s)"
                " on conflict (current_owner_id) where kind = 'business' and closed_at is null and business_legacy_default"
                " do nothing returning id::text, name, created_by::text,"
                " business_name_prompt_seen_at is not null, country, currency",
                (name, person_id, person_id, country, business_country(country).currency),
            ).fetchone()
            if created is not None:
                # The owner's grant is born with the space, in the same transaction.
                ensure_owner_grant(connection, created[0], person_id)
        if created is not None:
            return Space(*created), True
        existing = self.open_space(person_id)
        if existing is None:
            raise BusinessLifecycleError("business_record_not_found")
        return existing, False

    def create_additional(
        self, person_id: str, name: str, country: str, key: str
    ) -> tuple[Space, bool]:
        from argus.domain.business.workspace_postgres import create_additional

        space_id, created = create_additional(self._pool, person_id, name, country, key)
        space = self.get(space_id)
        if space is None:
            raise WorkspaceError("business_record_not_found")
        return space, created

    def read_workspace(self, person_id: str, space_id: str) -> WorkspaceSnapshot:
        from argus.domain.business.workspace_postgres import read_workspace

        return read_workspace(self._pool, person_id, space_id)

    def save_workspace(
        self,
        person_id: str,
        space_id: str,
        command: SaveWorkspace,
        key: str,
        objects: ProfileImageObjects | None = None,
    ) -> WorkspaceSnapshot:
        from argus.domain.business.workspace_postgres import save_workspace

        return save_workspace(self._pool, person_id, space_id, command, key, objects)

    def workspace_asset(
        self, person_id: str, space_id: str, asset_id: str
    ) -> WorkspaceAsset:
        from argus.domain.business.workspace_postgres import workspace_asset

        return workspace_asset(self._pool, person_id, space_id, asset_id)

    def upload_workspace_image(
        self,
        person_id: str,
        space_id: str,
        content: bytes,
        media_type: str,
        key: str,
        objects: ProfileImageObjects,
    ) -> WorkspaceAsset:
        from argus.domain.business.workspace_postgres import upload_workspace_image

        return upload_workspace_image(
            self._pool, person_id, space_id, content, media_type, key, objects
        )

    def claim_naming_visit(self, person_id: str, space_id: str) -> bool:
        from argus.domain.business.memberships import require_manager

        with self._pool.connection() as connection, connection.transaction():
            require_manager(connection, space_id, person_id)
            row = connection.execute(
                "update public.spaces set business_name_prompt_seen_at=now() where id=%s"
                " and business_name_prompt_seen_at is null and name=any(%s) returning id",
                (space_id, list(DEFAULT_SPACE_NAMES.values())),
            ).fetchone()
        return row is not None

    def rename(
        self, person_id: str, name: str, space_id: str | None = None
    ) -> Space | None:
        from argus.domain.business.memberships import require_manager

        with self._pool.connection() as connection, connection.transaction():
            if space_id is None:
                row = connection.execute(
                    "select public.business_space_of(%s)", (person_id,)
                ).fetchone()
                space_id = str(row[0]) if row and row[0] else None
            if space_id is None:
                return None
            require_manager(connection, space_id, person_id)
            row = connection.execute(
                "update public.spaces set name=%s where id=%s returning id::text,name,created_by::text,"
                " business_name_prompt_seen_at is not null,country,currency",
                (name, space_id),
            ).fetchone()
        return Space(*row) if row else None

    def consent_accepted_at(self, person_id: str, version: str) -> datetime | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                "select accepted_at from public.business_consent_acceptances"
                " where user_id = %s and copy_version = %s",
                (person_id, version),
            ).fetchone()
        return row[0] if row else None

    def accept_consent(self, person_id: str, space_id: str, version: str) -> datetime:
        with self._pool.connection() as connection:
            row = connection.execute(
                "with added as ("
                " insert into public.business_consent_acceptances"
                " (user_id, space_id, copy_version) values (%s, %s, %s)"
                " on conflict (user_id, copy_version) do nothing returning accepted_at)"
                " select accepted_at from added union all"
                " select accepted_at from public.business_consent_acceptances"
                " where user_id = %s and copy_version = %s limit 1",
                (person_id, space_id, version, person_id, version),
            ).fetchone()
        if row is not None:
            return row[0]
        # A concurrent first acceptance committed after this statement's snapshot.
        existing = self.consent_accepted_at(person_id, version)
        if existing is None:  # pragma: no cover - the conflict means it exists
            raise LookupError("business consent vanished during accept")
        return existing


class InMemorySpaceStore:
    def __init__(self, access=None) -> None:
        self.access = access
        self._lock = access._lock if access is not None else threading.RLock()
        self._spaces: dict[str, Space] = {}
        self._defaults: dict[str, str] = {}
        self._details: dict[str, BusinessDetails] = {}
        self._revisions: dict[str, int] = {}
        self._appearances: dict[str, object] = {}
        self._assets: dict[str, WorkspaceAsset] = {}
        self._commands: dict[tuple[str, str, str], tuple[dict, str]] = {}
        self._consents: dict[tuple[str, str], datetime] = {}

    def open_space(self, person_id: str) -> Space | None:
        with self._lock:
            return self._spaces.get(self._defaults.get(person_id, ""))

    def get(self, space_id: str) -> Space | None:
        with self._lock:
            return self._spaces.get(space_id)

    def create(
        self, person_id: str, name: str, country: str = DEFAULT_COUNTRY
    ) -> tuple[Space, bool]:
        with self._lock:
            existing = self._spaces.get(self._defaults.get(person_id, ""))
            if existing is not None:
                if self.access is not None and "read" not in self.access.capabilities(
                    existing.id, person_id
                ):
                    raise BusinessLifecycleError("business_record_not_found")
                return existing, False
            space = Space(
                str(uuid.uuid4()),
                name,
                person_id,
                country=country,
                currency=business_country(country).currency,
            )
            self._spaces[space.id] = space
            self._defaults[person_id] = space.id
            return space, True

    def create_additional(
        self, person_id: str, name: str, country: str, key: str
    ) -> tuple[Space, bool]:
        checked_key(key)
        payload = {"name": name, "country": country}
        with self._lock:
            previous = self._commands.get((person_id, "create", key))
            if previous is not None:
                if previous[0] != payload:
                    raise WorkspaceError("idempotency_conflict")
                self.read_workspace(person_id, previous[1])
                return self._spaces[previous[1]], False
            default = self.open_space(person_id)
            if default is None:
                raise WorkspaceError("business_default_required")
            space = Space(
                str(uuid.uuid4()),
                name,
                person_id,
                country=country,
                currency=business_country(country).currency,
            )
            if self.access is None:
                raise WorkspaceError("business_record_not_found")
            self.access.ensure_owner_grant(space.id, person_id)
            self._spaces[space.id] = space
            self._commands[(person_id, "create", key)] = (payload, space.id)
            return space, True

    def read_workspace(self, person_id: str, space_id: str) -> WorkspaceSnapshot:
        with self._lock:
            space = self.get(space_id)
            if (
                space is None
                or (
                    self.access is not None
                    and "read" not in self.access.capabilities(space_id, person_id)
                )
                or (self.access is None and space.custodian_id != person_id)
            ):
                raise WorkspaceError("business_record_not_found")
            return WorkspaceSnapshot(
                space_id=space.id,
                name=space.name,
                country=space.country,
                currency=space.currency,
                revision=self._revisions.get(space_id, 0),
                details=self._details.get(space_id, BusinessDetails()),
                appearance=self._appearances.get(space_id, DefaultAppearance()),
            )

    def save_workspace(
        self,
        person_id: str,
        space_id: str,
        command: SaveWorkspace,
        key: str,
        objects: ProfileImageObjects | None = None,
    ) -> WorkspaceSnapshot:
        checked_key(key)
        payload = {"space_id": space_id, **command_payload(command)}
        with self._lock:
            current = self.read_workspace(person_id, space_id)
            if self.access is not None:
                self.access._manager(space_id, person_id)
            previous = self._commands.get((person_id, "save", key))
            if previous is not None:
                if previous[0] != payload:
                    raise WorkspaceError("idempotency_conflict")
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
                    asset = self.workspace_asset(person_id, space_id, appearance.asset_id)
                    if objects is None:
                        raise ProfileImageStorageUnavailable("objects_unavailable")
                    render(objects, asset, appearance.crop)
            self._appearances[space_id] = appearance
            self._spaces[space_id] = replace(self._spaces[space_id], name=name)
            self._details[space_id] = details
            if (
                name != current.name
                or details != current.details
                or appearance != current.appearance
            ):
                self._revisions[space_id] = current.revision + 1
            self._commands[(person_id, "save", key)] = (payload, space_id)
            return self.read_workspace(person_id, space_id)

    def workspace_asset(
        self, person_id: str, space_id: str, asset_id: str
    ) -> WorkspaceAsset:
        with self._lock:
            self.read_workspace(person_id, space_id)
            asset = self._assets.get(asset_id)
            if asset is None or asset.space_id != space_id:
                raise WorkspaceError("business_image_not_found")
            return asset

    def upload_workspace_image(
        self,
        person_id: str,
        space_id: str,
        content: bytes,
        media_type: str,
        key: str,
        objects: ProfileImageObjects,
    ) -> WorkspaceAsset:
        checked_key(key)
        with self._lock:
            self.read_workspace(person_id, space_id)
            if self.access is not None:
                self.access._manager(space_id, person_id)
            stored, width, height = normalized_source(content, media_type)
            digest = hashlib.sha256(stored).hexdigest()
            payload = {"space_id": space_id, "sha256": digest}
            previous = self._commands.get((person_id, "upload", key))
            if previous is not None:
                if previous[0] != payload:
                    raise WorkspaceError("idempotency_conflict")
                return self.workspace_asset(person_id, space_id, previous[1])
            asset = next(
                (
                    a
                    for a in self._assets.values()
                    if a.space_id == space_id and a.sha256 == digest
                ),
                None,
            )
            asset = asset or WorkspaceAsset(
                str(uuid.uuid4()), space_id, digest, width, height
            )
            objects.put(asset.source_path, stored, "image/webp")
            self._assets[asset.id] = asset
            self._commands[(person_id, "upload", key)] = (payload, asset.id)
            return asset

    def claim_naming_visit(self, person_id: str, space_id: str) -> bool:
        with self._lock:
            space = self._spaces.get(self._defaults.get(person_id, ""))
            if self.access is not None:
                self.access._manager(space_id, person_id)
                space = self._spaces.get(space_id)
            if (
                space is None
                or space.id != space_id
                or space.name_prompt_seen
                or not space.name_required
            ):
                return False
            self._spaces[space.id] = replace(space, name_prompt_seen=True)
            return True

    def rename(
        self, person_id: str, name: str, space_id: str | None = None
    ) -> Space | None:
        with self._lock:
            current = self._spaces.get(self._defaults.get(person_id, ""))
            if space_id is not None and self.access is not None:
                self.access._manager(space_id, person_id)
                current = self._spaces.get(space_id)
            if current is None or (space_id is not None and current.id != space_id):
                return None
            space = replace(current, name=name)
            self._spaces[current.id] = space
            if space.name != current.name:
                self._revisions[current.id] = self._revisions.get(current.id, 0) + 1
            return space

    def consent_accepted_at(self, person_id: str, version: str) -> datetime | None:
        with self._lock:
            return self._consents.get((person_id, version))

    def accept_consent(self, person_id: str, space_id: str, version: str) -> datetime:
        with self._lock:
            return self._consents.setdefault(
                (person_id, version), datetime.now(timezone.utc)
            )
