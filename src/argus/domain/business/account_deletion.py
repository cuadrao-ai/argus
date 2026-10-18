"""Preserve Business records before a claimed personal account deletion."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from argus.domain.account_deletion.auth_admin import AuthAdmin
from argus.domain.business.custody_graph import (
    PostgresBusinessCustodyGraph,
    retained_dependencies,
)
from argus.domain.business.custody_objects import PostgresBusinessCustodyCopies
from argus.domain.business.departures import PostgresBusinessDepartures
from argus.domain.ingestion.documents.objects import SourceObjects


class BusinessRetentionError(RuntimeError):
    pass


class BusinessAccountDeletion:
    def __init__(self, connections: Any, auth: AuthAdmin, objects: SourceObjects | None):
        self.connections, self.auth, self.objects = connections, auth, objects
        self.graph = PostgresBusinessCustodyGraph(connections)
        self.departures = PostgresBusinessDepartures(connections)

    def retain(self, *, user_id: str, run_id: str, claim_id: str, renew: Callable):
        with self.connections.connection() as db, db.transaction():
            # An open Business still names this person. Close it here so the
            # copy and the custody move can run before Auth is deleted.
            db.execute(
                "update public.spaces set closed_at=clock_timestamp()"
                " where kind='business' and current_owner_id=%s and closed_at is null",
                (user_id,),
            )
            spaces = db.execute(
                "select id::text from public.spaces where kind='business' and created_by=%s order by id",
                (user_id,),
            ).fetchall()
        for (space_id,) in spaces:
            renew()
            if self.objects is None:
                raise BusinessRetentionError("business_source_storage_unavailable")
            reservation = PostgresBusinessCustodyCopies(
                self.connections, self.objects, self.auth
            ).prepare(space_id=space_id, departing_user_id=user_id, heartbeat=renew)
            renew()
            self.graph.detach(
                space_id=space_id,
                departing_user_id=user_id,
                reservation=reservation,
                deletion_run_id=run_id,
                claim_id=claim_id,
            )
        renew()
        self.departures.detach(user_id=user_id, run_id=run_id, claim_id=claim_id)
        self.require_detached(user_id)

    def require_detached(self, user_id: str) -> None:
        with self.connections.connection() as db:
            if retained_dependencies(db, user_id):
                raise BusinessRetentionError("business_custody_retained_dependency")

    def complete(self, *, user_id: str, run_id: str, claim_id: str, renew: Callable):
        if self.auth.user_exists(user_id):
            raise BusinessRetentionError("business_custody_auth_not_deleted")
        with self.connections.connection() as db:
            if db.execute("select 1 from auth.users where id=%s", (user_id,)).fetchone():
                raise BusinessRetentionError("business_custody_auth_not_deleted")
            spaces = db.execute(
                "select space_id::text from argus_private.business_custody_moves where deletion_run_id=%s order by space_id",
                (run_id,),
            ).fetchall()
        for (space_id,) in spaces:
            renew()
            self.graph.complete_identity_cleanup(
                space_id=space_id, deletion_run_id=run_id, claim_id=claim_id
            )
        renew()
        self.departures.complete(user_id=user_id, run_id=run_id, claim_id=claim_id)
