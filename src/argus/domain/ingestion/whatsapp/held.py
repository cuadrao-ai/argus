"""Private Personal drafts waiting for assignment; W9 owns the webhook caller.

The held row owns state and reason. The draft marker is immutable provenance.
Assignment and expiry share owner, source and row locks. Adoption and transfer
must use BoundPool inside assignment before settling the held row once.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import uuid4

from loguru import logger
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from argus.domain.business.contracts.deletion import PURGE_AFTER
from argus.domain.business.read_budget import (
    InMemoryHeldReadBudget,
    InMemoryReadBudget,
    PostgresHeldReadBudget,
)
from argus.domain.business.transactions import lock_owner
from argus.domain.ingestion.documents.models import DocumentDraft
from argus.domain.ingestion.documents.store import InMemoryDocumentStore
from argus.domain.ingestion.documents.store_postgres import (
    PostgresDocumentStore,
    lock_sources,
)
from argus.domain.ingestion.whatsapp.config import load_whatsapp_settings
from argus.domain.owner_scope import space_id

MARK = "whatsapp_held"
Reason = Literal[
    "no_buyer_rnc",
    "no_match",
    "two_matches",
    "no_eligible_business",
    "held_read_cap",
    "read_failed",
]
State = Literal["held", "assigned", "expired"]


@dataclass(frozen=True)
class HeldFile:
    id: str
    user_id: str
    sender_link_id: str
    provider_message_key: bytes
    connection_id: str
    reason: Reason
    held_at: datetime
    state: State = "held"
    assigned_space_id: str | None = None
    assigned_connection_id: str | None = None
    settled_at: datetime | None = None


@dataclass(frozen=True)
class PendingFile:
    held: HeldFile
    draft: DocumentDraft
    lease_until: datetime | None


def is_held(draft: DocumentDraft) -> bool:
    return draft.resolution.get(MARK) is True


class BoundPool:
    """Share an existing transaction and its locks with the document store."""

    def __init__(self, connection: Any) -> None:
        self.db = connection

    def connection(self) -> Any:
        return nullcontext(self.db)


def _row(row: dict[str, Any]) -> HeldFile:
    return HeldFile(
        **{
            key: str(value)
            if value is not None and (key.endswith("_id") or key == "id")
            else value
            for key, value in row.items()
        }
    )


class PostgresHeldFiles:
    def __init__(self, store: PostgresDocumentStore) -> None:
        self.store, self.pool = store, store._pool

    def capture(
        self,
        *,
        user_id: str,
        sender_link_id: str,
        provider_message_key: bytes,
        reason: Reason,
        now: datetime,
    ) -> Callable[[Any, str], None]:
        """An upload hook commits row and mark before dispatch sees the draft."""

        def captured(db: Any, connection_id: str) -> None:
            self._hold(
                db,
                user_id,
                sender_link_id,
                provider_message_key,
                connection_id,
                reason,
                now,
            )

        return captured

    def _hold(
        self,
        db: Any,
        user_id: str,
        sender_link_id: str,
        provider_message_key: bytes,
        connection_id: str,
        reason: Reason,
        now: datetime,
    ) -> HeldFile:
        found = db.execute(
            "select c.owner_space_id,c.lease_until,d.draft,d.batch from public.financial_source_connections c"
            " join public.financial_document_extractions d on d.connection_id=c.id and d.user_id=c.user_id"
            " where c.id=%s and c.user_id=%s for update of c,d",
            (connection_id, user_id),
        ).fetchone()
        if found is None or found[0] is not None:
            raise ValueError("held_file_requires_personal_draft")
        if not found[2].get("resolution", {}).get(MARK) and (
            found[3] is not None or found[1] is not None and found[1] > now
        ):
            raise ValueError("held_file_already_read")
        with db.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "insert into public.whatsapp_held_files(user_id,sender_link_id,provider_message_key,connection_id,reason,held_at) values(%s,%s,%s,%s,%s,%s) on conflict(provider_message_key) do nothing returning *",
                (
                    user_id,
                    sender_link_id,
                    provider_message_key,
                    connection_id,
                    reason,
                    now,
                ),
            )
            saved = cursor.fetchone()
            if saved is None:
                cursor.execute(
                    "select * from public.whatsapp_held_files where provider_message_key=%s",
                    (provider_message_key,),
                )
                saved = cursor.fetchone()
            row = _row(saved)
        if row.user_id != user_id or row.connection_id != connection_id:
            raise ValueError("held_message_conflict")
        db.execute(
            "update public.financial_document_extractions set draft=jsonb_set(draft,'{resolution}',coalesce(draft->'resolution','{}'::jsonb)||%s) where user_id=%s and connection_id=%s",
            (Jsonb({MARK: True}), user_id, connection_id),
        )
        return row

    def hold(
        self,
        *,
        user_id: str,
        sender_link_id: str,
        provider_message_key: bytes,
        connection_id: str,
        reason: Reason,
        now: datetime,
    ) -> HeldFile:
        with self.pool.connection() as db, db.transaction():
            lock_owner(db, user_id)
            lock_sources(db, user_id)
            return self._hold(
                db,
                user_id,
                sender_link_id,
                provider_message_key,
                connection_id,
                reason,
                now,
            )

    def list_for_user(self, user_id: str) -> list[HeldFile]:
        with self.pool.connection() as db, db.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "select * from public.whatsapp_held_files where user_id=%s order by held_at,id",
                (user_id,),
            )
            return [_row(row) for row in cursor.fetchall()]

    def pending_for_user(
        self, user_id: str, held_id: str | None = None
    ) -> list[PendingFile]:
        with self.pool.connection() as db, db.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "select h.*, d.draft, c.lease_until from public.whatsapp_held_files h"
                " join public.financial_document_extractions d on (d.user_id,d.connection_id)=(h.user_id,h.connection_id)"
                " join public.financial_source_connections c on (c.user_id,c.id)=(h.user_id,h.connection_id)"
                " where h.user_id=%s and h.state='held' and c.owner_space_id is null"
                " and (%s::uuid is null or h.id=%s) order by h.held_at desc,h.id",
                (user_id, held_id, held_id),
            )
            pending = []
            for row in cursor.fetchall():
                draft = DocumentDraft.model_validate(row.pop("draft"))
                lease_until = row.pop("lease_until")
                pending.append(PendingFile(_row(row), draft, lease_until))
            return pending

    @contextmanager
    def assignment(
        self, user_id: str, held_id: str
    ) -> Iterator[tuple[Any, HeldFile | None]]:
        """W9 adopts and settles in this transaction; expiry takes the same locks."""
        with self.pool.connection() as db, db.transaction():
            lock_owner(db, user_id)
            lock_sources(db, user_id)
            with db.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    "select * from public.whatsapp_held_files where id=%s and user_id=%s for update",
                    (held_id, user_id),
                )
                found = cursor.fetchone()
            yield db, _row(found) if found else None

    def settle(
        self,
        *,
        user_id: str,
        held_id: str,
        business_id: str,
        connection_id: str,
        now: datetime,
    ) -> bool:
        with self.assignment(user_id, held_id) as (db, row):
            if row is None or row.state != "held":
                return False
            source = db.execute(
                "select c.lease_until,d.source_path,d.rebuilt_path from public.financial_source_connections c join public.financial_document_extractions d on d.connection_id=c.id and d.user_id=c.user_id where c.user_id=%s and c.id=%s for update of c,d",
                (user_id, row.connection_id),
            ).fetchone()
            if source is None or source[0] is not None and source[0] > now:
                return False
            # External erasure cannot roll back with SQL. A partial erase cannot assign.
            if any(path and self.store.objects.get(path) is None for path in source[1:]):
                return False
            db.execute(
                "update public.whatsapp_held_files set state='assigned',assigned_space_id=%s,assigned_connection_id=%s,settled_at=%s where id=%s",
                (business_id, connection_id, now, held_id),
            )
            return True

    def charge(
        self, user_id: str, connection_id: str, now: datetime, business: Any
    ) -> str | None:
        with self.pool.connection() as db, db.transaction():
            lock_owner(db, user_id)
            lock_sources(db, user_id)
            active = db.execute(
                "select 1 from public.whatsapp_held_files h join public.financial_source_connections c on c.id=h.connection_id and c.user_id=h.user_id where h.user_id=%s and h.connection_id=%s and h.state='held' and c.owner_space_id is null limit 1",
                (user_id, connection_id),
            ).fetchone()
            if active is None:
                return "document_reading_not_allowed"
            return PostgresHeldReadBudget(
                BoundPool(db), getattr(business, "settings", None)
            ).charge(user_id, now)

    def budget(self, business: Any = None) -> PostgresHeldReadBudget:
        return PostgresHeldReadBudget(self.pool, getattr(business, "settings", None))

    def expire(self, held_id: str, now: datetime, user_id: str | None = None) -> bool:
        if user_id is None:
            with self.pool.connection() as db:
                found = db.execute(
                    "select user_id::text from public.whatsapp_held_files where id=%s",
                    (held_id,),
                ).fetchone()
            if found is None:
                return False
            user_id = found[0]
        with self.assignment(user_id, held_id) as (db, row):
            if row is None or row.state != "held" or row.held_at + PURGE_AFTER > now:
                return False
            draft = db.execute(
                "select d.source_path,d.rebuilt_path,c.owner_space_id,c.lease_until from public.financial_document_extractions d join public.financial_source_connections c on c.id=d.connection_id and c.user_id=d.user_id where d.user_id=%s and d.connection_id=%s for update of c,d",
                (user_id, row.connection_id),
            ).fetchone()
            if (
                draft is None
                or draft[2] is not None
                or draft[3] is not None
                and draft[3] > now
            ):
                return False
            paths = [path for path in draft[:2] if path]
            protected = db.execute(
                "select exists(select 1 from public.whatsapp_held_files where user_id=%s and connection_id=%s and (state='assigned' or state='held' and held_at>%s))"
                " or exists(select 1 from public.financial_document_extractions where connection_id<>%s and (source_path=any(%s) or rebuilt_path=any(%s)))"
                " or exists(select 1 from argus_private.business_custody_objects where source_path=any(%s) or destination_path=any(%s))"
                " or exists(select 1 from public.business_sources where connection_id=%s)"
                " or exists(select 1 from argus_private.account_deletion_runs where user_id=%s and status<>'done')",
                (
                    user_id,
                    row.connection_id,
                    now - PURGE_AFTER,
                    row.connection_id,
                    paths,
                    paths,
                    paths,
                    paths,
                    row.connection_id,
                    user_id,
                ),
            ).fetchone()[0]
            if protected:
                return False
            PostgresDocumentStore(BoundPool(db), self.store.objects).forget(
                user_id=user_id, connection_id=row.connection_id
            )
            db.execute(
                "update public.whatsapp_held_files set state='expired',settled_at=%s where user_id=%s and connection_id=%s and state='held'",
                (now, user_id, row.connection_id),
            )
            db.execute(
                "delete from public.financial_source_connections where user_id=%s and id=%s and owner_space_id is null",
                (user_id, row.connection_id),
            )
            return True


class InMemoryHeldFiles:
    def __init__(self, store: InMemoryDocumentStore) -> None:
        self.store = store
        self.rows: dict[str, HeldFile] = {}
        self._lock = threading.RLock()
        self._budget: InMemoryHeldReadBudget | None = None

    def hold(
        self,
        *,
        user_id: str,
        sender_link_id: str,
        provider_message_key: bytes,
        connection_id: str,
        reason: Reason,
        now: datetime,
    ) -> HeldFile:
        with self._lock:
            connection = self.store.connections.get_any_scope(
                user_id=user_id, connection_id=connection_id
            )
            draft = self.store.draft(user_id=user_id, connection_id=connection_id)
            if space_id(connection.scope) is not None or draft is None:
                raise ValueError("held_file_requires_personal_draft")
            for row in self.rows.values():
                if row.provider_message_key == provider_message_key:
                    if (row.user_id, row.connection_id) != (user_id, connection_id):
                        raise ValueError("held_message_conflict")
                    return row
            if not is_held(draft) and (
                self.store.get(user_id=user_id, connection_id=connection_id) is not None
                or connection.lease_until is not None
                and connection.lease_until > now
            ):
                raise ValueError("held_file_already_read")
            marked = draft.model_copy(
                update={"resolution": {**draft.resolution, MARK: True}}
            )
            if not self.store.update(
                user_id=user_id, draft=marked, expected_version=draft.version
            ):
                raise ValueError("held_file_changed")
            row = HeldFile(
                str(uuid4()),
                user_id,
                sender_link_id,
                provider_message_key,
                connection_id,
                reason,
                now,
            )
            self.rows[row.id] = row
            return row

    def list_for_user(self, user_id: str) -> list[HeldFile]:
        with self._lock:
            return [row for row in self.rows.values() if row.user_id == user_id]

    def pending_for_user(
        self, user_id: str, held_id: str | None = None
    ) -> list[PendingFile]:
        with self._lock:
            pending = []
            for row in self.list_for_user(user_id):
                if row.state != "held" or (held_id and row.id != held_id):
                    continue
                key = {"user_id": user_id, "connection_id": row.connection_id}
                draft = self.store.draft(**key)
                connection = self.store.connections.get_any_scope(**key)
                if draft is not None and space_id(connection.scope) is None:
                    pending.append(PendingFile(row, draft, connection.lease_until))
            return sorted(
                pending, key=lambda item: (-item.held.held_at.timestamp(), item.held.id)
            )

    def settle(
        self,
        *,
        user_id: str,
        held_id: str,
        business_id: str,
        connection_id: str,
        now: datetime,
    ) -> bool:
        with self._lock:
            row = self.rows.get(held_id)
            if row is None or row.user_id != user_id or row.state != "held":
                return False
            source = self.store.connections.get_any_scope(
                user_id=user_id, connection_id=row.connection_id
            )
            if source.lease_until is not None and source.lease_until > now:
                return False
            if (
                self.store.source(user_id=user_id, connection_id=row.connection_id)
                is None
            ):
                return False
            rebuilt = self.store._rebuilt.get((user_id, row.connection_id))
            if rebuilt and self.store.objects.get(rebuilt[0]) is None:
                return False
            self.rows[held_id] = replace(
                row,
                state="assigned",
                assigned_space_id=business_id,
                assigned_connection_id=connection_id,
                settled_at=now,
            )
            return True

    def budget(
        self, business: InMemoryReadBudget | None = None
    ) -> InMemoryHeldReadBudget:
        with self._lock:
            if self._budget is None:
                self._budget = InMemoryHeldReadBudget(business or InMemoryReadBudget())
            return self._budget

    def expire(self, held_id: str, now: datetime) -> bool:
        with self._lock:
            row = self.rows.get(held_id)
            if row is None or row.state != "held" or row.held_at + PURGE_AFTER > now:
                return False
            key = row.user_id, row.connection_id
            connection = self.store.connections.get_any_scope(
                user_id=row.user_id, connection_id=row.connection_id
            )
            if (
                space_id(connection.scope) is not None
                or connection.lease_until is not None
                and connection.lease_until > now
            ):
                return False
            if any(
                other.connection_id == row.connection_id
                and (
                    other.state == "assigned"
                    or other.state == "held"
                    and other.held_at + PURGE_AFTER > now
                )
                for other in self.rows.values()
            ):
                return False
            paths = {self.store._sources.get(key)}
            paths.update(v[0] for k, v in self.store._rebuilt.items() if k == key)
            paths.discard(None)
            if any(
                path in paths for k, path in self.store._sources.items() if k != key
            ) or any(v[0] in paths for k, v in self.store._rebuilt.items() if k != key):
                return False
            self.store.forget(user_id=row.user_id, connection_id=row.connection_id)
            for other in list(self.rows.values()):
                if other.connection_id == row.connection_id and other.state == "held":
                    self.rows[other.id] = replace(other, state="expired", settled_at=now)
            return True


_factory_lock = threading.Lock()


def held_files(store: Any) -> PostgresHeldFiles | InMemoryHeldFiles:
    if isinstance(store, PostgresDocumentStore):
        return PostgresHeldFiles(store)
    with _factory_lock:
        if not hasattr(store, "_whatsapp_held_files"):
            store._whatsapp_held_files = InMemoryHeldFiles(store)
        return store._whatsapp_held_files


def charge_read(
    store: Any, user_id: str, connection_id: str, now: datetime, business: Any
) -> str | None:
    if not load_whatsapp_settings().intake_ready:
        return "document_reading_not_allowed"
    files = held_files(store)
    if isinstance(files, PostgresHeldFiles):
        return files.charge(user_id, connection_id, now, business)
    with files._lock:
        if not any(
            row.connection_id == connection_id and row.state == "held"
            for row in files.list_for_user(user_id)
        ):
            return "document_reading_not_allowed"
        return files.budget(business).charge(user_id, now)


class HeldFileExpiry:
    def __init__(
        self,
        pool: Any,
        objects: Any,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.files = PostgresHeldFiles(PostgresDocumentStore(pool, objects))
        self.clock = clock
        self._next: datetime | None = None

    def tick(self) -> None:
        if not load_whatsapp_settings().intake_ready:
            return
        now = self.clock()
        if self._next is not None and now < self._next:
            return
        self._next = now + timedelta(hours=1)
        with self.files.pool.connection() as db:
            due = db.execute(
                "select id::text,user_id::text from public.whatsapp_held_files where state='held' and held_at<=%s order by held_at,id",
                (now - PURGE_AFTER,),
            ).fetchall()
        for held_id, user in due:
            try:
                self.files.expire(held_id, now, user)
            except Exception as error:
                logger.warning(
                    "Document upkeep held expiry failed; retry next hour",
                    failure_mode=type(error).__name__,
                )
