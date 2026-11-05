"""Asset estimate provenance and owner-qualified non-money commands."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AssetEstimateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    amount: str = Field(max_length=40)
    as_of: datetime
    time_zone: str = Field(max_length=64)
    estimate_basis: str | None = Field(default=None, max_length=200)
    reason: str | None = Field(default=None, max_length=200)
    record_id: str | None = None
    expected_revision: int | None = Field(default=None, ge=1)
    preview_token: str | None = None

    @model_validator(mode="after")
    def selected_revision(self):
        if (self.record_id is None) != (self.expected_revision is None):
            raise ValueError(
                "A correction identifies the observation and revision together."
            )
        return self


class AssetDetailsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    ownership_share_bps: int = Field(ge=1, le=10000)
    related_debt_account_id: str | None


class AssetEstimateRevision(BaseModel):
    revision: int
    amount_minor: int
    amount: str
    as_of: datetime
    time_zone: str
    estimate_basis: str | None
    reason: str | None
    recorded_by: str | None
    recorded_at: datetime


class AssetEstimate(AssetEstimateRevision):
    record_id: str
    kind: Literal["opening", "value_update"]
    revisions: list[AssetEstimateRevision]


class AssetChangeResponse(BaseModel):
    version: int
    previous_share_bps: int
    ownership_share_bps: int
    previous_debt_account_id: str | None
    related_debt_account_id: str | None
    recorded_by: str
    recorded_at: datetime


class AssetProjection(BaseModel):
    personal_position_minor: int | None
    current_estimate: AssetEstimate | None
    estimates: list[AssetEstimate]
    related_debt_account_id: str | None
    changes: list[AssetChangeResponse]
