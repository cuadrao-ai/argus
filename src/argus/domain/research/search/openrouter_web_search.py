from __future__ import annotations

import time
from datetime import datetime, timezone
from functools import partial
from typing import Any

import httpx

from argus.domain.research.search.contracts import (
    MAX_RESULTS,
    SearchResult,
    SearchResultPacket,
    SearchUnavailableError,
    sanitize_search_result,
)
from argus.domain.research.search.http_post import post_json
from argus.llm.openrouter_retention import (
    check_retention_response,
    openrouter_provider_policy,
    raise_for_retention_error,
)

OPENROUTER_CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"
_CLAIM_ABBREVIATIONS = frozenset(
    (
        "a.g.",
        "c.v.",
        "co.",
        "corp.",
        "inc.",
        "l.p.",
        "ltd.",
        "n.v.",
        "s.a.",
        "s.p.a.",
    )
)


class OpenRouterWebSearchProvider:
    """Thin single-attempt adapter for OpenRouter's web plugin.

    Shape confirmed against the official plugin docs on 2026-07-26:
    `plugins: [{"id": "web", "max_results": N}]` on chat completions; citations
    arrive as `choices[0].message.annotations[].url_citation{url, title,
    content}` with no source-date guarantee. This supersedes the eval
    scaffold's beta `openrouter:web_search` server-tool assumption.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        transport: httpx.BaseTransport | None = None,
        endpoint: str = OPENROUTER_CHAT_COMPLETIONS_URL,
    ) -> None:
        self._api_key = api_key.strip()
        self._model = model.strip()
        self._transport = transport
        self._endpoint = endpoint

    def search(
        self, query: str, *, max_results: int, timeout_seconds: float
    ) -> SearchResultPacket:
        self.require_configured()
        bounded_results = max(1, min(int(max_results), MAX_RESULTS))
        started = time.monotonic()
        payload = post_json(
            endpoint=self._endpoint,
            transport=self._transport,
            timeout_seconds=timeout_seconds,
            headers={"Authorization": f"Bearer {self._api_key}"},
            check_response=partial(check_retention_response, model=self._model),
            body={
                "model": self._model,
                "provider": openrouter_provider_policy(),
                "messages": [{"role": "user", "content": query}],
                "plugins": [{"id": "web", "max_results": bounded_results}],
            },
        )
        raise_for_retention_error(self._model, None, payload)
        latency_ms = int((time.monotonic() - started) * 1000)
        return SearchResultPacket(
            results=_sanitized_citations(payload),
            retrieved_at=datetime.now(timezone.utc),
            latency_ms=latency_ms,
            provider_id="openrouter_web_search",
            cost_usd=_reported_cost(payload),
        )

    def require_configured(self) -> None:
        """Fail before admission when this adapter cannot make a request."""
        if not self._api_key or not self._model:
            raise SearchUnavailableError(reason="not_configured")


def _message(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        choices = payload.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            message = choices[0].get("message")
            if isinstance(message, dict):
                return message
    raise SearchUnavailableError(reason="malformed_response")


def _sanitized_citations(payload: Any) -> list[SearchResult]:
    message = _message(payload)
    annotations = message.get("annotations")
    if not isinstance(annotations, list):
        annotations = []
    message_content = message.get("content")
    if not isinstance(message_content, str):
        message_content = ""
    sanitized: list[SearchResult] = []
    claim_floor = 0
    citation_group_start: int | None = None
    previous_citation_end: int | None = None
    for annotation in annotations:
        if not isinstance(annotation, dict):
            continue
        citation = annotation.get("url_citation", annotation)
        if not isinstance(citation, dict):
            continue
        citation_span = _citation_span(message_content, citation)
        if citation_span is not None:
            citation_start, _ = citation_span
            citation_separator = message_content[
                previous_citation_end or 0 : citation_start
            ]
            starts_new_group = (
                previous_citation_end is None
                or citation_start < previous_citation_end
                or not _continues_citation_group(citation_separator)
            )
            if starts_new_group:
                claim_floor = (
                    previous_citation_end
                    if previous_citation_end is not None
                    and previous_citation_end <= citation_start
                    else 0
                )
                citation_group_start = citation_start
        result = sanitize_search_result(
            title=str(citation.get("title") or ""),
            url=str(citation.get("url") or ""),
            snippet=str(citation.get("content") or "")
            or _cited_message_context(
                message_content,
                citation,
                previous_citation_end=claim_floor,
                claim_end_index=citation_group_start,
            ),
            source_date=None,
        )
        if result is not None:
            sanitized.append(result)
        if citation_span is not None:
            previous_citation_end = max(previous_citation_end or 0, citation_span[1])
    return sanitized


def _continues_citation_group(separator: str) -> bool:
    words = "".join(
        character.casefold() if character.isalnum() else " " for character in separator
    ).split()
    return not words or words in (["and"], ["y"])


def _citation_span(content: str, citation: dict[str, Any]) -> tuple[int, int] | None:
    start = citation.get("start_index")
    end = citation.get("end_index")
    if (
        isinstance(start, bool)
        or isinstance(end, bool)
        or not isinstance(start, int)
        or not isinstance(end, int)
        or start < 0
        or end < start
        or end > len(content)
    ):
        return None
    return start, end


def _is_dotted_name_prefix(token: str, *, preceding_text: str) -> bool:
    if token.casefold() in _CLAIM_ABBREVIATIONS:
        return False
    parts = token.strip("([{\"'").rstrip(".").split(".")
    dotted_initials = len(parts) >= 2 and all(
        len(part) == 1 and part.isalpha() and part.isupper() for part in parts
    )
    if not dotted_initials:
        return False
    previous_break = max(
        preceding_text.rfind(separator, 0, len(preceding_text) - 1)
        for separator in ("\n", "! ", "? ", "; ", ". ")
    )
    separator_width = (
        0 if previous_break < 0 else 1 if preceding_text[previous_break] == "\n" else 2
    )
    claim_prefix = preceding_text[previous_break + separator_width :].strip(" -*•")
    return claim_prefix == token


def _starts_lowercase_styled_name(text: str, *, citation_title: str = "") -> bool:
    token = text.split(maxsplit=1)[0].strip("([{\"'")
    core = token.rstrip(".,;:!?")
    domain_parts = core.split(".")
    title_token = citation_title.split(maxsplit=1)[0].strip("([{\"'")
    title_core = title_token.rstrip(".,;:!?")
    return (
        bool(core)
        and core[0].islower()
        and (
            any(character.isupper() for character in core[1:])
            or (len(domain_parts) >= 2 and any(len(part) > 1 for part in domain_parts))
            or (core.islower() and title_core == core)
        )
    )


def _cited_message_context(
    content: str,
    citation: dict[str, Any],
    *,
    previous_citation_end: int = 0,
    claim_end_index: int | None = None,
) -> str:
    """Recover only the claim structurally attached to a citation marker."""
    span = _citation_span(content, citation)
    if span is None:
        return ""
    start, end = span
    annotated = content[start:end].strip()
    citation_url = str(citation.get("url") or "").strip()
    if not citation_url or citation_url not in annotated:
        return annotated
    claim_floor = previous_citation_end if previous_citation_end <= start else 0
    claim_end = (
        claim_end_index
        if claim_end_index is not None and claim_floor <= claim_end_index <= start
        else start
    )
    line_start = content.rfind("\n", claim_floor, claim_end) + 1
    claim_start = max(claim_floor, line_start, claim_end - 400)
    claim = content[claim_start:claim_end].strip()
    boundary_text = claim[:-1] if claim.endswith((".", "!", "?", ";")) else claim
    claim_break = max(
        boundary_text.rfind(separator) for separator in ("\n", "! ", "? ", "; ")
    )
    period_search_end = len(boundary_text)
    while (period_break := boundary_text.rfind(". ", 0, period_search_end)) >= 0:
        preceding_token = boundary_text[: period_break + 1].rsplit(maxsplit=1)[-1]
        following_text = boundary_text[period_break + 2 :].lstrip()
        starts_new_claim = (
            preceding_token.casefold() not in _CLAIM_ABBREVIATIONS
            or not following_text
            or not following_text[0].islower()
            or _starts_lowercase_styled_name(
                following_text,
                citation_title=str(citation.get("title") or ""),
            )
        )
        if starts_new_claim and not _is_dotted_name_prefix(
            preceding_token,
            preceding_text=boundary_text[: period_break + 1],
        ):
            claim_break = max(claim_break, period_break)
            break
        period_search_end = period_break
    if claim_break < 0:
        return claim
    separator_width = 1 if boundary_text[claim_break] == "\n" else 2
    return claim[claim_break + separator_width :].strip()


def _reported_cost(payload: Any) -> float | None:
    if not isinstance(payload, dict):
        return None
    usage = payload.get("usage")
    if not isinstance(usage, dict) or usage.get("cost") is None:
        return None
    try:
        cost = float(usage["cost"])
    except (TypeError, ValueError):
        return None
    return cost if cost >= 0 else None
