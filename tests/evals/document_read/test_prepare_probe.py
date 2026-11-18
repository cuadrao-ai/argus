"""Temporary: finds why CI rejected one photo with document_memory_limit. Removed before merge."""

from __future__ import annotations

import collections
import os
import platform
import threading
import warnings
from concurrent.futures import ThreadPoolExecutor

import psutil
import pytest
from argus.domain.ingestion.documents import rebuilt
from argus.domain.ingestion.documents.models import DocumentExtractionError
from argus.domain.ingestion.documents.preparation import prepare_document

from tests.evals.document_read.dataset import build_set
from tests.evals.document_read.scoring import _SETTINGS


def test_probe_photo_preparation_on_this_machine(monkeypatch: pytest.MonkeyPatch) -> None:
    samples = build_set()
    process = psutil.Process
    lock = threading.Lock()
    reads: list[tuple[int, str]] = []

    class Watched:
        def __init__(self, pid: int) -> None:
            self.inner = process(pid)

        def memory_info(self):  # noqa: ANN202
            info = self.inner.memory_info()
            if info.rss > 100 * 1024 * 1024:
                try:
                    what = " ".join(self.inner.cmdline())[:60]
                except psutil.Error as error:
                    what = type(error).__name__
                with lock:
                    reads.append((info.rss >> 20, what))
            return info

    monkeypatch.setattr(rebuilt.psutil, "Process", Watched)

    def prepare(sample):  # noqa: ANN001, ANN202
        try:
            prepare_document(sample.image, "image/jpeg", _SETTINGS)
        except DocumentExtractionError as error:
            return (sample.case.case_id, error.code, str(error.metadata))
        return None

    lines = [
        f"kernel {platform.release()} cpus {os.cpu_count()} "
        f"os threads {process().num_threads()}"
    ]
    ballast = None
    for label, workers, rounds, extra_mb in (
        ("as CI found it, 8 at once", 8, 15, 0),
        ("parent 1.5 GB larger, 8 at once", 8, 15, 1500),
        ("parent 1.5 GB larger, 1 at a time", 1, 5, 1500),
    ):
        if extra_mb and ballast is None:
            ballast = bytearray(b"x") * (extra_mb << 20)
        reads.clear()
        fails: collections.Counter[tuple[str, str, str]] = collections.Counter()
        for _ in range(rounds):
            with ThreadPoolExecutor(max_workers=workers) as pool:
                fails.update(filter(None, pool.map(prepare, samples)))
        lines.append(
            f"{label}: parent rss {process().memory_info().rss >> 20} MB, "
            f"{rounds * len(samples)} photos, rejected {dict(fails)}, "
            f"child rss reads over 100 MB {collections.Counter(reads).most_common(4)}"
        )
    del ballast
    warnings.warn("PREPARE PROBE\n" + "\n".join(lines), stacklevel=1)
