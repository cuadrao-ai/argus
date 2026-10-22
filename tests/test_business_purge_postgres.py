"""Day-30 purge through the existing sweep with synthetic PostgreSQL and bytes."""

from datetime import timedelta
from uuid import uuid4

import pytest
from argus.domain.business.custody_graph import PostgresBusinessCustodyGraph
from argus.domain.business.purge import BusinessPurgePending, PostgresBusinessPurge

from tests import test_business_account_deletion_postgres as deletion
from tests import test_business_custody_graph_postgres as graph

users = graph.users
actions = graph.actions
prepared = graph.prepared
custody = graph.custody
pytestmark = [graph.pytestmark, pytest.mark.owner_acts]


@pytest.fixture(autouse=True)
def cleanup_purge_receipt(custody):
    yield
    with custody["pool"].connection() as db:
        db.execute(
            "delete from argus_private.business_purge_runs where space_id=%s",
            (custody["space"],),
        )


def expiry(w, *, days=30):
    with w["pool"].connection() as db:
        db.execute(
            "update public.spaces set closed_at=clock_timestamp()-%s where id=%s",
            (timedelta(days=days), w["space"]),
        )


def remover(w, monkeypatch):
    def remove(path):
        w["objects"].rows.pop(path, None)

    monkeypatch.setattr(w["objects"], "remove", remove, raising=False)
    return remove


@pytest.mark.parametrize("owner_deleted", [False, True])
def test_existing_sweep_purges_complete_expired_graph_and_originals(
    custody, monkeypatch, owner_deleted
):
    w = custody
    remover(w, monkeypatch)
    deletion.close(w)
    if owner_deleted:
        assert deletion.command(w).delete_account(user_id=w["old"]).status == "done"
    with w["pool"].connection() as db:
        scope = PostgresBusinessCustodyGraph._scope(db, w["space"], w["old"], lock=False)
    expiry(w)
    outcome = deletion.command(w).resume_pending(idle_seconds=0)
    assert outcome == dict(resumed=1, done=1, pending=0, failed=0, busy=0)
    assert not w["objects"].rows
    with w["pool"].connection() as db:
        assert (
            db.execute(
                "select 1 from public.spaces where id=%s", (w["space"],)
            ).fetchone()
            is None
        )
        assert (
            db.execute(
                "select 1 from public.financial_activity_groups where id=any(%s::uuid[])",
                (scope["activities"],),
            ).fetchone()
            is None
        )
        assert (
            db.execute(
                "select 1 from public.financial_accounts where id=any(%s::uuid[])",
                (scope["accounts"],),
            ).fetchone()
            is None
        )
        assert (
            db.execute(
                "select 1 from public.financial_document_extractions where connection_id=%s",
                (w["cid"],),
            ).fetchone()
            is None
        )
        for table in (
            "business_custody_moves",
            "business_custody_reservations",
            "business_custody_objects",
            "business_departure_aliases",
        ):
            assert (
                db.execute(
                    f"select 1 from argus_private.{table} where space_id=%s",
                    (w["space"],),
                ).fetchone()
                is None
            )
        receipt = db.execute(
            "select status,placeholder_id,claim_id,completed_at from argus_private.business_purge_runs where space_id=%s",
            (w["space"],),
        ).fetchone()
        assert receipt[:3] == ("done", None, None) and receipt[3] is not None
        assert (
            db.execute(
                "select count(*) from argus_private.business_purge_objects"
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "select count(*) from public.whatsapp_reply_days where sender_hash=%s",
                (w["transport"]["sender"],),
            ).fetchone()[0]
            == 0
        )
    assert deletion.Auth().user_exists(w["old"]) is not owner_deleted
    assert deletion.command(w).resume_pending(idle_seconds=0)["resumed"] == 0


def test_failed_object_delete_retains_retry_plan_and_sweep_finishes(custody, monkeypatch):
    w = custody
    remove = remover(w, monkeypatch)
    deletion.close(w)
    assert deletion.command(w).delete_account(user_id=w["old"]).status == "done"
    expiry(w)
    monkeypatch.setattr(
        w["objects"],
        "remove",
        lambda path: (_ for _ in ()).throw(RuntimeError("storage unavailable")),
    )
    service = deletion.command(w)
    assert service.resume_pending(idle_seconds=0)["pending"] == 1
    with w["pool"].connection() as db:
        assert db.execute(
            "select status,claim_id from argus_private.business_purge_runs where space_id=%s",
            (w["space"],),
        ).fetchone() == ("data_deleted", None)
        assert (
            db.execute(
                "select count(*) from argus_private.business_purge_objects where deleted_at is null"
            ).fetchone()[0]
            == 2
        )
    assert len(w["objects"].rows) == 2
    monkeypatch.setattr(w["objects"], "remove", remove)
    assert service.resume_pending(idle_seconds=0)["done"] == 1
    assert w["objects"].rows == {}


