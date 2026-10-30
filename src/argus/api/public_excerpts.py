"""Owner-side service for public evidence receipts.

Owner candidate and preview reads resolve private sources through one selection
service; creation rechecks and freezes that exact public document. Public readers
hold only a snapshot reader and never resolve source records.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Protocol

from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from argus.api import state as api_state
from argus.api.public_excerpt_schemas import (
    PublicExcerptSnapshot,
    PublicExcerptView,
)
from argus.api.schemas import Conversation, EvidenceArtifact, User
from argus.domain.public_excerpts import (
    PublicExcerptSourceError,
    revoked_public_view,
    snapshot_public_view,
)
from argus.domain.supabase_public_excerpts import DEFAULT_OWNER_PAGE_SIZE

_TRUE_VALUES = {"1", "true", "yes", "on"}

# Every path this lane adds, so the flag gate can recognise them before routing.
_RECEIPT_EXACT_PATHS = frozenset(
    {"/api/v1/public-excerpts", "/api/v1/public/receipt-funnel"}
)
_RECEIPT_PATH_PREFIXES = (
    "/api/v1/public-excerpts/",
    "/api/v1/public/receipts/",
)

RECEIPT_CREATE_LIMIT = 10
RECEIPT_CREATE_WINDOW_SECONDS = 3600
RECEIPT_CREATE_DAILY_LIMIT = 30
RECEIPT_CREATE_DAILY_WINDOW_SECONDS = 86_400


class EvidenceReceiptDisabledError(RuntimeError):
    """Sharing is behind a default-off flag and this deployment has it off."""


class EvidenceReceiptSourceMissingError(LookupError):
    """The artifact is absent, not owned, or its source was deleted.

    Deliberately the same error for all three. A stale tab sharing a result whose
    chat was deleted should hear that the result is not available, not learn which
    of those reasons applied.
    """


# The database refuses an insert whose source is gone; these are its signals.
_SOURCE_REFUSED_MARKERS = (
    "public_excerpt_source_deleted",
    "public_excerpt_source_missing",
)


def _is_source_refusal(error: BaseException) -> bool:
    text = str(error).lower()
    return any(marker in text for marker in _SOURCE_REFUSED_MARKERS)


def evidence_receipt_sharing_enabled() -> bool:
    """Default off. Landing this lane does not turn sharing on."""
    raw_value = os.getenv("CUADRAO_EVIDENCE_RECEIPT_SHARING_ENABLED", "")
    return raw_value.strip().lower() in _TRUE_VALUES


def require_evidence_receipt_sharing_enabled() -> None:
    """While sharing is off, these paths answer exactly as if they did not exist.

    Raising Starlette's base ``HTTPException`` rather than Argus's problem helper
    is deliberate: it is the same exception an unmatched route raises, so the
    response body is produced by the same handler and is byte-identical to a
    deployment without this lane. A distinctive problem body would advertise that
    receipt code is deployed.

    This is the in-route backstop. The gate that actually holds is
    :class:`EvidenceReceiptFlagGateMiddleware`, because a check inside the route
    runs too late.
    """
    if evidence_receipt_sharing_enabled():
        return
    raise StarletteHTTPException(status_code=404, detail="Not Found")


def _is_receipt_path(path: str) -> bool:
    path = path.rstrip("/")
    if path in _RECEIPT_EXACT_PATHS:
        return True
    if any(path.startswith(prefix) for prefix in _RECEIPT_PATH_PREFIXES):
        return True
    return (
        path.startswith("/api/v1/evidence-artifacts/")
        and path.endswith("/public-excerpt")
    ) or (
        path.startswith("/api/v1/conversations/")
        and path.rsplit("/", 1)[-1]
        in {"public-excerpt-candidates", "public-excerpt-preview", "public-excerpt"}
    )


class EvidenceReceiptFlagGateMiddleware:
    """Answer receipt paths as non-existent while sharing is off.

    A flag check inside the route is too late to keep that promise. FastAPI parses
    the body and resolves dependencies before the route body runs, so with sharing
    off an unauthenticated caller got 401 (or 500 where Supabase is absent) and a
    malformed body got 422, each of which tells an observer that receipt code is
    deployed. Gating here, before routing, makes every probe answer exactly as it
    would on a deployment that never had this lane: same status, same body, same
    headers, whatever the method, auth, or payload.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if (
            scope.get("type") == "http"
            and _is_receipt_path(scope.get("path", ""))
            and not evidence_receipt_sharing_enabled()
        ):
            response = JSONResponse({"detail": "Not Found"}, status_code=404)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


class PublicExcerptReader(Protocol):
    """The entire surface the unauthenticated public route may call."""

    def read_public_excerpt_view(self, *, public_id: str) -> PublicExcerptView: ...


