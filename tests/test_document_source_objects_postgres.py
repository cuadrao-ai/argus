"""Retained document sources in the private Storage bucket (#778), on real
PostgreSQL and the local Supabase Storage API.

Set ``ARGUS_DISPOSABLE_DATABASE_URL`` plus ``ARGUS_LOCAL_SUPABASE_URL``,
``ARGUS_LOCAL_SUPABASE_ANON_KEY`` and ``ARGUS_LOCAL_SUPABASE_SERVICE_ROLE_KEY``
to run locally.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from uuid import uuid4

import psycopg
import pytest
from argus.domain.ingestion.connections import ConnectionNotFound
from argus.domain.ingestion.connections_postgres import PostgresConnectionRepository
from argus.domain.ingestion.contract import ImportCandidate, SourceRef
from argus.domain.ingestion.documents.models import DocumentDraft, ExtractionBatch
from argus.domain.ingestion.documents.objects import (
    SOURCE_BUCKET,
    SourceObjects,
    SourceStorageUnavailable,
    owner_prefix,
)
from argus.domain.ingestion.documents.service import (
    DocumentServiceError,
    DocumentsService,
)
from argus.domain.ingestion.documents.store_postgres import PostgresDocumentStore
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.ingestion.reconcile.store_postgres import PostgresImportStore
from argus.domain.owner_scope import PERSONAL
from argus.domain.recording.postgres_repository import (
    PostgresFinancialAccountRepository,
)
from psycopg_pool import ConnectionPool

from tests import test_financial_accounts_postgres as shared
from tests.document_sources_support import (
    LOCAL_STORAGE,
    source_objects,
    stored_paths,
)
from tests.ingestion.reconcile_cases import DAY, NOW, accept, new_account, only
from tests.ingestion.reconcile_world import World, build

pytestmark = pytest.mark.skipif(
    not (shared.DSN and LOCAL_STORAGE),
    reason="ARGUS_DISPOSABLE_DATABASE_URL and the local Supabase stack are required",
)

PDF = b"%PDF-1.4 retained source fixture"
DIGEST = hashlib.sha256(PDF).hexdigest()


class StatementExtractor:
    async def extract(self, *, connection_id: str, observed_at, **_: object):  # noqa: ANN001
        return ExtractionBatch(
            candidates=(
                ImportCandidate(
                    source=SourceRef(
                        source="statement",
                        connection_id=connection_id,
                        external_id="p1:r1",
                        observed_at=observed_at,
                    ),
                    evidence="transaction",
                    status="posted",
                    amount="12.50",
                    currency="USD",
                    direction="outflow",
                    kind_hint="expense",
                    occurred_on=DAY,
                ),
            )
        )


class CrashAfterPut:
    """The process dies once the object is written, before the row commits."""

    def __init__(self, objects: SourceObjects) -> None:
        self.bucket, self._objects = objects.bucket, objects

    def put(self, path: str, content: bytes, media_type: str) -> None:
        self._objects.put(path, content, media_type)
        raise SystemExit("crashed after the object write")

    def get(self, path: str) -> bytes | None:
        return self._objects.get(path)

    def delete(self, prefix: str) -> None:
        self._objects.delete(prefix)

    def remove(self, path: str) -> None:
        self._objects.remove(path)


@pytest.fixture
def rig() -> Iterator[dict]:
    pool = ConnectionPool(shared.DSN, min_size=0, max_size=6, open=True)
    owner, other = str(uuid4()), str(uuid4())
    with pool.connection() as connection:
        for user in (owner, other):
            connection.execute(
                "insert into auth.users(id,email,is_anonymous) values(%s,%s,false)",
                (user, f"sources-{user}@example.test"),
            )
    objects = source_objects()
    connections = PostgresConnectionRepository(pool)
    world = build(
        PostgresFinancialAccountRepository(pool),
        PostgresImportStore(pool),
        connections,
        owner,
    )
    hub = IngestionHub(connections, box=None, sink=world.recon, clock=lambda: NOW)
    store = PostgresDocumentStore(pool, objects)
    try:
        yield {
            "pool": pool,
            "owner": owner,
            "other": other,
            "objects": objects,
            "hub": hub,
            "store": store,
            "world": world,
            "service": DocumentsService(hub, store, StatementExtractor()),
        }
    finally:
        for user in (owner, other):
            objects.delete(owner_prefix(user))
        with pool.connection() as connection:
            connection.execute(
                "delete from auth.users where id = any(%s)", ([owner, other],)
            )
        pool.close()


def _row(pool: ConnectionPool, connection_id: str) -> tuple | None:
    with pool.connection() as connection:
        return connection.execute(
            "select source_bytes, source_bucket, source_path, source_media_type,"
            " source_size_bytes, source_sha256"
            " from public.financial_document_extractions where connection_id = %s",
            (connection_id,),
        ).fetchone()


def _paths(pool: ConnectionPool, prefix: str) -> list[str]:
    with pool.connection() as connection:
        prefixes = (
            (prefix, f"sealed/{prefix}", f"rebuilt/{prefix}")
            if prefix.count("/") == 1
            else (prefix,)
        )
        return sorted(
            path for folder in prefixes for path in stored_paths(connection, folder)
        )


async def _upload(service: DocumentsService, user: str, *, consent: bool = False):
    return await service.upload(
        user_id=user,
        content=PDF,
        filename="statement.pdf",
        media_type="application/pdf",
        consent=consent,
        scope=PERSONAL,
    )


@pytest.mark.asyncio
async def test_upload_stores_the_object_and_no_bytes(rig: dict) -> None:
    owner = rig["owner"]
    outcome = await _upload(rig["service"], owner)
    path = f"sealed/{owner}/{DIGEST}"
    assert _row(rig["pool"], outcome.connection_id) == (
        None,
        SOURCE_BUCKET,
        path,
        "application/pdf",
        len(PDF),
        DIGEST,
    )
    assert _paths(rig["pool"], owner_prefix(owner)) == [path]
    assert rig["objects"].get(path) == PDF
    assert (
        rig["service"].source_bytes(
            user_id=owner, connection_id=outcome.connection_id, scope=PERSONAL
        )
        == PDF
    )


@pytest.mark.asyncio
async def test_duplicate_upload_makes_no_second_object(rig: dict) -> None:
    owner = rig["owner"]
    first = await _upload(rig["service"], owner)
    second = await _upload(rig["service"], owner)
    assert (second.connection_id, second.replayed) == (first.connection_id, True)
    assert _paths(rig["pool"], owner_prefix(owner)) == [f"sealed/{owner}/{DIGEST}"]


@pytest.mark.asyncio
async def test_only_the_owner_reads_the_source(rig: dict) -> None:
    owner, other, service = rig["owner"], rig["other"], rig["service"]
    outcome = await _upload(service, owner)
    with pytest.raises(ConnectionNotFound):
        service.source_bytes(
            user_id=other, connection_id=outcome.connection_id, scope=PERSONAL
        )
    assert rig["store"].source(user_id=other, connection_id=outcome.connection_id) is None
    assert (
        service.source_bytes(
            user_id=owner, connection_id=outcome.connection_id, scope=PERSONAL
        )
        == PDF
    )


@pytest.mark.asyncio
async def test_disconnect_removes_the_object_and_keeps_confirmed_activity(
    rig: dict,
) -> None:
    owner, world = rig["owner"], rig["world"]
    assert isinstance(world, World)
    captured = await _upload(rig["service"], owner, consent=True)
    connection_id = captured.connection_id
    prepared = await rig["service"].resume(
        user_id=owner, connection_id=connection_id, scope=PERSONAL
    )
    assert prepared.candidate_count == 1
    event = only(world)
    event = world.recon.resolve(
        user_id=owner,
        event_id=event["id"],
        version=event["version"],
        changes={"account_id": new_account(world)},
        scope=PERSONAL,
    )
    accept(world, event)

    rig["hub"].disconnect(user_id=owner, connection_id=connection_id, scope=PERSONAL)

    assert _paths(rig["pool"], owner_prefix(owner)) == []
    assert _row(rig["pool"], connection_id) is None
    kept = only(world, "accepted")
    assert kept["activity_id"] is not None
    assert [o["external_id"] for o in kept["observations"]] == ["p1:r1"]


class DisconnectDuringExtraction(StatementExtractor):
    def __init__(self, hub: IngestionHub, owner: str) -> None:
        self.hub, self.owner = hub, owner

    async def extract(self, *, connection_id: str, **kwargs: object):
        self.hub.disconnect(
            user_id=self.owner, connection_id=connection_id, scope=PERSONAL
        )
        return await super().extract(connection_id=connection_id, **kwargs)


@pytest.mark.asyncio
async def test_disconnect_during_preparation_leaves_no_object_and_no_row(
    rig: dict,
) -> None:
    owner, hub = rig["owner"], rig["hub"]
    service = DocumentsService(hub, rig["store"], DisconnectDuringExtraction(hub, owner))
    captured = await _upload(service, owner, consent=True)
    with pytest.raises(DocumentServiceError, match="document_lease_lost"):
        await service.resume(
            user_id=owner, connection_id=captured.connection_id, scope=PERSONAL
        )
    assert _paths(rig["pool"], owner_prefix(owner)) == []
    assert _row(rig["pool"], captured.connection_id) is None
    assert rig["world"].recon.list(user_id=owner, states=("open",), scope=PERSONAL) == []


@pytest.mark.asyncio
async def test_a_crash_after_the_object_write_leaves_a_retryable_reference(
    rig: dict,
) -> None:
    owner, pool = rig["owner"], rig["pool"]
    crashing = DocumentsService(
        rig["hub"],
        PostgresDocumentStore(pool, CrashAfterPut(rig["objects"])),
        StatementExtractor(),
    )
    with pytest.raises(SystemExit):
        await _upload(crashing, owner)
    [connection] = rig["hub"].connections.list(user_id=owner, scope=PERSONAL)
    orphan = f"sealed/{owner}/{DIGEST}"
    assert _row(pool, connection.id)[2] == orphan
    assert _paths(pool, owner_prefix(owner)) == [orphan]
    assert (
        not rig["service"]
        .get(user_id=owner, connection_id=connection.id, scope=PERSONAL)
        .source_available
    )

    retried = await _upload(rig["service"], owner)
    assert (retried.connection_id, retried.replayed) == (connection.id, True)
    assert _row(pool, connection.id)[2] == orphan
    assert _paths(pool, owner_prefix(owner)) == [orphan]

    rig["hub"].disconnect(user_id=owner, connection_id=connection.id, scope=PERSONAL)
    assert _paths(pool, owner_prefix(owner)) == []


@pytest.mark.asyncio
async def test_disconnect_takes_an_orphan_that_was_never_retried(rig: dict) -> None:
    owner, pool = rig["owner"], rig["pool"]
    crashing = DocumentsService(
        rig["hub"],
        PostgresDocumentStore(pool, CrashAfterPut(rig["objects"])),
        StatementExtractor(),
    )
    with pytest.raises(SystemExit):
        await _upload(crashing, owner)
    [connection] = rig["hub"].connections.list(user_id=owner, scope=PERSONAL)
    rig["hub"].disconnect(user_id=owner, connection_id=connection.id, scope=PERSONAL)
    assert _paths(pool, owner_prefix(owner)) == []


class FailingDelete(CrashAfterPut):
    def put(self, path: str, content: bytes, media_type: str) -> None:
        self._objects.put(path, content, media_type)

    def delete(self, prefix: str) -> None:
        raise ConnectionError("storage unavailable")

    def remove(self, path: str) -> None:
        raise ConnectionError("storage unavailable")


@pytest.mark.asyncio
async def test_a_failed_object_delete_keeps_the_row_for_the_retry(rig: dict) -> None:
    owner, pool, hub = rig["owner"], rig["pool"], rig["hub"]
    outcome = await _upload(rig["service"], owner)
    DocumentsService(
        hub,
        PostgresDocumentStore(pool, FailingDelete(rig["objects"])),
        StatementExtractor(),
    )
    with pytest.raises(ConnectionError):
        hub.disconnect(user_id=owner, connection_id=outcome.connection_id, scope=PERSONAL)
    assert _row(pool, outcome.connection_id) is not None
    assert len(_paths(pool, owner_prefix(owner))) == 1

    hub.register(rig["service"])
    hub.disconnect(user_id=owner, connection_id=outcome.connection_id, scope=PERSONAL)
    assert _row(pool, outcome.connection_id) is None
    assert _paths(pool, owner_prefix(owner)) == []


def test_rows_from_before_the_move_are_still_served_and_erased(rig: dict) -> None:
    owner, pool, store = rig["owner"], rig["pool"], rig["store"]
    connection = rig["hub"].connections.create(
        user_id=owner,
        source="statement",
        external_ref=str(uuid4()),
        label=None,
        now=NOW,
        scope=PERSONAL,
    )
    draft = DocumentDraft(
        connection_id=connection.id,
        filename="legacy.pdf",
        media_type="application/pdf",
        sha256=DIGEST,
        size_bytes=len(PDF),
        created_at=NOW,
        updated_at=NOW,
    )
    with pool.connection() as sql:
        sql.execute(
            "insert into public.financial_document_extractions"
            " (connection_id, user_id, draft, source_bytes) values (%s, %s, %s, %s)",
            (connection.id, owner, draft.model_dump_json(), PDF),
        )
    assert store.source(user_id=owner, connection_id=connection.id) == PDF
    assert store.capture(user_id=owner, draft=draft, content=PDF)
    assert _row(pool, connection.id)[:3] == (PDF, None, None)
    assert _paths(pool, owner_prefix(owner)) == []
    rig["hub"].disconnect(user_id=owner, connection_id=connection.id, scope=PERSONAL)
    assert _row(pool, connection.id) is None


@pytest.mark.parametrize(
    "columns",
    [
        "batch = null, draft = null",
        "source_path = source_path || 'x'",
        "source_sha256 = null",
        "source_bytes = '\\x25'::bytea",
        "draft = null",
    ],
    ids=["empty", "path off owner", "partial reference", "two sources", "no draft"],
)
@pytest.mark.asyncio
async def test_the_database_refuses_an_incoherent_source(rig: dict, columns: str) -> None:
    outcome = await _upload(rig["service"], rig["owner"])
    with psycopg.connect(shared.DSN) as connection:
        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute(
                f"update public.financial_document_extractions set {columns}"  # noqa: S608
                " where connection_id = %s",
                (outcome.connection_id,),
            )


@pytest.mark.asyncio
async def test_capture_on_a_gone_connection_removes_its_object(rig: dict) -> None:
    owner, pool, store = rig["owner"], rig["pool"], rig["store"]
    outcome = await _upload(rig["service"], owner)
    draft = store.draft(user_id=owner, connection_id=outcome.connection_id)
    rig["hub"].connections.disconnect(
        user_id=owner, connection_id=outcome.connection_id, now=NOW
    )
    assert not store.capture(user_id=owner, draft=draft, content=PDF)
    assert _paths(pool, owner_prefix(owner)) == []


@pytest.mark.asyncio
async def test_capture_during_an_account_deletion_run_leaves_no_object(rig: dict) -> None:
    owner, pool = rig["owner"], rig["pool"]
    with pool.connection() as connection:
        connection.execute(
            "insert into argus_private.account_deletion_runs"
            " (subject_hash, user_id, analytics_distinct_id) values (%s, %s, 'test')",
            (hashlib.sha256(owner.encode()).hexdigest(), owner),
        )
    try:
        with pytest.raises(DocumentServiceError, match="document_disconnected"):
            await _upload(rig["service"], owner)
        assert _paths(pool, owner_prefix(owner)) == []
    finally:
        with pool.connection() as connection:
            connection.execute(
                "delete from argus_private.account_deletion_runs where user_id = %s",
                (owner,),
            )


@pytest.mark.asyncio
async def test_a_lost_object_is_reported_and_an_identical_upload_restores_it(
    rig: dict,
) -> None:
    owner, service = rig["owner"], rig["service"]
    outcome = await _upload(service, owner)
    connection_id = outcome.connection_id
    rig["objects"].remove(f"sealed/{owner}/{DIGEST}")
    with pytest.raises(DocumentServiceError, match="document_source_unavailable"):
        service.source_bytes(user_id=owner, connection_id=connection_id, scope=PERSONAL)
    assert not service.get(
        user_id=owner, connection_id=connection_id, scope=PERSONAL
    ).source_available

    again = await _upload(service, owner)
    assert (again.connection_id, again.replayed) == (connection_id, True)
    assert service.get(
        user_id=owner, connection_id=connection_id, scope=PERSONAL
    ).source_available
    assert (
        service.source_bytes(user_id=owner, connection_id=connection_id, scope=PERSONAL)
        == PDF
    )
    assert _paths(rig["pool"], owner_prefix(owner)) == [f"sealed/{owner}/{DIGEST}"]


class StorageDown(CrashAfterPut):
    def put(self, path: str, content: bytes, media_type: str) -> None:
        raise SourceStorageUnavailable("ConnectError")

    def get(self, path: str) -> bytes | None:
        raise SourceStorageUnavailable("ConnectError")


@pytest.mark.asyncio
async def test_a_storage_outage_is_retryable_in_upload_and_preparation(
    rig: dict,
) -> None:
    owner, pool, hub = rig["owner"], rig["pool"], rig["hub"]
    captured = await _upload(rig["service"], owner, consent=True)
    down = DocumentsService(
        hub,
        PostgresDocumentStore(pool, StorageDown(rig["objects"])),
        StatementExtractor(),
    )
    with pytest.raises(DocumentServiceError) as raised:
        await down.resume(
            user_id=owner, connection_id=captured.connection_id, scope=PERSONAL
        )
    assert (raised.value.code, raised.value.retryable) == (
        "document_storage_unavailable",
        True,
    )
    draft = down.get(user_id=owner, connection_id=captured.connection_id, scope=PERSONAL)
    assert (draft.status, draft.error_code, draft.source_available) == (
        "needs_attention",
        "document_storage_unavailable",
        True,
    )
    with pytest.raises(DocumentServiceError) as raised:
        await down.upload(
            user_id=owner,
            content=b"%PDF-1.4 another",
            filename="b.pdf",
            media_type="application/pdf",
            scope=PERSONAL,
        )
    assert (raised.value.code, raised.value.retryable) == (
        "document_storage_unavailable",
        True,
    )


def test_the_installed_storage_client_reports_a_missing_object_as_none(
    rig: dict,
) -> None:
    assert rig["objects"].get(f"{rig['owner']}/{uuid4()}/{DIGEST}") is None