def test_before_deadline_and_active_business_are_untouched(custody, monkeypatch):
    w = custody
    remover(w, monkeypatch)
    assert deletion.command(w).resume_pending(idle_seconds=0)["resumed"] == 0
    deletion.close(w)
    expiry(w, days=29)
    before = graph._snapshot(w)
    assert deletion.command(w).resume_pending(idle_seconds=0)["resumed"] == 0
    assert graph._snapshot(w) == before and len(w["objects"].rows) == 2


def test_shared_original_and_other_business_survive_one_business_purge(
    custody, monkeypatch
):
    from tests.test_business_spaces_migration_postgres import connection, space

    w = custody
    remover(w, monkeypatch)
    deletion.close(w)
    with w["pool"].connection() as db:
        other_space = space(db, w["old"])
        other_connection = connection(db, w["old"], other_space)
        db.execute(
            "insert into public.financial_document_extractions(connection_id,user_id,draft,source_bucket,source_path,source_sha256,source_size_bytes,source_media_type) select %s,user_id,jsonb_set(draft,'{connection_id}',to_jsonb(%s::text)),source_bucket,source_path,source_sha256,source_size_bytes,source_media_type from public.financial_document_extractions where connection_id=%s",
            (other_connection, other_connection, w["cid"]),
        )
        saved = db.execute(
            "select to_jsonb(s) from public.spaces s where id=%s", (other_space,)
        ).fetchone()[0]
        source = db.execute(
            "select source_path from public.financial_document_extractions where connection_id=%s",
            (other_connection,),
        ).fetchone()[0]
    expiry(w)
    assert deletion.command(w).resume_pending(idle_seconds=0)["done"] == 1
    with w["pool"].connection() as db:
        assert (
            db.execute(
                "select to_jsonb(s) from public.spaces s where id=%s", (other_space,)
            ).fetchone()[0]
            == saved
        )
        assert db.execute(
            "select source_path from public.financial_document_extractions where connection_id=%s",
            (other_connection,),
        ).fetchone() == (source,)
    assert source in w["objects"].rows


def test_unverified_storage_delete_does_not_settle(custody, monkeypatch):
    w = custody
    monkeypatch.setattr(w["objects"], "remove", lambda path: None, raising=False)
    deletion.close(w)
    expiry(w)
    with pytest.raises(BusinessPurgePending):
        PostgresBusinessPurge(w["pool"], w["objects"], deletion.Auth()).purge(
            space_id=w["space"]
        )


def test_service_role_cannot_create_or_claim_purge(custody):
    import psycopg

    w = custody
    with w["pool"].connection() as db, db.transaction():
        db.execute("set local role service_role")
        with pytest.raises(psycopg.errors.InsufficientPrivilege), db.transaction():
            db.execute(
                "insert into argus_private.business_purge_runs(space_id,closed_at) values(%s,now()-interval '30 days')",
                (str(uuid4()),),
            )


def test_failed_graph_validation_keeps_records_and_retry_converges(custody, monkeypatch):
    w = custody
    remover(w, monkeypatch)
    deletion.close(w)
    with w["pool"].connection() as db:
        account = db.execute(
            "insert into public.financial_accounts(user_id,type,currency) values(%s,'cash','DOP') returning id",
            (w["old"],),
        ).fetchone()[0]
        record = db.execute(
            "insert into public.financial_records(user_id,account_id,record_kind) values(%s,%s,'expense') returning id",
            (w["old"], account),
        ).fetchone()[0]
        db.execute(
            "insert into public.financial_record_revisions(record_id,user_id,revision,amount_minor,as_of,as_of_zone) values(%s,%s,1,100,now(),'UTC')",
            (record, w["old"]),
        )
        group = db.execute(
            "select id from public.financial_activity_groups where user_id=%s limit 1",
            (w["old"],),
        ).fetchone()[0]
        db.execute(
            "insert into public.financial_activity_memberships(activity_id,user_id,activity_revision,record_id,record_revision,record_owner_id,role) values(%s,%s,1,%s,1,%s,'destination')",
            (group, w["old"], record, w["old"]),
        )
    expiry(w)
    before = graph._snapshot(w)
    purge = PostgresBusinessPurge(w["pool"], w["objects"], deletion.Auth())
    with pytest.raises(RuntimeError, match="cross_scope"):
        purge.purge(space_id=w["space"])
    assert graph._snapshot(w) == before and not w["objects"].erased
    with w["pool"].connection() as db:
        db.execute(
            "delete from public.financial_activity_memberships where record_id=%s",
            (record,),
        )
    purge.purge(space_id=w["space"])
    with w["pool"].connection() as db:
        assert db.execute(
            "select 1 from public.financial_records where id=%s", (record,)
        ).fetchone() == (1,)


