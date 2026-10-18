"""The one owner of user-facing reply punctuation at the point it becomes visible.

Argus never shows an em dash in user-facing copy, in any language
(AGENTS.md "Copy", founder-locked 2026-08-04). Model-written
replies reach the user through two doors, the live SSE frames and the
persisted assistant message, and both pass through here. A rewrite is
recorded on the turn so a model that keeps writing em dashes stays visible.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from loguru import logger

EM_DASH = "—"

_CLOSING_PUNCTUATION = ".,;:!?"
# A dash set directly between two figures, no space on either side, is the
# model's range notation ("5%—10%", "$1,000—$2,000"); a comma would change
# the fact, so the range keeps a hyphen in every language.


def _is_figure_char(char: str) -> bool:
    """A digit, any currency sign (Unicode category Sc) or a percent-like
    sign; a figure may open or close on any of them ("$1,000", "1.000€",
    "5%")."""
    return (
        char.isdigit()
        or unicodedata.category(char) == "Sc"
        or unicodedata.name(char, "").endswith(("PERCENT SIGN", "PER MILLE SIGN"))
    )


@dataclass(frozen=True)
class VisibleReply:
    text: str | None
    em_dash_count: int


def rewrite_visible_reply(
    text: str | None,
    *,
    surface: str,
    trailing: str = "sentence",
    left_tail: str = "",
) -> VisibleReply:
    """Replace every em dash with the comma the copy rule asks for, or the
    hyphen of a numeric range.

    ``trailing`` says what a dash with nothing after it means: the end of a
    whole reply ("sentence") or the end of a streamed token ("clause") whose
    continuation arrives in the next frame. ``left_tail`` is text already
    shown before this piece, so a dash at the start of a stream chunk is
    joined to the word that preceded it exactly as the whole reply would be.
    """
    if not isinstance(text, str) or EM_DASH not in text:
        return VisibleReply(text=text, em_dash_count=0)
    count = text.count(EM_DASH)
    rewritten = _without_em_dashes(text, trailing=trailing, left_tail=left_tail)
    logger.info(
        "Visible reply em dash rewritten surface={} count={}",
        surface,
        count,
        surface=surface,
        em_dash_count=count,
    )
    return VisibleReply(text=rewritten, em_dash_count=count)


def _without_em_dashes(text: str, *, trailing: str, left_tail: str = "") -> str:
    # A run of dashes with nothing but spaces between them is one dash: the
    # blank between them is not the end of anything, so the stream and the
    # final reply read it the same.
    split = text.split(EM_DASH)
    pieces = [
        split[0],
        *(piece for piece in split[1:-1] if piece.strip(" ")),
        *split[1:][-1:],
    ]
    result = pieces[0]
    for piece in pieces[1:]:
        raw_left = result or left_tail
        if (
            raw_left
            and piece
            and _is_figure_char(raw_left[-1])
            and _is_figure_char(piece[0])
        ):
            result = f"{result}-{piece}"
            continue
        left = result.rstrip(" ")
        # What the dash follows: this piece's own text, or the text already
        # shown when the dash opens a stream chunk.
        preceding = left or left_tail.rstrip(" ")
        right = piece.lstrip(" ")
        if not preceding or preceding.endswith("\n"):
            result = f"{left}{right}"
        elif not right or right.startswith("\n"):
            closer = "," if trailing == "clause" and not right else "."
            if not preceding.endswith(tuple(_CLOSING_PUNCTUATION)):
                left = f"{left}{closer}"
            result = f"{left}{right}"
        elif (
            preceding.endswith(tuple(_CLOSING_PUNCTUATION))
            or right[0] in _CLOSING_PUNCTUATION
        ):
            result = f"{left} {right}"
        else:
            result = f"{left}, {right}"
    return result
