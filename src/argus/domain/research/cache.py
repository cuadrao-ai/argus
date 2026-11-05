"""Shared public-market discovery packets with bounded retention.

Only searches built from provider-validated public symbols are eligible.
Free-form questions, categories, criteria and personalized provider answers
must bypass this cache. The runtime checks provenance before constructing the
adapter; this storage boundary accepts only SearchResultPacket values.

TTL is per data class, the seven rows of the spec section 7 table:

- ``quotes``               120s  (quotes, pre and after hours: seconds to minutes)
- ``movers``               300s  (top gainers, losers, most active: minutes)
- ``analyst_estimates``    3d    (analyst estimates: days)
- ``peers_constituents``   60d   (peers, ETF constituents and weights: months)
- ``fundamentals``         90d   (fundamentals and statements: quarterly)
- ``closed_ohlcv``         90d   (closed historical OHLCV: effectively immutable)
- ``filings_transcripts``  90d   (earnings transcripts, SEC filings: immutable
                                  once published)

Eligible discovery searches use the movers TTL. The data-class helpers also
own provider recency selection for grounded research, which no longer shares
answer packets. The older TTL classes remain that configuration vocabulary.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from argus.domain.research.search.contracts import SearchResultPacket

DataClass = Literal[
    "quotes",
    "movers",
    "analyst_estimates",
    "fundamentals",
    "peers_constituents",
    "closed_ohlcv",
    "filings_transcripts",
]

DATA_CLASS_TTL_SECONDS: dict[DataClass, float] = {
    "quotes": 120.0,
    "movers": 300.0,
    "analyst_estimates": 259_200.0,
    "peers_constituents": 5_184_000.0,
    "fundamentals": 7_776_000.0,
    "closed_ohlcv": 7_776_000.0,
    "filings_transcripts": 7_776_000.0,
}

# The longest a withheld packet is served: an absence is bounded by the day a
# page can appear, whatever the class of the figure that was not found.
WITHHELD_TTL_SECONDS = 86_400.0

# Ordered: the first family a category matches decides it, so
# "earnings_transcript" is a filing before it is fundamentals and
# "price_target" is an estimate before it is a quote.
_CATEGORY_FAMILIES: tuple[tuple[DataClass, tuple[str, ...]], ...] = (
    ("filings_transcripts", ("transcript", "filing", "sec_")),
    ("peers_constituents", ("holding", "peer", "constituent", "tickers_lookup")),
    ("analyst_estimates", ("estimate", "price_target", "recommendation", "rating")),
    ("movers", ("gainer", "loser", "most_active", "mover", "screen")),
    (
        "fundamentals",
        ("financial", "income", "balance", "cash", "statement", "ratio", "profile"),
    ),
    ("quotes", ("quote", "price", "market_cap")),
)

# The question's dominant data need, used when the packet mixes families.
# Comparisons lean on estimates and statements (days); lookups lean on
# statements (quarterly); current-facts finds and screens are movers-fresh.
_KIND_DATA_CLASS: dict[str, DataClass] = {
    "live_quote": "quotes",
    "market_pulse": "movers",
    "screening": "movers",
    "sector_radar": "movers",
    "find_assets": "movers",
    "etf_constituents": "peers_constituents",
    "company_lookup": "fundamentals",
    "cross_company": "analyst_estimates",
}

_MAX_ENTRIES = 512


def _family_for_category(category: str) -> DataClass | None:
    lowered = category.strip().lower()
    for family, needles in _CATEGORY_FAMILIES:
        if any(needle in lowered for needle in needles):
            return family
    return None


def data_class_for(
    *,
    question_kind: str | None,
    categories: Sequence[str] = (),
    closed_period: bool = False,
    scenario: bool = False,
) -> DataClass:
    """The section 7 data class governing one cache entry.

    A computed scenario (decision 10) is built from forecasts, targets and
    multiples whatever kind the question was typed as, so it lives in the
    analyst-estimates class: its recency filter and its TTL follow those
    inputs, not the company read it may have been typed as."""
    if closed_period:
        return "closed_ohlcv"
    if scenario:
        return "analyst_estimates"
    families = {
        family
        for family in (_family_for_category(category) for category in categories)
        if family is not None
    }
    if len(families) == 1:
        return next(iter(families))
    return _KIND_DATA_CLASS.get(str(question_kind or ""), "movers")


def ttl_for_packet(
    *,
    question_kind: str | None,
    categories: Sequence[str] = (),
    closed_period: bool = False,
    withheld: bool = False,
    scenario: bool = False,
) -> float:
    """The class TTL of one entry; a withheld packet's is capped at one day."""
    ttl = DATA_CLASS_TTL_SECONDS[
        data_class_for(
            question_kind=question_kind,
            categories=categories,
            closed_period=closed_period,
            scenario=scenario,
        )
    ]
    return min(ttl, WITHHELD_TTL_SECONDS) if withheld else ttl


