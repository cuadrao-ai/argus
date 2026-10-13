"""Wire shapes for the financial accounts routes.

Kept out of ``argus.api.schemas`` because that module is at its modularity
budget. Amounts cross the wire as dot-decimal strings plus signed minor units;
the client formats separators for its locale.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

from argus.domain.recording.accounts import (
    FULL_SHARE_BPS,
    AccountFacts,
    AccountType,
    Nature,
)
from argus.domain.recording.asset_schemas import AssetProjection
from argus.domain.recording.currency import currency_exponent, format_minor_units
from argus.domain.recording.loop import position
from argus.domain.recording.records import Balance, OpeningRecord
from argus.domain.recording.repository import StoredAccount


class CreateFinancialAccountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: AccountType
    currency: str = Field(min_length=3, max_length=3)
    nickname: str | None = Field(default=None, max_length=200)
    # Starting balance as typed, dot-decimal; a liability is the positive amount
    # owed. Omitted on a Personal account records 0; Business keeps it unknown.
    # `as_of` defaults to now.
    amount: str | None = Field(default=None, max_length=40)
    as_of: datetime | None = None
    time_zone: str | None = Field(default=None, max_length=64)
    ownership_share_bps: int = Field(default=FULL_SHARE_BPS, ge=1, le=FULL_SHARE_BPS)


class EditFinancialAccountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    nickname: str | None = Field(default=None, max_length=200)
    type: AccountType | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    archived: bool | None = None
    ownership_share_bps: int | None = Field(default=None, ge=1, le=FULL_SHARE_BPS)


class WriteOpeningRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Caller-visible account version from the GET/list/edit response the person
    # is acting on. Required so a concurrent currency/type edit between that
    # read and this write cannot apply under metadata the caller never saw.
    expected_version: int = Field(ge=1)
    # The current opening revision, or null when the account has no opening yet.
    expected_revision: int | None = Field(default=None, ge=1)
    amount: str | None = Field(default=None, max_length=40)
    as_of: datetime | None = None
    time_zone: str | None = Field(default=None, max_length=64)
    reason: str | None = Field(default=None, max_length=1000)


class BalanceResponse(BaseModel):
    state: Literal["known", "unknown"]
    amount_minor: int | None = None
    amount: str | None = None
    as_of: datetime | None = None
    basis: Literal["opening", "balance_check"] | None = None
    activity_since_tracking_minor: int = 0
    credit_minor: int | None = None


class OpeningRevisionResponse(BaseModel):
    revision: int
    amount_minor: int
    amount: str
    as_of: datetime
    time_zone: str
    reason: str | None
    recorded_by: str | None
    recorded_at: datetime


class OpeningResponse(BaseModel):
    record_id: str
    revision: int
    amount_minor: int
    amount: str
    as_of: datetime
    time_zone: str
    reason: str | None
    recorded_at: datetime
    revisions: list[OpeningRevisionResponse]


class FinancialAccountResponse(BaseModel):
    id: str
    type: AccountType
    nature: Nature
    currency: str
    currency_fraction_digits: int
    nickname: str | None
    archived: bool
    ownership_share_bps: int
    version: int
    created_at: datetime
    updated_at: datetime
    balance: BalanceResponse
    opening: OpeningResponse | None
    asset: AssetProjection | None = None


class FinancialAccountListResponse(BaseModel):
    accounts: list[FinancialAccountResponse]


def account_response(stored: StoredAccount) -> FinancialAccountResponse:
    from argus.domain.recording.asset_reads import asset_projection

    facts = stored.account
    return FinancialAccountResponse(
        id=facts.id,
        type=facts.type,
        nature=facts.nature,
        currency=facts.currency,
        currency_fraction_digits=currency_exponent(facts.currency),
        nickname=facts.nickname,
        archived=facts.archived,
        ownership_share_bps=facts.ownership_share_bps,
        version=facts.version,
        created_at=facts.created_at,
        updated_at=facts.updated_at,
        balance=_balance_response(
            position(stored.opening, stored.checks, stored.expenses, stored.coverage),
            facts,
        ),
        opening=_opening_response(stored.opening, facts),
        asset=asset_projection(stored),
    )


def _balance_response(balance: Balance, facts: AccountFacts) -> BalanceResponse:
    if balance.state == "unknown":
        return BalanceResponse(
            state="unknown",
            activity_since_tracking_minor=balance.activity_since_tracking_minor,
        )
    assert balance.amount_minor is not None and balance.as_of is not None
    return BalanceResponse(
        state="known",
        credit_minor=max(balance.amount_minor, 0)
        if facts.type == "credit_card"
        else None,
        amount_minor=balance.amount_minor,
        amount=format_minor_units(balance.amount_minor, facts.currency),
        as_of=balance.as_of,
        basis=balance.basis,
        activity_since_tracking_minor=balance.activity_since_tracking_minor,
    )


def _opening_response(
    opening: OpeningRecord | None, facts: AccountFacts
) -> OpeningResponse | None:
    if opening is None:
        return None
    current = opening.current
    revisions = [
        OpeningRevisionResponse(
            revision=item.revision,
            amount_minor=item.amount_minor,
            amount=format_minor_units(item.amount_minor, facts.currency),
            as_of=item.as_of.astimezone(ZoneInfo(item.time_zone)),
            time_zone=item.time_zone,
            reason=item.reason,
            recorded_by=item.recorded_by,
            recorded_at=item.recorded_at,
        )
        for item in opening.revisions
    ]
    return OpeningResponse(
        record_id=opening.id,
        revision=current.revision,
        amount_minor=current.amount_minor,
        amount=format_minor_units(current.amount_minor, facts.currency),
        as_of=current.as_of.astimezone(ZoneInfo(current.time_zone)),
        time_zone=current.time_zone,
        reason=current.reason,
        recorded_at=current.recorded_at,
        revisions=revisions,
    )
