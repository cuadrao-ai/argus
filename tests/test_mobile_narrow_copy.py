"""The retained shared stream request accepts the shell's viewport band."""

from __future__ import annotations

import pytest
from argus.api.schemas import ChatStreamRequest


def test_turn_request_carries_an_optional_viewport_band() -> None:
    assert ChatStreamRequest(conversation_id="c1", message="hi").viewport is None
    assert (
        ChatStreamRequest(conversation_id="c1", message="hi", viewport="narrow").viewport
        == "narrow"
    )
    with pytest.raises(ValueError):
        ChatStreamRequest(conversation_id="c1", message="hi", viewport="phone")
