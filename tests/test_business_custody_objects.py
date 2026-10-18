"""Reserved Business copies verify bytes before any custody rewrite."""

from hashlib import sha256
from uuid import uuid4

import pytest
from argus.domain.business.custody_objects import (
    CustodyCopyError,
    PostgresBusinessCustodyCopies,
)
from argus.domain.ingestion.documents.objects import InMemorySourceObjects

from tests import test_business_lifecycle_postgres as lifecycle
from tests import test_financial_accounts_postgres as shared

world = lifecycle.world
users = lifecycle.users
pytestmark = pytest.mark.skipif(not shared.DSN, reason="Disposable database required")


@pytest.fixture(autouse=True)
def cleanup_copies(world):
    yield
    pool, space, _, _, _ = world
    with pool.connection() as db:
        ids = db.execute(
            "select custodian_id from argus_private.business_custody_reservations where space_id=%s",
            (space.id,),
        ).fetchall()
        db.execute(
            "delete from argus_private.business_custody_objects where space_id=%s",
            (space.id,),
        )
        db.execute(
            "delete from argus_private.business_custody_reservations where space_id=%s",
            (space.id,),
        )
        for row in ids:
            db.execute(
                "delete from argus_private.account_placeholders where id=%s", (row[0],)
            )


class FakeAuth:
    def __init__(self):
        self.created = {}

    def user_exists(self, user_id):
        return user_id in self.created

    def create_placeholder(self, *, user_id, email):
        self.created[user_id] = email


def _seed(world, objects, *, rebuilt=False):
    from datetime import datetime, timezone

    from argus.domain.ingestion.documents.models import DocumentDraft
    from psycopg.types.json import Jsonb

    from tests.test_business_spaces_migration_postgres import connection

    pool, space, people, _, _ = world
    content = b"Synthetic original receipt"
    digest = sha256(content).hexdigest()
    path = f"sealed/{people['owner']}/{digest}"
    objects.put(path, content, "image/png")
    with pool.connection() as db:
        cid = connection(db, people["owner"], space.id)
        now = datetime.now(timezone.utc)
        draft = DocumentDraft(
            connection_id=cid,
            filename="synthetic.png",
            media_type="image/png",
            sha256=digest,
            size_bytes=len(content),
            consent=True,
            created_at=now,
            updated_at=now,
        )
        db.execute(
            "insert into public.financial_document_extractions(connection_id,user_id,draft,source_bucket,source_path,source_sha256,source_media_type,source_size_bytes) values(%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                cid,
                people["owner"],
                Jsonb(draft.model_dump(mode="json")),
                objects.bucket,
                path,
                digest,
                "image/png",
                len(content),
            ),
        )
        if rebuilt:
            rebuilt_content = b"synthetic rebuilt JPEG different from original digest"
            rebuilt_path = f"rebuilt/{people['owner']}/{digest}"
            objects.put(rebuilt_path, rebuilt_content, "image/jpeg")
            db.execute(
                "update public.financial_document_extractions set rebuilt_bucket=%s,rebuilt_path=%s,rebuilt_sha256=%s,rebuilt_media_type='image/jpeg',rebuilt_size_bytes=%s where connection_id=%s",
                (
                    objects.bucket,
                    rebuilt_path,
                    sha256(rebuilt_content).hexdigest(),
                    len(rebuilt_content),
                    cid,
                ),
            )
    return cid, path, content


def test_original_and_rebuilt_copies_are_verified_reserved_and_retry_safe(world):
    pool, space, people, _, _ = world
    objects = InMemorySourceObjects()
    cid, original, content = _seed(world, objects, rebuilt=True)
    auth = FakeAuth()
    copies = PostgresBusinessCustodyCopies(pool, objects, auth)
    from argus.domain.business.lifecycle import PostgresBusinessLifecycle

    PostgresBusinessLifecycle(pool).close(
        owner_id=people["owner"],
        space_id=space.id,
        confirmation=space.name,
        idempotency_key="close-copies",
    )
    reservation = copies.prepare(space_id=space.id, departing_user_id=people["owner"])
    again = copies.prepare(space_id=space.id, departing_user_id=people["owner"])
    assert again == reservation and len(auth.created) == 1
    assert reservation.custodian_id != people["owner"]
    assert (
        objects.get(f"sealed/{reservation.custodian_id}/{sha256(content).hexdigest()}")
        == content
    )
    with pool.connection() as db:
        rows = db.execute(
            "select source_path,destination_path,verified_at from argus_private.business_custody_objects where space_id=%s",
            (space.id,),
        ).fetchall()
        assert len(rows) == 2 and all(row[2] is not None for row in rows)
        assert db.execute(
            "select source_path,user_id::text from public.financial_document_extractions where connection_id=%s",
            (cid,),
        ).fetchone() == (original, people["owner"])
    assert objects.get(original) == content


