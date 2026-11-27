"""Capture first; preparation feeds reconciliation without financial writes."""

from __future__ import annotations

import asyncio
import hashlib
import time
import unicodedata
import uuid
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from copy import copy
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from typing import TYPE_CHECKING, Protocol

from loguru import logger

from argus.domain.business.document_type import DocumentType
from argus.domain.business.read_budget import HELD_READ_REFUSAL, READ_BUDGET_REFUSALS
from argus.domain.ingestion.connections import (
    LIVE,
    ConnectionNotFound,
    DuplicateConnection,
    SourceConnection,
)
from argus.domain.ingestion.contract import ImportCandidate, SourceKind, SourceRef
from argus.domain.ingestion.documents.breaker import (
    Admission,
    AdmittedCall,
    ReadBreaker,
    ask_breaker,
)
from argus.domain.ingestion.documents.config import (
    MAX_PROVIDER_CALLS,
    PROVIDER_CALLS_PER_READ,
)
from argus.domain.ingestion.documents.failures import (
    READS_PAUSED,
    alert_config,
    classify,
    held_back,
    next_take,
    provider_answered,
)
from argus.domain.ingestion.documents.models import (
    DocumentDraft,
    DraftProposal,
    DraftStatus,
    ExtractionBatch,
    ReceiptDetails,
)
from argus.domain.ingestion.documents.objects import (
    IMAGE_MEDIA_TYPES,
    SourceStorageUnavailable,
    connection_prefix,
)
from argus.domain.ingestion.documents.preparation import PreparedDocument, validate_source
from argus.domain.ingestion.documents.rebuilt import ensure_rebuilt_image
from argus.domain.ingestion.documents.storage_text import clean_extracted_text
from argus.domain.ingestion.documents.store import (
    CaptureHook,
    DocumentStore,
    download_source,
)
from argus.domain.ingestion.documents.store_postgres import PostgresDocumentStore
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.ingestion.whatsapp.config import load_whatsapp_settings
from argus.domain.ingestion.whatsapp.held import MARK, PostgresHeldFiles, is_held
from argus.domain.owner_scope import PERSONAL, BusinessSpace, OwnerScope, space_id

if TYPE_CHECKING:
    from psycopg import Connection

    from argus.domain.business.access import GrantedSpace
    from argus.domain.business.actions import BusinessActions
    from argus.domain.business.contracts.actions import Applied
    from argus.domain.ingestion.whatsapp.held import HeldFile

# Marks a batch the owner entered by hand: one purchase, nothing read.
ENTERED_BY_OWNER = {"entered_by": "owner"}


def entered_by_owner(batch: ExtractionBatch | None) -> bool:
    return batch is not None and batch.metadata.get("entered_by") == "owner"


def owner_entry_id(sha256: str) -> str:
    """The one purchase an owner enters by hand for a document, before or
    after it was read, so a repeat delivers the same observation."""

    return f"{sha256}:entered-by-owner"


def owner_purchase(draft: DocumentDraft, now: datetime) -> ImportCandidate:
    venta = draft.document_type == "venta"
    return ImportCandidate(
        source=SourceRef(
            source="statement",
            connection_id=draft.connection_id,
            external_id=owner_entry_id(draft.sha256),
            observed_at=now,
        ),
        evidence="transaction",
        direction="inflow" if venta else "outflow",
        kind_hint="income" if venta else "expense",
        uncertain=frozenset({"amount", "currency", "occurred_on"}),
    )


def lease_live(connection: SourceConnection, now: datetime) -> bool:
    return connection.lease_until is not None and connection.lease_until > now


class Extractor(Protocol):
    def prepare(
        self, content: bytes, media_type: str, *, rebuilt_image: bytes | None = None
    ) -> PreparedDocument: ...

    async def extract(
        self,
        *,
        content: bytes,
        filename: str,
        media_type: str,
        connection_id: str,
        observed_at: datetime,
        prepared: PreparedDocument | None = None,
        before_request: Callable[[], Awaitable[None]] | None = None,
    ) -> ExtractionBatch: ...


class ReadBudget(Protocol):
    def charge(self, business_id: str, now: datetime) -> str | None:
        """Count one read for this Business now, or return why it may not start."""


class DocumentServiceError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool = False) -> None:
        super().__init__(code)
        self.code, self.retryable = code, retryable


def stored_filename(filename: str) -> str:
    """Without control or format characters (bidi overrides included), so a
    stored name can neither break a log line nor disguise its extension."""

    kept = "".join(c for c in filename if unicodedata.category(c) not in ("Cc", "Cf"))
    return kept[:80] or "document"


def document_ref(
    user_id: str, scope: OwnerScope, digest: str, namespace: str | None = None
) -> str:
    """The connection reference for one file in one scope.

    References are globally unique, so the same bytes uploaded in Personal and
    in Business must differ. The Personal form is the original one, unchanged.
    The same bytes under a ``namespace`` are an upload of their own.
    """

    space = space_id(scope)
    owner = user_id if space is None else f"{user_id}:{space}"
    ref = hashlib.sha256(f"{owner}:{digest}".encode()).hexdigest()
    return ref if namespace is None else f"{namespace}:{ref}"


@dataclass(frozen=True)
class DocumentOutcome:
    connection_id: str
    replayed: bool
    candidate_count: int
    status: DraftStatus = "saved"


