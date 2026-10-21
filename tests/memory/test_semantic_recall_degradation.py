"""Every semantic-recall failure degrades to canonical truth, never open.

When the embedder, the vendor client, or the assessor fails, retrieval must
still answer from the canonical store, and no failure may widen what is stored
or shown.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from argus.api.personalization_memory_index import (
    RECORD_ID_METADATA_KEY,
    Mem0MemoryProvider,
    langchain_embeddings_adapter,
)
from argus.llm.memory_embedding import (
    EmbeddingResult,
    EmbeddingUsage,
    MemoryEmbeddingUnavailable,
)
from argus.memory.contracts import (
    MemoryCandidateDraft,
    MemoryCategory,
    MemoryEdit,
    MemoryOperationContext,
    MemoryProposalTrigger,
    MemoryProvenance,
    MemorySelectionReason,
    MemorySourceKind,
    MemoryUsePurpose,
    ProviderReconciliationStatus,
    SensitivityAssessment,
    SensitivityStatus,
)
from argus.memory.service import MemoryService, MemoryServiceConfig
from argus.memory.store import InMemoryCanonicalMemoryStore
from argus.memory.subject import MemoryAccountKind, MemorySubject, RegisteredMemoryOwner

NOW = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)
OWNER_ID = "3f8a1d02-6c4b-4a7e-9d51-2b0e7c3a5f18"
SUBJECT = MemorySubject(owner_id=OWNER_ID, kind=MemoryAccountKind.REGISTERED)
OWNER = RegisteredMemoryOwner(owner_id=OWNER_ID)
CLEAR = SensitivityAssessment(status=SensitivityStatus.CLEAR)
QUERY = "lower drawdown"
# Shares no token with the stored memory, so only a semantic index can match
# it. The A/B pair below depends on that.
SEMANTIC_QUERY = "gentler decline variant"


class _StubEmbedder:
    dimensions = 4

    def __init__(self, failure: Exception | None = None) -> None:
        self._failure = failure
        self.calls = 0

    def embed(self, text: str) -> list[float]:
        del text
        self.calls += 1
        if self._failure is not None:
            raise self._failure
        return [0.1, 0.2, 0.3, 0.4]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return self.embed_batch_with_usage(texts).vectors

    def embed_batch_with_usage(self, texts: list[str]) -> EmbeddingResult:
        return EmbeddingResult(
            [self.embed(text) for text in texts],
            EmbeddingUsage(),
        )


class _Mem0Double:
    """Mem0 client double whose calls can be made to fail on demand."""

    def __init__(
        self,
        *,
        embedder: _StubEmbedder,
        search_results: list[dict] | None = None,
        add_failure: Exception | None = None,
        search_failure: Exception | None = None,
        delete_failure: Exception | None = None,
        indexed: bool = False,
        post_embed_delay: float = 0.0,
    ) -> None:
        self._embedder = embedder
        self._search_results = search_results or []
        self._add_failure = add_failure
        self._search_failure = search_failure
        self._delete_failure = delete_failure
        self._indexed = indexed
        self._post_embed_delay = post_embed_delay
        self._adapter = langchain_embeddings_adapter(embedder)
        self.added: list[dict] = []

    def fail_next_add(self, failure: Exception) -> None:
        self._add_failure = failure

    def add(self, *, messages, user_id, metadata, infer):  # noqa: ANN001
        if self._add_failure is not None:
            raise self._add_failure
        # Through the adapter, which is what publishes per-call usage.
        self._adapter.embed_documents([messages[0]["content"]])
        self.added.append({"user_id": user_id, "metadata": metadata, "infer": infer})
        return {"results": [{"id": f"mem0-{len(self.added)}"}]}

    def search(self, query, *, top_k, filters, threshold):  # noqa: ANN001
        if self._search_failure is not None:
            raise self._search_failure
        self._adapter.embed_query(query)
        # Stands in for the pgvector round trip, between publish and read.
        if self._post_embed_delay:
            time.sleep(self._post_embed_delay)
        del top_k, filters, threshold
        return {"results": self._search_results}

    def get_all(self, *, filters, top_k):  # noqa: ANN001
        del filters, top_k
        present = self._indexed or bool(self.added)
        return {"results": [{"id": "row"}] if present else []}

    def delete(self, memory_id):  # noqa: ANN001
        del memory_id
        if self._delete_failure is not None:
            raise self._delete_failure

    def delete_all(self, user_id=None):  # noqa: ANN001
        del user_id


def _ids(prefix: str = "generated") -> Iterator[str]:
    index = 0
    while True:
        index += 1
        yield f"{prefix}-{index:03d}"


def _service(
    store: InMemoryCanonicalMemoryStore,
    provider: object | None = None,
    *,
    id_prefix: str = "generated",
) -> MemoryService:
    generated = _ids(id_prefix)
    return MemoryService(
        store=store,
        provider=provider,  # type: ignore[arg-type]
        config=MemoryServiceConfig(available=True),
        clock=lambda: NOW,
        id_factory=lambda: next(generated),
    )


def _confirm_one(
    service: MemoryService,
    *,
    label: str = "Lower drawdown choice",
    value: str = "Keep the lower drawdown choice for later comparison.",
    source_id: str = "decision-degradation-test",
) -> str:
    proposal = service.propose(
        SUBJECT,
        MemoryCandidateDraft(
            category=MemoryCategory.EXPLICIT_DECISION_NOTE,
            value=value,
            label=label,
            future_benefit="Argus can revisit the confirmed choice later.",
            provenance=(
                MemoryProvenance(
                    source_kind=MemorySourceKind.DECISION_NOTE,
                    source_id=source_id,
                    source_version="1",
                ),
            ),
            trigger=MemoryProposalTrigger.EXPLICIT_REQUEST,
            sensitivity=CLEAR,
        ),
        MemoryOperationContext.ORDINARY,
    )
    assert proposal is not None
    confirmation = service.confirm(
        SUBJECT,
        proposal.candidate.id,
        context=MemoryOperationContext.ORDINARY,
    )
    assert confirmation.created is True
    assert confirmation.record is not None
    return confirmation.record.id


@pytest.mark.parametrize(
    "failure",
    (
        MemoryEmbeddingUnavailable("timeout"),
        MemoryEmbeddingUnavailable("authentication_failed"),
        RuntimeError("vendor client exploded"),
    ),
)
def test_embedding_failure_at_search_falls_back_to_canonical_match(
    failure: Exception,
) -> None:
    """Catches a vectorization outage emptying recall instead of degrading it."""
    store = InMemoryCanonicalMemoryStore()
    record_id = _confirm_one(_service(store))
    embedder = _StubEmbedder(failure=failure)
    provider = Mem0MemoryProvider(
        embedder=embedder,
        memory=_Mem0Double(embedder=embedder),
    )

    retrieved = _service(store, provider).retrieve(
        SUBJECT,
        QUERY,
        MemoryUsePurpose.REVISIT_SAVED_DECISION,
    )

    assert [item.record.id for item in retrieved] == [record_id]
    assert retrieved[0].selection_reason is MemorySelectionReason.CANONICAL_TOKEN_MATCH


def test_vendor_search_failure_falls_back_to_canonical_match() -> None:
    """Catches an index outage failing the turn instead of degrading recall."""
    store = InMemoryCanonicalMemoryStore()
    record_id = _confirm_one(_service(store))
    embedder = _StubEmbedder()
    provider = Mem0MemoryProvider(
        embedder=embedder,
        memory=_Mem0Double(
            embedder=embedder,
            search_failure=RuntimeError("pgvector connection refused"),
        ),
    )

    retrieved = _service(store, provider).retrieve(
        SUBJECT,
        QUERY,
        MemoryUsePurpose.REVISIT_SAVED_DECISION,
    )

    assert [item.record.id for item in retrieved] == [record_id]
    assert retrieved[0].selection_reason is MemorySelectionReason.CANONICAL_TOKEN_MATCH


def test_indexing_failure_never_rolls_back_the_confirmed_memory() -> None:
    """Catches an index write failure costing the user a confirmed memory."""
    store = InMemoryCanonicalMemoryStore()
    embedder = _StubEmbedder()
    provider = Mem0MemoryProvider(
        embedder=embedder,
        memory=_Mem0Double(
            embedder=embedder,
            add_failure=RuntimeError("index write refused"),
        ),
    )

    record_id = _confirm_one(_service(store, provider))

    assert store.get_record(OWNER, record_id) is not None
    assert store.get_provider_ref(OWNER, record_id) is None


def test_successful_index_answers_semantically_rather_than_by_token_match() -> None:
    """Catches semantic recall silently never engaging."""
    store = InMemoryCanonicalMemoryStore()
    record_id = _confirm_one(_service(store))
    embedder = _StubEmbedder()
    provider = Mem0MemoryProvider(
        embedder=embedder,
        memory=_Mem0Double(
            embedder=embedder,
            search_results=[
                {
                    "id": "mem0-1",
                    "score": 0.77,
                    "metadata": {RECORD_ID_METADATA_KEY: record_id},
                }
            ],
        ),
    )

    retrieved = _service(store, provider).retrieve(
        SUBJECT,
        SEMANTIC_QUERY,
        MemoryUsePurpose.REVISIT_SAVED_DECISION,
    )

    assert [item.record.id for item in retrieved] == [record_id]
    assert retrieved[0].selection_reason is MemorySelectionReason.PROVIDER_RANKED


def test_token_match_alone_cannot_answer_the_semantic_query() -> None:
    """Pins the baseline the index improves on, so the previous test means something."""
    store = InMemoryCanonicalMemoryStore()
    _confirm_one(_service(store))

    retrieved = _service(store).retrieve(
        SUBJECT,
        SEMANTIC_QUERY,
        MemoryUsePurpose.REVISIT_SAVED_DECISION,
    )

    assert retrieved == ()


def test_unassessed_content_is_suppressed_before_storage_or_indexing() -> None:
    """Catches assessor failure failing open into stored, indexed content."""
    store = InMemoryCanonicalMemoryStore()
    embedder = _StubEmbedder()
    mem0 = _Mem0Double(embedder=embedder)
    service = _service(store, Mem0MemoryProvider(embedder=embedder, memory=mem0))

    # A failed classifier yields the default UNASSESSED assessment.
    proposal = service.propose(
        SUBJECT,
        MemoryCandidateDraft(
            category=MemoryCategory.EXPLICIT_DECISION_NOTE,
            value="Something the classifier could not reach a verdict on.",
            label="Unassessed note",
            future_benefit="Argus could revisit this later.",
            provenance=(
                MemoryProvenance(
                    source_kind=MemorySourceKind.DECISION_NOTE,
                    source_id="decision-unassessed",
                    source_version="1",
                ),
            ),
            trigger=MemoryProposalTrigger.EXPLICIT_REQUEST,
            sensitivity=SensitivityAssessment(),
        ),
        MemoryOperationContext.ORDINARY,
    )

    assert proposal is None
    assert store.list_records(OWNER) == ()
    assert mem0.added == []


def test_empty_index_falls_back_instead_of_answering_nothing() -> None:
    """Catches records confirmed before the index existed losing their recall."""
    store = InMemoryCanonicalMemoryStore()
    record_id = _confirm_one(_service(store))
    embedder = _StubEmbedder()
    provider = Mem0MemoryProvider(
        embedder=embedder,
        memory=_Mem0Double(embedder=embedder, search_results=[]),
    )

    retrieved = _service(store, provider).retrieve(
        SUBJECT,
        QUERY,
        MemoryUsePurpose.REVISIT_SAVED_DECISION,
    )

    assert [item.record.id for item in retrieved] == [record_id]
    assert retrieved[0].selection_reason is MemorySelectionReason.CANONICAL_TOKEN_MATCH


def test_hits_that_resolve_to_nothing_fall_back() -> None:
    """Catches stale or out-of-scope ranked ids hiding a findable memory."""
    store = InMemoryCanonicalMemoryStore()
    record_id = _confirm_one(_service(store))
    embedder = _StubEmbedder()
    provider = Mem0MemoryProvider(
        embedder=embedder,
        memory=_Mem0Double(
            embedder=embedder,
            search_results=[
                {
                    "id": "mem0-1",
                    "score": 0.9,
                    "metadata": {RECORD_ID_METADATA_KEY: "deleted-record"},
                }
            ],
        ),
    )

    retrieved = _service(store, provider).retrieve(
        SUBJECT,
        QUERY,
        MemoryUsePurpose.REVISIT_SAVED_DECISION,
    )

    assert [item.record.id for item in retrieved] == [record_id]
    assert retrieved[0].selection_reason is MemorySelectionReason.CANONICAL_TOKEN_MATCH


def test_recall_runs_off_the_event_loop() -> None:
    """Catches blocking vendor I/O stalling every other stream on one worker."""
    import asyncio
    import threading

    from argus.api.chat.memory_recall import memory_recalls_for_turn_async

    calling_threads: list[int] = []

    class _BlockingService:
        def retrieve(self, *args: object, **kwargs: object) -> object:
            calling_threads.append(threading.get_ident())
            raise RuntimeError("vendor down")

    import os
    import typing

    from argus.api import state as api_state
    from argus.api.guest_access import registered_account_context
    from argus.api.personalization_memory import configure_memory_service
    from argus.api.schemas import OnboardingState, User

    previous_flag = os.environ.get("ARGUS_ENABLE_PERSONALIZATION_MEMORY")
    previous_gateway = api_state.supabase_gateway
    os.environ["ARGUS_ENABLE_PERSONALIZATION_MEMORY"] = "true"
    api_state.supabase_gateway = None
    configure_memory_service(typing.cast(MemoryService, _BlockingService()))
    now = datetime.now(timezone.utc)
    user = User(
        id=OWNER_ID,
        email="qa@example.test",
        username=None,
        display_name=None,
        language="en",
        locale="en-US",
        is_admin=False,
        onboarding=OnboardingState(),
        created_at=now,
        updated_at=now,
    )

    from argus.api.message_store import memory_conversation
    from argus.domain.owner_scope import PERSONAL

    conversation_id = memory_conversation(
        title="ETH idea",
        title_source="system_default",
        language="en",
        scope=PERSONAL,
        user_id=OWNER_ID,
    ).id

    async def _drive() -> tuple[int, object]:
        loop_thread = threading.get_ident()
        result = await memory_recalls_for_turn_async(
            user=user,
            account=registered_account_context(OWNER_ID),
            conversation_id=conversation_id,
            user_message="what did I decide",
            memory_opt_out=False,
        )
        return loop_thread, result

    try:
        loop_thread, result = asyncio.run(_drive())
    finally:
        configure_memory_service(None)
        api_state.supabase_gateway = previous_gateway
        if previous_flag is None:
            os.environ.pop("ARGUS_ENABLE_PERSONALIZATION_MEMORY", None)
        else:
            os.environ["ARGUS_ENABLE_PERSONALIZATION_MEMORY"] = previous_flag

    assert result is None
    assert calling_threads, "retrieval never ran"
    assert calling_threads[0] != loop_thread


def test_a_fully_projected_eligible_set_is_believed_when_empty() -> None:
    """Catches token fallback resurrecting what semantic search rejected."""
    store = InMemoryCanonicalMemoryStore()
    embedder = _StubEmbedder()
    provider = Mem0MemoryProvider(
        embedder=embedder,
        memory=_Mem0Double(embedder=embedder, search_results=[]),
    )
    # Confirming through the provider is what projects the record, so the
    # eligible set is covered by construction.
    _confirm_one(_service(store, provider))

    retrieved = _service(store, provider).retrieve(
        SUBJECT,
        QUERY,
        MemoryUsePurpose.REVISIT_SAVED_DECISION,
    )

    assert retrieved == ()


def test_an_unprojected_eligible_set_falls_back() -> None:
    """Catches the never-projected case being answered as a real empty."""
    store = InMemoryCanonicalMemoryStore()
    record_id = _confirm_one(_service(store))
    embedder = _StubEmbedder()
    provider = Mem0MemoryProvider(
        embedder=embedder,
        memory=_Mem0Double(embedder=embedder, search_results=[]),
    )

    retrieved = _service(store, provider).retrieve(
        SUBJECT,
        QUERY,
        MemoryUsePurpose.REVISIT_SAVED_DECISION,
    )

    assert [item.record.id for item in retrieved] == [record_id]
    assert retrieved[0].selection_reason is MemorySelectionReason.CANONICAL_TOKEN_MATCH


def test_authority_is_per_eligible_set_not_per_owner() -> None:
    """Catches an owner-wide notion of authority hiding a legacy memory."""
    store = InMemoryCanonicalMemoryStore()
    embedder = _StubEmbedder()
    provider = Mem0MemoryProvider(
        embedder=embedder,
        memory=_Mem0Double(embedder=embedder, search_results=[]),
    )
    # Legacy: confirmed with no provider, so it never reached the index.
    legacy_id = _confirm_one(_service(store))
    # Newer: confirmed through the provider, so this one is projected.
    _confirm_one(
        _service(store, provider, id_prefix="later"),
        label="Later note",
        value="A later confirmed note that did reach the index.",
        source_id="decision-later",
    )

    owner_refs = store.settled_projection_record_ids(OWNER)
    retrieved = _service(store, provider).retrieve(
        SUBJECT,
        QUERY,
        MemoryUsePurpose.REVISIT_SAVED_DECISION,
    )

    # The owner does have an indexed row, which is exactly the trap.
    assert owner_refs
    assert legacy_id not in owner_refs
    assert legacy_id in {item.record.id for item in retrieved}
    assert retrieved[0].selection_reason is MemorySelectionReason.CANONICAL_TOKEN_MATCH


def test_usage_is_attributed_to_the_call_that_produced_it() -> None:
    """Catches concurrent recalls billing each other's tokens."""
    import concurrent.futures

    class _CountingEmbedder:
        dimensions = 4

        def __init__(self) -> None:
            self._lock = threading.Lock()
            self._next = 0

        def embed(self, text: str) -> list[float]:
            return self.embed_batch([text])[0]

        def embed_batch(self, texts: list[str]) -> list[list[float]]:
            return self.embed_batch_with_usage(texts).vectors

        def embed_batch_with_usage(self, texts: list[str]) -> EmbeddingResult:
            with self._lock:
                self._next += 1
                tokens = self._next
            return EmbeddingResult(
                [[0.1, 0.2, 0.3, 0.4] for _ in texts],
                EmbeddingUsage(total_tokens=tokens),
            )

    embedder = _CountingEmbedder()
    mem0 = _Mem0Double(
        embedder=embedder,  # type: ignore[arg-type]
        search_results=[
            {"id": "mem0-1", "score": 0.5, "metadata": {RECORD_ID_METADATA_KEY: "r"}}
        ],
        indexed=True,
        post_embed_delay=0.05,
    )
    provider = Mem0MemoryProvider(embedder=embedder, memory=mem0)  # type: ignore[arg-type]

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: provider.search(OWNER, QUERY, 3), range(8)))

    reported = sorted(result.usage_units for result in results)
    # Every call embedded exactly once, so each answer must carry a distinct
    # counter. A shared slot collapses or duplicates them.
    assert reported == list(range(1, 9))