def test_open_current_owner_cannot_prepare_retained_deletion(world):
    pool, space, people, _, _ = world
    with pytest.raises(CustodyCopyError, match="business_owner_must_exit"):
        PostgresBusinessCustodyCopies(pool, InMemorySourceObjects(), FakeAuth()).prepare(
            space_id=space.id, departing_user_id=people["owner"]
        )


def test_copy_failure_leaves_old_bytes_and_retry_converges(world):
    pool, space, people, _, _ = world

    class FailingObjects(InMemorySourceObjects):
        fail = True

        def put(self, path, content, media_type):
            if self.fail and path.startswith("sealed/") and people["owner"] not in path:
                raise RuntimeError("Synthetic copy failure")
            return super().put(path, content, media_type)

    objects = FailingObjects()
    _, original, content = _seed(world, objects)
    auth = FakeAuth()
    copies = PostgresBusinessCustodyCopies(pool, objects, auth)
    from argus.domain.business.lifecycle import PostgresBusinessLifecycle

    PostgresBusinessLifecycle(pool).close(
        owner_id=people["owner"],
        space_id=space.id,
        confirmation=space.name,
        idempotency_key="close-copy",
    )
    with pytest.raises(RuntimeError, match="Synthetic copy failure"):
        copies.prepare(space_id=space.id, departing_user_id=people["owner"])
    assert objects.get(original) == content
    with pool.connection() as db:
        assert (
            db.execute(
                "select verified_at from argus_private.business_custody_objects where space_id=%s",
                (space.id,),
            ).fetchone()[0]
            is None
        )
    objects.fail = False
    result = copies.prepare(space_id=space.id, departing_user_id=people["owner"])
    assert (
        objects.get(f"sealed/{result.custodian_id}/{sha256(content).hexdigest()}")
        == content
    )


def test_wrong_business_or_custodian_cannot_prepare_copies(world):
    pool, space, people, _, _ = world
    copies = PostgresBusinessCustodyCopies(pool, InMemorySourceObjects(), FakeAuth())
    for business, person in (
        (str(uuid4()), people["owner"]),
        (space.id, people["other"]),
    ):
        with pytest.raises(CustodyCopyError, match="business_record_not_found"):
            copies.prepare(space_id=business, departing_user_id=person)


@pytest.mark.parametrize("failure", ["missing_destination", "after_copy"])
def test_manifest_tracks_unverified_copy_until_readback_succeeds(world, failure):
    pool, space, people, _, _ = world

    class InterruptedObjects(InMemorySourceObjects):
        interrupted = True

        def put(self, path, content, media_type):
            copying = people["owner"] not in path
            if copying and self.interrupted and failure == "missing_destination":
                return
            super().put(path, content, media_type)
            if copying and self.interrupted and failure == "after_copy":
                raise RuntimeError("Synthetic interruption after copy")

    objects = InterruptedObjects()
    _, original, content = _seed(world, objects)
    from argus.domain.business.lifecycle import PostgresBusinessLifecycle

    PostgresBusinessLifecycle(pool).close(
        owner_id=people["owner"],
        space_id=space.id,
        confirmation=space.name,
        idempotency_key="close-interruption",
    )
    copies = PostgresBusinessCustodyCopies(pool, objects, FakeAuth())
    with pytest.raises((CustodyCopyError, RuntimeError)):
        copies.prepare(space_id=space.id, departing_user_id=people["owner"])
    with pool.connection() as db:
        manifest = db.execute(
            "select destination_path,verified_at from argus_private.business_custody_objects where space_id=%s",
            (space.id,),
        ).fetchone()
        assert manifest is not None and manifest[1] is None
    assert objects.get(original) == content
    objects.interrupted = False
    copies.prepare(space_id=space.id, departing_user_id=people["owner"])
    assert objects.get(manifest[0]) == content


