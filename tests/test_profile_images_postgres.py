"""Profile photos and Business logos on real Postgres and the local Storage.

``ARGUS_DISPOSABLE_DATABASE_URL`` on a throwaway stack with every migration
applied. The Storage round trip also needs ``ARGUS_LOCAL_SUPABASE_URL`` and
``ARGUS_LOCAL_SUPABASE_SERVICE_ROLE_KEY``, as the CI gate exports them.
"""

from __future__ import annotations

import hashlib
import os
from uuid import uuid4

import httpx
import psycopg
import pytest
from argus.domain.business.spaces import PostgresSpaceStore
from argus.domain.profile_images import ProfileImages, business, person
from argus.domain.profile_images.objects import (
    PROFILE_IMAGE_BUCKET,
    SupabaseProfileImageObjects,
)
from argus.domain.profile_images.store import PostgresProfileImageStore
from psycopg_pool import ConnectionPool

from tests import test_financial_accounts_postgres as shared
from tests.profile_images.pictures import jpeg_with_gps, png

users = shared.users
DSN = shared.DSN
LOCAL_STORAGE = all(
    os.getenv(name, "").strip()
    for name in ("ARGUS_LOCAL_SUPABASE_URL", "ARGUS_LOCAL_SUPABASE_SERVICE_ROLE_KEY")
)
pytestmark = pytest.mark.skipif(not DSN, reason="Disposable database required")


@pytest.fixture
def pool():
    with ConnectionPool(DSN, min_size=0, max_size=4) as pool:
        yield pool


def _objects() -> SupabaseProfileImageObjects:
    from tests.local_supabase_support import local_supabase_gateway

    return SupabaseProfileImageObjects(local_supabase_gateway().client.storage)


def stored_paths(connection, prefix: str) -> list[str]:
    return [
        name
        for (name,) in connection.execute(
            "select name from storage.objects where bucket_id = %s"
            " and starts_with(name, %s) order by name",
            (PROFILE_IMAGE_BUCKET, prefix),
        ).fetchall()
    ]


def test_the_bucket_is_private_and_takes_only_small_webp() -> None:
    with psycopg.connect(DSN) as db:
        row = db.execute(
            "select public, file_size_limit, allowed_mime_types from storage.buckets"
            " where id = %s",
            (PROFILE_IMAGE_BUCKET,),
        ).fetchone()
    assert row == (False, 1048576, ["image/webp"])


@pytest.mark.parametrize("table", ["profile_photos", "business_logos"])
@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_no_client_role_reads_or_writes_the_rows(users, table: str, role: str) -> None:
    with psycopg.connect(DSN) as db, db.transaction():
        db.execute(f"set local role {role}")
        db.execute(
            "select set_config('request.jwt.claims', %s, true)",
            (f'{{"sub": "{users["owner"]}", "role": "{role}"}}',),
        )
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with db.transaction():
                db.execute(f"select count(*) from public.{table}")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with db.transaction():
                db.execute(
                    f"insert into public.{table} values (%s, %s)",
                    (users["owner"], "a" * 64),
                )


def test_rows_are_replaced_in_place_and_go_with_their_user_or_space(pool, users) -> None:
    store = PostgresProfileImageStore(pool)
    owner = users["owner"]
    space, _ = PostgresSpaceStore(pool).create(owner, "Colmado")
    first = store.save("person", owner, "a" * 64)
    second = store.save("person", owner, "b" * 64)
    assert second.sha256 == "b" * 64 and second.updated_at >= first.updated_at
    store.save("business", space.id, "c" * 64)
    assert store.get_many("person", [owner, users["other"]]) == {owner: second}
    assert set(store.get_many("business", [space.id])) == {space.id}
    assert store.get_many("person", []) == {}

    with psycopg.connect(DSN) as db:
        with db.transaction(force_rollback=True):
            db.execute("delete from public.spaces where id = %s", (space.id,))
            assert db.execute("select count(*) from public.business_logos where space_id = %s", (space.id,)).fetchone() == (0,)
        with db.transaction(force_rollback=True):
            db.execute("delete from auth.users where id = %s", (owner,))
            assert db.execute("select count(*) from public.profile_photos where user_id = %s", (owner,)).fetchone() == (0,)
            assert db.execute("select count(*) from public.business_logos where space_id = %s", (space.id,)).fetchone() == (0,)

    assert store.delete("person", owner) is True
    assert store.delete("person", owner) is False
    assert store.get_many("person", [owner]) == {}


@pytest.mark.skipif(not LOCAL_STORAGE, reason="Local Supabase Storage required")
def test_a_picture_round_trips_through_the_bucket_and_its_signed_url(pool, users) -> None:
    owner = users["owner"]
    images = ProfileImages(PostgresProfileImageStore(pool), _objects(), url_ttl_seconds=120)
    subject = person(owner)
    try:
        assert images.url(subject) is None
        images.replace(subject, jpeg_with_gps(), "image/jpeg")
        url = images.url(subject)
        assert url is not None
        served = httpx.get(url, timeout=10)
        assert served.status_code == 200, served.text
        assert served.headers["content-type"].startswith("image/webp")
        assert served.content[:4] == b"RIFF" and served.content[8:12] == b"WEBP"
        sha = hashlib.sha256(served.content).hexdigest()
        assert url.endswith(f"v={sha[:12]}")
        with psycopg.connect(DSN) as db:
            assert stored_paths(db, f"people/{owner}/") == [subject.path]

        images.replace(subject, png(), "image/png")
        replaced = images.url(subject)
        assert replaced is not None and replaced != url
        again = httpx.get(replaced, timeout=10)
        assert again.status_code == 200 and again.content != served.content

        images.remove(subject)
        assert images.url(subject) is None
        with psycopg.connect(DSN) as db:
            assert stored_paths(db, f"people/{owner}/") == []
        assert httpx.get(replaced, timeout=10).status_code in (400, 404)
        images.remove(subject)
    finally:
        images.remove(subject)


@pytest.mark.skipif(not LOCAL_STORAGE, reason="Local Supabase Storage required")
def test_erase_removes_the_object_and_leaves_other_subjects(pool, users) -> None:
    images = ProfileImages(PostgresProfileImageStore(pool), _objects())
    space, _ = PostgresSpaceStore(pool).create(users["owner"], "Colmado")
    mine, theirs, logo = person(users["owner"]), person(users["other"]), business(space.id)
    try:
        for subject in (mine, theirs, logo):
            images.replace(subject, png(), "image/png")
        images.erase(mine)
        images.erase(mine)
        images.erase(business(str(uuid4())))
        with psycopg.connect(DSN) as db:
            assert stored_paths(db, "people/") == [theirs.path]
            assert stored_paths(db, "business/") == [logo.path]
        images.erase(logo)
        with psycopg.connect(DSN) as db:
            assert stored_paths(db, "business/") == []
    finally:
        for subject in (mine, theirs, logo):
            images.remove(subject)
