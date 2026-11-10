"""Capture first; preparation feeds reconciliation without financial writes."""

from __future__ import annotations

import asyncio
import hashlib
import time
import unicodedata
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from typing import TYPE_CHECKING, Protocol

from loguru import logger

from argus.domain.business.document_type import DocumentType
from argus.domain.business.read_budget import READ_BUDGET_REFUSALS
from argus.domain.ingestion.connections import (
    LIVE,
    ConnectionNotFound,
    DuplicateConnection,
    SourceConnection,
)
from argus.domain.ingestion.contract import ImportCandidate, SourceKind, SourceRef
from argus.domain.ingestion.documents.models import (
    DocumentDraft,
    DraftProposal,
    DraftStatus,
    ExtractionBatch,
    ReceiptDetails,
)
from argus.domain.ingestion.documents.objects import SourceStorageUnavailable
from argus.domain.ingestion.documents.preparation import PreparedDocument, validate_source
from argus.domain.ingestion.documents.rebuilt import ensure_rebuilt_image
from argus.domain.ingestion.documents.storage_text import clean_extracted_text
from argus.domain.ingestion.documents.store import (
    CaptureHook,
    DocumentStore,
    download_source,
)
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.owner_scope import OwnerScope, space_id

if TYPE_CHECKING:
    from argus.domain.business.actions import BusinessActions

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


def document_ref(user_id: str, scope: OwnerScope, digest: str) -> str:
    """The connection reference for one file in one scope.

    References are globally unique, so the same bytes uploaded in Personal and
    in Business must differ. The Personal form is the original one, unchanged.
    """

    space = space_id(scope)
    owner = user_id if space is None else f"{user_id}:{space}"
    return hashlib.sha256(f"{owner}:{digest}".encode()).hexdigest()


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
        connection = self._connection(user_id, connection_id, scope=scope)
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

    def source_bytes(
        self, *, user_id: str, connection_id: str, scope: OwnerScope
    ) -> bytes:
        """A draft whose stored object is gone says so (``source_available``
        false) instead of promising a source that cannot be read."""

        self._connection(user_id, connection_id, scope=scope)
        try:
            try:
                ensure_rebuilt_image(
                    store=self.store, user_id=user_id, connection_id=connection_id
                )
                self._connection(user_id, connection_id, scope=scope)
                source = download_source(
                    self.store, user_id=user_id, connection_id=connection_id
                )
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
        if version != draft.version or draft.status == "preparing":
            raise DocumentServiceError("document_version_conflict", retryable=True)
        return self._update(user_id, draft, proposal=proposal)

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
    ) -> DocumentOutcome:
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
    ) -> DocumentOutcome:
        validate_source(content, media_type)
        digest = hashlib.sha256(content).hexdigest()
        external_ref = document_ref(user_id, scope, digest)
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
        draft = DocumentDraft(
            connection_id=connection.id,
            filename=stored_filename(filename),
            media_type=media_type,
            proposal=proposal or DraftProposal(),
            sha256=digest,
            size_bytes=len(content),
            consent=consent,
            business_reading_consent_id=consent_id,
            source_text=source_text,
            document_type=document_type,
            status="queued" if consent else "saved",
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
        """A queued read that could not start waits saved, unread, with its reason."""

        draft = self.get(user_id=user_id, connection_id=connection_id, scope=scope)
        if draft.status == "queued":
            self._update(user_id, draft, status="saved", consent=False, error_code=code)

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
        business = space_id(row.scope)
        if business is None:
            return True
        if self.business_receipt_consent is None:
            return False
        draft = self.store.draft(user_id=user_id, connection_id=connection_id)
        return bool(
            draft
            and draft.business_reading_consent_id
            and self.business_receipt_consent.enabled(
                business, user_id, draft.business_reading_consent_id
            )
        )

    def read_pending(
        self, user_id: str, connection_id: str, draft: DocumentDraft
    ) -> bool:
        """A read will happen: one is in flight, or the document is queued with
        consent and the owner's reading is allowed right now. A queued document
        whose owner switched reading off waits for a person, not for a read."""

        if draft.status == "preparing":
            return True
        return (
            draft.status == "queued"
            and draft.consent
            and self._reading_allowed(user_id, connection_id)
        )

    def queue(
        self, *, user_id: str, connection_id: str, consent: bool, scope: OwnerScope
    ) -> DocumentOutcome:
        draft = self.get(user_id=user_id, connection_id=connection_id, scope=scope)
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
        if attempt_id is not None:
            # Checked under the lease: a reconciler cannot supersede a held lease.
            job = self.store.job(user_id=user_id, connection_id=connection_id)
            if (
                job is None
                or job.attempt_id != attempt_id
                or job.draft_version != draft.version
            ):
                repo.release(connection_id=connection_id, holder=holder)
                raise DocumentServiceError("document_attempt_superseded")
        replayed = batch is not None
        from argus.domain.business import analytics as business_analytics
        from argus.domain.business.actions.mutations import _read_refusal

        if batch is not None and _read_refusal(batch) == "receipt_requires_review":
            # The same saved batch refuses again. Only a new read can finish it.
            batch = None
            replayed = False
        # Set once a provider call is admitted: only such a read is reported.
        provider_called = False
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
                if draft.media_type in ("image/png", "image/jpeg"):
                    try:
                        await asyncio.to_thread(
                            ensure_rebuilt_image,
                            store=self.store,
                            user_id=user_id,
                            connection_id=connection_id,
                        )
                        image = await asyncio.to_thread(
                            self.store.rebuilt,
                            user_id=user_id,
                            connection_id=connection_id,
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
                    nonlocal provider_called
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
                    if attempt_id is not None and not self.store.mark_provider_call(
                        user_id=user_id,
                        connection_id=connection_id,
                        attempt_id=attempt_id,
                        holder=holder,
                        now=self.hub.clock(),
                    ):
                        raise DocumentServiceError("document_lease_lost", retryable=True)
                    business_id = space_id(scope)
                    if business_id is not None and self.read_budget is not None:
                        refused = await asyncio.to_thread(
                            self.read_budget.charge, business_id, self.hub.clock()
                        )
                        if refused is not None:
                            raise DocumentServiceError(refused)
                    provider_called = True

                read_started = time.monotonic()
                batch = await self.extractor.extract(
                    content=content,
                    filename=draft.filename,
                    media_type=draft.media_type,
                    connection_id=connection_id,
                    observed_at=self.hub.clock(),
                    prepared=prepared,
                    before_request=before_request,
                )
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
            elif batch.candidates:
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
            if not repo.record_success(
                connection_id=connection_id,
                holder=holder,
                expected_cursor=connection.cursor,
                cursor="delivered",
                now=self.hub.clock(),
            ):
                raise DocumentServiceError("document_lease_lost", retryable=True)
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
            try:
                withdrawn = code == "document_reading_not_allowed"
                # A withdrawn permission or a spent budget is not a failure:
                # the receipt waits saved and unread, the budget with its reason.
                unread = withdrawn or code in READ_BUDGET_REFUSALS
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
