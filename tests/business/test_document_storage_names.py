"""The retained original and the user-readable copy have separate identities."""

from __future__ import annotations

import hashlib

import pytest
from argus.domain.ingestion.documents.objects import (
    InMemorySourceObjects,
    SourceStorageUnavailable,
    owner_prefix,
    source_path,
)

ORIGINAL = b"sealed receipt fixture"
REBUILT = b"rebuilt receipt fixture"
DIGEST = hashlib.sha256(ORIGINAL).hexdigest()


def test_original_and_rebuilt_have_distinct_deterministic_names() -> None:
    assert source_path(user_id="owner", sha256=DIGEST, kind="sealed") == (
        f"sealed/owner/{DIGEST}"
    )
    assert source_path(user_id="owner", sha256=DIGEST, kind="rebuilt") == (
        f"rebuilt/owner/{DIGEST}"
    )


def test_sealed_retry_is_a_noop_and_changed_bytes_cannot_replace_it() -> None:
    objects = InMemorySourceObjects()
    path = f"sealed/owner/{DIGEST}"
    objects.put(path, ORIGINAL, "image/jpeg")
    objects.put(path, ORIGINAL, "image/jpeg")
    with pytest.raises(SourceStorageUnavailable):
        objects.put(path, b"replacement", "image/jpeg")
    assert objects.get(path) == ORIGINAL
    assert len(objects.objects) == 1


def test_corrupt_original_read_fails_closed() -> None:
    objects = InMemorySourceObjects()
    path = f"sealed/owner/{DIGEST}"
    objects.objects[path] = b"corrupt stored object"
    with pytest.raises(SourceStorageUnavailable):
        objects.get(path)


def test_legacy_original_read_checks_the_content_hash() -> None:
    objects = InMemorySourceObjects()
    path = f"owner/connection/{DIGEST}"
    objects.objects[path] = ORIGINAL
    assert objects.get(path) == ORIGINAL
    objects.objects[path] = b"corrupt legacy object"
    with pytest.raises(SourceStorageUnavailable):
        objects.get(path)


def test_owner_deletion_covers_both_kinds_and_legacy_without_other_owners() -> None:
    objects = InMemorySourceObjects()
    mine = [f"sealed/owner/{DIGEST}", f"rebuilt/owner/{DIGEST}", f"owner/c/{DIGEST}"]
    theirs = f"sealed/other/{DIGEST}"
    for path in [*mine, theirs]:
        objects.objects[path] = ORIGINAL
    objects.delete(owner_prefix("owner"))
    assert objects.objects == {theirs: ORIGINAL}


@pytest.fixture(params=["memory", "postgres"])
def storage_rig(request):
    import os
    from datetime import datetime, timezone
    from uuid import uuid4

    from argus.domain.ingestion.connections import InMemoryConnectionRepository
    from argus.domain.ingestion.connections_postgres import PostgresConnectionRepository
    from argus.domain.ingestion.documents.models import DocumentDraft
    from argus.domain.ingestion.documents.store import InMemoryDocumentStore
    from argus.domain.ingestion.documents.store_postgres import PostgresDocumentStore
    from argus.domain.owner_scope import PERSONAL
    from psycopg_pool import ConnectionPool

    objects = InMemorySourceObjects()
    owner = str(uuid4())
    pool = None
    if request.param == "postgres":
        dsn = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL")
        if not dsn:
            pytest.skip("isolated PostgreSQL is required")
        pool = ConnectionPool(dsn, min_size=0, max_size=4, open=True)
        with pool.connection() as connection:
            connection.execute(
                "insert into auth.users(id,email,is_anonymous) values(%s,%s,false)",
                (owner, f"storage-{owner}@example.test"),
            )
        connections = PostgresConnectionRepository(pool)
        store = PostgresDocumentStore(pool, objects)
    else:
        connections = InMemoryConnectionRepository()
        store = InMemoryDocumentStore(connections, objects)

    def capture(*, write=True):
        now = datetime.now(timezone.utc)
        connection = connections.create(
            user_id=owner,
            source="statement",
            external_ref=str(uuid4()),
            label="receipt",
            now=now,
            scope=PERSONAL,
        )
        draft = DocumentDraft(
            connection_id=connection.id,
            filename="receipt.png",
            media_type="image/png",
            sha256=DIGEST,
            size_bytes=len(ORIGINAL),
            source_available=True,
            created_at=now,
            updated_at=now,
        )
        if write:
            assert store.capture(user_id=owner, draft=draft, content=ORIGINAL)
        return draft

    try:
        yield store, objects, owner, capture, pool
    finally:
        if pool:
            with pool.connection() as connection:
                connection.execute("delete from auth.users where id=%s", (owner,))
            pool.close()


