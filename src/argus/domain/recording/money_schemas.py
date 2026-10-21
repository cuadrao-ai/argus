"""One reviewed command for personal money movements."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

ActivityKind = Literal[
    "expense",
    "income",
    "transfer",
    "card_payment",
    "refund",
    "debt_payment",
    "payment_reversal",
]
SOURCE_IDS = ("salary", "remittance", "interest", "other")
LIQUID_TYPES = ("cash", "checking", "savings", "investment")
ELIGIBILITY = {
    "expense": ("cash", "checking", "savings", "credit_card"),
    "income": LIQUID_TYPES,
    "refund": ("cash", "checking", "savings", "credit_card"),
    "transfer": LIQUID_TYPES,
    "card_payment": LIQUID_TYPES,
    "debt_payment": ("cash", "checking", "savings"),
    "payment_reversal": LIQUID_TYPES,
}


class MoneyCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: str
    observation_id: str
    included: bool

    @field_validator("account_id", "observation_id")
    @classmethod
    def uuid_value(cls, value: str) -> str:
        return str(UUID(value))


class OwnerFunds(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    owner_space_id: UUID
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class MoneyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: ActivityKind
    owner_funding: OwnerFunds | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    account_id: str | None = None
    source_account_id: str | None = None
    destination_account_id: str | None = None
    amount: str = Field(max_length=40)
    destination_amount: str | None = Field(
        default=None, max_length=40, exclude_if=lambda value: value is None
    )
    principal: str | None = Field(default=None, max_length=40)
    interest: str | None = Field(default=None, max_length=40)
    fees: str | None = Field(default=None, max_length=40)
    reversal_of_activity_id: str | None = None
    occurred_at: datetime
    time_zone: str = Field(default="America/Santo_Domingo", max_length=64)
    note: str | None = Field(default=None, max_length=200)
    category_id: str | None = None
    source_id: str | None = None
    purchase_activity_id: str | None = None
    expected_revision: int | None = Field(default=None, ge=1)
    reason: str | None = Field(default=None, max_length=200)
    expected_versions: dict[str, int] = Field(default_factory=dict)
    coverage: list[MoneyCoverage] = Field(default_factory=list, max_length=1000)
    preview_token: str | None = Field(default=None, max_length=128)
    # Echoed from the preview for older clients; the server ignores it and uses its own day.
    entered_on: date | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def owner_funded_expense(self) -> "MoneyRequest":
        if self.owner_funding is not None:
            excluded = (
                self.account_id,
                self.source_account_id,
                self.destination_account_id,
                self.destination_amount,
                self.principal,
                self.interest,
                self.fees,
                self.reversal_of_activity_id,
                self.source_id,
                self.purchase_activity_id,
                self.expected_revision,
                self.reason,
                self.expected_versions,
                self.coverage,
            )
            if self.kind != "expense" or any(
                value is not None and value != {} and value != [] for value in excluded
            ):
                raise ValueError(
                    "Owner funds records a new expense without an account movement."
                )
        return self

    @field_validator(
        "account_id",
        "source_account_id",
        "destination_account_id",
        "purchase_activity_id",
        "reversal_of_activity_id",
    )
    @classmethod
    def uuid_value(cls, value: str | None) -> str | None:
        return str(UUID(value)) if value is not None else None

    @field_validator("expected_versions")
    @classmethod
    def versions(cls, value: dict[str, int]) -> dict[str, int]:
        if any(v < 1 for v in value.values()):
            raise ValueError("Account versions must be positive.")
        return {str(UUID(k)): v for k, v in value.items()}


DESTINATION_ELIGIBILITY = {
    "transfer": LIQUID_TYPES,
    "card_payment": ("credit_card",),
    "debt_payment": ("other_debt",),
    "payment_reversal": ("credit_card", "other_debt"),
}
