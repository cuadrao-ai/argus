"""The documented research sidecar has to be the one the runtime emits.

The example in `docs/API_CONTRACT.md` declared `sources` as an array of URL
strings long after the runtime started emitting typed source objects. Prose
two sections below described the object shape correctly, so the contract was
right in one place and wrong in another, and a client generated from the
example would reject every real payload.

String assertions over the document are what let that happen: they check the
words, never the shape. These parse the canonical example and hold it against
the runtime's own models and its own key set instead.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from argus.domain.research.contracts import ResearchSource

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs" / "API_CONTRACT.md"

# Emitted only when a turn degraded, so it is absent from a healthy sidecar
# while the example carries it to document the shape.
CONDITIONAL_KEYS = {"degraded"}


def documented_sidecar() -> dict[str, Any]:
    """The canonical `research` example, parsed as JSON rather than matched."""
    text = CONTRACT.read_text(encoding="utf-8")
    marker = '"schema_version": "argus_research/v1"'
    at = text.index(marker)
    start = text.rindex("```json", 0, at) + len("```json")
    end = text.index("```", start)
    return json.loads(text[start:end])["research"]


def test_the_documented_sources_are_the_typed_model() -> None:
    """Every documented citation has to validate as the model the runtime
    emits, which is what makes a generated client work against real traffic."""
    sources = documented_sidecar()["sources"]
    assert sources, "the example must show at least one source"
    for entry in sources:
        assert isinstance(entry, dict), (
            "sources carries objects, not URL strings; a string array here is "
            "the defect this test exists for"
        )
        source = ResearchSource.model_validate(entry)
        assert source.url
        assert set(entry) <= set(ResearchSource.model_fields) | {"domain"}
