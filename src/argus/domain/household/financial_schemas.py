"""Authorized Household projections of canonical Recording values."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from argus.domain.recording.asset_schemas import AssetChangeResponse, AssetProjection
from argus.domain.recording.money_responses import (
    MoneyActivityResponse,
    MoneyOptionsResponse,
)
from argus.domain.recording.money_schemas import MoneyRequest
from argus.domain.recording.schemas import FinancialAccountResponse

from .planning_schemas import PlanRef, SharedPlan
from .schemas import VersionRequest


class FinancialCommand(VersionRequest):
    membership_id: UUID
    activity: MoneyRequest


class HouseholdAssetChange(AssetChangeResponse):
    recorded_by: None


class HouseholdAssetProjection(AssetProjection):
    changes: list[HouseholdAssetChange]


class HouseholdAccountResponse(FinancialAccountResponse):
    asset: HouseholdAssetProjection | None = None


class HouseholdMoneyOptions(MoneyOptionsResponse):
    accounts: list[HouseholdAccountResponse]


class SharedAccount(BaseModel):
    account: HouseholdAccountResponse
    owner_name: str
    permission: Literal["view", "edit"]
    is_owner: bool


class HouseholdActivityResponse(MoneyActivityResponse):
    amount_minor: int | None
    amount: str | None


class SharedActivity(BaseModel):
    activity: HouseholdActivityResponse
    author_name: str
    can_edit: bool
    private_counterpart: bool


class Position(BaseModel):
    currency: str
    currency_fraction_digits: int
    amount_minor: int
    unknown_count: int


class Snapshot(BaseModel):
    household_id: str
    membership_id: str
    authorization_version: int
    accounts: list[SharedAccount]
    activities: list[SharedActivity]
    positions: list[Position]
    plans: list[SharedPlan] = []


class SharedDetail(BaseModel):
    account: SharedAccount
    activities: list[SharedActivity]


class ActivityHistory(BaseModel):
    items: list[SharedActivity]


class SearchHit(BaseModel):
    id: str
    kind: Literal["account", "activity", "plan"]
    title: str
    account_id: str | None
    activity_id: str | None = None
    plan_ref: PlanRef | None = None


class SearchPage(BaseModel):
    items: list[SearchHit]
    next_cursor: str | None


class SharedReceipt(BaseModel):
    activity: SharedActivity
    accounts: list[SharedAccount]
    replayed: bool
