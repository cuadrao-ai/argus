from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Money = Annotated[str, StringConstraints(pattern=r"^(?:0|[1-9]\d{0,8})(?:\.\d{1,2})?$")]
Identifier = Annotated[str, StringConstraints(pattern=r"^[A-Z0-9]{1,19}$")]


class FiscalInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rnc: Identifier | None
    ncf: Identifier | None
    itbis: Money | None


class Declaration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id_type: Literal["1", "2", "3"] | None
    modified_ncf: Identifier | None
    selective_tax: Money | None
    other_taxes: Money | None
    legal_tip: Money | None


class PurchaseDeclaration(Declaration):
    form: Literal["606"]
    id_type: Literal["1", "2"] | None
    category: (
        Literal["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11"] | None
    )
    paid_on: date | None
    services_amount: Money | None
    goods_amount: Money | None
    itbis_withheld: Money | None
    itbis_proportionality: Money | None
    itbis_cost: Money | None
    itbis_perceived: Money | None
    income_withholding_type: (
        Literal["01", "02", "03", "04", "05", "06", "07", "08", "09"] | None
    )
    income_withheld: Money | None
    income_perceived: Money | None
    payment_method: Literal["01", "02", "03", "04", "05", "06", "07"] | None
    actual_refund: bool = False
    purchase_activity_id: UUID | None = None


class SalesDeclaration(Declaration):
    form: Literal["607"]
    income_type: Literal["1", "2", "3", "4", "5", "6"] | None
    withheld_on: date | None
    billed_amount: Money | None
    itbis_withheld_by_third_parties: Money | None
    itbis_perceived: Money | None
    income_withheld_by_third_parties: Money | None
    income_perceived: Money | None
    cash: Money | None
    bank: Money | None
    card: Money | None
    credit: Money | None
    gift: Money | None
    barter: Money | None
    other_payment: Money | None

    @field_validator("income_type", mode="before")
    @classmethod
    def numeric_income_code(cls, value):
        return (
            value[1:]
            if isinstance(value, str) and value in {"01", "02", "03", "04", "05", "06"}
            else value
        )


DgiiDeclaration = Annotated[
    PurchaseDeclaration | SalesDeclaration, Field(discriminator="form")
]


class FiscalReview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fiscal: FiscalInput
    declaration: DgiiDeclaration


class TaxId(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    type: Literal["rnc", "cedula"]
    value: str


class FiscalProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    tax_id: TaxId | None
    can_edit: bool


class FiscalField(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    label: str
    kind: Literal["select", "date", "text", "money"]
    options: tuple[str, ...]


def decimal_money(value: str) -> Decimal:
    return Decimal(value)


def money_text(value: Decimal) -> str:
    return format(value, ".2f")
