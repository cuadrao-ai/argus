"""Retained document sources for real-Postgres tests: the local Supabase
Storage when the stack is configured, otherwise one in-memory bucket. Either
way every store in the process reads the same bucket, as API instances share
Storage in production."""

import os

from argus.domain.ingestion.documents.objects import (
    SOURCE_BUCKET,
    InMemorySourceObjects,
    SourceObjects,
    SupabaseSourceObjects,
)

LOCAL_STORAGE = bool(os.getenv("ARGUS_LOCAL_SUPABASE_URL", "").strip())
_BUCKET = InMemorySourceObjects()


def source_objects() -> SourceObjects:
    if not LOCAL_STORAGE:
        return _BUCKET
    from tests.local_supabase_support import local_supabase_gateway

    return SupabaseSourceObjects(local_supabase_gateway().client.storage)


def stored_paths(connection, prefix: str) -> list[str]:  # noqa: ANN001
    """Object names under prefix, read from Storage's own catalog."""
    return [
        name
        for (name,) in connection.execute(
            "select name from storage.objects where bucket_id = %s"
            " and starts_with(name, %s) order by name",
            (SOURCE_BUCKET, prefix),
        ).fetchall()
    ]