def test_an_edit_whose_projection_failed_does_not_certify_an_empty_answer() -> None:
    """Catches a stale projection being counted as coverage."""
    store = InMemoryCanonicalMemoryStore()
    embedder = _StubEmbedder()
    mem0 = _Mem0Double(embedder=embedder, search_results=[])
    provider = Mem0MemoryProvider(embedder=embedder, memory=mem0)
    service = _service(store, provider)
    record_id = _confirm_one(service)

    # Projected and settled: an empty answer is believable here.
    assert store.settled_projection_record_ids(OWNER) == frozenset({record_id})

    mem0.fail_next_add(RuntimeError("index write refused"))
    edited = service.edit(
        SUBJECT,
        record_id,
        MemoryEdit(value="Now about gentler declines instead.", sensitivity=CLEAR),
    )

    assert edited.changed is True
    assert edited.provider_status is ProviderReconciliationStatus.RECONCILIATION_REQUIRED
    # Still projected, but under the superseded text.
    assert store.get_provider_ref(OWNER, record_id) is not None
    assert store.settled_projection_record_ids(OWNER) == frozenset()

    retrieved = _service(store, provider).retrieve(
        SUBJECT,
        "gentler declines",
        MemoryUsePurpose.REVISIT_SAVED_DECISION,
    )

    assert [item.record.id for item in retrieved] == [record_id]
    assert retrieved[0].selection_reason is MemorySelectionReason.CANONICAL_TOKEN_MATCH


