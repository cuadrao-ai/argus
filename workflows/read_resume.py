"""A read the Business read budget refused starts again on its own.

The refused receipt waits saved and unread. Once the budget's Santo Domingo
day or month has turned, the document worker's upkeep queues it again the way
"Leer de nuevo" does: ``DocumentsService.queue`` under the owner's reading
setting as it stands now, then ``dispatch_preparation`` under the authority
the read was first bound to. No person acts, so nothing is queued while the
owner's reading is off, and a receipt that moved since the pass chose it is
left to whoever moved it.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from argus.api.business_drafts import bind_to_grant
from argus.api.documents import dispatch_preparation, release_unstarted
from argus.domain.business.read_budget import READ_BUDGET_REFUSALS, window_start
from argus.domain.ingestion.connections import ConnectionNotFound
from argus.domain.ingestion.documents.config import load_document_extraction_settings
from argus.domain.ingestion.documents.service import (
    DocumentServiceError,
    DocumentsService,
)
from argus.domain.owner_scope import OwnerScope
from loguru import logger

RESUME_EVERY = timedelta(minutes=10)


class ReadResume:
    """The documents worker's sweep loop calls ``tick`` every 30 seconds; it
    runs at most once per ``every``. A pass takes every receipt that is due,
    oldest first: one that cannot start yet never holds back the ones after it."""

    def __init__(
        self, service: DocumentsService, *, every: timedelta = RESUME_EVERY
    ) -> None:
        self.service, self.every = service, every
        self._next: datetime | None = None

    def tick(self) -> None:
        now = self.service.hub.clock()
        if self._next is not None and now < self._next:
            return
        self._next = now + self.every
        # As in the sweep: with extraction off a queued read neither runs nor fails.
        if load_document_extraction_settings().enabled:
            self.run(now)

    def run(self, now: datetime) -> dict[str, int]:
        from argus.domain.business.read_budget import HELD_READ_REFUSAL
        from argus.domain.ingestion.whatsapp.config import load_whatsapp_settings
        from argus.domain.owner_scope import space_id

        before = {code: window_start(code, now) for code in READ_BUDGET_REFUSALS}
        if not load_whatsapp_settings().intake_ready:
            before.pop(HELD_READ_REFUSAL, None)
        due = self.service.store.refused_before(before=before)
        requeued = 0
        for user, connection, version in due:
            try:
                scope = self.service.hub.connections.get_any_scope(
                    user_id=user, connection_id=connection
                ).scope
                if space_id(scope) is not None:
                    requeued += self._resume(user, connection, version)
                    continue
                # A Personal held read has no Business grant to bind.
                self.service.queue(user_id=user, connection_id=connection,
                                   consent=True, scope=scope, expected_version=version)
                asyncio.run(dispatch_preparation(self.service, user, connection, scope=scope))
                requeued += 1
            except Exception as error:
                logger.warning("Refused held read left waiting", failure_mode=type(error).__name__)
        logger.info("Refused reads resumed due={} requeued={}", len(due), requeued)
        return dict(due=len(due), requeued=requeued)

    def _resume(self, user_id: str, connection_id: str, version: int) -> bool:
        service = self.service
        try:
            scope = service.hub.connections.get_any_scope(
                user_id=user_id, connection_id=connection_id
            ).scope
            # The owner's standing setting is the consent, as it was at upload.
            service.queue(
                user_id=user_id,
                connection_id=connection_id,
                consent=True,
                scope=scope,
                expected_version=version,
            )
        except (ConnectionNotFound, DocumentServiceError) as error:
            logger.info(
                "Refused read left waiting connection_id={} code={}",
                connection_id,
                getattr(error, "code", type(error).__name__),
            )
            return False
        try:
            asyncio.run(self._start(user_id, connection_id, scope))
        except Exception as error:  # noqa: BLE001
            # ``release_unstarted`` already left the receipt saved with this reason.
            logger.warning(
                "Refused read could not start again connection_id={} failure_mode={}",
                connection_id,
                getattr(error, "code", type(error).__name__),
            )
            return False
        return True

    async def _start(self, user_id: str, connection_id: str, scope: OwnerScope) -> None:
        service, actions = self.service, self.service.business_actions
        try:
            context = actions.preparation_context(
                user_id=user_id, connection_id=connection_id, scope=scope
            )
            bound, _ = bind_to_grant(service, service.hub, actions, context, "prepare")
        except Exception as error:  # noqa: BLE001
            release_unstarted(service, user_id, connection_id, scope=scope, error=error)
        await dispatch_preparation(bound, user_id, connection_id, scope=scope)