def test_store_keeps_original_internal_until_rebuilt_is_written(storage_rig) -> None:
    store, objects, owner, capture, _ = storage_rig
    draft = capture()
    key = dict(user_id=owner, connection_id=draft.connection_id)
    assert store.source(**key) == ORIGINAL
    assert store.rebuilt(**key) is None
    assert store.save_rebuilt(**key, content=REBUILT, media_type="image/jpeg")
    assert store.save_rebuilt(**key, content=REBUILT, media_type="image/jpeg")
    assert store.rebuilt(**key) == ("image/jpeg", REBUILT)
    assert store.source(**key) == ORIGINAL
    assert set(objects.objects) == {
        f"sealed/{owner}/{DIGEST}",
        f"rebuilt/{owner}/{DIGEST}",
    }


def test_rebuilt_conflict_and_corruption_fail_closed(storage_rig) -> None:
    store, objects, owner, capture, _ = storage_rig
    draft = capture()
    key = dict(user_id=owner, connection_id=draft.connection_id)
    store.save_rebuilt(**key, content=REBUILT, media_type="image/jpeg")
    with pytest.raises(SourceStorageUnavailable):
        store.save_rebuilt(**key, content=ORIGINAL, media_type="image/jpeg")
    objects.objects[f"rebuilt/{owner}/{DIGEST}"] = ORIGINAL
    with pytest.raises(SourceStorageUnavailable):
        store.rebuilt(**key)


def test_disconnect_preserves_shared_copies_until_last_reference(storage_rig) -> None:
    store, objects, owner, capture, _ = storage_rig
    first, second = capture(), capture()
    for draft in (first, second):
        store.save_rebuilt(
            user_id=owner,
            connection_id=draft.connection_id,
            content=REBUILT,
            media_type="image/jpeg",
        )
    store.forget(user_id=owner, connection_id=first.connection_id)
    assert store.source(user_id=owner, connection_id=second.connection_id) == ORIGINAL
    assert store.rebuilt(user_id=owner, connection_id=second.connection_id) == (
        "image/jpeg",
        REBUILT,
    )
    store.forget(user_id=owner, connection_id=second.connection_id)
    assert not objects.objects
    assert not store.save_rebuilt(
        user_id=owner,
        connection_id=second.connection_id,
        content=REBUILT,
        media_type="image/jpeg",
    )


def test_copy_erasure_failure_keeps_reference_for_retry(storage_rig, monkeypatch) -> None:
    store, objects, owner, capture, _ = storage_rig
    draft = capture()
    key = dict(user_id=owner, connection_id=draft.connection_id)
    store.save_rebuilt(**key, content=REBUILT, media_type="image/jpeg")
    remove = objects.remove
    with monkeypatch.context() as patch:

        def fail(path):
            raise SourceStorageUnavailable("temporary")

        patch.setattr(objects, "remove", fail)
        with pytest.raises(SourceStorageUnavailable):
            store.forget(**key)
    assert store.draft(**key) is not None
    assert objects.remove == remove
    store.forget(**key)
    assert store.draft(**key) is None
    assert not objects.objects


def test_other_owner_cannot_read_or_publish_copy(storage_rig) -> None:
    from uuid import uuid4

    store, _, owner, capture, _ = storage_rig
    draft = capture()
    store.save_rebuilt(
        user_id=owner,
        connection_id=draft.connection_id,
        content=REBUILT,
        media_type="image/jpeg",
    )
    key = dict(user_id=str(uuid4()), connection_id=draft.connection_id)
    assert store.source(**key) is None
    assert store.rebuilt(**key) is None
    assert not store.save_rebuilt(**key, content=ORIGINAL, media_type="image/jpeg")


def test_postgres_copy_constraints_reject_owner_and_partial_references(
    storage_rig,
) -> None:
    import psycopg

    store, _, owner, capture, pool = storage_rig
    if pool is None:
        pytest.skip("database constraints")
    draft = capture()
    key = dict(user_id=owner, connection_id=draft.connection_id)
    store.save_rebuilt(**key, content=REBUILT, media_type="image/jpeg")
    for statement in (
        "update public.financial_document_extractions set rebuilt_path='sealed/forbidden' where connection_id=%s",
        "update public.financial_document_extractions set rebuilt_sha256=null where connection_id=%s",
        "update public.financial_document_extractions set source_path=rebuilt_path where connection_id=%s",
    ):
        with (
            pytest.raises(psycopg.errors.CheckViolation),
            pool.connection() as connection,
        ):
            connection.execute(statement, (draft.connection_id,))
    with pool.connection() as connection:
        assert connection.execute(
            "select source_path,rebuilt_path,source_bytes is null from public.financial_document_extractions where connection_id=%s",
            (draft.connection_id,),
        ).fetchone() == (f"sealed/{owner}/{DIGEST}", f"rebuilt/{owner}/{DIGEST}", True)