def test_an_edit_stops_certifying_before_any_provider_call() -> None:
    """Catches the window between committing an edit and projecting it."""
    store = InMemoryCanonicalMemoryStore()
    embedder = _StubEmbedder()
    provider = Mem0MemoryProvider(
        embedder=embedder, memory=_Mem0Double(embedder=embedder)
    )
    record_id = _confirm_one(_service(store, provider))
    assert store.settled_projection_record_ids(OWNER) == frozenset({record_id})

    # Commit the edit exactly as the service does, and stop before projecting.
    mutation = store.edit_record(
        OWNER,
        record_id,
        value="Now about gentler declines instead.",
        label=None,
        clock=lambda: NOW,
    )

    assert mutation is not None
    # No cleanup target exists yet; only the generation reveals the staleness.
    assert store.list_provider_cleanup_targets(OWNER, record_id) == ()
    assert store.get_provider_ref(OWNER, record_id) is not None
    assert store.settled_projection_record_ids(OWNER) == frozenset()


def test_an_obsolete_ref_awaiting_deletion_does_not_block_a_current_projection() -> None:
    """Catches one failed delete permanently demoting an account to token match."""
    store = InMemoryCanonicalMemoryStore()
    embedder = _StubEmbedder()
    provider = Mem0MemoryProvider(
        embedder=embedder,
        memory=_Mem0Double(
            embedder=embedder,
            delete_failure=RuntimeError("index delete refused"),
        ),
    )
    service = _service(store, provider)
    record_id = _confirm_one(service)

    edited = service.edit(
        SUBJECT,
        record_id,
        MemoryEdit(value="Now about gentler declines instead.", sensitivity=CLEAR),
    )

    assert edited.changed is True
    # The projection is current even though the old ref is still queued.
    assert store.list_provider_cleanup_targets(OWNER, record_id) != ()
    assert store.settled_projection_record_ids(OWNER) == frozenset({record_id})


