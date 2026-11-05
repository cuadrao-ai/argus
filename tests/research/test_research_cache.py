"""Shared cache locks: cross-user hits, per-data-class TTL, no user identity."""

from __future__ import annotations

import hashlib
import inspect
import time
from datetime import datetime, timezone

from argus.domain.research import cache as research_cache
from argus.domain.research.cache import (
    DATA_CLASS_TTL_SECONDS,
    WITHHELD_TTL_SECONDS,
    cache_get,
    cache_put,
    cache_stats,
    data_class_for,
    research_cache_key,
    ttl_for_packet,
)
from argus.domain.research.search.contracts import SearchResultPacket


def _key_for_user(query: str) -> str:
    return research_cache_key(query=query, provider_id="perplexity_direct", max_results=5)


def _search_packet() -> SearchResultPacket:
    return SearchResultPacket(
        retrieved_at=datetime.now(timezone.utc),
        latency_ms=1,
        provider_id="perplexity_direct",
    )


def test_cache_key_has_no_user_parameter() -> None:
    parameters = inspect.signature(research_cache_key).parameters
    assert not any(
        "user" in name or "guest" in name or "visitor" in name or "session" in name
        for name in parameters
    ), "the shared cache key must never accept user-scoped identity"


def test_cross_user_hit_shares_one_provider_answer() -> None:
    key_user_a = _key_for_user("equity peers of AAPL")
    key_user_b = _key_for_user("equity peers of AAPL")
    assert key_user_a == key_user_b

    packet = _search_packet()
    assert cache_get(key_user_a) is None
    cache_put(
        key_user_a,
        packet,
        ttl_seconds=ttl_for_packet(question_kind="live_quote"),
    )
    served = cache_get(key_user_b)
    assert served is not None
    assert served is packet
    stats = cache_stats()
    assert stats["hits"] == 1 and stats["misses"] == 1


def test_the_seven_data_classes_match_the_section_7_table() -> None:
    """One row per spec table row; the ladder orders tolerance exactly."""
    assert DATA_CLASS_TTL_SECONDS["quotes"] == 120.0
    assert DATA_CLASS_TTL_SECONDS["movers"] == 300.0
    assert DATA_CLASS_TTL_SECONDS["analyst_estimates"] == 259_200.0
    assert DATA_CLASS_TTL_SECONDS["peers_constituents"] == 5_184_000.0
    assert DATA_CLASS_TTL_SECONDS["fundamentals"] == 7_776_000.0
    assert DATA_CLASS_TTL_SECONDS["closed_ohlcv"] == 7_776_000.0
    assert DATA_CLASS_TTL_SECONDS["filings_transcripts"] == 7_776_000.0
    assert len(DATA_CLASS_TTL_SECONDS) == 7
    assert (
        DATA_CLASS_TTL_SECONDS["quotes"]
        < DATA_CLASS_TTL_SECONDS["movers"]
        < DATA_CLASS_TTL_SECONDS["analyst_estimates"]
        < DATA_CLASS_TTL_SECONDS["peers_constituents"]
        <= DATA_CLASS_TTL_SECONDS["fundamentals"]
    )


def test_question_kinds_map_to_their_dominant_data_class() -> None:
    assert data_class_for(question_kind="live_quote") == "quotes"
    assert data_class_for(question_kind="screening") == "movers"
    assert data_class_for(question_kind="find_assets") == "movers"
    assert data_class_for(question_kind="etf_constituents") == "peers_constituents"
    assert data_class_for(question_kind="company_lookup") == "fundamentals"
    assert data_class_for(question_kind="cross_company") == "analyst_estimates"
    # Unknown kinds stay conservative, never long-lived.
    assert data_class_for(question_kind="something_new") == "movers"


def test_uniform_packet_categories_decide_the_class_over_the_kind() -> None:
    """A holdings-only pull is constituents data whatever the question was;
    an estimates-only pull is estimates data. Mixed packets keep the
    question's dominant need, so a genuinely current ask stays fresh."""
    assert (
        data_class_for(question_kind="company_lookup", categories=("etf_holdings",))
        == "peers_constituents"
    )
    assert (
        data_class_for(question_kind="company_lookup", categories=("analyst_estimates",))
        == "analyst_estimates"
    )
    assert (
        data_class_for(
            question_kind="company_lookup", categories=("earnings_transcript",)
        )
        == "filings_transcripts"
    )
    # A fast answer mixing a quote with its verification table stays a quote.
    assert (
        data_class_for(question_kind="live_quote", categories=("quote", "tickers_lookup"))
        == "quotes"
    )
    # price_target is an estimate before it is a price.
    assert (
        data_class_for(question_kind="live_quote", categories=("price_target",))
        == "analyst_estimates"
    )


