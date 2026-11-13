"""Reading queued receipts in tests through the one read path: the attempt
recorded on the receipt's row, taken as ``store.pull`` takes it, then
``run_attempt``. Each helper takes only the receipt it names, so rows other
tests leave waiting in a shared database are never read here."""

import asyncio
import sys
from collections.abc import Callable
from contextvars import ContextVar
from typing import Any

import pytest
from argus.domain.ingestion.documents.jobs import (
    PreparationJobs,
    SweepReport,
    run_attempt,
)
from argus.domain.ingestion.documents.service import (
    DocumentServiceError,
    DocumentsService,
)
from argus.domain.owner_scope import PERSONAL


def take(service: DocumentsService, user_id: str, connection_id: str) -> str | None:
    """A puller's take of this one receipt: its attempt id, when the attempt
    waits for a puller as ``store.pull`` requires, else ``None``."""
    store, now = service.store, service.hub.clock()
    draft = store.draft(user_id=user_id, connection_id=connection_id)
    job = store.job(user_id=user_id, connection_id=connection_id)
    if (
        draft is None
        or job is None
        or draft.status != "queued"
        or not draft.source_available
        or job.dispatched_at is not None
        or job.draft_version != draft.version
    ):
        return None
    taken = job.model_copy(update={"dispatched_at": now})
    if not store.advance(
        user_id=user_id,
        connection_id=connection_id,
        now=now,
        expected_attempt_id=job.attempt_id,
        job=taken,
    ):
        return None
    return job.attempt_id


async def read_receipt(
    service: DocumentsService, user_id: str, connection_id: str
) -> str | None:
    """Take this receipt's waiting attempt and read it; the outcome."""
    attempt = await asyncio.to_thread(take, service, user_id, connection_id)
    if attempt is None:
        return None
    return await run_attempt(service, connection_id, attempt)


async def read_queued(service: DocumentsService, user_id: str, connection_id: str) -> None:
    """A channel's read: record the attempt, then a puller takes it."""
    await asyncio.to_thread(
        PreparationJobs(service).start, user_id=user_id, connection_id=connection_id
    )
    await read_receipt(service, user_id, connection_id)


async def refused_while_another_records(
    service: DocumentsService, user_id: str, connection_id: str
) -> None:
    """Two dispatches of one queued Personal receipt, interleaved: the refused
    one reads what it needs to release it, the authorized one records its
    attempt, then the refused one writes its release."""
    from argus.api.documents import dispatch_preparation

    authorized = PreparationJobs(service).start
    writes = service.store.update

    def refused(*_: Any, **__: Any) -> None:
        raise DocumentServiceError("business_preparation_binding_conflict")

    with pytest.MonkeyPatch.context() as patch:

        def authorized_records_then_write(**kwargs: Any) -> bool:
            patch.setattr(service.store, "update", writes)
            authorized(user_id=user_id, connection_id=connection_id)
            return writes(**kwargs)

        patch.setattr(PreparationJobs, "start", refused)
        patch.setattr(service.store, "update", authorized_records_then_write)
        with pytest.raises(DocumentServiceError, match="binding_conflict"):
            await dispatch_preparation(service, user_id, connection_id, scope=PERSONAL)


class TakenAtOnce(PreparationJobs):
    """A running puller takes each attempt the moment this records or requeues
    it; ``taken`` hears ``(connection_id, attempt_id)`` for each take."""

    def __init__(self, service: DocumentsService, taken: Callable[[str, str], None]) -> None:
        super().__init__(service)
        self.taken = taken

    def _take(self, connection_id: str) -> None:
        user_id = self.service.store.owner(connection_id=connection_id)
        attempt = take(self.service, user_id, connection_id) if user_id else None
        if attempt is not None:
            self.taken(connection_id, attempt)

    def start(self, **kwargs: Any) -> None:
        super().start(**kwargs)
        self._take(kwargs["connection_id"])

    def sweep(self, **kwargs: Any) -> SweepReport:
        report = super().sweep(**kwargs)
        for connection_id in (*report.redispatched, *report.rerun):
            self._take(connection_id)
        return report


class _ReadsAfterTheRequest(list):
    """Receipts a request recorded, read once its response is sent."""

    open = True


_after_the_request: ContextVar[_ReadsAfterTheRequest | None] = ContextVar(
    "reads_after_the_request", default=None
)


def read_inside_each_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    """A receipt is settled when the dispatching request or delivery finishes,
    as most tests assert. A request's receipts are read after its response is
    sent, as the document worker would read them; a delivery outside a request
    has its receipt read as its dispatch returns. No worker or sweep runs."""
    from argus.api import documents as api_documents
    from argus.api.routers import business as routers_business
    from argus.api.routers import financial_documents as routers_financial_documents
    from fastapi import FastAPI

    recorded = api_documents.dispatch_preparation

    async def dispatch_and_read(  # noqa: ANN202
        service,  # noqa: ANN001
        user_id,  # noqa: ANN001
        connection_id,  # noqa: ANN001
        *,
        scope,  # noqa: ANN001
    ):
        await recorded(service, user_id, connection_id, scope=scope)
        later = _after_the_request.get()
        if later is None or not later.open:
            await read_receipt(service, user_id, connection_id)
        else:
            later.append((service, user_id, connection_id))

    for module in (api_documents, routers_business, routers_financial_documents):
        monkeypatch.setattr(module, "dispatch_preparation", dispatch_and_read)

    served = FastAPI.__call__

    async def serve_then_read(self, scope, receive, send):  # noqa: ANN001, ANN202
        if scope["type"] != "http":
            return await served(self, scope, receive, send)
        later = _ReadsAfterTheRequest()
        token = _after_the_request.set(later)
        try:
            await served(self, scope, receive, send)
        finally:
            _after_the_request.reset(token)
        while later:
            await read_receipt(*later.pop(0))
        later.open = False

    monkeypatch.setattr(FastAPI, "__call__", serve_then_read)


def leave_reads_waiting(monkeypatch: pytest.MonkeyPatch) -> None:
    """From here on no dispatch's read runs: its receipt stays ``queued``, as
    one waiting behind the cap does."""

    async def no_puller(*_: object) -> None:
        return None

    monkeypatch.setattr(sys.modules[__name__], "read_receipt", no_puller)
