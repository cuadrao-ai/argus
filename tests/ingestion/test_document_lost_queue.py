"""With document jobs off, a queued read whose task never ran settles visibly."""

from datetime import timedelta

import pytest
from argus.domain.ingestion.connections import DEFAULT_LEASE
from argus.domain.owner_scope import PERSONAL

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
class TestQueuedReadWithJobsOff:
    async def test_old_queued_read_settles_to_needs_attention(self, rig):
        service, hub, extractor, _ = rig
        connection_id = await queued(service)
        advance(hub, DEFAULT_LEASE)
        draft = read(service, connection_id)
        assert draft.status == "needs_attention"
        assert draft.error_code == "document_preparation_interrupted"
        await service.background_prepare(
            user_id=OWNER, connection_id=connection_id, scope=PERSONAL
        )
        extractor.extract.assert_not_awaited()

    async def test_fresh_queued_read_stays_queued(self, rig):
        service, hub, _, _ = rig
        connection_id = await queued(service)
        advance(hub, DEFAULT_LEASE - timedelta(seconds=1))
        assert read(service, connection_id).status == "queued"

    async def test_repeated_reads_settle_once(self, rig):
        service, hub, _, _ = rig
        connection_id = await queued(service)
        advance(hub, DEFAULT_LEASE)
        first = read(service, connection_id)
        advance(hub, DEFAULT_LEASE)
        second = read(service, connection_id)
        assert second.status == "needs_attention"
        assert second.version == first.version
        assert second.updated_at == first.updated_at

    async def test_running_worker_lease_keeps_the_read(self, rig):
        service, hub, _, _ = rig
        connection_id = await queued(service)
        advance(hub, DEFAULT_LEASE)
        hub.connections.lease(
            connection_id=connection_id, holder="worker", now=hub.clock()
        )
        assert read(service, connection_id).status == "queued"


@pytest.mark.asyncio
class TestQueuedReadWithJobsOn:
    async def test_worker_that_finishes_after_the_window_wins(self, rig):
        service, hub, extractor, _ = rig
        service.jobs_recover_interruptions = True
        connection_id = await queued(service)
        advance(hub, DEFAULT_LEASE * 3)
        assert read(service, connection_id).status == "queued"
        await service.background_prepare(
            user_id=OWNER, connection_id=connection_id, scope=PERSONAL
        )
        extractor.extract.assert_awaited_once()
        assert read(service, connection_id).status not in {"queued", "needs_attention"}
