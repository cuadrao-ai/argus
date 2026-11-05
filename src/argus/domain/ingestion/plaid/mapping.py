"""Plaid ``/transactions/sync`` rows as ``ImportCandidate`` evidence.

Plaid semantics kept as Plaid states them (API 2020-09-14):

- ``amount`` is positive when money leaves the account and negative when it
  enters; the candidate carries the magnitude plus a direction.
- ``date`` is the occurrence date of a pending row and the posting date of a
  posted row; ``authorized_date`` is when a posted row was authorized. So the
  activity day is ``authorized_date`` when present, else ``date``, and only a
  posted row has a ``posted_on``.
- ``iso_currency_code`` and ``unofficial_currency_code`` are exclusive. An
  unofficial code (crypto, some national currencies) is not ISO 4217, so the
  candidate keeps ``currency=None`` and marks it uncertain instead of guessing.
- A posted row names the pending row it settles in ``pending_transaction_id``;
  that becomes ``replaces_external_id`` so reconciliation keeps one event.
- ``personal_finance_category`` is Plaid's own structured taxonomy. It maps to
  a ``kind_hint`` only; the person still decides what the activity is.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from argus.domain.ingestion.contract import (
    AccountHint,
    AccountTypeHint,
    Direction,
    ImportCandidate,
    KindHint,
    SourceRef,
)

_ACCOUNT_TYPES: dict[str, AccountTypeHint] = {
    "depository": "depository",
    "credit": "credit",
    "loan": "loan",
    "investment": "investment",
}
_PRIMARY_KIND: dict[str, KindHint] = {
    "INCOME": "income",
    "TRANSFER_IN": "transfer",
    "TRANSFER_OUT": "transfer",
    "BANK_FEES": "fee",
}
_DETAILED_KIND: dict[str, KindHint] = {
    "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT": "card_payment",
}
_NOT_SPENDING = frozenset({"LOAN_PAYMENTS", "LOAN_DISBURSEMENTS", "OTHER"})
# Content that defines a revision; Plaid has no row version of its own.
_REVISION_FIELDS = (
    "account_id", "amount", "iso_currency_code", "unofficial_currency_code",
    "date", "authorized_date", "pending", "pending_transaction_id",
    "merchant_name", "name", "personal_finance_category",
)  # fmt: skip


def account_hints(
    accounts: list[Any], *, institution: str | None
) -> tuple[dict[str, AccountHint], int]:
    """Hints by Plaid ``account_id`` plus how many accounts were unusable.

    Each account is built on its own: one malformed account (bad id, a
    non-ISO currency) is dropped and counted, never failing the whole sync.
    Its transactions still carry their ``account_id`` when that id is valid.
    """

    hints: dict[str, AccountHint] = {}
    dropped = 0
    for account in accounts:
        try:
            account_id = account.get("account_id")
            if not isinstance(account_id, str):
                raise ValueError("account without account_id")
            balances = account.get("balances")
            hints[account_id] = AccountHint(
                external_account_id=account_id,
                institution=institution,
                name=_text(account.get("official_name")) or _text(account.get("name")),
                mask=_text(account.get("mask")),
                currency=balances.get("iso_currency_code")
                if isinstance(balances, dict)
                else None,
                type_hint=_ACCOUNT_TYPES.get(str(account.get("type")), "unknown"),
            )
        except (ValueError, TypeError, AttributeError):
            dropped += 1
    return hints, dropped


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def transaction_candidate(
    row: Mapping[str, Any],
    *,
    connection_id: str,
    accounts: Mapping[str, AccountHint],
    observed_at: datetime,
) -> ImportCandidate:
    pending = bool(row.get("pending"))
    amount, direction = _amount(row.get("amount"))
    uncertain: set[str] = set()
    currency = row.get("iso_currency_code") or None
    if currency is None and row.get("unofficial_currency_code"):
        uncertain.add("currency")
    account_id = row.get("account_id")
    account = accounts.get(account_id) if isinstance(account_id, str) else None
    if account is None:
        account = AccountHint(
            external_account_id=account_id if isinstance(account_id, str) else None
        )
    reported = _date(row.get("date"))
    authorized = _date(row.get("authorized_date"))
    return ImportCandidate(
        source=SourceRef(
            source="plaid",
            connection_id=connection_id,
            external_id=_transaction_id(row),
            revision=revision(row),
            replaces_external_id=None
            if pending
            else (row.get("pending_transaction_id") or None),
            observed_at=observed_at,
        ),
        evidence="transaction",
        status="pending" if pending else "posted",
        account=account,
        occurred_on=authorized or reported,
        posted_on=None if pending else reported,
        amount=amount,
        currency=currency,
        direction=direction,
        kind_hint=_kind(row.get("personal_finance_category"), direction),
        merchant=row.get("merchant_name"),
        description=row.get("name"),
        uncertain=frozenset(uncertain),  # type: ignore[arg-type]
    )


def removed_candidate(
    row: Mapping[str, Any], *, connection_id: str, observed_at: datetime
) -> ImportCandidate:
    account_id = row.get("account_id")
    return ImportCandidate(
        source=SourceRef(
            source="plaid",
            connection_id=connection_id,
            external_id=_transaction_id(row),
            revision="removed",
            observed_at=observed_at,
        ),
        evidence="transaction",
        status="removed",
        account=AccountHint(
            external_account_id=account_id if isinstance(account_id, str) else None
        ),
    )


def revision(row: Mapping[str, Any]) -> str:
    body = {key: row.get(key) for key in _REVISION_FIELDS}
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _transaction_id(row: Mapping[str, Any]) -> str:
    value = row.get("transaction_id")
    if not isinstance(value, str) or not value:
        raise ValueError("Plaid row has no transaction_id")
    return value


def _amount(value: object) -> tuple[str | None, Direction]:
    if isinstance(value, bool) or value is None:
        return None, "unknown"
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None, "unknown"
    if not number.is_finite():
        return None, "unknown"
    if number > 0:
        return str(number), "outflow"
    if number < 0:
        return str(-number), "inflow"
    return "0", "unknown"


def _date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _kind(category: object, direction: Direction) -> KindHint:
    if not isinstance(category, dict):
        return "unknown"
    detailed = _DETAILED_KIND.get(str(category.get("detailed")))
    if detailed is not None:
        return detailed
    primary = str(category.get("primary"))
    if primary in _PRIMARY_KIND:
        return _PRIMARY_KIND[primary]
    if primary in _NOT_SPENDING:
        return "unknown"
    # A spending category leaving the account; an inflow there may be a
    # refund or a reversal, which the person decides.
    return "expense" if direction == "outflow" else "unknown"
