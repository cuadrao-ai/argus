"""Profile pictures for real-Postgres tests: the local Supabase Storage when
the stack is configured, otherwise one in-memory bucket, over a Postgres row
store on the disposable database."""

import os

from argus.domain.profile_images import ProfileImages
from argus.domain.profile_images.objects import (
    PROFILE_IMAGE_BUCKET,
    InMemoryProfileImageObjects,
    SupabaseProfileImageObjects,
)
from argus.domain.profile_images.store import PostgresProfileImageStore
from psycopg_pool import ConnectionPool

LOCAL_STORAGE = all(
    os.getenv(name, "").strip()
    for name in ("ARGUS_LOCAL_SUPABASE_URL", "ARGUS_LOCAL_SUPABASE_SERVICE_ROLE_KEY")
)
_BUCKET = InMemoryProfileImageObjects()


def profile_images() -> ProfileImages:
    pool = ConnectionPool(
        os.environ["ARGUS_DISPOSABLE_DATABASE_URL"], min_size=0, max_size=2, open=True
    )
    if not LOCAL_STORAGE:
        return ProfileImages(PostgresProfileImageStore(pool), _BUCKET)
    from tests.local_supabase_support import local_supabase_gateway

    return ProfileImages(
        PostgresProfileImageStore(pool),
        SupabaseProfileImageObjects(local_supabase_gateway().client.storage),
    )


def photo_paths(connection, prefix: str) -> list[str]:
    """Object names under prefix, read from Storage's own catalog."""
    return [
        name
        for (name,) in connection.execute(
            "select name from storage.objects where bucket_id = %s"
            " and starts_with(name, %s) order by name",
            (PROFILE_IMAGE_BUCKET, prefix),
        ).fetchall()
    ]
