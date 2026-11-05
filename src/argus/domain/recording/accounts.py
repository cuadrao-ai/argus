"""Account facts and the rules that govern their edits.

Nature derives from type by one table and is never stored. A liability's typed
amount owed becomes a negative owner-signed balance here and nowhere else.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, get_args

from argus.domain.recording.currency import normalize_currency
from argus.domain.recording.errors import RecordingInputError

AccountType = Literal[
    "cash",
    "checking",
    "savings",
    "investment",
    "credit_card",
    "other_debt",
    "property",
    "vehicle",
    "other_asset",
]
Nature = Literal["asset", "liability"]

ACCOUNT_TYPES: tuple[str, ...] = get_args(AccountType)
OPTIONAL_ASSET_TYPES = frozenset({"property", "vehicle", "other_asset"})
LIABILITY_TYPES = frozenset({"credit_card", "other_debt"})


def nature_of(account_type: str) -> Nature:
    return "liability" if account_type in LIABILITY_TYPES else "asset"


FULL_SHARE_BPS = 10_000
NICKNAME_MAX_CODE_POINTS = 60
PERSONAL_SPACE = "personal"


@dataclass(frozen=True)
class AccountFacts:
    """One stored account row, as the owner sees it."""

    id: str
    user_id: str
    type: str
    currency: str
    nickname: str | None
    archived: bool
    ownership_share_bps: int
    version: int
    created_at: datetime
    updated_at: datetime

    @property
    def nature(self) -> Nature:
        return nature_of(self.type)


def validate_type(value: str) -> str:
    if value not in ACCOUNT_TYPES:
        raise RecordingInputError(
            "account_type_unsupported", f"{value!r} is not an account type"
        )
    return value


def signed_to_owner(typed_minor: int, account_type: str) -> int:
    """The person types a debt as a positive amount owed; the server flips once."""

    return -typed_minor if nature_of(account_type) == "liability" else typed_minor


def normalize_nickname(text: str | None) -> str | None:
    trimmed = (text or "").strip()
    if len(trimmed) > NICKNAME_MAX_CODE_POINTS:
        raise RecordingInputError(
            "nickname_invalid",
            f"a nickname has at most {NICKNAME_MAX_CODE_POINTS} characters",
        )
    return trimmed or None


def validate_share(bps: int) -> int:
    if not 1 <= bps <= FULL_SHARE_BPS:
        raise RecordingInputError(
            "ownership_share_invalid",
            f"ownership share is 1 to {FULL_SHARE_BPS} basis points",
        )
    return bps


class Unset:
    """Marks an edit field the caller did not send, so ``None`` can mean clear."""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "UNSET"


UNSET = Unset()


@dataclass(frozen=True)
class AccountEdit:
    nickname: str | None | Unset = UNSET
    type: str | None = None
    currency: str | None = None
    archived: bool | None = None
    ownership_share_bps: int | None = None


def plan_account_edit(
    account: AccountFacts,
    edit: AccountEdit,
    *,
    has_records: bool,
    has_activity: bool,
) -> dict[str, object]:
    """Return the column changes an edit produces, or raise the rule it breaks.

    Currency locks once any record exists. Type locks once activity exists; with
    only an opening, a change inside the same nature is allowed and a nature
    flip is refused because it would reverse the stored sign.
    """

    changes: dict[str, object] = {}
    if not isinstance(edit.nickname, Unset):
        changes["nickname"] = normalize_nickname(edit.nickname)
    if edit.type is not None and edit.type != account.type:
        validate_type(edit.type)
        if has_activity:
            raise RecordingInputError(
                "type_locked", "the type is kept with its recorded activity"
            )
        if has_records and nature_of(edit.type) != nature_of(account.type):
            raise RecordingInputError(
                "nature_change_requires_empty_account",
                "an account with a recorded balance keeps its nature",
            )
        changes["type"] = edit.type
    if edit.currency is not None:
        currency = normalize_currency(edit.currency)
        if currency != account.currency:
            if has_records:
                raise RecordingInputError(
                    "currency_locked", "the currency is kept with its recorded balance"
                )
            changes["currency"] = currency
    if edit.archived is not None and edit.archived != account.archived:
        changes["archived"] = edit.archived
    if edit.ownership_share_bps is not None:
        share = validate_share(edit.ownership_share_bps)
        if share != account.ownership_share_bps and account.type in OPTIONAL_ASSET_TYPES:
            raise RecordingInputError(
                "asset_details_required", "Review asset ownership with its related debt."
            )
        if share != account.ownership_share_bps:
            changes["ownership_share_bps"] = share
    return changes
