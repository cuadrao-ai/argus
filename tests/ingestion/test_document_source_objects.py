"""The Supabase Storage adapter's paging, over a fake of storage3's bucket API."""

from __future__ import annotations

import pytest
from argus.domain.ingestion.documents.objects import (
    SourceStorageUnavailable,
    SupabaseSourceObjects,
)


class PagedBucket:
    """storage3's list: one folder level per call, ``limit`` entries from
    ``offset``, folders as entries without an id."""

    def __init__(self, paths: set[str]) -> None:
        self.paths, self.removed, self.calls = paths, [], 0

    def list(self, prefix: str, options: dict) -> list[dict]:
        self.calls += 1
        level = sorted(
            {
                p[len(prefix) + 1 :].split("/", 1)[0]
                for p in self.paths
                if p.startswith(f"{prefix}/")
            }
        )
        page = level[options["offset"] : options["offset"] + options["limit"]]
        return [
            {"name": name, "id": None if f"{prefix}/{name}" not in self.paths else name}
            for name in page
        ]

    def remove(self, paths: list[str]) -> list[dict]:
        assert len(paths) <= 1000
        self.removed.append(len(paths))
        self.paths -= set(paths)
        return []


class Storage:
    def __init__(self, bucket: PagedBucket) -> None:
        self.bucket = bucket

    def from_(self, name: str) -> PagedBucket:
        assert name == "financial-document-sources"
        return self.bucket


def test_delete_pages_through_more_than_a_thousand_objects_and_folders() -> None:
    owner = "u"
    mine = {f"{owner}/c{i // 1200}/{i:064x}" for i in range(2500)}
    theirs = {"v/c0/" + "0" * 64}
    bucket = PagedBucket(mine | theirs)
    SupabaseSourceObjects(Storage(bucket)).delete(f"{owner}/")
    assert bucket.paths == theirs
    assert sum(bucket.removed) == 2500
    assert max(bucket.removed) == 1000


def test_storage_failures_surface_as_one_retryable_kind() -> None:
    class Down(PagedBucket):
        def download(self, path: str) -> bytes:
            raise ConnectionError("refused")

        def upload(self, *args: object) -> None:
            raise ConnectionError("refused")

    objects = SupabaseSourceObjects(Storage(Down(set())))
    with pytest.raises(SourceStorageUnavailable):
        objects.get("u/c/" + "0" * 64)
    with pytest.raises(SourceStorageUnavailable):
        objects.put("u/c/" + "0" * 64, b"%PDF-", "application/pdf")