def test_two_sweeps_do_not_run_the_same_storage_plan_together(custody, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    w = custody
    remove = remover(w, monkeypatch)
    deletion.close(w)
    expiry(w)
    entered, release = Event(), Event()

    def blocked_remove(path):
        entered.set()
        assert release.wait(5)
        remove(path)

    monkeypatch.setattr(w["objects"], "remove", blocked_remove)
    purge = PostgresBusinessPurge(w["pool"], w["objects"], deletion.Auth())
    with ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(purge.sweep)
        try:
            assert entered.wait(5)
            assert purge.sweep() == dict(resumed=0, done=0, pending=0, failed=0, busy=1)
        finally:
            release.set()
        assert first.result(timeout=10)["done"] == 1


class LogoObjects:
    """Synthetic picture storage that records which space rows existed at
    each erase, and can be made to fail."""

    def __init__(self, pool, paths):
        self.pool, self.rows, self.erased, self.fail = pool, dict.fromkeys(paths, b"webp"), [], False

    def put(self, path, content, media_type):
        self.rows[path] = content

    def remove(self, path):
        if self.fail:
            raise OSError("synthetic picture storage outage")
        space_id = path.split("/")[1]
        with self.pool.connection() as db:
            row = db.execute(
                "select exists(select 1 from public.spaces where id=%s),"
                " exists(select 1 from public.business_logos where space_id=%s)",
                (space_id, space_id),
            ).fetchone()
        self.erased.append((path, row))
        self.rows.pop(path, None)

    def signed_urls(self, paths, expires_in):
        return {}


@pytest.fixture
def logos(custody):
    """After the Business closes: a logo for it and for another Business of the
    same person, each named by its row and present in synthetic storage."""
    from argus.domain.profile_images import ProfileImages, business
    from argus.domain.profile_images.store import PostgresProfileImageStore

    from tests.test_business_spaces_migration_postgres import space

    w, made = custody, []

    def make():
        with w["pool"].connection() as db:
            made.append(space(db, w["old"]))
        store = PostgresProfileImageStore(w["pool"])
        for space_id in (w["space"], made[0]):
            store.save("business", space_id, uuid4().hex * 2)
        paths = [business(w["space"]).path, business(made[0]).path]
        objects = LogoObjects(w["pool"], paths)
        return ProfileImages(store, objects), objects, made[0], paths

    yield make
    with w["pool"].connection() as db:
        db.execute("delete from public.spaces where id=any(%s::uuid[])", (made,))


def test_logo_object_goes_before_its_space_row_and_other_logos_stay(
    custody, logos, monkeypatch
):
    w = custody
    remover(w, monkeypatch)
    deletion.close(w)
    images, objects, other, (mine, theirs) = logos()
    expiry(w)
    assert deletion.command(w, images=images).resume_pending(idle_seconds=0)["done"] == 1
    # Erased once, while the space row and its logo row still named it.
    assert objects.erased == [(mine, (True, True))]
    assert set(objects.rows) == {theirs}
    with w["pool"].connection() as db:
        assert db.execute(
            "select space_id::text from public.business_logos where space_id=any(%s::uuid[])",
            ([w["space"], other],),
        ).fetchall() == [(other,)]


def test_failed_logo_erase_keeps_the_business_and_the_sweep_retries(
    custody, logos, monkeypatch
):
    w = custody
    remover(w, monkeypatch)
    deletion.close(w)
    images, objects, _, (mine, _theirs) = logos()
    expiry(w)
    before = graph._snapshot(w)
    objects.fail = True
    service = deletion.command(w, images=images)
    assert service.resume_pending(idle_seconds=0)["pending"] == 1
    assert graph._snapshot(w) == before and mine in objects.rows
    with w["pool"].connection() as db:
        assert db.execute(
            "select status,claim_id from argus_private.business_purge_runs where space_id=%s",
            (w["space"],),
        ).fetchone() == ("started", None)
        assert db.execute(
            "select count(*) from public.business_logos where space_id=%s", (w["space"],)
        ).fetchone() == (1,)
    objects.fail = False
    assert service.resume_pending(idle_seconds=0)["done"] == 1
    assert mine not in objects.rows
    with w["pool"].connection() as db:
        assert db.execute(
            "select 1 from public.spaces where id=%s", (w["space"],)
        ).fetchone() is None


def test_a_logo_without_picture_storage_holds_the_purge(custody, logos, monkeypatch):
    w = custody
    remover(w, monkeypatch)
    deletion.close(w)
    logos()
    expiry(w)
    before = graph._snapshot(w)
    with pytest.raises(BusinessPurgePending, match="business_logo_storage_unavailable"):
        PostgresBusinessPurge(w["pool"], w["objects"], deletion.Auth()).purge(
            space_id=w["space"]
        )
    assert graph._snapshot(w) == before
