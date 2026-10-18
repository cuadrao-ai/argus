"""Receipt alias shape, name suggestion, and the only availability checker."""

from __future__ import annotations

import secrets
import unicodedata
from collections.abc import Callable

from argus.domain.ingestion.email_intake.words import (
    ALLOW_WORDS,
    ANYWHERE_WORDS,
    SYSTEM_WORDS,
)

ALIAS_UNAVAILABLE = "Ese nombre no está disponible. Prueba otro."
_LEGAL = frozenset({"srl", "eirl", "sas", "sa", "cia", "cxa", "ltda", "inc"})
_DIGIT = {"0": "o", "3": "e", "4": "a", "5": "s"}
_SUFFIXES = ("rd", "do", "norte", "sur", "centro", "este", "oeste", "dos", "tres")


def strip_marks(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def storage_form(alias: str) -> str | None:
    cleaned = strip_marks(alias.strip().lower())
    if not cleaned or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789-" for ch in cleaned):
        return None
    if not 3 <= len(cleaned) <= 32:
        return None
    return cleaned


def suggest_alias(name: str) -> str:
    text = strip_marks(name.strip().lower())
    text = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text)
    tokens = [token for token in text.split() if token]
    while tokens and tokens[-1] in _LEGAL:
        tokens.pop()
    while len(tokens) >= 3 and tokens[-3:] == ["s", "r", "l"]:
        tokens = tokens[:-3]
    while len(tokens) >= 4 and tokens[-4:] == ["e", "i", "r", "l"]:
        tokens = tokens[:-4]
    while len(tokens) >= 2 and tokens[-2:] == ["s", "a"]:
        tokens = tokens[:-2]
    joined = "".join(ch for ch in "".join(tokens) if ch.isalnum())[:32]
    if len(joined) < 3:
        joined = (joined + "negocio")[:32]
    return joined


def fold_variants(text: str) -> tuple[str, ...]:
    base = "".join(_DIGIT.get(ch, ch) for ch in text)
    ones = [index for index, ch in enumerate(base) if ch == "1"]
    if not ones:
        return (base,)
    ones = ones[:8]
    variants = []
    for mask in range(1 << len(ones)):
        chars = list(base)
        for bit, index in enumerate(ones):
            chars[index] = "i" if mask & (1 << bit) else "l"
        variants.append("".join(chars))
    return tuple(variants)


def _mask_allow(text: str) -> str:
    chars = list(text)
    for word in sorted(ALLOW_WORDS, key=len, reverse=True):
        start = 0
        while True:
            index = text.find(word, start)
            if index < 0:
                break
            for offset in range(len(word)):
                chars[index + offset] = " "
            start = index + len(word)
    return "".join(chars)


def variant_hits(folded: str) -> bool:
    if folded in SYSTEM_WORDS:
        return True
    masked = _mask_allow(folded)
    return any(word in masked for word in ANYWHERE_WORDS)


def judge_normalized(alias: str, *, taken: bool) -> str:
    if taken:
        return "refused"
    hits = [variant_hits(variant) for variant in fold_variants(alias)]
    if any(hits) and all(hits):
        return "refused"
    if any(hits):
        return "review"
    return "available"


def _with_tail(base: str, tail: str) -> str | None:
    if not tail or len(tail) >= 30:
        return None
    candidate = base[: 32 - len(tail)] + tail
    if storage_form(candidate) != candidate:
        return None
    return candidate


def name_candidates(base: str) -> list[str]:
    """Name-based chips: the name, a number, a city, then the older suffixes."""

    tails = ("2", "3", "-santiago", "-santodomingo", "-lavega", *_SUFFIXES)
    found: list[str] = []
    seen: set[str] = set()
    for candidate in (base, *(_with_tail(base, tail) for tail in tails)):
        if candidate and candidate not in seen:
            seen.add(candidate)
            found.append(candidate)
    return found


def free_suggestions(
    base: str,
    taken: Callable[[str], bool],
    *,
    count: int = 3,
    code: Callable[[], str] | None = None,
) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for candidate in name_candidates(base):
        if candidate in seen:
            continue
        seen.add(candidate)
        if judge_normalized(candidate, taken=taken(candidate)) == "available":
            found.append(candidate)
        if len(found) == count:
            return found
    if found:
        return found
    spare = code or (lambda: secrets.token_hex(3))
    for _ in range(12):
        if len(found) == count:
            break
        candidate = _with_tail(base, spare())
        if candidate is None or candidate in seen:
            continue
        seen.add(candidate)
        if judge_normalized(candidate, taken=taken(candidate)) == "available":
            found.append(candidate)
    return found


def inspect_alias(raw: str, taken: Callable[[str], bool]) -> dict:
    alias = storage_form(raw)
    if alias is None:
        return {
            "status": "invalid",
            "alias": None,
            "available": False,
            "review_required": False,
            "suggestions": [],
            "message": None,
        }
    verdict = judge_normalized(alias, taken=taken(alias))
    available = verdict in {"available", "review"}
    return {
        "status": verdict,
        "alias": alias,
        "available": available,
        "review_required": verdict == "review",
        "suggestions": free_suggestions(alias, taken),
        "message": None if available else ALIAS_UNAVAILABLE,
    }
