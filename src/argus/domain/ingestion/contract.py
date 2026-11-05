"""The shared import-candidate contract every connector emits.

A candidate is *evidence*, never a conclusion. It says what one source observed
about one real-world fact (a card authorization, a posted transaction, a due-date
notice, an as-of balance). The reconciliation owner decides whether several
candidates describe the same event and, only after the person reviews, writes
canonical activity through ``MoneyService``.

Rules this model enforces so every connector inherits them:

- Source identity is explicit: ``source`` + ``connection_id`` + ``external_id``
  name one observation, and the same triple re-delivered is the same evidence.
- Missing is ``None``; doubtful is listed in ``uncertain``. Nothing is guessed.
  An unqualified amount keeps ``currency=None`` instead of assuming DOP or USD.
- Amounts are positive decimal strings plus a ``direction``; minor units are
  computed only at acceptance, once the account's currency is known.
- Free text (merchant, description, excerpt, file names) is untrusted provider
  content. It is normalized to inert display text here, capped, and never
  interpreted as instructions anywhere downstream.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SourceKind = Literal["plaid", "gmail", "shortcuts", "statement"]
SOURCE_KINDS: tuple[SourceKind, ...] = ("plaid", "gmail", "shortcuts", "statement")

# transaction: one money movement was observed (alert, feed row, wallet tap).
# balance: an as-of balance; never activity, and an alert balance is partial.
# statement_period: a statement exists for a period (optionally its closing).
# due_notice: a payment is due; it is not proof that anything was paid.
# payment_notice: the institution says a payment was received or sent.
# unclassified: something financial arrived (an email, a message capture) but
# what it is needs a person or a measured extractor; it is never activity
# until the person says what it is.
EvidenceKind = Literal[
    "transaction",
    "balance",
    "statement_period",
    "due_notice",
    "payment_notice",
    "unclassified",
]
ObservedStatus = Literal["pending", "posted", "unknown", "removed"]
Direction = Literal["outflow", "inflow", "unknown"]
KindHint = Literal[
    "expense", "income", "transfer", "card_payment", "refund", "fee", "unknown"
]
BalanceScope = Literal["available", "current", "statement_closing"]
AccountTypeHint = Literal["depository", "credit", "loan", "investment", "unknown"]
UncertainField = Literal[
    "amount", "currency", "occurred_on", "direction", "merchant", "account", "kind"
]

_EXTERNAL_ID = re.compile(r"^[A-Za-z0-9._:@/+=-]{1,200}$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")
_MASK = re.compile(r"^[0-9]{2,6}$")
_MAX_AMOUNT_DIGITS = 18
_BIDI_AND_INVISIBLE = {
    "​", "‌", "‍", "‎", "‏", "⁠", "﻿",
    "‪", "‫", "‬", "‭", "‮",
    "⁦", "⁧", "⁨", "⁩",
}  # fmt: skip


def inert_text(value: str | None, limit: int) -> str | None:
    """Untrusted provider text as single-line, capped display text.

    Removes control, format (bidi/zero-width) and private-use characters,
    collapses whitespace, and truncates. It does not try to recognize
    "instructions": nothing downstream executes candidate text, so the only job
    here is keeping it bounded and visually honest.
    """

    if value is None:
        return None
    text = unicodedata.normalize("NFKC", str(value))
    kept = []
    for char in text:
        if char in _BIDI_AND_INVISIBLE:
            continue
        category = unicodedata.category(char)
        if category in ("Cc", "Cf", "Co", "Cs"):
            kept.append(" ")
            continue
        kept.append(char)
    cleaned = " ".join("".join(kept).split())
    if not cleaned:
        return None
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1].rstrip() + "…"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SourceRef(_Frozen):
    source: SourceKind
    connection_id: str = Field(min_length=1, max_length=64)
    # Stable per (source, connection): Plaid transaction_id, Gmail message id
    # plus part, Shortcuts device event id, statement file hash plus row.
    external_id: str
    # Provider's own change marker when it has one; informs "is this newer".
    revision: str | None = Field(default=None, max_length=64)
    # This observation supersedes another of the same source (Plaid's posted
    # transaction naming its pending_transaction_id).
    replaces_external_id: str | None = None
    observed_at: datetime

    @field_validator("external_id", "replaces_external_id")
    @classmethod
    def _external(cls, value: str | None) -> str | None:
        if value is not None and not _EXTERNAL_ID.match(value):
            raise ValueError("external ids are 1-200 safe ASCII characters")
        return value

    @field_validator("observed_at")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("observed_at must carry a time zone")
        return value


class AccountHint(_Frozen):
    """What the source says about the account; never a Cuadrao account id.

    Mapping a hint to a ``financial_accounts`` row is a reviewed link owned by
    reconciliation, so a connector can never route money into an account.
    """

    external_account_id: str | None = None
    institution: str | None = None
    name: str | None = None
    mask: str | None = None
    currency: str | None = None
    type_hint: AccountTypeHint = "unknown"

    @field_validator("external_account_id")
    @classmethod
    def _external(cls, value: str | None) -> str | None:
        if value is not None and not _EXTERNAL_ID.match(value):
            raise ValueError("external account ids are 1-200 safe ASCII characters")
        return value

    @field_validator("institution", "name", mode="before")
    @classmethod
    def _label(cls, value: str | None) -> str | None:
        return inert_text(value, 80)

    @field_validator("mask", mode="before")
    @classmethod
    def _mask(cls, value: str | None) -> str | None:
        if value is None:
            return None
        digits = "".join(ch for ch in str(value) if ch.isdigit())[-4:]
        return digits if _MASK.match(digits) else None

    @field_validator("currency", mode="before")
    @classmethod
    def _currency(cls, value: str | None) -> str | None:
        return _currency_code(value)


class Attachment(_Frozen):
    """Reference to a source file; the bytes stay with the source or its
    retention-bounded store, never inside the candidate."""

    external_id: str
    media_type: str = Field(max_length=100)
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    filename: str | None = None

    @field_validator("external_id")
    @classmethod
    def _external(cls, value: str) -> str:
        if not _EXTERNAL_ID.match(value):
            raise ValueError("attachment ids are 1-200 safe ASCII characters")
        return value

    @field_validator("filename", mode="before")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return inert_text(value, 120)


class ImportCandidate(_Frozen):
    source: SourceRef
    evidence: EvidenceKind
    status: ObservedStatus = "unknown"
    account: AccountHint = AccountHint()
    # The day the money moved as the source reports it, in the source's own
    # calendar; occurred_at only when the source gives a real instant.
    occurred_on: date | None = None
    occurred_at: datetime | None = None
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
    excerpt: str | None = None
    attachments: tuple[Attachment, ...] = Field(default=(), max_length=10)
    uncertain: frozenset[UncertainField] = frozenset()

    @field_validator("amount", mode="before")
    @classmethod
    def _amount(cls, value: object) -> str | None:
        if value is None:
            return None
        try:
            number = Decimal(str(value).strip())
        except InvalidOperation:
            raise ValueError("amount must be a plain decimal") from None
        if not number.is_finite() or number < 0:
            raise ValueError("amount is a non-negative magnitude; use direction")
        text = format(number.normalize(), "f")
        if len(text.replace(".", "")) > _MAX_AMOUNT_DIGITS:
            raise ValueError("amount has too many digits")
        return text

    @field_validator("currency", mode="before")
    @classmethod
    def _currency(cls, value: str | None) -> str | None:
        return _currency_code(value)

    @field_validator("merchant", mode="before")
    @classmethod
    def _merchant(cls, value: str | None) -> str | None:
        return inert_text(value, 120)

    @field_validator("description", mode="before")
    @classmethod
    def _description(cls, value: str | None) -> str | None:
        return inert_text(value, 200)

    @field_validator("excerpt", mode="before")
    @classmethod
    def _excerpt(cls, value: str | None) -> str | None:
        return inert_text(value, 280)

    @field_validator("occurred_at")
    @classmethod
    def _aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("occurred_at must carry a time zone")
        return value

    @model_validator(mode="after")
    def _evidence_shape(self) -> ImportCandidate:
        if self.status == "removed":
            return self
        if self.evidence == "balance" and self.balance_scope is None:
            raise ValueError("balance evidence names its scope")
        if self.evidence != "balance" and self.balance_scope is not None:
            raise ValueError("only balance evidence has a balance scope")
        if self.period_start and self.period_end and self.period_start > self.period_end:
            raise ValueError("period_start is after period_end")
        return self

    def unresolved(self) -> frozenset[str]:
        """Fields a person must supply or confirm before this can become
        canonical activity: missing ones plus the ones marked uncertain."""

        missing: set[str] = set(self.uncertain)
        if self.evidence == "unclassified":
            missing.add("kind")
        if self.evidence in ("transaction", "payment_notice", "unclassified"):
            if self.amount is None:
                missing.add("amount")
            if self.currency is None:
                missing.add("currency")
            if self.occurred_on is None and self.occurred_at is None:
                missing.add("occurred_on")
            if self.direction == "unknown":
                missing.add("direction")
            if not (
                self.account.external_account_id or self.account.mask or self.account.name
            ):
                missing.add("account")
        return frozenset(missing)

    def fingerprint(self) -> str:
        """Content identity for "nothing changed" on re-delivery.

        ``observed_at`` is excluded: re-fetching the same fact later is not a
        change in what the source says.
        """

        body = self.model_dump(mode="json")
        body["source"].pop("observed_at", None)
        body["uncertain"] = sorted(body["uncertain"])
        raw = json.dumps(body, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode()).hexdigest()

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.source.source, self.source.connection_id, self.source.external_id)


def _currency_code(value: str | None) -> str | None:
    if value is None:
        return None
    code = str(value).strip().upper()
    if not code:
        return None
    if not _CURRENCY.match(code):
        raise ValueError("currency is a three-letter ISO 4217 code")
    return code
