"""What an email may claim, and the default that claims almost nothing.

``EmailExtractor`` is the seam for a future content extractor. It returns
``EmailFacts``: the contract fields it is willing to assert plus what it is
unsure of. It cannot touch source identity, observation time, the excerpt or
attachments; ``build_candidate`` owns those from the message itself, so no
extractor can relabel where evidence came from.

The shipped ``UnreviewedEmailExtractor`` interprets nothing. The kind of
evidence cannot be known without reading the message, so it emits
``unclassified``: the contract then requires the person to say what it is and
to supply amount, currency, date, direction and account before anything can
become activity. Reading content (amounts, due dates, statement periods) is a
separate, measured step that needs founder authorization: a paid model and a
committed scorecard (AGENTS.md Never-Violate 12).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from argus.domain.ingestion.contract import (
    AccountHint,
    Attachment,
    BalanceScope,
    Direction,
    EvidenceKind,
    ImportCandidate,
    KindHint,
    ObservedStatus,
    SourceRef,
    UncertainField,
)
from argus.domain.ingestion.gmail.mime import ParsedEmail

EXCERPT_SOURCE_CHARS = 1000


@dataclass(frozen=True)
class EmailFacts:
    evidence: EvidenceKind = "unclassified"
    status: ObservedStatus = "unknown"
    account: AccountHint = AccountHint()
    occurred_on: date | None = None
    posted_on: date | None = None
    amount: str | None = None
    currency: str | None = None
    direction: Direction = "unknown"
    kind_hint: KindHint = "unknown"
    merchant: str | None = None
    description: str | None = None
    balance_scope: BalanceScope | None = None
    due_on: date | None = None
    period_start: date | None = None
    period_end: date | None = None
    uncertain: frozenset[UncertainField] = frozenset()


class EmailExtractor(Protocol):
    name: str

    def extract(self, email: ParsedEmail) -> EmailFacts:
        """Contract fields this extractor asserts, with its doubts listed."""
        ...


class UnreviewedEmailExtractor:
    """Machine-certain facts only: who sent it. Everything else is review."""

    name = "unreviewed"

    def extract(self, email: ParsedEmail) -> EmailFacts:
        return EmailFacts(
            evidence="unclassified",
            account=AccountHint(institution=email.sender_domain),
        )


def excerpt_of(email: ParsedEmail) -> str | None:
    pieces = [p for p in (email.subject, email.text) if p and p.strip()]
    if not pieces:
        return None
    # The contract makes it inert and caps it; this only bounds the copy.
    return " · ".join(pieces)[:EXCERPT_SOURCE_CHARS]


def build_candidate(
    email: ParsedEmail,
    facts: EmailFacts,
    *,
    connection_id: str,
    attachments: tuple[Attachment, ...],
) -> ImportCandidate:
    return ImportCandidate(
        source=SourceRef(
            source="gmail",
            connection_id=connection_id,
            external_id=email.message_id,
            observed_at=email.received_at,
        ),
        evidence=facts.evidence,
        status=facts.status,
        account=facts.account,
        occurred_on=facts.occurred_on,
        posted_on=facts.posted_on,
        amount=facts.amount,
        currency=facts.currency,
        direction=facts.direction,
        kind_hint=facts.kind_hint,
        merchant=facts.merchant,
        description=facts.description,
        balance_scope=facts.balance_scope,
        due_on=facts.due_on,
        period_start=facts.period_start,
        period_end=facts.period_end,
        excerpt=excerpt_of(email),
        attachments=attachments,
        uncertain=facts.uncertain,
    )
