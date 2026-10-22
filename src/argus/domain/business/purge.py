"""Retry-safe day-30 Business graph and original-object removal."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from loguru import logger
from psycopg import sql

from argus.domain.account_deletion.auth_admin import AuthAdmin
from argus.domain.business.custody_graph import PostgresBusinessCustodyGraph
from argus.domain.ingestion.documents.objects import SourceObjects, owner_prefix
from argus.domain.profile_images import ProfileImages, business


class BusinessPurgePending(RuntimeError):
    pass


class BusinessPurgeBusy(RuntimeError):
    pass


class PostgresBusinessPurge:
    def __init__(
        self,
        connections: Any,
        objects: SourceObjects | None,
        auth: AuthAdmin,
        images: ProfileImages | None = None,
    ):
        self.connections, self.objects, self.auth = connections, objects, auth
        self.images = images

    def sweep(self, *, limit: int = 25) -> dict[str, int]:
        from argus.domain.business.close_mail import (
            deliver_close_mail,
            enqueue_purge_reminders,
        )

        # Day 23: each closed Business's owner is reminded once, with the
        # reopen path, before day 30 removes it.
        for reminded in enqueue_purge_reminders(self.connections):
            deliver_close_mail(self.connections, reminded)
        with self.connections.connection() as db:
            candidates = db.execute(
                "select space_id::text from ("
                "select id as space_id,closed_at as since from public.spaces where kind='business' and closed_at<=clock_timestamp()-interval '30 days' "
                "union select space_id,started_at from argus_private.business_purge_runs where status<>'done'"
                ") q group by space_id order by min(since),space_id limit %s",
                (limit,),
            ).fetchall()
        result = dict(resumed=0, done=0, pending=0, failed=0, busy=0)
        for (space,) in candidates:
            try:
                self.purge(space_id=space)
            except BusinessPurgeBusy:
                result["busy"] += 1
                continue
            except BusinessPurgePending:
                result["pending"] += 1
            except Exception as error:
                logger.error(
                    "Closed Business purge failed", failure_mode=type(error).__name__
                )
                result["failed"] += 1
            else:
                result["done"] += 1
            result["resumed"] += 1
        return result

    def purge(self, *, space_id: str) -> None:
        claimed = self._claim(space_id)
        if claimed is None:
            return
        run, claim = claimed
        try:
            self._erase_logo(run, claim)
            self._delete_graph(run, claim)
            self._erase_objects(run, claim)
            self._finish(run, claim)
        finally:
            with self.connections.connection() as db:
                db.execute(
                    "update argus_private.business_purge_runs set claim_id=null,claimed_until=null where id=%s and claim_id=%s",
                    (run, claim),
                )

    def _claim(self, space: str) -> tuple[str, str] | None:
        claim = str(uuid4())
        with self.connections.connection() as db, db.transaction():
            db.execute("set local lock_timeout='5s'; set local statement_timeout='60s'")
            row = db.execute(
                "select id::text,status,claim_id,claimed_until>clock_timestamp() from argus_private.business_purge_runs where space_id=%s for update",
                (space,),
            ).fetchone()
            if row is None:
                closed = db.execute(
                    "select closed_at,created_by,current_owner_id from public.spaces where id=%s and kind='business' and closed_at<=clock_timestamp()-interval '30 days' for update",
                    (space,),
                ).fetchone()
                if closed is None:
                    raise BusinessPurgeBusy("business_purge_not_due")
                if db.execute(
                    "select 1 from argus_private.account_deletion_runs where user_id in (%s,%s) and status<>'done'",
                    closed[1:],
                ).fetchone():
                    raise BusinessPurgeBusy("business_account_deletion_pending")
                placeholder = db.execute(
                    "select custodian_id from argus_private.business_custody_reservations where space_id=%s",
                    (space,),
                ).fetchone()
                row = db.execute(
                    "insert into argus_private.business_purge_runs(space_id,closed_at,placeholder_id) values(%s,%s,%s) on conflict(space_id) do nothing returning id::text,status,claim_id,false",
                    (space, closed[0], placeholder[0] if placeholder else None),
                ).fetchone()
                if row is None:
                    raise BusinessPurgeBusy("business_purge_claimed")
            if row[1] == "done":
                return None
            if row[2] is not None and row[3]:
                raise BusinessPurgeBusy("business_purge_claimed")
            db.execute(
                "update argus_private.business_purge_runs set claim_id=%s,claimed_until=clock_timestamp()+interval '15 minutes' where id=%s",
                (claim, row[0]),
            )
            return row[0], claim

    @staticmethod
    def _live(db: Any, run: str, claim: str) -> tuple:
        row = db.execute(
            "update argus_private.business_purge_runs set claimed_until=clock_timestamp()+interval '15 minutes' where id=%s and claim_id=%s and claimed_until>clock_timestamp() returning space_id::text,status,placeholder_id::text,closed_at",
            (run, claim),
        ).fetchone()
        if row is None:
            raise BusinessPurgeBusy("business_purge_claim_lost")
        return row

    def _erase_logo(self, run: str, claim: str) -> None:
        """The logo object goes before the space row that names it. Erasing is
        idempotent, so a failure keeps the graph and the next sweep retries."""
        with self.connections.connection() as db:
            space, status, _, _ = self._live(db, run, claim)
            if status != "started":
                return
            named = db.execute(
                "select 1 from public.business_logos where space_id=%s", (space,)
            ).fetchone()
        if self.images is None:
            if named:
                raise BusinessPurgePending("business_logo_storage_unavailable")
            return
        try:
            self.images.erase(business(space))
        except Exception as error:
            raise BusinessPurgePending("business_logo_delete_pending") from error

    def _delete_graph(self, run: str, claim: str) -> None:
        with self.connections.connection() as db, db.transaction():
            db.execute("set local lock_timeout='5s'; set local statement_timeout='60s'")
            space, status, _, closed_at = self._live(db, run, claim)
            if status != "started":
                return
            custodian = db.execute(
                "select created_by::text from public.spaces where id=%s and kind='business' and closed_at=%s and closed_at<=clock_timestamp()-interval '30 days' for update",
                (space, closed_at),
            ).fetchone()
            if custodian is None:
                raise BusinessPurgePending("business_purge_state_changed")
            if db.execute(
                "select 1 from argus_private.account_deletion_runs d join public.spaces s on s.id=%s where d.user_id in (s.created_by,s.current_owner_id) and d.status<>'done'",
                (space,),
            ).fetchone():
                raise BusinessPurgeBusy("business_account_deletion_pending")
            scope = PostgresBusinessCustodyGraph._scope(db, space, custodian[0])
            graph = PostgresBusinessCustodyGraph._lock_graph(db, scope, custodian[0])
            paths = {
                row[key]
                for _, row in graph["financial_document_extractions"]
                for key in ("source_path", "rebuilt_path")
                if row.get(key)
            }
            for source, destination in db.execute(
                "select source_path,destination_path from argus_private.business_custody_objects where space_id=%s for update",
                (space,),
            ):
                paths.update(path for path in (source, destination) if path)
            for path in sorted(paths):
                db.execute(
                    "insert into argus_private.business_purge_objects(run_id,path) values(%s,%s) on conflict do nothing",
                    (run, path),
                )
            PostgresBusinessCustodyGraph._remove_transport(db, scope, custodian[0])
            db.execute("set constraints all deferred")
            db.execute(
                "delete from public.financial_activity_groups where id=any(%s::uuid[])",
                (scope["activities"],),
            )
            for table in (
                "business_custody_changes",
                "business_custody_moves",
                "business_custody_objects",
                "business_custody_reservations",
            ):
                db.execute(
                    sql.SQL("delete from argus_private.{} where space_id=%s").format(
                        sql.Identifier(table)
                    ),
                    (space,),
                )
            db.execute("delete from public.spaces where id=%s", (space,))
            db.execute("set constraints all immediate")
            db.execute(
                "update argus_private.business_purge_runs set status='data_deleted' where id=%s",
                (run,),
            )

    def _erase_objects(self, run: str, claim: str) -> None:
        with self.connections.connection() as db:
            _, _, placeholder, _ = self._live(db, run, claim)
            paths = db.execute(
                "select path from argus_private.business_purge_objects where run_id=%s and deleted_at is null order by path",
                (run,),
            ).fetchall()
        if (paths or placeholder) and self.objects is None:
            raise BusinessPurgePending("business_source_storage_unavailable")
        for (path,) in paths:
            with self.connections.connection() as db:
                self._live(db, run, claim)
                shared = db.execute(
                    "select exists(select 1 from public.financial_document_extractions where source_path=%s or rebuilt_path=%s) or exists(select 1 from argus_private.business_custody_objects where source_path=%s or destination_path=%s)",
                    (path, path, path, path),
                ).fetchone()[0]
            if not shared:
                try:
                    self.objects.remove(path)
                    if self.objects.get(path) is not None:
                        raise BusinessPurgePending("business_source_delete_unverified")
                except Exception as error:
                    raise BusinessPurgePending(
                        "business_source_delete_pending"
                    ) from error
            with self.connections.connection() as db:
                self._live(db, run, claim)
                db.execute(
                    "update argus_private.business_purge_objects set deleted_at=clock_timestamp() where run_id=%s and path=%s",
                    (run, path),
                )
        if placeholder:
            with self.connections.connection() as db:
                self._live(db, run, claim)
                if db.execute(
                    "select 1 from public.spaces where created_by=%s union all select 1 from public.financial_accounts where user_id=%s union all select 1 from public.financial_source_connections where user_id=%s union all select 1 from public.conversations where user_id=%s limit 1",
                    (placeholder,) * 4,
                ).fetchone():
                    raise BusinessPurgePending("business_purge_placeholder_in_use")
            try:
                self.objects.delete(owner_prefix(placeholder))
            except Exception as error:
                raise BusinessPurgePending("business_source_delete_pending") from error

    def _finish(self, run: str, claim: str) -> None:
        with self.connections.connection() as db:
            _, _, placeholder, _ = self._live(db, run, claim)
        if placeholder:
            self.auth.delete_user(placeholder)
            if self.auth.user_exists(placeholder):
                raise BusinessPurgePending("business_purge_auth_pending")
        with self.connections.connection() as db, db.transaction():
            self._live(db, run, claim)
            if placeholder:
                if db.execute(
                    "select 1 from auth.users where id=%s", (placeholder,)
                ).fetchone():
                    raise BusinessPurgePending("business_purge_auth_pending")
                db.execute(
                    "delete from argus_private.account_placeholders where id=%s",
                    (placeholder,),
                )
            db.execute(
                "delete from argus_private.business_purge_objects where run_id=%s", (run,)
            )
            db.execute(
                "update argus_private.business_purge_runs set status='done',placeholder_id=null,claim_id=null,claimed_until=null,completed_at=clock_timestamp() where id=%s",
                (run,),
            )
