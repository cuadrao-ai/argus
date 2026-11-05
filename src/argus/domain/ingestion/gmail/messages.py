"""One Gmail message id to one candidate, or a counted reason to skip it.

Order keeps content private until it is known to be relevant:

1. ``format=metadata`` with only ``From`` and ``Authentication-Results``.
2. Skip spam, trash and drafts; skip senders outside the allowlist; skip
   messages whose sender domain Gmail did not authenticate.
3. Only then ``format=full``, MIME parsing, and attachment fetches for allowed
   types under the size cap.

The candidate's ``external_id`` is the Gmail message id on every path, so the
same message seen by the initial scan, by history, by a retry or by a second
sync is one observation to the sink.

A message or attachment Gmail refuses on its own (deleted, oversized,
malformed, another per-item 4xx) is a counted skip, so one bad item can never
stall the mailbox: the cursor moves past it. Auth refusals, rate limits and
outages still fail the whole sync without moving the cursor.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Literal

from loguru import logger

from argus.domain.ingestion.contract import Attachment, ImportCandidate
from argus.domain.ingestion.gmail import attachments as files
from argus.domain.ingestion.gmail.authenticity import sender_authenticated
from argus.domain.ingestion.gmail.client import GmailClient, GmailError
from argus.domain.ingestion.gmail.extract import EmailExtractor, build_candidate
from argus.domain.ingestion.gmail.failures import message_skip
from argus.domain.ingestion.gmail.mime import first_header, headers_of, parse_message
from argus.domain.ingestion.gmail.senders import (
    SenderRule,
    domain_of,
    from_address,
    matches,
)

METADATA_HEADERS = ("From", "Authentication-Results")
HIDDEN_LABELS = frozenset({"SPAM", "TRASH", "DRAFT"})

Skip = Literal[
    "gone",
    "hidden_label",
    "not_allowlisted",
    "unverified_sender",
    "unreadable",
    "too_large",
]


@dataclass
class ReadTally:
    candidates: list[ImportCandidate] = field(default_factory=list)
    skipped: Counter = field(default_factory=Counter)
    attachments: int = 0
    attachments_skipped: Counter = field(default_factory=Counter)


class MessageReader:
    def __init__(self, client: GmailClient, extractor: EmailExtractor) -> None:
        self.client = client
        self.extractor = extractor

    def read_all(
        self,
        access: str,
        message_ids: list[str],
        *,
        rules: list[SenderRule],
        connection_id: str,
    ) -> ReadTally:
        tally = ReadTally()
        for message_id in dict.fromkeys(message_ids):
            outcome = self.read(
                access, message_id, rules=rules, connection_id=connection_id, tally=tally
            )
            if isinstance(outcome, ImportCandidate):
                tally.candidates.append(outcome)
            else:
                tally.skipped[outcome] += 1
        return tally

    def read(
        self,
        access: str,
        message_id: str,
        *,
        rules: list[SenderRule],
        connection_id: str,
        tally: ReadTally,
    ) -> ImportCandidate | Skip:
        try:
            return self._read(access, message_id, rules, connection_id, tally)
        except GmailError as exc:
            skip = message_skip(exc)
            if skip is None:
                raise  # auth, rate limit, outage: the whole sync fails
            logger.info("Skipped a Gmail message", skip=skip, reason=exc.reason)
            return skip
        except ValueError as exc:
            logger.warning(
                "Skipped a Gmail message the contract refuses",
                failure_mode=type(exc).__name__,
            )
            return "unreadable"

    def _read(
        self,
        access: str,
        message_id: str,
        rules: list[SenderRule],
        connection_id: str,
        tally: ReadTally,
    ) -> ImportCandidate | Skip:
        meta = self.client.get_message(
            access, message_id, fmt="metadata", headers=METADATA_HEADERS
        )
        labels = set(meta.get("labelIds") or ())
        if labels & HIDDEN_LABELS:
            return "hidden_label"
        headers = headers_of(meta.get("payload") or {})
        sender = from_address(first_header(headers, "From"))
        if matches(sender, rules) is None:
            return "not_allowlisted"
        if not sender_authenticated(headers, domain_of(sender) if sender else None):
            return "unverified_sender"
        full = self.client.get_message(access, message_id, fmt="full")
        email = parse_message(full)
        facts = self.extractor.extract(email)
        refs = self._attachments(access, email.message_id, email.attachments, tally)
        return build_candidate(
            email, facts, connection_id=connection_id, attachments=refs
        )

    def _attachments(
        self, access: str, message_id: str, parts: tuple, tally: ReadTally
    ) -> tuple[Attachment, ...]:
        refs: list[Attachment] = []
        for decision in files.admissible(parts):
            if decision.skip is not None:
                tally.attachments_skipped[decision.skip] += 1
                continue
            part = decision.part
            if part.inline_data is not None:
                data = part.inline_data
            elif part.attachment_id:
                try:
                    data = self.client.get_attachment(
                        access,
                        message_id,
                        part.attachment_id,
                        max_bytes=files.MAX_ATTACHMENT_BYTES,
                    )
                except GmailError as exc:
                    skip = message_skip(exc)
                    if skip is None:
                        raise
                    tally.attachments_skipped[
                        "too_large" if skip == "too_large" else "unreadable"
                    ] += 1
                    continue
            else:
                tally.attachments_skipped["empty"] += 1
                continue
            result = files.reference(message_id, part, data)
            del data
            if isinstance(result, Attachment):
                refs.append(result)
                tally.attachments += 1
            else:
                tally.attachments_skipped[result] += 1
        return tuple(refs)
