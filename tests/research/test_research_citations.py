"""Citations reach the panel, from the channels the provider actually uses.

These run against a real captured Agent API response, not a hand-written
fixture, because the defect they cover was a channel nobody had looked at:
web search citations arrive in their own output items (and, for some models,
as annotations on the answer chunk), while only the finance channel had been
read. Argus discarded 45 publisher URLs and then told the reader there were
no source links to open.
"""

from __future__ import annotations

import json
from pathlib import Path

from argus.domain.research.perplexity_agent import _packet_from_response

from tests.research.conftest import agent_response

PROBES = Path(__file__).resolve().parents[2] / "docs/reports/evidence/377/probes"


def _probe(name: str) -> dict:
    document = json.loads((PROBES / f"{name}.json").read_text(encoding="utf-8"))
    return document.get("response", document)




def test_provider_identity_never_becomes_a_citation() -> None:
    """finance_search cites its own provider pages; those stay scrubbed even
    now that the other channels are read."""
    for name in ("etf_spy_constituents_steps3", "equity_steps2"):
        packet = _packet_from_response(_probe(name), latency_ms=10)
        for source in packet.sources:
            assert "perplexity.ai" not in source.url










def test_packet_retains_sources_beyond_the_public_drawer_cap() -> None:
    """Selection happens after parsing, so early repeats from one publisher
    cannot erase later outlets before publisher deduplication runs."""
    document = agent_response(sources=[])
    search_results = {
        "type": "search_results",
        "results": [
            {
                "url": f"https://publisher-{index}.example/story",
                "title": f"Publisher {index}",
                "date": "2026-08-12",
            }
            for index in range(7)
        ],
    }
    document["output"].insert(1, search_results)

    packet = _packet_from_response(document, latency_ms=10)

    assert len(packet.sources) == 7