class DocumentsService:
    source: SourceKind = "statement"

    def __init__(
        self,
        hub: IngestionHub,
        store: DocumentStore,
        extractor: Extractor,
        *,
        business_actions: BusinessActions | None = None,
        business_preparation_required: bool = False,
        read_budget: ReadBudget | None = None,
        read_breaker: ReadBreaker | None = None,
    ) -> None:
        self.hub, self.store, self.extractor = hub, store, extractor
        # One bounded decode/capture at a time on this app-owned service.
        self._capture_slot = asyncio.Semaphore(1)
        self.business_actions = business_actions
        # The owner's stored receipt-reading setting: the only consent for a
        # Business read, asked again at the moment of each read.
        self.business_receipt_consent = None
        # Reads a Business may start today and this month, charged just before
        # the provider is reached, whichever channel the receipt came from.
        self.read_budget = read_budget
        self.read_breaker = read_breaker  # Stops sends while the provider fails.
        # An app with a Postgres pool never falls back to legacy Business
        # delivery; without a pool there is no canonical wiring to require.
        self.business_preparation_required = business_preparation_required
        hub.register(self)

    def revoke(self, connection: SourceConnection, credential: str | None) -> None:
        """An uploaded document has no provider grant to revoke."""

    def forget(self, connection: SourceConnection) -> None:
        self.store.forget(user_id=connection.user_id, connection_id=connection.id)

    def _connection(
        self, user_id: str, connection_id: str, *, scope: OwnerScope
    ) -> SourceConnection:
        row = self.hub.connections.get(
            user_id=user_id, connection_id=connection_id, scope=scope
        )
        if row.source != self.source:
            raise ConnectionNotFound()
        if row.status not in LIVE:
            raise DocumentServiceError("document_disconnected")
        return row

    def get(
        self, *, user_id: str, connection_id: str, scope: OwnerScope
    ) -> DocumentDraft:
        return self._stored_draft(self._connection(user_id, connection_id, scope=scope))

    def _stored_draft(self, connection: SourceConnection) -> DocumentDraft:
        user_id, connection_id = connection.user_id, connection.id
        draft = self.store.draft(user_id=user_id, connection_id=connection_id)
        if draft is None:
            if self.store.get(user_id=user_id, connection_id=connection_id) is None:
                raise DocumentServiceError("document_source_unavailable")
            return DocumentDraft(
                connection_id=connection_id,
                filename="document",
                media_type="",
                sha256="",
                size_bytes=0,
                source_available=False,
                status="review_ready",
                created_at=connection.created_at,
                updated_at=connection.updated_at,
            )
        # An expired attempt is the sweep's to settle; a read never settles it.
        return draft

    def _read_source(self, user_id: str, connection_id: str) -> bytes:
        try:
            content = self.store.source(user_id=user_id, connection_id=connection_id)
        except SourceStorageUnavailable:
            raise DocumentServiceError(
                "document_storage_unavailable", retryable=True
            ) from None
        if content is None:
            raise DocumentServiceError("document_source_unavailable")
        return content

    def _rebuilt_copy(
        self,
        user_id: str,
        draft: DocumentDraft,
        *,
        ensure: bool = False,
    ) -> tuple[str, bytes] | None:
        connection_id = draft.connection_id
        previous = draft.resolution.get("held_image_source")
        if previous is not None and is_held(draft):
            # The rebuilt image is keyed by sender and digest. Keep its original
            # owner so an independently expiring resend never pins that path.
            origin = self.get(user_id=user_id, connection_id=previous, scope=PERSONAL)
            if not is_held(origin) or origin.sha256 != draft.sha256:
                raise DocumentServiceError("document_source_changed")
            connection_id = origin.connection_id
        if ensure:
            ensure_rebuilt_image(
                store=self.store, user_id=user_id, connection_id=connection_id
            )
        return self.store.rebuilt(user_id=user_id, connection_id=connection_id)

    def source_bytes(
        self, *, user_id: str, connection_id: str, scope: OwnerScope
    ) -> bytes:
        """A draft whose stored object is gone says so (``source_available``
        false) instead of promising a source that cannot be read."""

        self._connection(user_id, connection_id, scope=scope)
        try:
            try:
                draft = self.store.draft(user_id=user_id, connection_id=connection_id)
                if draft is not None and draft.media_type in IMAGE_MEDIA_TYPES:
                    source = self._rebuilt_copy(user_id, draft, ensure=True)
                else:
                    source = download_source(
                        self.store, user_id=user_id, connection_id=connection_id
                    )
                self._connection(user_id, connection_id, scope=scope)
            except SourceStorageUnavailable:
                raise DocumentServiceError(
                    "document_storage_unavailable", retryable=True
                ) from None
            if source is None:
                raise DocumentServiceError("document_source_unavailable")
            return source[1]
        except DocumentServiceError as error:
            if error.code == "document_source_unavailable":
                draft = self.store.draft(user_id=user_id, connection_id=connection_id)
                if (
                    draft is not None
                    and draft.source_available
                    and draft.status != "preparing"
                ):
                    try:
                        self._update(user_id, draft, source_available=False)
                    except DocumentServiceError:
                        pass
            raise

    def _update(
        self,
        user_id: str,
        draft: DocumentDraft,
        *,
        holder: str | None = None,
        claim: str | None = None,
        **changes: object,
    ) -> DocumentDraft:
        updated = self.revise(draft, **changes)
        if not self.store.update(
            user_id=user_id,
            draft=updated,
            expected_version=draft.version,
            holder=holder,
            claim=claim,
        ):
            raise DocumentServiceError("document_version_conflict", retryable=True)
        return updated

    def revise(self, draft: DocumentDraft, **changes: object) -> DocumentDraft:
        return draft.model_copy(
            update={
                **changes,
                "version": draft.version + 1,
                "updated_at": self.hub.clock(),
            }
        )

    def update_proposal(
        self,
        *,
        user_id: str,
        connection_id: str,
        version: int,
        proposal: DraftProposal,
        scope: OwnerScope,
    ) -> DocumentDraft:
        draft = self.get(user_id=user_id, connection_id=connection_id, scope=scope)
        if draft.status == "dismissed":
            raise DocumentServiceError("business_document_deleted")
        if version != draft.version or draft.status == "preparing":
            raise DocumentServiceError("document_version_conflict", retryable=True)
        return self._update(user_id, draft, proposal=proposal)

    def on_connection(self, db: Connection) -> DocumentsService:
        """Use the caller's transaction for publication, preparation and settlement."""
        from argus.domain.business.actions import BusinessActions
        from argus.domain.ingestion.connections_postgres import (
            PostgresConnectionRepository,
        )
        from argus.domain.postgres_connection import BorrowedConnection

        class Savepoints(BorrowedConnection):
            @contextmanager
            def connection(self, timeout: float | None = None) -> Iterator[Connection]:
                # Repository calls can recover a duplicate-key error inside this transaction.
                with db.transaction():
                    yield db

        pool = Savepoints(db)
        assert isinstance(self.store, PostgresDocumentStore)
        scoped = copy(self)
        scoped.hub = copy(self.hub)
        scoped.hub.connections = PostgresConnectionRepository(pool)
        scoped.store = PostgresDocumentStore(pool, self.store.objects)
        if self.business_actions is not None:
            scoped.business_actions = BusinessActions(pool, self.business_actions.imports)
        if self.business_receipt_consent is not None:
            scoped.business_receipt_consent = copy(self.business_receipt_consent)
            scoped.business_receipt_consent.pool = pool
        return scoped

    def for_sender(self, person_id: str, scope: BusinessSpace) -> DocumentsService:
        """Bind a delivery to the sender's current grant."""
        from argus.api.business_drafts import bind_to_grant
        from argus.domain.business.contracts.authority import TrustedActor
        from argus.domain.ingestion.reconcile.service import ReconciliationService

        if self.business_actions is None or not isinstance(
            self.hub.sink, ReconciliationService
        ):
            return self
        context = self.business_actions.resolve_actor(
            TrustedActor(actor_id=person_id, actor_kind="member", space_id=scope.space_id)
        )
        return bind_to_grant(self, self.hub, self.business_actions, context, "prepare")[0]

    async def upload(
        self,
        *,
        user_id: str,
        content: bytes,
        filename: str,
        media_type: str,
        consent: bool = False,
        proposal: DraftProposal | None = None,
        source_text: str | None = None,
        scope: OwnerScope,
        on_capture: CaptureHook | None = None,
        context_only: bool = False,
        document_type: DocumentType | None = None,
        defer_capture: bool = False,
        namespace: str | None = None,
    ) -> DocumentOutcome:
        """Save the bytes, or leave publication to a delivery's settlement."""
        consent_id = None
        if space_id(scope) is not None:
            permission = await asyncio.to_thread(
                self._business_permission, scope, user_id
            )
            consent = permission["enabled"] and not context_only
            consent_id = permission["consent_id"] if consent else None

        def capture() -> DocumentOutcome | BaseException:
            try:
                return self._upload(
                    user_id=user_id,
                    content=content,
                    filename=filename,
                    media_type=media_type,
                    consent=consent,
                    proposal=proposal,
                    source_text=source_text,
                    scope=scope,
                    on_capture=on_capture,
                    consent_id=consent_id,
                    document_type=document_type,
                    defer_capture=defer_capture,
                    namespace=namespace,
                )
            except BaseException as error:
                # SystemExit/KeyboardInterrupt must travel as data: raising
                # either inside the worker Task stops the caller's event loop.
                return error

        async with self._capture_slot:
            worker = asyncio.create_task(asyncio.to_thread(capture))
            try:
                result = await asyncio.shield(worker)
            except asyncio.CancelledError:
                # A thread cannot be cancelled. Keep its slot and caller alive
                # until the write settles, even if cancellation repeats.
                while not worker.done():
                    try:
                        await asyncio.shield(worker)
                    except asyncio.CancelledError:
                        continue
                    except Exception:
                        break
                if not worker.cancelled():
                    worker.exception()
                raise
            if isinstance(result, BaseException):
                raise result
            return result

    def _upload(
        self,
        *,
        user_id: str,
        content: bytes,
        filename: str,
        media_type: str,
        consent: bool,
        proposal: DraftProposal | None,
        source_text: str | None,
        scope: OwnerScope,
        on_capture: CaptureHook | None,
        consent_id: str | None = None,
        document_type: DocumentType | None = None,
        namespace: str | None = None,
        defer_capture: bool = False,
    ) -> DocumentOutcome:
        validate_source(content, media_type)
        digest = hashlib.sha256(content).hexdigest()
        external_ref = document_ref(user_id, scope, digest, namespace)
        replayed = False
        try:
            connection = self.hub.connections.create(
                user_id=user_id,
                source=self.source,
                external_ref=external_ref,
                label="Document",
                now=self.hub.clock(),
                scope=scope,
            )
        except DuplicateConnection as error:
            if error.elsewhere:
                raise DocumentServiceError("document_unavailable") from None
            connection = self._connection(user_id, error.existing_id, scope=scope)
            replayed = True
            stored = self.store.draft(user_id=user_id, connection_id=connection.id)
            if (
                document_type is not None
                and stored is not None
                and stored.document_type is not None
                and stored.document_type != document_type
            ):
                raise DocumentServiceError("document_type_conflict") from None
        queue_read = consent and not defer_capture
        draft = DocumentDraft(
            connection_id=connection.id,
            filename=stored_filename(filename),
            media_type=media_type,
            proposal=proposal or DraftProposal(),
            sha256=digest,
            resolution={MARK: True} if namespace == MARK and scope == PERSONAL else {},
            size_bytes=len(content),
            consent=queue_read,
            business_reading_consent_id=consent_id,
            source_text=source_text,
            document_type=document_type,
            status="queued" if queue_read else "saved",
            source_available=not defer_capture,
            created_at=self.hub.clock(),
            updated_at=self.hub.clock(),
        )
        try:
            captured = self.store.capture(
                user_id=user_id, draft=draft, content=content, on_capture=on_capture
            )
        except SourceStorageUnavailable:
            raise DocumentServiceError(
                "document_storage_unavailable", retryable=True
            ) from None
        if not captured:
            raise DocumentServiceError("document_disconnected")
        return self.outcome(
            user_id=user_id, connection_id=connection.id, replayed=replayed, scope=scope
        )

    def publish_capture(
        self,
        *,
        user_id: str,
        connection_id: str,
        scope: OwnerScope,
        error_code: str | None = None,
    ) -> DocumentDraft:
        """Make a staged capture available after its delivery has been accepted."""
        draft = self.get(user_id=user_id, connection_id=connection_id, scope=scope)
        if not draft.source_available:
            draft = self._update(
                user_id,
                draft,
                source_available=True,
                error_code=error_code if error_code is not None else draft.error_code,
            )
        return draft

    def outcome(
        self, *, user_id: str, connection_id: str, replayed: bool, scope: OwnerScope
    ) -> DocumentOutcome:
        draft = self.get(user_id=user_id, connection_id=connection_id, scope=scope)
        batch = self.store.get(user_id=user_id, connection_id=connection_id)
        return DocumentOutcome(
            connection_id, replayed, len(batch.candidates) if batch else 0, draft.status
        )

    def release_queued(
        self, *, user_id: str, connection_id: str, scope: OwnerScope, code: str
    ) -> None:
        """A queued read that could not start waits saved, unread, with its reason.
        One store write checks and releases, so a dispatch that records an
        attempt for this version, or any writer that moves the draft, keeps it."""

        draft = self.get(user_id=user_id, connection_id=connection_id, scope=scope)
        if draft.status == "queued":
            self.store.update(
                user_id=user_id,
                draft=self.revise(draft, status="saved", consent=False, error_code=code),
                expected_version=draft.version,
                unstarted=True,
            )

    def _business_permission(self, scope: OwnerScope, user_id: str) -> dict:
        """The owner's setting for this Business; off when the service has none."""

        if self.business_receipt_consent is None:
            return {"enabled": False, "consent_id": None}
        return self.business_receipt_consent.status(space_id(scope), user_id)

    def _reading_allowed(self, user_id: str, connection_id: str) -> bool:
        """A Personal upload carries its own consent. A Business receipt is read
        only under the owner's current setting, the one it was queued under."""

        row = self.hub.connections.get_any_scope(
            user_id=user_id, connection_id=connection_id
        )
        if space_id(row.scope) is None:
            return True
        draft = self.store.draft(user_id=user_id, connection_id=connection_id)
        return bool(
            draft and draft.reading_allowed(self._business_permission(row.scope, user_id))
        )

    def get_with_read_pending(
        self, *, user_id: str, connection_id: str, scope: OwnerScope
    ) -> tuple[DocumentDraft, bool]:
        connection = self._connection(user_id, connection_id, scope=scope)
        draft = self._stored_draft(connection)
        return draft, draft.read_pending(
            business_permission=self._business_permission(scope, user_id)
            if draft.status == "queued" and space_id(scope) is not None
            else None,
            lease_until=connection.lease_until,
            now=self.hub.clock(),
        )

    def queue(
        self,
        *,
        user_id: str,
        connection_id: str,
        consent: bool,
        scope: OwnerScope,
        expected_version: int | None = None,
    ) -> DocumentOutcome:
        """``expected_version`` queues only the draft its caller chose: one
        that moved since is someone else's, and is left to them."""

        draft = self.get(user_id=user_id, connection_id=connection_id, scope=scope)
        if expected_version is not None and draft.version != expected_version:
            raise DocumentServiceError("document_version_conflict", retryable=True)
        if draft.status == "dismissed":
            raise DocumentServiceError("business_document_deleted")
        if draft.status == "preparing":
            raise DocumentServiceError("document_busy", retryable=True)
        batch = self.store.get(user_id=user_id, connection_id=connection_id)
        if entered_by_owner(batch):
            # Preparing now would read a second purchase from the same receipt.
            raise DocumentServiceError("document_entered_by_owner")
        if batch is None:
            if not consent:
                raise DocumentServiceError("document_extraction_consent_required")
            if not draft.source_available:
                raise DocumentServiceError("document_source_unavailable")
            if space_id(scope) is not None:
                permission = self._business_permission(scope, user_id)
                if not permission["enabled"]:
                    # A click is a fresh action: it is told why nothing was queued.
                    raise DocumentServiceError("business_receipt_reading_off")
                draft = self._update(
                    user_id, draft, business_reading_consent_id=permission["consent_id"]
                )
            self._update(user_id, draft, status="queued", consent=True, error_code=None)
        return self.outcome(
            user_id=user_id,
            connection_id=connection_id,
            replayed=batch is not None,
            scope=scope,
        )

    async def enter(
        self, *, user_id: str, connection_id: str, scope: OwnerScope
    ) -> DocumentOutcome:
        """The owner records this document's one purchase by hand.

        Unread, it saves one purchase observation with nothing read, marked
        entered by the owner, and delivers it to review like extracted
        candidates. Read, the batch stays as read and the same observation is
        delivered beside it; the caller decides that the read settled no
        purchase. The owner's values then become that import's resolution. No
        extractor is called. Repeating it delivers the same observation again,
        so an interrupted entry is finished. A queued or preparing document is
        refused.
        """

        draft = self.get(user_id=user_id, connection_id=connection_id, scope=scope)
        if draft.status == "dismissed":
            raise DocumentServiceError("business_document_deleted")
        if draft.status in ("queued", "preparing"):
            raise DocumentServiceError("document_busy", retryable=True)
        batch = self.store.get(user_id=user_id, connection_id=connection_id)
        if batch is not None and not entered_by_owner(batch):
            purchase = owner_purchase(draft, self.hub.clock())
            self._deliver(user_id, connection_id, (purchase,), scope)
            return self.outcome(
                user_id=user_id, connection_id=connection_id, replayed=False, scope=scope
            )
        if batch is None:
            holder = str(uuid.uuid4())
            repo = self.hub.connections
            if not repo.lease(
                connection_id=connection_id, holder=holder, now=self.hub.clock()
            ):
                raise DocumentServiceError("document_busy", retryable=True)
            try:
                entered = ExtractionBatch(
                    candidates=(owner_purchase(draft, self.hub.clock()),),
                    receipt=ReceiptDetails(),
                    metadata=dict(ENTERED_BY_OWNER),
                )
                if not self.store.save(
                    user_id=user_id,
                    connection_id=connection_id,
                    holder=holder,
                    now=self.hub.clock(),
                    batch=entered,
                ):
                    raise DocumentServiceError("document_lease_lost", retryable=True)
            finally:
                repo.release(connection_id=connection_id, holder=holder)
            # A read saved before the lease was taken is kept by ``save``.
            if not entered_by_owner(
                self.store.get(user_id=user_id, connection_id=connection_id)
            ):
                raise DocumentServiceError("document_already_prepared")
        return await self.resume(
            user_id=user_id, connection_id=connection_id, scope=scope
        )

    async def resume(
        self,
        *,
        user_id: str,
        connection_id: str,
        queued_only: bool = False,
        attempt_id: str | None = None,
        scope: OwnerScope,
    ) -> DocumentOutcome:
        connection = self._connection(user_id, connection_id, scope=scope)
        draft = self.get(user_id=user_id, connection_id=connection_id, scope=scope)
        batch = self.store.get(user_id=user_id, connection_id=connection_id)
        if batch is None and (
            not draft.consent or (queued_only and draft.status != "queued")
        ):
            raise DocumentServiceError("document_preparation_not_queued")
        if draft.status == "dismissed":
            raise DocumentServiceError("business_document_deleted")
        if draft.status == "preparing":
            raise DocumentServiceError("document_busy", retryable=True)
        if batch is None and not self._reading_allowed(user_id, connection_id):
            if draft.status == "queued":
                self._update(user_id, draft, status="saved", consent=False)
            raise DocumentServiceError("document_reading_not_allowed")
        holder = str(uuid.uuid4())
        repo = self.hub.connections
        if not repo.lease(
            connection_id=connection_id, holder=holder, now=self.hub.clock()
        ):
            raise DocumentServiceError("document_busy", retryable=True)
        calls_left = PROVIDER_CALLS_PER_READ
        if attempt_id is not None:
            # Checked under the lease: a reconciler cannot supersede a held lease.
            job = self.store.job(user_id=user_id, connection_id=connection_id)
            if job is not None:
                calls_left = MAX_PROVIDER_CALLS - job.provider_calls
            if (
                job is None
                or job.attempt_id != attempt_id
                or job.draft_version != draft.version
            ):
                repo.release(connection_id=connection_id, holder=holder)
                raise DocumentServiceError("document_attempt_superseded")
        replayed = batch is not None
        from argus.domain.business import analytics as business_analytics

        # Set once a provider call is admitted: only such a read is reported.
        provider_called = False
        # The last call the breaker admitted in this take.
        call: AdmittedCall | None = None

        async def ended(answered: bool) -> None:
            if call is not None:
                await asyncio.to_thread(call.end, self.hub.clock(), answered)

        finishing_held = False
        read_started = read_ms = None
        try:
            business = self._canonical_business(connection_id, scope)
            if business:
                self.business_actions.check_attachment_preparation(
                    user_id=user_id,
                    connection_id=connection_id,
                    scope=scope,
                    holder=holder,
                    attempt_id=attempt_id,
                )
            if batch is None:
                # The claim names the attempt; a flag-off writer names none.
                draft = self._update(
                    user_id,
                    draft,
                    holder=holder,
                    claim=attempt_id,
                    status="preparing",
                    error_code=None,
                )
                content = await asyncio.to_thread(
                    self._read_source, user_id, connection_id
                )
                if hashlib.sha256(content).hexdigest() != draft.sha256:
                    raise DocumentServiceError("document_source_changed")
                rebuilt_image = None
                if draft.media_type in IMAGE_MEDIA_TYPES:
                    try:
                        image = await asyncio.to_thread(
                            self._rebuilt_copy, user_id, draft, ensure=True
                        )
                    except SourceStorageUnavailable:
                        raise DocumentServiceError(
                            "document_storage_unavailable", retryable=True
                        ) from None
                    if image is None:
                        raise DocumentServiceError("document_source_unavailable")
                    rebuilt_image = image[1]
                prepared = await asyncio.to_thread(
                    self.extractor.prepare,
                    content,
                    draft.media_type,
                    rebuilt_image=rebuilt_image,
                )

                async def before_request() -> None:
                    nonlocal provider_called, calls_left, call, draft
                    # Asked again in the same take: the call before timed out.
                    await ended(False)
                    if calls_left <= 0:
                        raise DocumentServiceError("extraction_provider_failed")
                    if not self._reading_allowed(user_id, connection_id):
                        raise DocumentServiceError("document_reading_not_allowed")
                    if business:
                        self.business_actions.check_attachment_preparation(
                            user_id=user_id,
                            connection_id=connection_id,
                            scope=scope,
                            holder=holder,
                            attempt_id=attempt_id,
                        )
                    # Before anything is charged: a held read was never sent.
                    admission = await self._admit()
                    if admission.until is not None:
                        raise held_back(
                            DocumentServiceError(READS_PAUSED),
                            admission.until - self.hub.clock(),
                        )
                    # From here to the end of ``extract`` the call is out.
                    call = AdmittedCall(self.read_breaker, admission)
                    if is_held(draft):
                        draft = await asyncio.to_thread(
                            self._charge_held_read, user_id, draft, holder, attempt_id
                        )
                    elif attempt_id is not None and not self.store.mark_provider_call(
                        user_id=user_id, connection_id=connection_id,
                        attempt_id=attempt_id, holder=holder, now=self.hub.clock(),
                    ):
                        raise DocumentServiceError("document_lease_lost", retryable=True)
                    business_id = space_id(scope)
                    if not is_held(draft) and business_id is not None and self.read_budget is not None:
                        refused = await asyncio.to_thread(
                            self.read_budget.charge, business_id, self.hub.clock()
                        )
                        if refused is not None:
                            raise DocumentServiceError(refused)
                    call.sent = provider_called = True
                    calls_left -= 1

                read_started = time.monotonic()
                # The one place an admitted call ends at the breaker: however
                # ``extract`` returns, the call that is out is told once.
                try:
                    batch = await self.extractor.extract(
                        content=content,
                        filename=draft.filename,
                        media_type=draft.media_type,
                        connection_id=connection_id,
                        observed_at=self.hub.clock(),
                        prepared=prepared,
                        before_request=before_request,
                    )
                except Exception as error:
                    await ended(provider_answered(error))
                    raise
                await ended(True)
                read_ms = _elapsed_ms(read_started)
                batch = clean_extracted_text(batch)
                self._validate(batch, connection_id)
                if not self.store.save(
                    user_id=user_id,
                    connection_id=connection_id,
                    holder=holder,
                    now=self.hub.clock(),
                    batch=batch,
                ):
                    raise DocumentServiceError("document_lease_lost", retryable=True)
            self._validate(batch, connection_id)
            if not entered_by_owner(batch) and not self._reading_allowed(
                user_id, connection_id
            ):
                raise DocumentServiceError("document_reading_not_allowed")
            if not repo.renew(
                connection_id=connection_id, holder=holder, now=self.hub.clock()
            ):
                raise DocumentServiceError("document_lease_lost", retryable=True)
            if is_held(draft):
                if not load_whatsapp_settings().intake_ready:
                    raise DocumentServiceError("document_reading_not_allowed")
                if isinstance(self.store, PostgresDocumentStore):
                    finishing_held = True
                    return self._finish_held_read(connection, draft, batch, holder, replayed)
            draft, attached = self._finish_read(connection, draft, batch, holder, attempt_id, business)
            business_id = space_id(scope)
            if provider_called and business_id is not None:
                business_analytics.document_read(
                    business_id=business_id,
                    user_id=user_id,
                    metadata=batch.metadata,
                    latency_ms=read_ms or 0,
                    issue_code=batch.issues[0].code if batch.issues else None,
                )
                draft_id = getattr(attached, "draft_id", None)
                if draft_id is not None:
                    business_analytics.document_needs_review(
                        business_id=business_id,
                        user_id=user_id,
                        reasons=partial(
                            self.business_actions.review_gaps,
                            user_id=user_id,
                            connection_id=connection_id,
                            scope=scope,
                            draft_id=draft_id,
                        ),
                    )
            return DocumentOutcome(
                connection_id, replayed, len(batch.candidates), draft.status
            )
        except Exception as error:
            from argus.domain.business.authority import ActionError
            from argus.domain.ingestion.documents.models import DocumentExtractionError

            if finishing_held:
                # Its batch is durable and its draft is still recoverable by the sweep.
                raise
            code = (
                error.code
                if isinstance(
                    error, (DocumentServiceError, DocumentExtractionError, ActionError)
                )
                else "document_extraction_failed"
            )
            if code in {
                "unreadable_document",
                "not_a_receipt",
                "receipt_requires_review",
            }:
                logger.warning(
                    "document_preparation_refused connection_id={} code={}",
                    connection_id,
                    code,
                )
            failure = classify(error)
            requeue = next_take(
                failure,
                attempt_id,
                partial(self.store.job, user_id=user_id, connection_id=connection_id),
            )
            if failure.kind == "config":
                alert_config(connection_id, code, error)
            try:
                withdrawn = code == "document_reading_not_allowed"
                # A withdrawn permission or a spent budget is not a failure:
                # the receipt waits saved and unread, the budget with its reason.
                unread = withdrawn or code in READ_BUDGET_REFUSALS
                if requeue is not None:
                    # The draft stays claimed and shows as being read: the
                    # puller writes its next take once the lease is released.
                    error.requeue = requeue
                else:
                    if not unread:
                        logger.warning(
                            "document_read_failed connection_id={} code={} kind={}",
                            *(connection_id, code, failure.kind),
                        )
                    if draft.source_available:
                        self._update(
                            user_id,
                            draft,
                            holder=holder,
                            status="saved" if unread else "needs_attention",
                            error_code=None if withdrawn else code,
                            **({"consent": False} if unread else {}),
                            source_available=code != "document_source_unavailable",
                        )
                    if is_held(draft) and not withdrawn and load_whatsapp_settings().intake_ready:
                        if isinstance(self.store, PostgresDocumentStore):
                            with PostgresHeldFiles(self.store).pool.connection() as db:
                                db.execute(
                                    "update public.whatsapp_held_files set reason=%s where user_id=%s"
                                    " and connection_id=%s and state='held'",
                                    ("held_read_cap" if code == HELD_READ_REFUSAL else "read_failed",
                                     user_id, connection_id),
                                )
                    repo.record_failure(
                        connection_id=connection_id,
                        holder=holder,
                        code=code,
                        status="error",
                        now=self.hub.clock(),
                    )
            except (ConnectionNotFound, DocumentServiceError):
                pass
            business_id = space_id(scope)
            if provider_called and business_id is not None:
                business_analytics.document_read(
                    business_id=business_id,
                    user_id=user_id,
                    metadata=getattr(error, "metadata", None)
                    or (batch.metadata if batch is not None else {}),
                    latency_ms=read_ms if read_ms is not None else _elapsed_ms(read_started),
                    code=code,
                )
            raise
        finally:
            repo.release(connection_id=connection_id, holder=holder)

    def _finish_read(
        self,
        connection: SourceConnection,
        draft: DocumentDraft,
        batch: ExtractionBatch,
        holder: str,
        attempt_id: str | None,
        business: bool,
    ) -> tuple[DocumentDraft, Applied | None]:
        user_id, connection_id, scope = (
            connection.user_id,
            connection.id,
            connection.scope,
        )
        repo = self.hub.connections
        attached = None
        if business:
            from argus.domain.business.contracts.actions import canonical_input_hash

            attached = self.business_actions.prepare_attachment(
                expected_batch_sha256=canonical_input_hash(batch),
                user_id=user_id,
                connection_id=connection_id,
                scope=scope,
                holder=holder,
                attempt_id=attempt_id,
            )
        elif batch.candidates and not is_held(draft):
            self._deliver(user_id, connection_id, batch.candidates, scope)
            if space_id(scope) is not None:
                self._flag_business_duplicates(user_id, connection_id, scope)
        if draft.source_available:
            draft = self._update(
                user_id,
                draft,
                holder=holder,
                status="needs_attention" if batch.issues else "review_ready",
                error_code=batch.issues[0].code if batch.issues else None,
            )
        if attached is not None:
            self.business_actions.complete_attachment_read(
                user_id=user_id,
                connection_id=connection_id,
                scope=scope,
                holder=holder,
                attempt_id=attempt_id,
                document_version=draft.version,
                prepared=attached,
            )
        if not repo.record_success(
            connection_id=connection_id,
            holder=holder,
            expected_cursor=connection.cursor,
            cursor="delivered",
            now=self.hub.clock(),
        ):
            raise DocumentServiceError("document_lease_lost", retryable=True)
        return draft, attached

    def _charge_held_read(
        self, user_id: str, draft: DocumentDraft, holder: str, attempt_id: str | None
    ) -> DocumentDraft:
        from argus.domain.ingestion.whatsapp.held import charge_read

        def charge(store: DocumentStore, held_id: str | None = None) -> DocumentDraft:
            charged_at = self.hub.clock()
            if attempt_id is not None and not store.mark_provider_call(
                user_id=user_id,
                connection_id=draft.connection_id,
                attempt_id=attempt_id,
                holder=holder,
                now=charged_at,
            ):
                raise DocumentServiceError("document_lease_lost", retryable=True)
            refused = charge_read(
                store, user_id, draft.connection_id, charged_at, self.read_budget
            )
            if refused is not None:
                raise DocumentServiceError(refused)
            marked = draft.model_copy(
                update={
                    "resolution": {
                        **draft.resolution,
                        "held_read_charged_at": charged_at.isoformat(),
                        **({"held_read_id": held_id} if held_id else {}),
                    }
                }
            )
            # The job still owns this version. Replacing its attempt after a
            # crash must not replace the day its provider call actually cost.
            if not store.update(
                user_id=user_id,
                draft=marked,
                holder=holder,
                expected_version=draft.version,
            ):
                raise DocumentServiceError("document_lease_lost", retryable=True)
            return marked

        if not load_whatsapp_settings().intake_ready:
            raise DocumentServiceError("document_reading_not_allowed")
        if not isinstance(self.store, PostgresDocumentStore):
            return charge(self.store)
        from argus.domain.ingestion.whatsapp.receipt_consent import receipt_consent_store
        from argus.domain.ingestion.whatsapp.store_postgres import PostgresWhatsAppStore
        from argus.domain.postgres_connection import BorrowedConnection

        with PostgresHeldFiles(self.store).pool.connection() as db, db.transaction():
            original = db.execute(
                "select sender_link_id::text,id::text from public.whatsapp_held_files where user_id=%s"
                " and connection_id=%s and state='held' order by held_at,id limit 1",
                (user_id, draft.connection_id),
            ).fetchone()
            if original is not None:
                pool = BorrowedConnection(db)
                active = PostgresWhatsAppStore(pool).destination_link(
                    destination_owner_id=user_id
                )
                consent = (
                    receipt_consent_store(pool).status(uuid.UUID(user_id))
                    if active is not None and active.id == original[0]
                    else None
                )
                if consent and consent["enabled"]:
                    return charge(self.on_connection(db).store, original[1])
                reason = (
                    "no_eligible_business"
                    if consent and consent["reason"] == "whatsapp_setup_required"
                    else "read_failed"
                )
                db.execute(
                    "update public.whatsapp_held_files set reason=%s where user_id=%s"
                    " and connection_id=%s and state='held'",
                    (reason, user_id, draft.connection_id),
                )
        raise DocumentServiceError("document_reading_not_allowed")

    def _finish_held_read(
        self,
        connection: SourceConnection,
        draft: DocumentDraft,
        batch: ExtractionBatch,
        holder: str,
        replayed: bool,
    ) -> DocumentOutcome:
        files = PostgresHeldFiles(self.store)
        user_id = connection.user_id
        with files.pool.connection() as db, db.transaction():
            record = db.execute(
                "select id::text from public.whatsapp_held_files where user_id=%s"
                " and connection_id=%s and state='held' order by held_at,id limit 1",
                (user_id, connection.id),
            ).fetchone()
            if record is None:
                raise DocumentServiceError("held_file_unavailable")
            scoped = self.on_connection(db)
            with PostgresHeldFiles(scoped.store).assignment(user_id, record[0]) as (
                _,
                row,
            ):
                if row is None or row.state != "held":
                    raise DocumentServiceError("held_file_unavailable")
                draft, _ = scoped._finish_read(
                    connection, draft, batch, holder, None, False
                )
                scoped.hub.connections.release(connection_id=connection.id, holder=holder)
                routed = scoped._route_held(db, row, batch, new_delivery=False)
        if routed and not routed[1].replayed:
            self._report_whatsapp_arrival(draft, user_id, routed[0])
        return DocumentOutcome(
            connection.id, replayed, len(batch.candidates), draft.status
        )

    @staticmethod
    def _resent_connection(user_id: str, message_key: bytes) -> str:
        return str(uuid.uuid5(uuid.UUID(user_id), message_key.hex()))

    def discard_unpublished_held_copy(
        self, *, user_id: str, message_key: bytes, digest: str
    ) -> None:
        """Clean a scoped copy after a failed publication, including an uncertain commit."""
        from argus.domain.ingestion.documents.store_postgres import lock_sources

        target = self._resent_connection(user_id, message_key)
        path = (
            connection_prefix(user_id=user_id, connection_id=target)
            + bytes.fromhex(digest).hex()
        )
        with PostgresHeldFiles(self.store).pool.connection() as db, db.transaction():
            lock_sources(db, user_id)
            if not db.execute(
                "select 1 from public.financial_document_extractions where user_id=%s and source_path=%s",
                (user_id, path),
            ).fetchone():
                self.store.objects.remove(path)

    def reopen_held_delivery(
        self,
        *,
        user_id: str,
        previous_id: str,
        message_key: bytes,
        content: bytes,
        filename: str,
        media_type: str,
        source_text: str | None,
    ) -> DocumentOutcome:
        """Stage a resend independently of the retained receipt's expiry and original inbound."""
        from psycopg.types.json import Jsonb

        validate_source(content, media_type)
        digest = hashlib.sha256(content).hexdigest()
        files = PostgresHeldFiles(self.store)
        with files.assignment(user_id, previous_id) as (db, previous):
            if previous is None or previous.state != "assigned":
                raise DocumentServiceError("held_file_unavailable")
            scoped = self.on_connection(db)
            original = scoped.get(
                user_id=user_id, connection_id=previous.connection_id, scope=PERSONAL
            )
            if not is_held(original) or original.sha256 != digest:
                raise DocumentServiceError("document_source_changed")
            batch = scoped.store.get(
                user_id=user_id, connection_id=previous.connection_id
            )
            target = self._resent_connection(user_id, message_key)
            namespace = f"{MARK}:{message_key.hex()}"
            try:
                scoped.hub.connections.create(
                    connection_id=target,
                    user_id=user_id,
                    source=self.source,
                    external_ref=document_ref(user_id, PERSONAL, digest, namespace),
                    label="Document",
                    now=self.hub.clock(),
                    scope=PERSONAL,
                )
            except DuplicateConnection as duplicate:
                if duplicate.elsewhere or duplicate.existing_id != target:
                    raise DocumentServiceError("document_source_changed") from None
                return scoped.outcome(
                    user_id=user_id, connection_id=target, scope=PERSONAL, replayed=True
                )
            # A repeat owns the new delivery's caption and filename. Only the
            # private sender's same-byte read and sanitized image may carry over.
            provenance = {
                MARK: True,
                "held_image_source": original.resolution.get(
                    "held_image_source", original.connection_id
                ),
            }
            status: DraftStatus = "saved"
            if batch is not None:
                self._validate(batch, original.connection_id)
                provenance["held_read_id"] = original.resolution.get(
                    "held_read_id", previous_id
                )
                batch = self._rebind_batch(
                    batch,
                    target,
                    filename=stored_filename(filename),
                    media_type=media_type,
                )
                status = "needs_attention" if batch.issues else "review_ready"
            now = self.hub.clock()
            draft = DocumentDraft(
                connection_id=target,
                filename=stored_filename(filename),
                media_type=media_type,
                sha256=digest,
                size_bytes=len(content),
                source_text=source_text,
                resolution=provenance,
                created_at=now,
                updated_at=now,
                status=status,
                error_code=batch.issues[0].code if batch and batch.issues else None,
            )
            path = connection_prefix(user_id=user_id, connection_id=target) + digest
            db.execute(
                "insert into public.financial_document_extractions(connection_id,user_id,draft,batch,"
                "created_at,source_bucket,source_path,source_media_type,source_size_bytes,source_sha256)"
                " values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    target,
                    user_id,
                    Jsonb(draft.model_dump(mode="json")),
                    Jsonb(batch.model_dump(mode="json")) if batch else None,
                    now,
                    scoped.store.objects.bucket,
                    path,
                    media_type,
                    len(content),
                    digest,
                ),
            )
            try:
                scoped.store.objects.put(path, content, media_type)
            except Exception:
                # The scoped path belongs exclusively to the rolled-back draft.
                scoped.store.objects.remove(path)
                raise
            return DocumentOutcome(
                target, False, len(batch.candidates) if batch else 0, draft.status
            )

    @staticmethod
    def _rebind_batch(
        batch: ExtractionBatch,
        target: str,
        *,
        filename: str | None = None,
        media_type: str | None = None,
    ) -> ExtractionBatch:
        candidates = []
        for candidate in batch.candidates:
            changes = {
                "source": candidate.source.model_copy(update={"connection_id": target})
            }
            if filename is not None:
                changes["attachments"] = tuple(
                    attachment.model_copy(
                        update={"filename": filename, "media_type": media_type}
                    )
                    for attachment in candidate.attachments
                )
            candidates.append(candidate.model_copy(update=changes))
        return batch.model_copy(update={"candidates": tuple(candidates)})

    def route_saved_hold(
        self, *, user_id: str, held_id: str
    ) -> tuple[str, DocumentOutcome] | None:
        """Route a new delivery of retained bytes inside its publication transaction."""
        if not load_whatsapp_settings().intake_ready or not isinstance(
            self.store, PostgresDocumentStore
        ):
            raise DocumentServiceError("whatsapp_unavailable")
        with PostgresHeldFiles(self.store).assignment(user_id, held_id) as (db, row):
            if row is None or row.state != "held":
                return None
            scoped = self.on_connection(db)
            batch = scoped.store.get(user_id=user_id, connection_id=row.connection_id)
            return scoped._route_held(db, row, batch, new_delivery=True)

    def _route_held(
        self,
        db: Connection,
        row: HeldFile,
        batch: ExtractionBatch | None,
        *,
        new_delivery: bool,
    ) -> tuple[str, DocumentOutcome] | None:
        from argus.domain.business.document_type import buyer_tax_id, issuer_tax_id
        from argus.domain.ingestion.whatsapp.routing import route_document
        from argus.domain.ingestion.whatsapp.senders import postgres_senders

        grants = {
            g.space_id: g for g in postgres_senders(db).eligible_businesses(row.user_id)
        }
        if new_delivery and len(grants) == 1:
            route = BusinessSpace(next(iter(grants)))
        else:
            # A file held for a read must still match a fiscal party if another
            # grant disappears while the provider is reading.
            identities = dict(
                db.execute(
                    "select id::text,business_rnc from public.spaces where id=any(%s::uuid[])",
                    (list(grants),),
                ).fetchall()
            )
            receipt = batch.receipt if batch else None
            qr = batch.dgii_qr if batch else None
            route = route_document(
                identities,
                issuer=issuer_tax_id(qr, receipt.rnc if receipt else None),
                buyer=buyer_tax_id(qr, receipt.buyer_rnc if receipt else None),
            )
        if isinstance(route, BusinessSpace):
            assigned, _ = self._adopt_locked(db, row, grants[route.space_id])
            return route.space_id, assigned
        db.execute(
            "update public.whatsapp_held_files set reason=%s where user_id=%s"
            " and connection_id=%s and state='held'",
            (route, row.user_id, row.connection_id),
        )
        return None

    def adopt(self, *, user_id: str, held_id: str, business_id: str) -> DocumentOutcome:
        """Assign a sender's retained file under their current Business grant."""
        from argus.domain.ingestion.whatsapp.senders import postgres_senders

        if not load_whatsapp_settings().intake_ready or not isinstance(
            self.store, PostgresDocumentStore
        ):
            raise DocumentServiceError("whatsapp_unavailable")
        with PostgresHeldFiles(self.store).assignment(user_id, held_id) as (db, row):
            grants = postgres_senders(db).eligible_businesses(user_id)
            grant = next((g for g in grants if g.space_id == business_id), None)
            if grant is None:
                raise DocumentServiceError("business_permission_denied")
            if row is None or row.state == "expired":
                raise DocumentServiceError("held_file_unavailable")
            scoped = self.on_connection(db)
            if row.state == "assigned":
                if row.assigned_space_id != business_id:
                    raise DocumentServiceError("held_file_already_assigned")
                return scoped.outcome(
                    user_id=grant.owner_id,
                    connection_id=row.assigned_connection_id,
                    scope=BusinessSpace(business_id),
                    replayed=True,
                )
            result, draft = scoped._adopt_locked(db, row, grant)
        if not result.replayed:
            self._report_whatsapp_arrival(draft, user_id, business_id)
        return result

    @staticmethod
    def _report_whatsapp_arrival(
        draft: DocumentDraft, person: str, business: str
    ) -> None:
        from argus.domain.business.analytics import document_received

        document_received(
            channel="whatsapp",
            business_id=business,
            user_id=person,
            media_type=draft.media_type,
            size_bytes=draft.size_bytes,
        )

    def _adopt_locked(
        self, db: Connection, row: HeldFile, grant: GrantedSpace
    ) -> tuple[DocumentOutcome, DocumentDraft]:
        from argus.domain.business.transactions import lock_owner
        from argus.domain.ingestion.documents.objects import source_path
        from argus.domain.ingestion.documents.store_postgres import lock_sources

        user, original = row.user_id, row.connection_id
        connection = self._connection(user, original, scope=PERSONAL)
        now = self.hub.clock()
        if lease_live(connection, now):
            raise DocumentServiceError("document_busy", retryable=True)
        draft = self._stored_draft(connection)
        batch = self.store.get(user_id=user, connection_id=original)
        files = PostgresHeldFiles(self.store)
        scope = BusinessSpace(grant.space_id)
        lock_owner(db, grant.owner_id)
        lock_sources(db, grant.owner_id)
        source = self._read_source(user, original)
        rebuilt = self._rebuilt_copy(user, draft)
        paths = [source_path(user_id=grant.owner_id, sha256=draft.sha256)]
        if rebuilt:
            paths.append(
                source_path(user_id=grant.owner_id, sha256=draft.sha256, kind="rebuilt")
            )
        new_paths = [path for path in paths if self.store.objects.get(path) is None]
        try:
            with db.transaction():
                if batch is not None:
                    self._settle_held_charge(db, connection, draft, grant.space_id, now)
                destination = self.for_sender(user, scope)
                result = destination._receive_held(grant, draft, source, rebuilt, batch)
                # Older captures can share one Personal connection. The assignment
                # lock settles all its original messages with the same single read.
                siblings = db.execute(
                    "select id::text,provider_message_key,sender_link_id from public.whatsapp_held_files"
                    " where user_id=%s and connection_id=%s and state='held' for update",
                    (user, original),
                ).fetchall()
                for held_id, message, link in siblings:
                    if not files.settle(
                        user_id=user,
                        held_id=held_id,
                        business_id=scope.space_id,
                        connection_id=result.connection_id,
                        now=now,
                    ):
                        raise DocumentServiceError("held_file_unavailable")
                    moved = db.execute(
                        "update public.whatsapp_inbound_messages set connection_id=%s"
                        " where provider_message_key=%s and sender_link_id=%s and destination_owner_id=%s"
                        " and connection_id=%s and status='captured'",
                        (result.connection_id, message, link, user, original),
                    )
                    if moved.rowcount != 1:
                        raise DocumentServiceError("held_message_unavailable")
                if batch is None:
                    self._update(
                        user, draft, status="saved", consent=False, error_code=None
                    )
        except Exception:
            # The SQL savepoint rolled back. Only remove unpublished copies while
            # still holding the custodian's object lock. Other receipts can share them.
            for path in new_paths:
                referenced = db.execute(
                    "select 1 from public.financial_document_extractions where source_path=%s"
                    " or rebuilt_path=%s union all select 1 from argus_private.business_custody_objects"
                    " where source_path=%s or destination_path=%s limit 1",
                    (path,) * 4,
                ).fetchone()
                if not referenced:
                    self.store.objects.remove(path)
            raise
        return result, draft

    def _settle_held_charge(
        self,
        db: Connection,
        connection: SourceConnection,
        draft: DocumentDraft,
        business_id: str,
        now: datetime,
    ) -> None:
        origin = draft.resolution.get("held_read_id")
        if origin:
            row = db.execute(
                "select h.state from public.whatsapp_held_files h"
                " join public.financial_source_connections c on c.id=h.connection_id and c.user_id=h.user_id"
                " join public.financial_document_extractions d on d.connection_id=c.id and d.user_id=c.user_id"
                " where h.id=%s and h.user_id=%s and c.owner_space_id is null and d.draft->>'sha256'=%s",
                (origin, connection.user_id, draft.sha256),
            ).fetchone()
            if row is None or row[0] == "expired":
                raise DocumentServiceError("held_read_charge_missing")
            if row[0] == "assigned":
                return
        instant = self._held_charge_time(connection, draft)
        if instant is None:
            raise DocumentServiceError("held_read_charge_missing")
        if not origin:
            # Older charge records have a time but no held-row ID. A previous
            # assignment after that charge has already settled it under the lock.
            if db.execute(
                "select 1 from public.whatsapp_held_files where user_id=%s and connection_id=%s"
                " and state='assigned' and held_at<=%s and settled_at>=%s",
                (connection.user_id, connection.id, instant, instant),
            ).fetchone():
                return
        transfer = (
            PostgresHeldFiles(self.store)
            .budget(self.read_budget)
            .hand_over(
                connection.user_id,
                business_id,
                now,
                charged_at=instant,
            )
        )
        if transfer == "no_held_read":
            raise DocumentServiceError("held_read_charge_missing")

    def _held_charge_time(
        self, connection: SourceConnection, draft: DocumentDraft
    ) -> datetime | None:
        charged_at = draft.resolution.get("held_read_charged_at")
        if isinstance(charged_at, str):
            return datetime.fromisoformat(charged_at)
        # A pre-marker read proves its debit day only if the entire call
        # fits within one billing day.
        from argus.domain.ingestion.email_intake.budget import business_day

        job = self.store.job(user_id=connection.user_id, connection_id=connection.id)
        admission = job.provider_call_started_at if job else None
        end = connection.last_success_at
        if (
            admission
            and end
            and admission <= end
            and business_day(admission) == business_day(end)
        ):
            return admission
        return None

    def _receive_held(
        self,
        grant: GrantedSpace,
        original: DocumentDraft,
        source: bytes,
        rebuilt: tuple[str, bytes] | None,
        batch: ExtractionBatch | None,
    ) -> DocumentOutcome:
        from argus.api.documents import record_dispatch_preparation

        scope, owner = BusinessSpace(grant.space_id), grant.owner_id
        permission = self._business_permission(scope, owner)
        if not permission["enabled"]:
            raise DocumentServiceError("business_permission_denied")
        result = self._upload(
            user_id=owner,
            content=source,
            filename=original.filename,
            media_type=original.media_type,
            consent=True,
            consent_id=permission["consent_id"],
            proposal=None,
            source_text=original.source_text,
            scope=scope,
            on_capture=None,
        )
        target = result.connection_id
        if result.replayed and result.status in (
            "review_ready",
            "needs_attention",
            "dismissed",
        ):
            if (
                self.store.get(user_id=owner, connection_id=target) is not None
                or result.status == "dismissed"
            ):
                return result
        if rebuilt and not self.store.save_rebuilt(
            user_id=owner, connection_id=target, media_type=rebuilt[0], content=rebuilt[1]
        ):
            raise DocumentServiceError("document_source_unavailable")
        if result.replayed and result.status != "queued":
            self.queue(user_id=owner, connection_id=target, scope=scope, consent=True)
        record_dispatch_preparation(self, owner, target, scope=scope)
        if batch is None:
            return self.outcome(
                user_id=owner, connection_id=target, scope=scope, replayed=result.replayed
            )
        rebound = self._rebind_batch(batch, target)
        connection = self._connection(owner, target, scope=scope)
        holder = str(uuid.uuid4())
        if not self.hub.connections.lease(
            connection_id=target, holder=holder, now=self.hub.clock()
        ):
            raise DocumentServiceError("document_busy", retryable=True)
        if not self.store.save(
            user_id=owner,
            connection_id=target,
            holder=holder,
            now=self.hub.clock(),
            batch=rebound,
        ):
            raise DocumentServiceError("document_lease_lost", retryable=True)
        job = self.store.job(user_id=owner, connection_id=target)
        draft, _ = self._finish_read(
            connection,
            self._stored_draft(connection),
            rebound,
            holder,
            job.attempt_id,
            True,
        )
        self.hub.connections.release(connection_id=target, holder=holder)
        return DocumentOutcome(
            target, result.replayed, len(rebound.candidates), draft.status
        )

    async def _admit(self) -> Admission:
        return (
            await asyncio.to_thread(
                ask_breaker, self.read_breaker, "admit", self.hub.clock()
            )
            or Admission()
        )

    def _canonical_business(self, connection_id: str, scope: OwnerScope) -> bool:
        """A Business receipt takes the canonical bridge when it is wired.

        Without a pool, the legacy import path keeps the receipt and the
        fallback is logged; with a pool, a missing bridge fails closed."""

        if space_id(scope) is None:
            return False
        if self.business_actions is not None:
            return True
        if self.business_preparation_required:
            raise DocumentServiceError("business_preparation_unavailable")
        logger.warning(
            "business_legacy_delivery",
            connection_id=connection_id,
            space_id=space_id(scope),
        )
        return False

    def _deliver(
        self,
        user_id: str,
        connection_id: str,
        candidates: tuple[ImportCandidate, ...],
        scope: OwnerScope,
    ) -> None:
        if self.hub.sink is None:
            raise DocumentServiceError("document_delivery_failed", retryable=True)
        try:
            result = self.hub.sink.submit(
                user_id=user_id,
                connection_id=connection_id,
                candidates=candidates,
                scope=scope,
            )
        except Exception:
            raise DocumentServiceError(
                "document_delivery_failed", retryable=True
            ) from None
        if result.ignored:
            raise DocumentServiceError("document_disconnected")

    def _flag_business_duplicates(
        self, user_id: str, connection_id: str, scope: OwnerScope
    ) -> None:
        """A Business receipt delivered without the bridge still gets the
        duplicate mark on its event, from the same read-facts rule."""

        from argus.domain.business.duplicates import (
            events_of_connection,
            flag_receipt_duplicates,
        )
        from argus.domain.ingestion.reconcile.service import ReconciliationService

        if not isinstance(self.hub.sink, ReconciliationService):
            # Only the real import store holds the events to compare.
            return
        with self.hub.sink.store.transaction(user_id, scope=scope) as tx:
            for event in events_of_connection(tx, connection_id):
                flag_receipt_duplicates(tx, event.id)

    @staticmethod
    def _validate(batch: ExtractionBatch, connection_id: str) -> None:
        keys = set()
        for candidate in batch.candidates:
            if (
                candidate.source.source != "statement"
                or candidate.source.connection_id != connection_id
                or candidate.status == "removed"
                or candidate.source.replaces_external_id is not None
                or candidate.key in keys
            ):
                raise DocumentServiceError("document_invalid_extraction")
            keys.add(candidate.key)


def _elapsed_ms(started: float | None) -> int:
    return 0 if started is None else int((time.monotonic() - started) * 1000)