class MemoryPublicExcerptRepository:
    """In-process parity for dev and test runs, same contract as the gateway."""

    def __init__(self, store: Any) -> None:
        self._store = store

    def create_public_excerpt_snapshot(
        self, *, snapshot: PublicExcerptSnapshot
    ) -> tuple[PublicExcerptSnapshot, bool]:
        with self._store.conversation_message_lock:
            existing = self.get_live_public_excerpt_for_artifact(
                owner_id=snapshot.owner_id,
                evidence_artifact_id=snapshot.evidence_artifact_id,
            ) or self.get_live_public_excerpt_for_selection(
                owner_id=snapshot.owner_id, selection_key=snapshot.selection_key
            )
            if existing is not None:
                return existing, False
            self._store.public_excerpt_snapshots[snapshot.id] = snapshot
            return snapshot, True

    def get_live_public_excerpt_for_artifact(
        self, *, owner_id: str, evidence_artifact_id: str | None
    ) -> PublicExcerptSnapshot | None:
        if evidence_artifact_id is None:
            return None
        for snapshot in self._store.public_excerpt_snapshots.values():
            if (
                snapshot.owner_id == owner_id
                and snapshot.evidence_artifact_id == evidence_artifact_id
                and snapshot.revoked_at is None
            ):
                return snapshot
        return None

    def get_live_public_excerpt_for_selection(
        self, *, owner_id: str, selection_key: str | None
    ) -> PublicExcerptSnapshot | None:
        if selection_key is None:
            return None
        return next(
            (
                row
                for row in self._store.public_excerpt_snapshots.values()
                if row.owner_id == owner_id
                and row.selection_key == selection_key
                and row.revoked_at is None
            ),
            None,
        )

    def list_public_excerpt_snapshots(
        self,
        *,
        owner_id: str,
        limit: int = DEFAULT_OWNER_PAGE_SIZE,
        before: tuple[str, str] | None = None,
    ) -> list[PublicExcerptSnapshot]:
        owned = sorted(
            (
                snapshot
                for snapshot in self._store.public_excerpt_snapshots.values()
                if snapshot.owner_id == owner_id
            ),
            key=lambda snapshot: (snapshot.created_at.isoformat(), snapshot.id),
            reverse=True,
        )
        if before is not None:
            owned = [
                snapshot
                for snapshot in owned
                if (snapshot.created_at.isoformat(), snapshot.id) < before
            ]
        return owned[:limit]

    def get_owned_public_excerpt_snapshot(
        self, *, owner_id: str, snapshot_id: str
    ) -> PublicExcerptSnapshot | None:
        snapshot = self._store.public_excerpt_snapshots.get(snapshot_id)
        if snapshot is None or snapshot.owner_id != owner_id:
            return None
        return snapshot

    def revoke_public_excerpt_snapshot(
        self,
        *,
        owner_id: str,
        snapshot_id: str,
        reason: str = "owner_revoked",
    ) -> tuple[PublicExcerptSnapshot | None, bool]:
        snapshot = self.get_owned_public_excerpt_snapshot(
            owner_id=owner_id,
            snapshot_id=snapshot_id,
        )
        if snapshot is None or snapshot.revoked_at is not None:
            return snapshot, False
        return self._revoke(snapshot, reason=reason), True

    def revoke_public_excerpts_for_conversation(
        self, *, owner_id: str, conversation_id: str
    ) -> int:
        revoked = 0
        for snapshot in list(self._store.public_excerpt_snapshots.values()):
            if (
                snapshot.owner_id == owner_id
                and snapshot.source_conversation_id == conversation_id
                and snapshot.revoked_at is None
            ):
                self._revoke(snapshot, reason="source_deleted")
                revoked += 1
        return revoked

    def revoke_all_public_excerpts(self, *, owner_id: str) -> int:
        revoked = 0
        for snapshot in list(self._store.public_excerpt_snapshots.values()):
            if snapshot.owner_id == owner_id and snapshot.revoked_at is None:
                self._revoke(snapshot, reason="source_deleted")
                revoked += 1
        return revoked

    def read_public_excerpt_view(self, *, public_id: str) -> PublicExcerptView:
        for snapshot in self._store.public_excerpt_snapshots.values():
            if snapshot.public_id == public_id:
                return snapshot_public_view(snapshot)
        return revoked_public_view(public_id)

    def _revoke(
        self, snapshot: PublicExcerptSnapshot, *, reason: str
    ) -> PublicExcerptSnapshot:
        revoked = snapshot.model_copy(
            update={
                "revoked_at": datetime.now(timezone.utc),
                "revocation_reason": reason,
            }
        )
        self._store.public_excerpt_snapshots[snapshot.id] = revoked
        return revoked


def public_excerpt_repository() -> Any:
    if api_state.supabase_gateway is not None:
        return api_state.supabase_gateway
    return MemoryPublicExcerptRepository(api_state.store)


