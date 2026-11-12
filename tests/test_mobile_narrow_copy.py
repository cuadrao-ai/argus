"""Backend-owned narrow-screen copy for the mobile shell.

The backend owns user-facing copy, so a narrow screen gets a shorter Try next
label and a shorter generated title composed here, never clipped in the client.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from argus.api.naming import (
    NARROW_TITLE_MAX_WORDS,
    WIDE_TITLE_MAX_WORDS,
    title_word_budget,
)
from argus.api.schemas import ChatStreamRequest

LANGUAGES = ("en", "es-419")
_LABEL_PREFIX = "chat.next_experiments.labels."
_LOCALES = Path(__file__).resolve().parents[1] / "web" / "public" / "locales"
















def test_narrow_titles_are_generated_short_not_clipped() -> None:
    assert title_word_budget("narrow") == NARROW_TITLE_MAX_WORDS
    assert title_word_budget("wide") == WIDE_TITLE_MAX_WORDS
    assert title_word_budget(None) == WIDE_TITLE_MAX_WORDS
    assert NARROW_TITLE_MAX_WORDS < WIDE_TITLE_MAX_WORDS


def test_turn_request_carries_an_optional_viewport_band() -> None:
    assert ChatStreamRequest(conversation_id="c1", message="hi").viewport is None
    assert (
        ChatStreamRequest(conversation_id="c1", message="hi", viewport="narrow").viewport
        == "narrow"
    )
    with pytest.raises(ValueError):
        ChatStreamRequest(conversation_id="c1", message="hi", viewport="phone")