def test_storage_adapter_never_upserts_and_verifies_duplicate_bytes() -> None:
    from argus.domain.ingestion.documents.objects import SupabaseSourceObjects
    from storage3.exceptions import StorageApiError

    class Bucket:
        def __init__(self):
            self.saved = {}
            self.options = []

        def upload(self, path, content, options):
            self.options.append(options)
            if path in self.saved:
                raise StorageApiError("exists", "Duplicate", 409)
            self.saved[path] = content

        def download(self, path):
            return self.saved[path]

    class Storage:
        def from_(self, name):
            return bucket

    bucket = Bucket()
    objects = SupabaseSourceObjects(Storage())
    path = f"sealed/owner/{DIGEST}"
    objects.put(path, ORIGINAL, "image/jpeg")
    objects.put(path, ORIGINAL, "image/jpeg")
    assert all(options["upsert"] == "false" for options in bucket.options)
    bucket.saved[path] = b"corruption"
    with pytest.raises(SourceStorageUnavailable):
        objects.put(path, ORIGINAL, "image/jpeg")
    assert bucket.saved[path] == b"corruption"


def test_postgres_crash_intent_is_not_extracted_and_disconnect_erases_it(
    storage_rig, monkeypatch
) -> None:
    store, objects, owner, capture, pool = storage_rig
    if pool is None:
        pytest.skip("durable crash checkpoint requires PostgreSQL")
    draft = capture(write=False)
    put = objects.put

    def crash(path, content, media_type):
        put(path, content, media_type)
        raise SystemExit("crashed after upload")

    with monkeypatch.context() as patch:
        patch.setattr(objects, "put", crash)
        with pytest.raises(SystemExit):
            store.capture(user_id=owner, draft=draft, content=ORIGINAL)
    key = dict(user_id=owner, connection_id=draft.connection_id)
    assert not store.draft(**key).source_available
    assert store.source(**key) is None
    assert (owner, draft.connection_id) not in store.pending(limit=100)
    assert f"sealed/{owner}/{DIGEST}" in objects.objects
    store.forget(**key)
    assert not objects.objects
    assert store.draft(**key) is None


def test_postgres_legacy_inline_bytes_stay_internal_and_are_verified(storage_rig) -> None:
    store, _, owner, capture, pool = storage_rig
    if pool is None:
        pytest.skip("legacy inline storage is PostgreSQL only")
    from psycopg.types.json import Jsonb

    draft = capture(write=False)
    with pool.connection() as connection:
        connection.execute(
            "insert into public.financial_document_extractions(connection_id,user_id,draft,source_bytes) values(%s,%s,%s,%s)",
            (draft.connection_id, owner, Jsonb(draft.model_dump(mode="json")), ORIGINAL),
        )
    key = dict(user_id=owner, connection_id=draft.connection_id)
    assert store.source(**key) == ORIGINAL
    assert store.rebuilt(**key) is None
    with pool.connection() as connection:
        connection.execute(
            "update public.financial_document_extractions set source_bytes=%s where connection_id=%s",
            (b"tampered", draft.connection_id),
        )
    with pytest.raises(SourceStorageUnavailable):
        store.source(**key)
    store.forget(**key)
    with pool.connection() as connection:
        assert connection.execute(
            "select count(*) from public.financial_document_extractions where connection_id=%s",
            (draft.connection_id,),
        ).fetchone() == (0,)


def test_capture_rejects_bytes_that_do_not_match_the_intake_digest(storage_rig):
    store, objects, owner, capture, _ = storage_rig
    draft = capture(write=False)
    with pytest.raises(SourceStorageUnavailable):
        store.capture(user_id=owner, draft=draft, content=b"different original")
    assert not objects.objects
    assert store.source(user_id=owner, connection_id=draft.connection_id) is None


def test_unchanged_account_deletion_caller_removes_every_owner_prefix():
    from unittest.mock import Mock

    from argus.domain.account_deletion.service import AccountDeletionService

    objects = InMemorySourceObjects()
    mine = [f"sealed/owner/{DIGEST}", f"rebuilt/owner/{DIGEST}", f"owner/c/{DIGEST}"]
    theirs = f"rebuilt/other/{DIGEST}"
    for path in [*mine, theirs]:
        objects.objects[path] = ORIGINAL
    service = object.__new__(AccountDeletionService)
    service._sources = objects
    service._record_step = Mock()
    run = {"steps": {}}
    assert service._erase_sources("owner", "subject", run) is None
    assert objects.objects == {theirs: ORIGINAL}
    service._record_step.assert_called_once_with("subject", "storage", "deleted", run=run)