def public_excerpt_reader() -> PublicExcerptReader:
    """Resolve the narrow reader the public route is allowed to hold."""
    return public_excerpt_repository()


def create_receipt_for_artifact(
    *,
    user: User,
    artifact_id: str,
    owner_note: str | None,
) -> tuple[PublicExcerptSnapshot, bool]:
    """Freeze a receipt from an owned result. Reads private records exactly once.

    Returns ``(snapshot, created)``. Sharing the same result twice returns the
    existing link, and the caller needs to know that so a retry or a reload is not
    counted as a new receipt in the funnel.
    """
    from argus.api.public_excerpt_selection import create_receipt_for_artifact_adapter

    return create_receipt_for_artifact_adapter(
        user=user, artifact_id=artifact_id, owner_note=owner_note
    )


def revoke_receipts_for_conversation(*, user_id: str, conversation_id: str) -> int:
    """Deleting a conversation revokes the receipts it produced."""
    return public_excerpt_repository().revoke_public_excerpts_for_conversation(
        owner_id=user_id,
        conversation_id=conversation_id,
    )


def revoke_all_receipts(*, user_id: str) -> int:
    return public_excerpt_repository().revoke_all_public_excerpts(owner_id=user_id)


def _artifact_content_language(conversation: Conversation | None) -> str:
    """The language the frozen prose was written in, read from the record it came from.

    Not the owner's current profile language. A receipt claims to be a frozen moment,
    so every field it captures has to belong to the artifact rather than to a setting
    the owner can change afterwards. An English result shared after switching the app
    to Spanish is still an English result.

    ``conversations.language`` is set when the conversation is created and is not in
    ``ConversationPatch``, so it does not move. The artifact records no language of
    its own, and neither does the run, which makes this the only stable anchor. With
    no conversation there is no anchor at all, so this falls back to the schema
    default rather than guessing from a mutable value.
    """
    language = getattr(conversation, "language", None) if conversation else None
    return "es-419" if language == "es-419" else "en"


def _owned_artifact(
    *, user_id: str, artifact_id: str
) -> tuple[EvidenceArtifact, Conversation | None]:
    """Resolve the artifact and its source conversation, or refuse.

    Returns the conversation too because the caller needs it for the frozen content
    language, and reading it twice would be two chances to disagree.
    """
    if api_state.supabase_gateway is not None:
        artifact = api_state.supabase_gateway.get_evidence_artifact(
            user_id=user_id,
            artifact_id=artifact_id,
        )
    else:
        artifact = api_state.store.evidence_artifacts.get(artifact_id)
        if artifact is not None and (
            api_state.store.evidence_artifact_owners.get(artifact_id) != user_id
        ):
            artifact = None
    if artifact is None:
        raise EvidenceReceiptSourceMissingError("That result is not available.")
    if artifact.artifact_type != "backtest":
        raise PublicExcerptSourceError("Only completed backtest results are shareable.")
    # An artifact outlives its conversation, so ownership alone does not mean the
    # owner still has the thing they would be publishing. A stale result card in an
    # open tab is the ordinary way this happens.
    conversation = _owned_source_conversation(
        user_id=user_id,
        conversation_id=artifact.source_conversation_id,
    )
    if artifact.source_conversation_id is not None and (
        conversation is None or conversation.deleted_at is not None
    ):
        raise EvidenceReceiptSourceMissingError("That result is not available.")
    return artifact, conversation


def _owned_source_conversation(
    *, user_id: str, conversation_id: str | None
) -> Conversation | None:
    """Cheap read for the common case. The database trigger closes the race."""
    if conversation_id is None:
        return None
    if api_state.supabase_gateway is not None:
        conversation = api_state.supabase_gateway.get_conversation(
            user_id=user_id,
            conversation_id=conversation_id,
        )
    else:
        conversation = api_state.store.conversations.get(conversation_id)
        if conversation is not None and (
            api_state.store.conversation_owners.get(conversation_id) != user_id
        ):
            conversation = None
    return conversation


def _owned_run(*, user_id: str, run_id: str | None) -> Any | None:
    """Read the run once. It is immutable, and the public view never reads it.

    Both the frozen chart and the frozen strategy facts come from here, so one
    read means the two cannot describe different runs.
    """
    if run_id is None:
        return None
    if api_state.supabase_gateway is not None:
        return api_state.supabase_gateway.get_backtest_run(
            user_id=user_id,
            run_id=run_id,
        )
    run = api_state.store.backtest_runs.get(run_id)
    if run is None:
        return None
    if api_state.store.backtest_run_owners.get(run_id) != user_id:
        return None
    return run


# Public owner entry points, kept out of the storage and flag middleware module.
from argus.api.public_excerpt_selection import (  # noqa: E402,F401
    create_receipt_for_messages,
    preview_receipt_for_messages,
    receipt_candidates,
)
