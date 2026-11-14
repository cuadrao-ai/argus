"""Permanent removal of a deleted document. The owner's "Eliminar
definitivamente" and the 7-day expiry run the same two steps:

1. ``purge``, in one transaction under the owner lock: record the purge with
   the stored objects still to erase, then delete the draft, its revisions,
   its message sources and the uploads with their reads. From the commit on,
   the document is gone for every reader and cannot be restored.
2. ``erase``: remove each recorded object and take it off the record. A
   failed erase keeps the rest on the record, and the next run finishes it.

Both steps are safe to repeat, and a second purge of the same document finds
the record and changes nothing."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import UUID

from loguru import logger
from psycopg import Connection
from psycopg.rows import dict_row

from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.deletion import deletion
from argus.domain.business.transactions import lock_owner
from argus.domain.ingestion.documents.objects import SourceObjects, connection_prefix
from argus.domain.ingestion.documents.store_postgres import lock_sources
from argus.domain.ingestion.reconcile import duplicates
from argus.domain.ingestion.reconcile.store import ImportTx
from argus.domain.ingestion.reconcile.store_postgres import _PostgresTx
from argus.domain.owner_scope import BusinessSpace

PurgeReason = Literal["owner", "expiry"]
BATCH = 25
#: Batches in one expiry run, so one run stays short however large the backlog.
MAX_BATCHES = 20


def was_purged(connection: Connection, space_id: UUID, document_id: UUID) -> bool:
    return (
        connection.execute(
            "select 1 from argus_private.business_document_purges"
            " where space_id=%s and %s=any(document_ids)",
            (space_id, document_id),
        ).fetchone()
        is not None
    )


def purge(
    connection: Connection,
    imports: ImportTx,
    *,
    space_id: UUID,
    owner_id: str,
    document_id: UUID,
    reason: PurgeReason,
    now: datetime,
) -> bool:
    """Step 1, inside the caller's transaction, which holds the owner lock.
    False when the document was purged before."""

    from argus.domain.business.actions.document_deletion import target

    if was_purged(connection, space_id, document_id):
        return False

    def rows(statement: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(statement, params)
            return list(cursor.fetchall()) if cursor.description else []

    event, attachments, candidates = target(
        rows, imports, space_id, owner_id, document_id
    )
    document = attachments[0]["draft"] if attachments else None
    marker = deletion(
        event.state if event else document["status"],
        event.resolution if event else document.get("resolution", {}),
    )
    if marker is None:
        raise ActionError("invalid_input", "business_document_not_deleted")
    if reason == "expiry" and marker.purge_at > now:
        raise ActionError("invalid_input", "business_document_purge_not_due")
    if any(
        row["lease_until"] is not None and row["lease_until"] > now for row in attachments
    ):
        raise ActionError("invalid_input", "business_document_reading")
    events = [event] if event is not None else list(candidates)
    uploads = [str(row["connection_id"]) for row in attachments]
    paths = sorted(
        {
            path
            for row in rows(
                "select source_path,rebuilt_path from public.financial_document_extractions"
                " where connection_id=any(%s::uuid[])",
                (uploads,),
            )
            for path in (row["source_path"], row["rebuilt_path"])
            if path
        }
    )
    if rows(
        "select 1 where exists(select 1 from argus_private.business_custody_objects"
        " where space_id=%s and source_path is not null"
        " and (source_path=any(%s) or destination_path=any(%s)))"
        " or exists(select 1 from argus_private.account_deletion_runs"
        " where user_id=%s and status<>'done')",
        (space_id, paths, paths, owner_id),
    ):
        raise ActionError("invalid_input", "business_document_purge_busy")
    ids = sorted({str(document_id), *(item.id for item in events), *uploads})
    pending = [
        *paths,
        *(
            connection_prefix(user_id=owner_id, connection_id=upload)
            for upload in uploads
        ),
    ]
    connection.execute(
        "insert into argus_private.business_document_purges"
        "(space_id,document_ids,reason,pending_objects) values (%s,%s::uuid[],%s,%s)",
        (space_id, ids, reason, pending),
    )
    messages = [
        row["id"]
        for row in rows(
            "select distinct s.id from public.business_sources s"
            " join public.business_draft_sources l on l.source_id=s.id and l.space_id=s.space_id"
            " where s.space_id=%s and s.connection_id is null and l.draft_id=any(%s::uuid[])"
            " and not exists (select 1 from public.business_draft_sources o"
            " where o.source_id=s.id and o.space_id=s.space_id"
            " and o.draft_id<>all(%s::uuid[]))",
            (space_id, [item.id for item in events], [item.id for item in events]),
        )
    ]
    for item in events:
        duplicates.forget(imports, item, now)
    connection.execute(
        "select set_config('argus.business_document_purge_space',%s,true)",
        (str(space_id),),
    )
    connection.execute(
        "delete from public.financial_import_events where owner_space_id=%s and id=any(%s::uuid[])",
        (space_id, [item.id for item in events]),
    )
    connection.execute(
        "delete from public.business_sources where space_id=%s and id=any(%s::uuid[])",
        (space_id, messages),
    )
    connection.execute(
        "delete from public.financial_source_connections where owner_space_id=%s and id=any(%s::uuid[])",
        (space_id, uploads),
    )
    connection.execute("select set_config('argus.business_document_purge_space','',true)")
    connection.execute(
        "delete from argus_private.business_custody_objects where space_id=%s"
        " and source_path is null and destination_path=any(%s)",
        (space_id, paths),
    )
    return True


def erase(pool: Any, objects: SourceObjects | None, space_id: UUID) -> int:
    """Step 2 for every purge of one Business with objects left. Returns how
    many objects are still left; a failure leaves them for the next run."""

    with pool.connection() as db:
        records = db.execute(
            "select p.id,p.pending_objects,s.created_by::text"
            " from argus_private.business_document_purges p"
            " join public.spaces s on s.id=p.space_id"
            " where p.space_id=%s and p.pending_objects<>'{}' order by p.purged_at,p.id",
            (space_id,),
        ).fetchall()
    left = sum(len(pending) for _, pending, _ in records)
    if objects is None:
        return left
    for record, pending, owner in records:
        for item in pending:
            with pool.connection() as db, db.transaction():
                # The same lock a new upload takes, so one that brings the
                # same bytes back either keeps them or writes them again.
                lock_sources(db, owner)
                if item.endswith("/"):
                    objects.delete(item)
                elif not db.execute(
                    "select exists(select 1 from public.financial_document_extractions"
                    " where source_path=%s or rebuilt_path=%s)"
                    " or exists(select 1 from argus_private.business_custody_objects"
                    " where source_path=%s or destination_path=%s)",
                    (item, item, item, item),
                ).fetchone()[0]:
                    objects.remove(item)
                    if objects.get(item) is not None:
                        raise RuntimeError("business_document_erase_unverified")
                db.execute(
                    "update argus_private.business_document_purges"
                    " set pending_objects=array_remove(pending_objects,%s) where id=%s",
                    (item, record),
                )
            left -= 1
    return left


class DocumentExpiry:
    """Purges documents deleted ``PURGE_AFTER`` ago and finishes erases left
    over. The documents worker's sweep loop calls ``tick`` every 30 seconds;
    it runs at most once per ``every``."""

    def __init__(
        self,
        pool: Any,
        objects: SourceObjects | None,
        *,
        every: timedelta,
        clock: Any = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.pool, self.objects, self.every, self.clock = pool, objects, every, clock
        self._next: datetime | None = None

    def tick(self) -> None:
        now = self.clock()
        if self.every <= timedelta(0) or (self._next is not None and now < self._next):
            return
        self._next = now + self.every
        self.run(now)

    def run(self, now: datetime) -> dict[str, int]:
        result = dict(purged=0, skipped=0, failed=0, left=0)
        with self.pool.connection() as db:
            spaces = [
                row[0]
                for row in db.execute(
                    "select distinct space_id from argus_private.business_document_purges"
                    " where pending_objects<>'{}'"
                ).fetchall()
            ]
        for space in spaces:
            self._erase(space, result)
        after: tuple[UUID, UUID] | None = None
        for _ in range(MAX_BATCHES):
            due = self._due(now, after)
            for space, owner, document in due:
                self._purge(space, owner, document, now, result)
            if len(due) < BATCH:
                break
            after = (due[-1][0], due[-1][2])
        if any(result.values()):
            logger.info("Document expiry run {}", result)
        return result

    def _due(
        self, now: datetime, after: tuple[UUID, UUID] | None
    ) -> list[tuple[UUID, str, UUID]]:
        from argus.domain.business.contracts.deletion import PURGE_AFTER

        with self.pool.connection() as db:
            return db.execute(
                "select owner_space_id,user_id::text,id from ("
                " select e.owner_space_id,e.user_id,e.id from public.financial_import_events e"
                " where e.state='dismissed' and e.resolution ? 'deleted'"
                " and (e.resolution->'deleted'->>'at')::timestamptz<=%(cutoff)s"
                " union all"
                " select c.owner_space_id,d.user_id,d.connection_id"
                " from public.financial_document_extractions d"
                " join public.financial_source_connections c on c.id=d.connection_id"
                " and c.user_id=d.user_id"
                " where (d.draft->>'status')='dismissed' and (d.draft->'resolution') ? 'deleted'"
                " and (d.draft->'resolution'->'deleted'->>'at')::timestamptz<=%(cutoff)s"
                " and c.owner_space_id is not null"
                ") due where %(after)s::uuid is null or (owner_space_id,id)>(%(after)s,%(id)s)"
                " order by owner_space_id,id limit %(limit)s",
                {
                    "cutoff": now - PURGE_AFTER,
                    "after": after[0] if after else None,
                    "id": after[1] if after else None,
                    "limit": BATCH,
                },
            ).fetchall()

    def _purge(
        self, space: UUID, owner: str, document: UUID, now: datetime, result: dict
    ) -> None:
        try:
            with self.pool.connection() as db, db.transaction():
                lock_owner(db, owner)
                purged = purge(
                    db,
                    _PostgresTx(db, owner, BusinessSpace(str(space))),
                    space_id=space,
                    owner_id=owner,
                    document_id=document,
                    reason="expiry",
                    now=now,
                )
        except ActionError as error:
            # A restore, an ambiguous link or a running read wins this round.
            logger.info("Document expiry skipped a document code={}", error.code)
            result["skipped"] += 1
            return
        except Exception as error:
            logger.warning("Document expiry failed", failure_mode=type(error).__name__)
            result["failed"] += 1
            return
        result["purged"] += purged
        self._erase(space, result)

    def _erase(self, space: UUID, result: dict) -> None:
        try:
            result["left"] += erase(self.pool, self.objects, space)
        except Exception as error:
            logger.warning(
                "Document erase failed; the next run retries",
                failure_mode=type(error).__name__,
            )
            result["failed"] += 1
