"""The four ratified Mem0 parameters, enforced in code rather than by habit.

Index-only over confirmed content, storage on the existing Supabase database,
the OSS library in-process, and the extraction pipeline unused.
"""

from __future__ import annotations

import pytest
from argus.api.personalization_memory import (
    build_semantic_recall_provider,
    semantic_recall_enabled,
)
from argus.api.personalization_memory_index import (
    EPHEMERAL_HISTORY_DB_PATH,
    Mem0ExtractionAttempted,
    build_mem0_config,
    extraction_disabled_chat_model,
    import_mem0_memory,
)
from argus.llm.memory_embedding import EmbeddingResult, EmbeddingUsage


class _StubEmbedder:
    dimensions = 1024

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return self.embed_batch_with_usage(texts).vectors

    def embed_batch_with_usage(self, texts: list[str]) -> EmbeddingResult:
        return EmbeddingResult([[0.0] * 1024 for _ in texts], EmbeddingUsage())


class _StubPool:
    """Stands in for the shared process-owned database pool."""


def _config(pool: object | None = None) -> dict:
    return build_mem0_config(
        embedder=_StubEmbedder(),
        connection_pool=pool if pool is not None else _StubPool(),
    )


def test_vectors_borrow_the_shared_pool_without_a_second_datastore() -> None:
    """Catches semantic recall introducing a second datastore or credential."""
    pool = _StubPool()

    vector_store = _config(pool)["vector_store"]

    assert vector_store["provider"] == "pgvector"
    assert vector_store["config"]["connection_pool"]._pool is pool
    assert vector_store["config"]["embedding_model_dims"] == 1024
    assert "api_key" not in vector_store["config"]
    assert "host" not in vector_store["config"]


def test_no_durable_store_exists_outside_supabase() -> None:
    """Catches Mem0's SQLite history journal becoming a second durable store."""
    assert _config()["history_db_path"] == EPHEMERAL_HISTORY_DB_PATH
    assert EPHEMERAL_HISTORY_DB_PATH == ":memory:"


def test_the_extraction_seat_is_filled_by_something_that_refuses_to_generate() -> None:
    """Catches Mem0's extraction pipeline reaching a real model."""
    model = _config()["llm"]["config"]["model"]

    with pytest.raises(Mem0ExtractionAttempted):
        model.invoke([("human", "extract facts from this conversation")])


def test_the_extraction_seat_holds_no_vendor_credential() -> None:
    """Catches an LLM provider key being introduced for a pipeline Argus disabled."""
    llm = _config()["llm"]

    assert llm["provider"] == "langchain"
    assert set(llm["config"]) == {"model"}


def test_the_embedder_is_the_argus_perplexity_client() -> None:
    """Catches a second embedding vendor being configured behind Mem0."""
    embedder = _StubEmbedder()

    config = build_mem0_config(embedder=embedder, connection_pool=_StubPool())
    adapter = config["embedder"]["config"]["model"]

    assert config["embedder"]["provider"] == "langchain"
    assert adapter.embed_query("anything") == [0.0] * 1024


def test_importing_mem0_disables_vendor_telemetry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches the OSS library phoning home about Argus memory usage."""
    import os

    import mem0.memory.main as mem0_main
    import mem0.memory.telemetry as telemetry

    monkeypatch.setenv("MEM0_TELEMETRY", "True")
    monkeypatch.setattr(telemetry, "MEM0_TELEMETRY", True)
    monkeypatch.setattr(mem0_main, "MEM0_TELEMETRY", True)

    import_mem0_memory()

    assert os.environ["MEM0_TELEMETRY"] == "False"
    # Both bindings, because main.py holds its own from-imported copy.
    assert telemetry.MEM0_TELEMETRY is False
    assert mem0_main.MEM0_TELEMETRY is False


def test_the_in_process_oss_client_is_used_not_the_hosted_platform() -> None:
    """Catches a swap to the hosted Mem0 Platform, which would move custody."""
    memory_class = import_mem0_memory()

    assert memory_class.__module__.startswith("mem0.memory")
    # MemoryClient is the hosted platform entry point; this must not be it.
    assert memory_class.__name__ == "Memory"


def test_extraction_sentinel_names_itself_for_diagnosis() -> None:
    """Catches an opaque failure if Mem0 ever does try to extract."""
    assert extraction_disabled_chat_model()._llm_type == (
        "argus-memory-extraction-disabled"
    )


def test_semantic_recall_is_off_unless_explicitly_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches the flag defaulting on."""
    monkeypatch.delenv("ARGUS_ENABLE_MEMORY_SEMANTIC_RECALL", raising=False)
    assert semantic_recall_enabled() is False

    monkeypatch.setenv("ARGUS_ENABLE_MEMORY_SEMANTIC_RECALL", "false")
    assert semantic_recall_enabled() is False

    monkeypatch.setenv("ARGUS_ENABLE_MEMORY_SEMANTIC_RECALL", "true")
    assert semantic_recall_enabled() is True


def test_flag_off_builds_no_provider_and_touches_no_vendor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches flag-off deployments constructing vendor clients anyway."""
    monkeypatch.delenv("ARGUS_ENABLE_MEMORY_SEMANTIC_RECALL", raising=False)

    assert build_semantic_recall_provider(_StubPool()) is None


def test_flag_on_without_a_key_keeps_token_match_recall(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches a misconfigured deployment failing the memory surface outright."""
    monkeypatch.setenv("ARGUS_ENABLE_MEMORY_SEMANTIC_RECALL", "true")
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)

    assert build_semantic_recall_provider(_StubPool()) is None


def test_flag_on_without_a_pool_keeps_token_match_recall(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches semantic recall trying to run without the Supabase database."""
    monkeypatch.setenv("ARGUS_ENABLE_MEMORY_SEMANTIC_RECALL", "true")
    monkeypatch.setenv("PERPLEXITY_API_KEY", "pplx-test-key")

    assert build_semantic_recall_provider(None) is None