def test_deduplicated_object_and_foreign_business_bytes_remain_independent(world):
    from argus.domain.business.lifecycle import PostgresBusinessLifecycle
    from argus.domain.business.spaces import PostgresSpaceStore

    pool, space, people, _, _ = world
    objects = InMemorySourceObjects()
    _, original, content = _seed(world, objects)
    other, _ = PostgresSpaceStore(pool).create(people["other"], "Other Business")
    foreign = f"sealed/{people['other']}/{sha256(content).hexdigest()}"
    objects.put(foreign, content, "image/png")
    PostgresBusinessLifecycle(pool).close(
        owner_id=people["owner"],
        space_id=space.id,
        confirmation=space.name,
        idempotency_key="close-independent",
    )
    copies = PostgresBusinessCustodyCopies(pool, objects, FakeAuth())
    saved = copies.prepare(space_id=space.id, departing_user_id=people["owner"])
    assert objects.get(foreign) == content and objects.get(original) == content
    assert (
        objects.get(f"sealed/{saved.custodian_id}/{sha256(content).hexdigest()}")
        == content
    )
    with pool.connection() as db:
        assert not db.execute(
            "select 1 from argus_private.business_custody_objects where space_id=%s",
            (other.id,),
        ).fetchone()


def test_transferred_active_business_can_prepare_departed_custodian_copies(world):
    from argus.domain.business.transfer import PostgresBusinessTransfer

    pool, space, people, _, member = world
    objects = InMemorySourceObjects()
    _, original, content = _seed(world, objects)
    transfer = PostgresBusinessTransfer(pool)
    pending = transfer.request(
        owner_id=people["owner"],
        space_id=space.id,
        target_grant_id=member.id,
        confirmation=space.name,
        idempotency_key="copy-after-transfer",
    )
    transfer.accept(actor_id=people["other"], transfer_id=pending.id)
    saved = PostgresBusinessCustodyCopies(pool, objects, FakeAuth()).prepare(
        space_id=space.id, departing_user_id=people["owner"]
    )
    assert objects.get(original) == content
    assert (
        objects.get(f"sealed/{saved.custodian_id}/{sha256(content).hexdigest()}")
        == content
    )
    with pool.connection() as db:
        assert db.execute(
            "select current_owner_id::text,closed_at from public.spaces where id=%s",
            (space.id,),
        ).fetchone() == (people["other"], None)


@pytest.mark.parametrize("failure", ["missing_source", "corrupt_destination"])
def test_unverifiable_objects_block_copy_completion_and_preserve_database_paths(
    world, failure
):
    from argus.domain.business.lifecycle import PostgresBusinessLifecycle

    pool, space, people, _, _ = world

    class DamagedObjects(InMemorySourceObjects):
        def get(self, path):
            if failure == "corrupt_destination" and people["owner"] not in path:
                return b"Damaged destination"
            return super().get(path)

    objects = DamagedObjects()
    cid, original, _ = _seed(world, objects)
    if failure == "missing_source":
        objects.remove(original)
    PostgresBusinessLifecycle(pool).close(
        owner_id=people["owner"],
        space_id=space.id,
        confirmation=space.name,
        idempotency_key="close-damaged",
    )
    with pytest.raises(CustodyCopyError, match="business_source_integrity_failed"):
        PostgresBusinessCustodyCopies(pool, objects, FakeAuth()).prepare(
            space_id=space.id, departing_user_id=people["owner"]
        )
    with pool.connection() as db:
        assert db.execute(
            "select source_path,user_id::text from public.financial_document_extractions where connection_id=%s",
            (cid,),
        ).fetchone() == (original, people["owner"])
        assert (
            db.execute(
                "select verified_at from argus_private.business_custody_objects where space_id=%s",
                (space.id,),
            ).fetchone()[0]
            is None
        )


def test_copy_plans_are_private_and_cannot_be_discarded_by_service_role(world):
    pool, _, _, _, _ = world
    with pool.connection() as db:
        for table in ("business_custody_reservations", "business_custody_objects"):
            for role in ("anon", "authenticated"):
                assert not db.execute(
                    "select has_table_privilege(%s,%s,'SELECT')",
                    (role, f"argus_private.{table}"),
                ).fetchone()[0]
            assert not db.execute(
                "select has_table_privilege('service_role',%s,'DELETE')",
                (f"argus_private.{table}",),
            ).fetchone()[0]
