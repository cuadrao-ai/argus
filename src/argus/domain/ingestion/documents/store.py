"""Owner-scoped source drafts and immutable preparation checkpoints."""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from typing import Any, Protocol

from argus.domain.ingestion.connections import (
    DEFAULT_LEASE,
    LIVE,
    ConnectionNotFound,
    InMemoryConnectionRepository,
)
from argus.domain.ingestion.documents.models import (
    DocumentDraft,
    ExtractionBatch,
    PreparationJob,
)
from argus.domain.ingestion.documents.objects import (
    InMemorySourceObjects,
    SourceObjects,
    SourceStorageUnavailable,
    connection_prefix,
    source_path,
    verify_content,
)

# Runs inside the transaction that saves a captured document, with that
# connection and the document id: a ledger row that must not outlive a failed
# save, or be missing from a successful one, is written through it.
CaptureHook = Callable[[Any, str], None]


class DocumentStore(Protocol):
    def get(self, *, user_id: str, connection_id: str) -> ExtractionBatch | None: ...
    def draft(self, *, user_id: str, connection_id: str) -> DocumentDraft | None: ...
    def earliest_saved(self, *, space_id: str, sha256: str) -> datetime | None: ...
    def source(self, *, user_id: str, connection_id: str) -> bytes | None: ...
    def rebuilt(
        self, *, user_id: str, connection_id: str
    ) -> tuple[str, bytes] | None: ...
    def save_rebuilt(
        self, *, user_id: str, connection_id: str, content: bytes, media_type: str
    ) -> bool: ...
    def capture(
        self,
        *,
        user_id: str,
        draft: DocumentDraft,
        content: bytes,
        on_capture: CaptureHook | None = None,
    ) -> bool: ...
    def update(
        self,
        *,
        user_id: str,
        draft: DocumentDraft,
        expected_version: int,
        holder: str | None = None,
        claim: str | None = None,
    ) -> bool:
        """With ``claim``, the same write requires that attempt to be current
        and records that it claimed the draft."""
        ...

    def save(
        self,
        *,
        user_id: str,
        connection_id: str,
        holder: str,
        now: datetime,
        batch: ExtractionBatch,
    ) -> bool: ...
    def forget(self, *, user_id: str, connection_id: str) -> None: ...
    def owner(self, *, connection_id: str) -> str | None: ...
    def job(self, *, user_id: str, connection_id: str) -> PreparationJob | None: ...
    def pending(self, *, limit: int) -> list[tuple[str, str]]:
        """Owner and connection of drafts awaiting preparation or a retry."""
        ...

    def mark_provider_call(
        self,
        *,
        user_id: str,
        connection_id: str,
        attempt_id: str,
        holder: str,
        now: datetime,
    ) -> bool:
        """Record that ``attempt_id`` may now reach the provider and renew the
        lease, only while ``holder`` holds it and the attempt is current."""
        ...

    def advance(
        self,
        *,
        user_id: str,
        connection_id: str,
        now: datetime,
        expected_attempt_id: str | None,
        job: PreparationJob,
        draft: DocumentDraft | None = None,
        unmarked: bool = False,
    ) -> bool:
        """Replace the job (and draft) only while no lease is live and the current
        attempt is ``expected_attempt_id``. With a draft, its version moves by
        one; installing a new attempt without one requires the draft to still be
        the version that attempt is for. ``unmarked`` also requires the current
        attempt never to have marked a provider call."""
        ...