def test_closed_period_rule_wins_over_everything() -> None:
    for kind in ("live_quote", "company_lookup", "cross_company", "screening"):
        assert data_class_for(question_kind=kind, closed_period=True) == "closed_ohlcv"
    assert (
        data_class_for(
            question_kind="live_quote",
            categories=("quote",),
            closed_period=True,
        )
        == "closed_ohlcv"
    )
    assert (
        ttl_for_packet(question_kind="live_quote", closed_period=True)
        == DATA_CLASS_TTL_SECONDS["closed_ohlcv"]
    )


def test_expired_entries_fall_out(monkeypatch) -> None:
    key = _key_for_user("expiring")
    cache_put(key, _search_packet(), ttl_seconds=120.0)
    real_monotonic = time.monotonic
    monkeypatch.setattr(
        research_cache.time, "monotonic", lambda: real_monotonic() + 121.0
    )
    assert cache_get(key) is None


def test_a_withheld_record_serves_for_its_class_capped_at_a_day() -> None:
    """An absence is bounded twice: by how fast the figure itself changes,
    and by the day a page can appear. Volatile classes keep their minutes,
    so a model fault on a quote never outlives a retry; quarterly and closed
    classes are cut from ninety days to one."""
    assert WITHHELD_TTL_SECONDS == 86_400.0
    assert (
        DATA_CLASS_TTL_SECONDS["movers"]
        < WITHHELD_TTL_SECONDS
        < DATA_CLASS_TTL_SECONDS["analyst_estimates"]
    )
    for kind in ("live_quote", "market_pulse", "screening"):
        assert ttl_for_packet(question_kind=kind, withheld=True) == ttl_for_packet(
            question_kind=kind
        )
    for kind in ("cross_company", "company_lookup", "etf_constituents"):
        assert ttl_for_packet(question_kind=kind, withheld=True) == WITHHELD_TTL_SECONDS
        assert ttl_for_packet(question_kind=kind) > WITHHELD_TTL_SECONDS
    assert (
        ttl_for_packet(question_kind="live_quote", closed_period=True, withheld=True)
        == WITHHELD_TTL_SECONDS
    )


def test_provider_request_dimensions_have_distinct_cache_identity() -> None:
    base = dict(
        query="equity peers of NVDA", provider_id="perplexity_direct", max_results=5
    )
    key = research_cache_key(**base)
    for changed in (
        {"query": "equity peers of AMD"},
        {"provider_id": "brave"},
        {"max_results": 3},
    ):
        assert research_cache_key(**(base | changed)) != key


def test_cache_key_preserves_field_boundaries() -> None:
    assert research_cache_key(query="A|B", provider_id="C", max_results=5) != (
        research_cache_key(query="A", provider_id="B|C", max_results=5)
    )


def test_old_contract_entries_are_neither_read_nor_written() -> None:
    old_key = hashlib.sha256(
        b"fast_quote|fast|AAPL|current|quote|en|retrieval|"
    ).hexdigest()
    cache_put(old_key, _search_packet(), ttl_seconds=120.0)
    assert cache_get(old_key) is None
    assert cache_stats()["entries"] == 0


def test_cache_contract_version_invalidates_existing_entries(monkeypatch) -> None:
    old_key = _key_for_user("equity peers of AAPL")
    packet = _search_packet()
    cache_put(old_key, packet, ttl_seconds=120.0)
    assert cache_get(old_key) is packet

    monkeypatch.setattr(research_cache, "CACHE_CONTRACT", "future-public-contract")
    new_key = _key_for_user("equity peers of AAPL")
    assert new_key != old_key
    assert cache_get(old_key) is None
    assert cache_get(new_key) is None


def test_a_scenario_lives_in_the_analyst_estimates_class() -> None:
    """Decision 10: a computed scenario is built from forecasts, targets and
    multiples, so its cache TTL and its recency filter follow the
    analyst-estimates class whatever kind the question was typed as, and a
    closed window still wins."""
    from argus.domain.research.cache import (
        DATA_CLASS_TTL_SECONDS,
        data_class_for,
        ttl_for_packet,
    )
    from argus.domain.research.config import retrieval_spec

    assert data_class_for(question_kind="company_lookup") == "fundamentals"
    assert (
        data_class_for(question_kind="company_lookup", scenario=True)
        == "analyst_estimates"
    )
    assert data_class_for(
        question_kind="company_lookup", scenario=True, closed_period=True
    ) == ("closed_ohlcv")
    assert (
        ttl_for_packet(question_kind="company_lookup", scenario=True)
        == (DATA_CLASS_TTL_SECONDS["analyst_estimates"])
    )
    assert retrieval_spec(
        "balanced", question_kind="company_lookup", country=None, scenario=True
    ).recency == ("month")
    assert (
        retrieval_spec("balanced", question_kind="company_lookup", country=None).recency
        is None
    )
