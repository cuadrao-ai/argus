"""Sender suggestions from headers only, on the person's explicit request.

Reads ``From`` and ``Authentication-Results`` of a bounded number of recent
messages (``format=metadata``; no body is fetched), and returns the most
frequent senders not already allowed, with whether Gmail authenticated them.
It does not guess which senders are banks: the person chooses. Nothing here is
stored or logged.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from argus.domain.ingestion.gmail.authenticity import sender_authenticated
from argus.domain.ingestion.gmail.client import GmailClient, GmailError
from argus.domain.ingestion.gmail.messages import METADATA_HEADERS
from argus.domain.ingestion.gmail.mime import first_header, headers_of
from argus.domain.ingestion.gmail.senders import (
    SenderRule,
    domain_of,
    from_address,
    matches,
)

SUGGESTION_DAYS = 60
SUGGESTION_MESSAGES = 50
MAX_SUGGESTIONS = 15
_QUERY = f"newer_than:{SUGGESTION_DAYS}d -in:chats -in:sent -in:drafts"


@dataclass(frozen=True)
class SenderSuggestion:
    sender: str
    domain: str
    messages: int
    authenticated: bool


def suggest_senders(
    client: GmailClient, access: str, rules: list[SenderRule]
) -> list[SenderSuggestion]:
    page = client.list_messages(
        access, query=_QUERY, page_token=None, max_results=SUGGESTION_MESSAGES
    )
    counts: Counter[str] = Counter()
    verified: dict[str, bool] = {}
    for item in (page.get("messages") or ())[:SUGGESTION_MESSAGES]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            continue
        try:
            meta = client.get_message(
                access, item["id"], fmt="metadata", headers=METADATA_HEADERS
            )
        except GmailError as exc:
            if exc.status == 404:
                continue
            raise
        headers = headers_of(meta.get("payload") or {})
        sender = from_address(first_header(headers, "From"))
        if sender is None or matches(sender, rules) is not None:
            continue
        counts[sender] += 1
        verified[sender] = verified.get(sender, False) or sender_authenticated(
            headers, domain_of(sender)
        )
    ranked = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    return [
        SenderSuggestion(sender, domain_of(sender), count, verified[sender])
        for sender, count in ranked[:MAX_SUGGESTIONS]
    ]