class InMemoryDocumentStore:
    def __init__(
        self,
        connections: InMemoryConnectionRepository,
        objects: SourceObjects | None = None,
    ) -> None:
        self.connections = connections
        self.objects = objects if objects is not None else InMemorySourceObjects()
        self._rows: dict[tuple[str, str], str] = {}
        self._drafts: dict[tuple[str, str], str] = {}
        self._sources: dict[tuple[str, str], str] = {}
        self._rebuilt: dict[tuple[str, str], tuple[str, str, str]] = {}
        self._jobs: dict[tuple[str, str], str] = {}
        self._lock = threading.RLock()

    def _live(
        self,
        user_id: str,
        connection_id: str,
        holder: str | None = None,
        now: datetime | None = None,
    ) -> bool:
        try:
            row = self.connections.get_any_scope(
                user_id=user_id, connection_id=connection_id
            )
        except ConnectionNotFound:
            return False
        return (
            row.source == "statement"
            and row.status in LIVE
            and (
                holder is None
                or (
                    row.lease_holder == holder
                    and row.lease_until is not None
                    and now is not None
                    and row.lease_until > now
                )
            )
        )

    def get(self, *, user_id: str, connection_id: str) -> ExtractionBatch | None:
        with self.connections._lock, self._lock:
            raw = (
                self._rows.get((user_id, connection_id))
                if self._live(user_id, connection_id)
                else None
            )
            return ExtractionBatch.model_validate_json(raw) if raw is not None else None

    def draft(self, *, user_id: str, connection_id: str) -> DocumentDraft | None:
        with self.connections._lock, self._lock:
            raw = (
                self._drafts.get((user_id, connection_id))
                if self._live(user_id, connection_id)
                else None
            )
            return DocumentDraft.model_validate_json(raw) if raw is not None else None

    def earliest_saved(self, *, space_id: str, sha256: str) -> datetime | None:
        """When these bytes were first saved in this Business, by anyone, or
        None: a Business keeps one receipt per person and file, so the same
        file from two people is two documents that share this answer."""

        from argus.domain.owner_scope import space_id as scope_space

        with self.connections._lock, self._lock:
            found: datetime | None = None
            for (user_id, connection_id), raw in self._drafts.items():
                if not self._live(user_id, connection_id):
                    continue
                row = self.connections.get_any_scope(
                    user_id=user_id, connection_id=connection_id
                )
                if scope_space(row.scope) != space_id:
                    continue
                draft = DocumentDraft.model_validate_json(raw)
                if draft.sha256 == sha256 and (found is None or draft.created_at < found):
                    found = draft.created_at
            return found

    def source(self, *, user_id: str, connection_id: str) -> bytes | None:
        with self.connections._lock, self._lock:
            path = (
                self._sources.get((user_id, connection_id))
                if self._live(user_id, connection_id)
                else None
            )
            return self.objects.get(path) if path is not None else None

    def capture(
        self,
        *,
        user_id: str,
        draft: DocumentDraft,
        content: bytes,
        on_capture: CaptureHook | None = None,
    ) -> bool:
        # The in-memory store keeps no transaction and no ledger: the hook is
        # the Postgres store's.
        del on_capture
        verify_content(content, draft.sha256)
        with self.connections._lock, self._lock:
            if not self._live(user_id, draft.connection_id):
                return False
            key = (user_id, draft.connection_id)
            if key not in self._drafts:
                if key in self._rows:
                    draft = draft.model_copy(update={"status": "review_ready"})
                path = source_path(
                    user_id=user_id,
                    sha256=hashlib.sha256(content).hexdigest(),
                )
                self.objects.put(path, content, draft.media_type)
                self._drafts[key] = draft.model_dump_json()
                self._sources[key] = path
            return True

    def rebuilt(self, *, user_id: str, connection_id: str) -> tuple[str, bytes] | None:
        with self.connections._lock, self._lock:
            saved = self._rebuilt.get((user_id, connection_id))
            if not self._live(user_id, connection_id) or saved is None:
                return None
            path, media_type, digest = saved
            content = verify_content(self.objects.get(path), digest)
            return (media_type, content) if content is not None else None

    def save_rebuilt(
        self, *, user_id: str, connection_id: str, content: bytes, media_type: str
    ) -> bool:
        from argus.domain.ingestion.documents.config import (
            SOURCE_MAX_BYTES,
            SOURCE_MEDIA_TYPES,
        )

        with self.connections._lock, self._lock:
            raw = self._drafts.get((user_id, connection_id))
            if not self._live(user_id, connection_id) or raw is None:
                return False
            draft = DocumentDraft.model_validate_json(raw)
            if (
                not content
                or len(content) > SOURCE_MAX_BYTES
                or media_type not in SOURCE_MEDIA_TYPES
            ):
                raise ValueError("invalid rebuilt copy")
            path = source_path(user_id=user_id, sha256=draft.sha256, kind="rebuilt")
            digest = hashlib.sha256(content).hexdigest()
            saved = self._rebuilt.get((user_id, connection_id))
            if saved is not None and saved != (path, media_type, digest):
                raise SourceStorageUnavailable("rebuilt_copy_conflict")
            self.objects.put(path, content, media_type)
            self._rebuilt[(user_id, connection_id)] = (path, media_type, digest)
            return True

    def update(
        self,
        *,
        user_id: str,
        draft: DocumentDraft,
        expected_version: int,
        holder: str | None = None,
        claim: str | None = None,
    ) -> bool:
        key = (user_id, draft.connection_id)
        with self.connections._lock, self._lock:
            raw = self._drafts.get(key)
            previous = DocumentDraft.model_validate_json(raw) if raw else None
            if (
                not self._live(user_id, draft.connection_id, holder, draft.updated_at)
                or previous is None
                or previous.version != expected_version
            ):
                return False
            lease = self.connections.get_any_scope(
                user_id=user_id, connection_id=draft.connection_id
            ).lease_until
            if (
                draft.error_code == "document_preparation_interrupted"
                and lease is not None
                and lease > draft.updated_at
            ):
                return False
            if claim is not None:
                job_raw = self._jobs.get(key)
                job = PreparationJob.model_validate_json(job_raw) if job_raw else None
                if job is None or job.attempt_id != claim:
                    return False
                self._jobs[key] = job.model_copy(
                    update={"claimed": True}
                ).model_dump_json()
            self._drafts[key] = draft.model_dump_json()
            return True

    def save(
        self,
        *,
        user_id: str,
        connection_id: str,
        holder: str,
        now: datetime,
        batch: ExtractionBatch,
    ) -> bool:
        with self.connections._lock, self._lock:
            if not self._live(user_id, connection_id, holder, now):
                return False
            self._rows.setdefault((user_id, connection_id), batch.model_dump_json())
            return True

    def forget(self, *, user_id: str, connection_id: str) -> None:
        with self.connections._lock, self._lock:
            key = (user_id, connection_id)
            paths = {self._sources.get(key)}
            if key in self._rebuilt:
                paths.add(self._rebuilt[key][0])
            remaining = {p for k, p in self._sources.items() if k != key}
            remaining.update(p[0] for k, p in self._rebuilt.items() if k != key)
            for path in paths - remaining - {None}:
                self.objects.remove(path)
            self.objects.delete(
                connection_prefix(user_id=user_id, connection_id=connection_id)
            )
            self._rows.pop(key, None)
            self._drafts.pop(key, None)
            self._sources.pop(key, None)
            self._rebuilt.pop(key, None)
            self._jobs.pop(key, None)

    def owner(self, *, connection_id: str) -> str | None:
        with self.connections._lock, self._lock:
            row = self.connections._rows.get(connection_id)
            if row is None or not self._live(row.user_id, connection_id):
                return None
            return row.user_id if (row.user_id, connection_id) in self._drafts else None

    def job(self, *, user_id: str, connection_id: str) -> PreparationJob | None:
        with self.connections._lock, self._lock:
            raw = (
                self._jobs.get((user_id, connection_id))
                if self._live(user_id, connection_id)
                else None
            )
            return PreparationJob.model_validate_json(raw) if raw is not None else None

    def pending(self, *, limit: int) -> list[tuple[str, str]]:
        with self.connections._lock, self._lock:
            rows = []
            for key, raw in self._drafts.items():
                draft = DocumentDraft.model_validate_json(raw)
                job = self._jobs.get(key)
                retry = job is not None and PreparationJob.model_validate_json(job).retry
                if self._live(*key) and (
                    draft.status in {"queued", "preparing"}
                    or (draft.status == "needs_attention" and retry)
                ):
                    rows.append((draft.created_at, key))
            return [key for _, key in sorted(rows)[:limit]]

    def advance(
        self,
        *,
        user_id: str,
        connection_id: str,
        now: datetime,
        expected_attempt_id: str | None,
        job: PreparationJob,
        draft: DocumentDraft | None = None,
        unmarked: bool = False,
    ) -> bool:
        key = (user_id, connection_id)
        with self.connections._lock, self._lock:
            if not self._live(user_id, connection_id) or key not in self._drafts:
                return False
            lease = self.connections.get_any_scope(
                user_id=user_id, connection_id=connection_id
            ).lease_until
            raw = self._jobs.get(key)
            current = PreparationJob.model_validate_json(raw) if raw else None
            previous = DocumentDraft.model_validate_json(self._drafts[key])
            if (
                (lease is not None and lease > now)
                or (current.attempt_id if current else None) != expected_attempt_id
                or (unmarked and current and current.provider_call_started_at)
                or (draft is not None and draft.version != previous.version + 1)
                or (
                    draft is None
                    and job.attempt_id != expected_attempt_id
                    and previous.version != job.draft_version
                )
            ):
                return False
            if draft is not None:
                self._drafts[key] = draft.model_dump_json()
            self._jobs[key] = job.model_dump_json()
            return True

    def mark_provider_call(
        self,
        *,
        user_id: str,
        connection_id: str,
        attempt_id: str,
        holder: str,
        now: datetime,
    ) -> bool:
        key = (user_id, connection_id)
        with self.connections._lock, self._lock:
            raw = self._jobs.get(key)
            job = PreparationJob.model_validate_json(raw) if raw is not None else None
            if (
                not self._live(user_id, connection_id, holder, now)
                or job is None
                or job.attempt_id != attempt_id
            ):
                return False
            row = self.connections._rows[connection_id]
            self.connections._rows[connection_id] = replace(
                row, lease_until=now + DEFAULT_LEASE
            )
            self._jobs[key] = job.model_copy(
                update={"provider_call_started_at": now}
            ).model_dump_json()
            return True