def test_reasserting_the_same_ref_cannot_make_a_stale_projection_fresh() -> None:
    """Catches a setup helper laundering staleness into authority."""
    store = InMemoryCanonicalMemoryStore()
    embedder = _StubEmbedder()
    provider = Mem0MemoryProvider(
        embedder=embedder, memory=_Mem0Double(embedder=embedder)
    )
    record_id = _confirm_one(_service(store, provider))
    projected_ref = store.get_provider_ref(OWNER, record_id)
    assert projected_ref is not None

    store.edit_record(
        OWNER,
        record_id,
        value="Superseding text the index has never seen.",
        label=None,
        clock=lambda: NOW,
    )
    assert store.settled_projection_record_ids(OWNER) == frozenset()

    # Re-asserting the ref already on file is a no-op by design.
    assert store.set_provider_ref(OWNER, record_id, projected_ref) is True

    assert store.settled_projection_record_ids(OWNER) == frozenset()


def test_a_reset_retires_the_generation_with_the_projection() -> None:
    """Catches a retired generation surviving reset and re-arming on recreate."""
    store = InMemoryCanonicalMemoryStore()
    embedder = _StubEmbedder()
    provider = Mem0MemoryProvider(
        embedder=embedder, memory=_Mem0Double(embedder=embedder)
    )
    service = _service(store, provider)
    record_id = _confirm_one(service)
    # Advance well past generation 1 so a retired value would be conspicuous.
    for index in range(2):
        service.edit(
            SUBJECT,
            record_id,
            MemoryEdit(value=f"revision {index} of the note.", sensitivity=CLEAR),
        )
    assert store.settled_projection_record_ids(OWNER) == frozenset({record_id})

    service.reset(SUBJECT)

    # Nothing survives the reset that a recreated record could inherit.
    assert store.settled_projection_record_ids(OWNER) == frozenset()
    assert store.get_provider_ref(OWNER, record_id) is None


