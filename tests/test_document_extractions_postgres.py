"""Document checkpoints are private, immutable and fenced by the live lease."""

import hashlib
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from argus.domain.ingestion.connections_postgres import PostgresConnectionRepository
from argus.domain.ingestion.contract import ImportCandidate, SourceRef
from argus.domain.ingestion.documents.models import ExtractionBatch
from argus.domain.ingestion.documents.store_postgres import PostgresDocumentStore
from argus.domain.owner_scope import PERSONAL
from psycopg_pool import ConnectionPool

from tests import test_financial_accounts_postgres as shared
from tests.document_sources_support import source_objects

users = shared.users
pytestmark = pytest.mark.skipif(
    not shared.DSN, reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured"
)


@pytest.fixture
def pool() -> Iterator[ConnectionPool]:
    with ConnectionPool(shared.DSN, min_size=0, max_size=4) as opened:
        yield opened


def test_checkpoint_is_immutable_and_owner_scoped(
    pool: ConnectionPool, users: dict[str, str]
) -> None:
    now = datetime.now(timezone.utc)
    repo = PostgresConnectionRepository(pool)
    store = PostgresDocumentStore(pool, source_objects())
    row = repo.create(
        user_id=users["owner"],
        source="statement",
        external_ref=str(uuid4()),
        label=None,
        now=now,
        scope=PERSONAL,
    )
    holder = str(uuid4())
    assert repo.lease(connection_id=row.id, holder=holder, now=now)
    candidate = ImportCandidate(
        source=SourceRef(
            source="statement", connection_id=row.id, external_id="p1:r1", observed_at=now
        ),
        evidence="unclassified",
    )
    batch = ExtractionBatch(candidates=(candidate,))
    assert store.save(
        user_id=users["owner"], connection_id=row.id, holder=holder, now=now, batch=batch
    )
    changed = batch.model_copy(update={"metadata": {"changed": True}})
    assert store.save(
        user_id=users["owner"],
        connection_id=row.id,
        holder=holder,
        now=now,
        batch=changed,
    )
    assert store.get(user_id=users["owner"], connection_id=row.id) == batch
    from argus.domain.ingestion.documents.models import DocumentDraft

    legacy_capture = DocumentDraft(
        connection_id=row.id,
        filename="legacy.pdf",
        media_type="application/pdf",
        sha256=hashlib.sha256(b"%PDF-fixture").hexdigest(),
        size_bytes=12,
        created_at=now,
        updated_at=now,
    )
    assert store.capture(
        user_id=users["owner"], draft=legacy_capture, content=b"%PDF-fixture"
    )
    assert store.source(user_id=users["owner"], connection_id=row.id) == b"%PDF-fixture"
    assert store.get(user_id=users["owner"], connection_id=row.id) == batch
    assert store.get(user_id=users["other"], connection_id=row.id) is None
    assert not store.save(
        user_id=users["other"], connection_id=row.id, holder=holder, now=now, batch=batch
    )
    assert not store.save(
        user_id=users["owner"],
        connection_id=row.id,
        holder=holder,
        now=now + timedelta(minutes=6),
        batch=batch,
    )
    repo.disconnect(user_id=users["owner"], connection_id=row.id, now=now)
    store.forget(user_id=users["owner"], connection_id=row.id)
    assert not store.save(
        user_id=users["owner"], connection_id=row.id, holder=holder, now=now, batch=batch
    )
    assert store.get(user_id=users["owner"], connection_id=row.id) is None


def test_capture_survives_new_store_handles_and_disconnect_hides_source(
    pool: ConnectionPool, users: dict[str, str]
) -> None:
    from argus.domain.ingestion.documents.models import DocumentDraft

    now = datetime.now(timezone.utc)
    repo = PostgresConnectionRepository(pool)
    owner, other = users["owner"], users["other"]
    connection = repo.create(
        user_id=owner,
        source="statement",
        external_ref=str(uuid4()),
        label="Document",
        now=now,
        scope=PERSONAL,
    )
    draft = DocumentDraft(
        connection_id=connection.id,
        filename="synthetic.pdf",
        media_type="application/pdf",
        sha256=hashlib.sha256(b"%PDF-fixture").hexdigest(),
        size_bytes=12,
        created_at=now,
        updated_at=now,
    )
    source = b"%PDF-fixture"
    objects = source_objects()
    assert PostgresDocumentStore(pool, objects).capture(
        user_id=owner, draft=draft, content=source
    )
    with ConnectionPool(shared.DSN, min_size=0, max_size=2) as restarted:
        store = PostgresDocumentStore(restarted, objects)
        assert store.draft(user_id=owner, connection_id=connection.id) == draft
        assert store.source(user_id=owner, connection_id=connection.id) == source
        assert store.source(user_id=other, connection_id=connection.id) is None
        changed = draft.model_copy(
            update={"version": 2, "status": "queued", "consent": True}
        )
        assert store.update(user_id=owner, draft=changed, expected_version=1)
        assert not store.update(user_id=owner, draft=changed, expected_version=1)
        repo.disconnect(user_id=owner, connection_id=connection.id, now=now)
        assert store.source(user_id=owner, connection_id=connection.id) is None
        assert store.draft(user_id=owner, connection_id=connection.id) is None
        assert not store.capture(user_id=owner, draft=draft, content=source)
        assert not store.update(user_id=owner, draft=changed, expected_version=2)
        store.forget(user_id=owner, connection_id=connection.id)
    with pool.connection() as sql:
        assert sql.execute(
            "select count(*) from public.financial_document_extractions where connection_id=%s",
            (connection.id,),
        ).fetchone() == (0,)


def test_bucket_and_reference_check_use_the_python_limits(
    pool: ConnectionPool, users: dict[str, str]
) -> None:
    from argus.domain.ingestion.documents.config import (
        SOURCE_MAX_BYTES,
        SOURCE_MEDIA_TYPES,
    )
    from argus.domain.ingestion.documents.objects import SOURCE_BUCKET
    from psycopg import errors

    with pool.connection() as sql:
        assert sql.execute(
            "select file_size_limit, allowed_mime_types from storage.buckets where id = %s",
            (SOURCE_BUCKET,),
        ).fetchone() == (SOURCE_MAX_BYTES, list(SOURCE_MEDIA_TYPES))
    owner, now = users["owner"], datetime.now(timezone.utc)
    connection = PostgresConnectionRepository(pool).create(
        user_id=owner,
        source="statement",
        external_ref=str(uuid4()),
        label=None,
        now=now,
        scope=PERSONAL,
    )
    digest = "c" * 64

    def reference(media_type: str, size: int) -> None:
        with pool.connection() as sql, sql.transaction():
            sql.execute(
                "insert into public.financial_document_extractions"
                " (connection_id, user_id, draft, source_bucket, source_path,"
                "  source_media_type, source_size_bytes, source_sha256)"
                " values (%s, %s, '{}'::jsonb, %s, %s, %s, %s, %s)",
                (
                    connection.id,
                    owner,
                    SOURCE_BUCKET,
                    f"{owner}/{connection.id}/{digest}",
                    media_type,
                    size,
                    digest,
                ),
            )
            raise _RolledBack()

    for media_type in SOURCE_MEDIA_TYPES:
        with pytest.raises(_RolledBack):
            reference(media_type, SOURCE_MAX_BYTES)
    for media_type, size in (
        ("application/zip", 1),
        ("application/pdf", SOURCE_MAX_BYTES + 1),
    ):
        with pytest.raises(errors.CheckViolation):
            reference(media_type, size)


class _RolledBack(Exception):
    pass
