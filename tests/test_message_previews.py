from __future__ import annotations

from argus.api.chat.previews import stored_message_preview as message_preview


def test_message_preview_renders_markdown_as_plain_text() -> None:
    preview = message_preview(
        "**Quick take**\n\n"
        "A buy-and-hold on BTC returned 75.1%.\n\n"
        "- **Tested:** Buy BTC and hold.\n"
        "- **Next check:** Try RSI."
    )

    assert preview == (
        "Quick take A buy-and-hold on BTC returned 75.1%. "
        "Tested: Buy BTC and hold. Next check: Try RSI."
    )
    assert "**" not in preview
    assert "\n" not in preview


def test_message_preview_keeps_markdown_punctuation_tight() -> None:
    preview = message_preview(
        "For the long haul, the simplest strategy is **buy and hold**. "
        "It means buying an asset and sitting tight."
    )

    assert preview == (
        "For the long haul, the simplest strategy is buy and hold. "
        "It means buying an asset and sitting tight."
    )
    assert "hold ." not in preview


def test_message_preview_returns_none_for_markdown_without_visible_text() -> None:
    assert message_preview("   \n\n") is None