@dataclass
class _Entry:
    packet: SearchResultPacket
    stored_at: float
    ttl_seconds: float


_CACHE: dict[str, _Entry] = {}
_LOCK = threading.Lock()
_HITS = 0
_MISSES = 0


CACHE_CONTRACT = "public-discovery-packet/v2"


def research_cache_key(*, query: str, provider_id: str, max_results: int) -> str:
    """Identity of the actual eligible provider request, without lossy folding.

    The caller must establish public-only provenance before constructing a key.
    JSON preserves field boundaries; query case, order and punctuation remain
    significant unless the provider's own query builder already normalized them.
    """
    material = json.dumps(
        [CACHE_CONTRACT, query, provider_id, max_results], ensure_ascii=False
    )
    return f"{CACHE_CONTRACT}:" + hashlib.sha256(material.encode()).hexdigest()


class SearchPacketCache:
    """One identity for both reads and writes of an eligible search request."""

    def __init__(self, *, query: str, provider_id: str, max_results: int) -> None:
        # The direct Search API receives only query and result limit. Model-backed
        # adapters have further configuration and need their own identity contract.
        self._key = (
            research_cache_key(
                query=query, provider_id=provider_id, max_results=max_results
            )
            if provider_id == "perplexity_direct"
            else None
        )

    def get(self) -> SearchResultPacket | None:
        return cache_get(self._key) if self._key is not None else None

    def put(self, packet: SearchResultPacket) -> None:
        if self._key is None:
            return
        cache_put(
            self._key,
            packet,
            ttl_seconds=ttl_for_packet(question_kind="find_assets"),
        )


def cache_get(key: str) -> SearchResultPacket | None:
    global _HITS, _MISSES
    if not key.startswith(f"{CACHE_CONTRACT}:"):
        return None
    now = time.monotonic()
    with _LOCK:
        entry = _CACHE.get(key)
        if entry is None:
            _MISSES += 1
            return None
        if now - entry.stored_at > entry.ttl_seconds:
            del _CACHE[key]
            _MISSES += 1
            return None
        _HITS += 1
        return entry.packet


def cache_put(key: str, packet: SearchResultPacket, *, ttl_seconds: float) -> None:
    if (
        ttl_seconds <= 0
        or not key.startswith(f"{CACHE_CONTRACT}:")
        or not isinstance(packet, SearchResultPacket)
    ):
        return
    with _LOCK:
        if len(_CACHE) >= _MAX_ENTRIES:
            oldest = min(_CACHE.items(), key=lambda item: item[1].stored_at)[0]
            del _CACHE[oldest]
        _CACHE[key] = _Entry(
            packet=packet, stored_at=time.monotonic(), ttl_seconds=ttl_seconds
        )


def cache_stats() -> dict[str, int]:
    with _LOCK:
        return {"entries": len(_CACHE), "hits": _HITS, "misses": _MISSES}


def cache_clear() -> None:
    """Test seam."""
    global _HITS, _MISSES
    with _LOCK:
        _CACHE.clear()
        _HITS = 0
        _MISSES = 0