def test_attaching_a_ref_out_of_band_cannot_certify_the_index() -> None:
    """Catches freshness being asserted by a caller instead of earned."""
    store = InMemoryCanonicalMemoryStore()
    embedder = _StubEmbedder()
    provider = Mem0MemoryProvider(
        embedder=embedder, memory=_Mem0Double(embedder=embedder)
    )
    record_id = _confirm_one(_service(store, provider))

    store.edit_record(
        OWNER,
        record_id,
        value="Edited text the index has never seen.",
        label=None,
    )
    assert store.settled_projection_record_ids(OWNER) == frozenset()

    # A ref that was never projected for this record, at any generation.
    assert store.set_provider_ref(OWNER, record_id, "ref-never-projected") is True

    assert store.get_provider_ref(OWNER, record_id) == "ref-never-projected"
    assert store.settled_projection_record_ids(OWNER) == frozenset()


def test_an_out_of_band_ref_cannot_inherit_a_proven_generation() -> None:
    """Catches a replacement ref borrowing the credibility of the one it replaces."""
    store = InMemoryCanonicalMemoryStore()
    embedder = _StubEmbedder()
    provider = Mem0MemoryProvider(
        embedder=embedder, memory=_Mem0Double(embedder=embedder)
    )
    record_id = _confirm_one(_service(store, provider))
    assert store.settled_projection_record_ids(OWNER) == frozenset({record_id})

    assert store.set_provider_ref(OWNER, record_id, "ref-swapped-in") is True

    assert store.settled_projection_record_ids(OWNER) == frozenset()
