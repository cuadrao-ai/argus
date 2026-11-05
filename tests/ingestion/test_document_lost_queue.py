"""A queued read waits on its row however old: a read never settles it, the
sweep does, and a worker that finishes after the window wins."""

import pytest
from argus.domain.ingestion.connections import DEFAULT_LEASE
from argus.domain.owner_scope import PERSONAL

from tests.document_reads_support import read_queued
from tests.ingestion import test_document_service as support

rig = support.rig

OWNER = "owner"


async def queued(service) -> str:
    saved = await service.upload(
        user_id=OWNER,
        content=b"%PDF-fixture",
        filename="test.pdf",
        media_type="application/pdf",
        consent=True,
        scope=PERSONAL,
    )
    return saved.connection_id


def read(service, connection_id):
    return service.get(user_id=OWNER, connection_id=connection_id, scope=PERSONAL)


def advance(hub, delta):
    now = hub.clock() + delta
    hub.clock = lambda: now


@pytest.mark.asyncio
class TestQueuedReadWaitsOnItsRow:
    async def test_an_old_queued_read_stays_queued_for_a_puller(self, rig):
        service, hub, extractor, _ = rig
        connection_id = await queued(service)
        advance(hub, DEFAULT_LEASE * 3)
        first = read(service, connection_id)
        assert first.status == "queued"
        advance(hub, DEFAULT_LEASE)
        second = read(service, connection_id)
        assert (second.status, second.version) == ("queued", first.version)
        extractor.extract.assert_not_awaited()

    async def test_a_dead_preparing_draft_is_the_sweeps_to_settle(self, rig):
        service, hub, _, _ = rig
        connection_id = await queued(service)
        draft = service.store.draft(user_id=OWNER, connection_id=connection_id)
        service._update(OWNER, draft, status="preparing")
        advance(hub, DEFAULT_LEASE * 2)
        assert read(service, connection_id).status == "preparing"

    async def test_worker_that_finishes_after_the_window_wins(self, rig):
        service, hub, extractor, _ = rig
        connection_id = await queued(service)
        advance(hub, DEFAULT_LEASE * 3)
        assert read(service, connection_id).status == "queued"
        await read_queued(service, OWNER, connection_id)
        extractor.extract.assert_awaited_once()
        assert read(service, connection_id).status not in {"queued", "needs_attention"}
