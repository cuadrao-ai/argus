"""Connection-fenced document drafts, preparation checkpoints and source references.

A pending reference commits before Storage writes. An interrupted upload stays
unavailable and retryable, and disconnect can find every copy. Owner locks
serialize shared object writes with last-reference deletion.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

from loguru import logger
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from argus.domain.ingestion.connections import DEFAULT_LEASE
from argus.domain.ingestion.documents.models import (
    DocumentDraft,
    ExtractionBatch,
    PreparationJob,
)
from argus.domain.ingestion.documents.objects import (
    SourceObjects,
    SourceStorageUnavailable,
    connection_prefix,
    source_path,
    verify_content,
)
from argus.domain.ingestion.documents.store import CaptureHook, download_source


class PostgresDocumentStore:
    def __init__(self, pool: ConnectionPool, objects: SourceObjects) -> None:
        self._pool = pool
        self.objects = objects

    def _read(self, user_id: str, connection_id: str, *columns: str) -> tuple | None:
        from psycopg import sql

        with self._pool.connection() as connection:
            return connection.execute(
                sql.SQL(
                    "select {} from public.financial_document_extractions d join "
                    "public.financial_source_connections c on c.id=d.connection_id "
                    "where d.user_id=%s and d.connection_id=%s and c.user_id=%s "
                    "and c.source='statement' and c.status <> 'disconnected'"
                ).format(
                    sql.SQL(",").join(sql.Identifier("d", column) for column in columns)
                ),
                (user_id, connection_id, user_id),
            ).fetchone()

    def get(self, *, user_id: str, connection_id: str) -> ExtractionBatch | None:
        row = self._read(user_id, connection_id, "batch")
        return (
            ExtractionBatch.model_validate(row[0]) if row and row[0] is not None else None
        )

    def earliest_saved(self, *, space_id: str, sha256: str) -> datetime | None:
        """When these bytes were first saved in this Business, by anyone, or None."""

        with self._pool.connection() as connection:
            row = connection.execute(
                "select min(d.created_at) from public.financial_document_extractions d "
                "join public.financial_source_connections c on c.id=d.connection_id "
                "where c.owner_space_id=%s and d.source_sha256=%s and d.draft is not null "
                "and c.source='statement' and c.status <> 'disconnected'",
                (space_id, sha256),
            ).fetchone()
            return row[0] if row else None

    def draft(self, *, user_id: str, connection_id: str) -> DocumentDraft | None:
        row = self._read(user_id, connection_id, "draft")
        return (
            DocumentDraft.model_validate(row[0]) if row and row[0] is not None else None
        )

    @contextmanager
    def _locked(self, user_id: str) -> Iterator:
        with self._pool.connection() as connection, connection.transaction():
            connection.execute(
                "select pg_advisory_xact_lock(hashtextextended(%s,0))",
                (f"document_sources:{user_id}",),
            )
            yield connection

    @staticmethod
    def _live(connection, user_id: str, connection_id: str) -> bool:
        return (
            connection.execute(
                "select id from public.financial_source_connections where id=%s "
                "and user_id=%s and source='statement' and status <> 'disconnected' "
                "and not exists (select 1 from argus_private.account_deletion_runs "
                "where user_id=%s) for update",
                (connection_id, user_id, user_id),
            ).fetchone()
            is not None
        )

    def source(self, *, user_id: str, connection_id: str) -> bytes | None:
        row = self._read(user_id, connection_id, "source_path", "source_bytes", "draft")
        if row is None:
            return None
        path, legacy, draft = row
        if draft and not draft.get("source_available", True):
            return None
        if path is not None:
            return self.objects.get(path)
        content = bytes(legacy) if legacy is not None else None
        if content is not None:
            logger.info("document_original_read caller=source_inline_reader")
        return verify_content(content, (draft or {}).get("sha256", ""))

    def download_source(
        self, *, user_id: str, connection_id: str
    ) -> tuple[str, bytes] | None:
        return download_source(self, user_id=user_id, connection_id=connection_id)

    def rebuilt(self, *, user_id: str, connection_id: str) -> tuple[str, bytes] | None:
        row = self._read(
            user_id, connection_id, "rebuilt_path", "rebuilt_media_type", "rebuilt_sha256"
        )
        if row is None or row[0] is None:
            return None
        path, media_type, digest = row
        content = verify_content(self.objects.get(path), digest)
        return (media_type, content) if content is not None else None

    def save_rebuilt(
        self, *, user_id: str, connection_id: str, content: bytes, media_type: str
    ) -> bool:
        from argus.domain.ingestion.documents.config import (
            SOURCE_MAX_BYTES,
            SOURCE_MEDIA_TYPES,
        )

        if (
            not content
            or len(content) > SOURCE_MAX_BYTES
            or media_type not in SOURCE_MEDIA_TYPES
        ):
            raise ValueError("invalid rebuilt copy")
        digest = hashlib.sha256(content).hexdigest()
        with self._locked(user_id) as connection:
            if not self._live(connection, user_id, connection_id):
                return False
            row = connection.execute(
                "select draft->>'sha256',rebuilt_sha256,rebuilt_media_type "
                "from public.financial_document_extractions "
                "where user_id=%s and connection_id=%s",
                (user_id, connection_id),
            ).fetchone()
            if row is None or not row[0]:
                return False
            if row[1] is not None and (row[1], row[2]) != (digest, media_type):
                raise SourceStorageUnavailable("rebuilt_copy_conflict")
            path = source_path(user_id=user_id, sha256=row[0], kind="rebuilt")
            connection.execute(
                "update public.financial_document_extractions set rebuilt_bucket=%s,"
                "rebuilt_path=%s,rebuilt_media_type=%s,rebuilt_size_bytes=%s,rebuilt_sha256=%s "
                "where user_id=%s and connection_id=%s",
                (
                    self.objects.bucket,
                    path,
                    media_type,
                    len(content),
                    digest,
                    user_id,
                    connection_id,
                ),
            )
        with self._locked(user_id) as connection:
            if not self._live(connection, user_id, connection_id):
                return False
            retained = connection.execute(
                "select 1 from public.financial_document_extractions "
                "where user_id=%s and connection_id=%s and rebuilt_path=%s and rebuilt_sha256=%s",
                (user_id, connection_id, path, digest),
            ).fetchone()
            if retained is None:
                return False
            self.objects.put(path, content, media_type)
        return True

    def capture(
        self,
        *,
        user_id: str,
        draft: DocumentDraft,
        content: bytes,
        on_capture: CaptureHook | None = None,
    ) -> bool:
        connection_id = draft.connection_id
        digest = hashlib.sha256(content).hexdigest()
        verify_content(content, draft.sha256)
        path = source_path(user_id=user_id, sha256=digest)
        # Commit the reference before the external write so disconnect can find
        # a copy left by a process crash. Availability stays false until upload.
        with self._locked(user_id) as connection:
            if not self._live(connection, user_id, connection_id):
                self._forget(connection, user_id, connection_id)
                return False
            connection.execute(
                "insert into public.financial_document_extractions "
                "(connection_id,user_id,draft,created_at) values (%s,%s,%s,%s) "
                "on conflict (connection_id) do update set "
                "draft=coalesce(financial_document_extractions.draft, case "
                "when financial_document_extractions.batch is not null then "
                'excluded.draft || \'{"status":"review_ready"}\'::jsonb else excluded.draft end)',
                (
                    connection_id,
                    user_id,
                    Jsonb(
                        draft.model_copy(update={"source_available": False}).model_dump(
                            mode="json"
                        )
                    ),
                    draft.created_at,
                ),
            )
            connection.execute(
                "update public.financial_document_extractions set "
                "source_bucket=%s,source_path=%s,source_media_type=%s,"
                "source_size_bytes=%s,source_sha256=%s "
                "where connection_id=%s and source_path is null and source_bytes is null",
                (
                    self.objects.bucket,
                    path,
                    draft.media_type,
                    len(content),
                    digest,
                    connection_id,
                ),
            )
        with self._locked(user_id) as connection:
            if not self._live(connection, user_id, connection_id):
                self._forget(connection, user_id, connection_id)
                return False
            row = connection.execute(
                "select source_path,source_bytes,source_sha256 from "
                "public.financial_document_extractions where connection_id=%s and user_id=%s",
                (connection_id, user_id),
            ).fetchone()
            if row is None:
                return False
            if row[0] is not None:
                verify_content(content, row[2])
                self.objects.put(row[0], content, draft.media_type)
            if on_capture is not None:
                on_capture(connection, connection_id)
            connection.execute(
                "update public.financial_document_extractions set draft=draft || "
                "jsonb_build_object('source_available',true) where connection_id=%s",
                (connection_id,),
            )
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
        with self._pool.connection() as connection, connection.transaction():
            row = connection.execute(
                "select lease_holder,lease_until from public.financial_source_connections "
                "where id=%s and user_id=%s and source='statement' and status <> 'disconnected' for update",
                (draft.connection_id, user_id),
            ).fetchone()
            if row is None or (
                holder is not None
                and (row[0] != holder or row[1] is None or row[1] <= draft.updated_at)
            ):
                return False
            if (
                draft.error_code == "document_preparation_interrupted"
                and row[1] is not None
                and row[1] > draft.updated_at
            ):
                return False
            if claim is not None:
                changed = connection.execute(
                    "update public.financial_document_extractions set draft=%s, "
                    "preparation_job=preparation_job || '{\"claimed\": true}'::jsonb "
                    "where connection_id=%s and user_id=%s "
                    "and (draft->>'version')::integer=%s "
                    "and preparation_job->>'attempt_id' = %s returning connection_id",
                    (
                        Jsonb(draft.model_dump(mode="json")),
                        draft.connection_id,
                        user_id,
                        expected_version,
                        claim,
                    ),
                ).fetchone()
                return changed is not None
            changed = connection.execute(
                "update public.financial_document_extractions set draft=%s "
                "where connection_id=%s and user_id=%s and (draft->>'version')::integer=%s returning connection_id",
                (
                    Jsonb(draft.model_dump(mode="json")),
                    draft.connection_id,
                    user_id,
                    expected_version,
                ),
            ).fetchone()
        return changed is not None

    def save(
        self,
        *,
        user_id: str,
        connection_id: str,
        holder: str,
        now: datetime,
        batch: ExtractionBatch,
    ) -> bool:
        with self._pool.connection() as connection, connection.transaction():
            row = connection.execute(
                "select id from public.financial_source_connections "
                "where id=%s and user_id=%s and source='statement' "
                "and status <> 'disconnected' and lease_holder=%s and lease_until > %s for update",
                (connection_id, user_id, holder, now),
            ).fetchone()
            if row is None:
                return False
            connection.execute(
                "insert into public.financial_document_extractions "
                "(connection_id,user_id,batch,created_at) values (%s,%s,%s,%s) "
                "on conflict (connection_id) do update set batch=excluded.batch "
                "where financial_document_extractions.batch is null",
                (connection_id, user_id, Jsonb(batch.model_dump(mode="json")), now),
            )
        return True

    def forget(self, *, user_id: str, connection_id: str) -> None:
        with self._locked(user_id) as connection:
            self._forget(connection, user_id, connection_id)

    def _forget(self, connection, user_id: str, connection_id: str) -> None:
        # The row remains until erasure succeeds, so retry has the same paths.
        row = connection.execute(
            "select source_path,rebuilt_path from public.financial_document_extractions "
            "where user_id=%s and connection_id=%s",
            (user_id, connection_id),
        ).fetchone()
        for path in row or ():
            if path is None:
                continue
            other = connection.execute(
                "select 1 from public.financial_document_extractions "
                "where user_id=%s and connection_id<>%s "
                "and (source_path=%s or rebuilt_path=%s) limit 1",
                (user_id, connection_id, path, path),
            ).fetchone()
            if other is None:
                self.objects.remove(path)
        self.objects.delete(
            connection_prefix(user_id=user_id, connection_id=connection_id)
        )
        connection.execute(
            "delete from public.financial_document_extractions where user_id=%s and connection_id=%s",
            (user_id, connection_id),
        )

    def owner(self, *, connection_id: str) -> str | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                "select d.user_id::text from public.financial_document_extractions d "
                "join public.financial_source_connections c on c.id=d.connection_id "
                "and c.user_id=d.user_id where d.connection_id=%s "
                "and c.source='statement' and c.status <> 'disconnected'",
                (connection_id,),
            ).fetchone()
        return row[0] if row else None

    def job(self, *, user_id: str, connection_id: str) -> PreparationJob | None:
        row = self._read(user_id, connection_id, "preparation_job")
        return (
            PreparationJob.model_validate(row[0]) if row and row[0] is not None else None
        )

    def pending(self, *, limit: int) -> list[tuple[str, str]]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                "select d.user_id::text, d.connection_id::text "
                "from public.financial_document_extractions d "
                "join public.financial_source_connections c on c.id=d.connection_id "
                "and c.user_id=d.user_id where c.source='statement' "
                "and c.status <> 'disconnected' and (d.draft->>'source_available')::boolean "
                "and (d.draft->>'status' in "
                "('queued','preparing') or (d.draft->>'status'='needs_attention' "
                "and (d.preparation_job->>'retry')::boolean)) "
                "order by d.created_at, d.connection_id limit %s",
                (limit,),
            ).fetchall()
        return [(row[0], row[1]) for row in rows]

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
        # A new attempt without a draft write must still match the draft version.
        version = (
            draft.version - 1
            if draft
            else job.draft_version
            if job.attempt_id != expected_attempt_id
            else None
        )
        with self._pool.connection() as connection, connection.transaction():
            row = connection.execute(
                "select lease_until from public.financial_source_connections "
                "where id=%s and user_id=%s and source='statement' "
                "and status <> 'disconnected' for update",
                (connection_id, user_id),
            ).fetchone()
            if row is None or (row[0] is not None and row[0] > now):
                return False
            changed = connection.execute(
                "update public.financial_document_extractions "
                "set preparation_job=%s, draft=coalesce(%s::jsonb, draft) "
                "where connection_id=%s and user_id=%s and draft is not null "
                "and preparation_job->>'attempt_id' is not distinct from %s::text "
                "and (not %s or preparation_job->>'provider_call_started_at' is null) "
                "and (%s::integer is null or (draft->>'version')::integer=%s) "
                "returning connection_id",
                (
                    Jsonb(job.model_dump(mode="json")),
                    Jsonb(draft.model_dump(mode="json")) if draft else None,
                    connection_id,
                    user_id,
                    expected_attempt_id,
                    unmarked,
                    version,
                    version,
                ),
            ).fetchone()
        return changed is not None

    def mark_provider_call(
        self,
        *,
        user_id: str,
        connection_id: str,
        attempt_id: str,
        holder: str,
        now: datetime,
    ) -> bool:
        with self._pool.connection() as connection, connection.transaction():
            leased = connection.execute(
                "update public.financial_source_connections set lease_until=%s "
                "where id=%s and user_id=%s and source='statement' "
                "and status <> 'disconnected' and lease_holder=%s and lease_until > %s "
                "returning id",
                (now + DEFAULT_LEASE, connection_id, user_id, holder, now),
            ).fetchone()
            if leased is None:
                return False
            marked = connection.execute(
                "update public.financial_document_extractions set preparation_job="
                "preparation_job || jsonb_build_object('provider_call_started_at', "
                "%s::timestamptz) where connection_id=%s and user_id=%s "
                "and preparation_job->>'attempt_id' = %s returning connection_id",
                (now, connection_id, user_id, attempt_id),
            ).fetchone()
        return marked is not None
