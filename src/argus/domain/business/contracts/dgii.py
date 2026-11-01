from __future__ import annotations

import re
import string
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

Money = Annotated[str, StringConstraints(pattern=r"^(?:0|[1-9]\d{0,8})(?:\.\d{1,2})?$")]

_ASCII_UPPER = str.maketrans(string.ascii_lowercase, string.ascii_uppercase)
_PRINTED_SEPARATOR = re.compile(r"(?<=[0-9])[-\s]+(?=[0-9])")


def _printed_identifier(value: object) -> object:
    """An RNC, cédula or NCF as a person keys it or a read kept it: the
    dashes and spaces printed between its digit groups go, and a to z become
    upper case. Nothing else is folded, so a letter that upper-cases to two
    and a word typed into the field still fail the shape. The one place that
    cleans fiscal input; every reader after it sees digits."""

    if not isinstance(value, str):
        return value
    return _PRINTED_SEPARATOR.sub("", value.strip()).translate(_ASCII_UPPER)


Identifier = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Z0-9]{1,19}$"),
    BeforeValidator(_printed_identifier),
]


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


ExpenseType = Literal["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11"]
PaymentForm = Literal["01", "02", "03", "04", "05", "06", "07"]
IsrWithholding = Literal["01", "02", "03", "04", "05", "06", "07", "08", "09"]
#: Servicios y suministros, alquiler, gastos financieros, seguros.
SERVICE_EXPENSE_TYPES = frozenset({"02", "03", "07", "11"})


class PurchaseDeclaration(Declaration):
    form: Literal["606"]
    id_type: Literal["1", "2"] | None
    category: ExpenseType | None
    #: A prefilled expense type the owner has not confirmed. Export treats it as missing.
    category_suggested: bool = False
    paid_on: date | None
    services_amount: Money | None
    goods_amount: Money | None
    itbis_withheld: Money | None
    itbis_proportionality: Money | None
    itbis_cost: Money | None
    itbis_perceived: Money | None
    income_withholding_type: IsrWithholding | None
    income_withheld: Money | None
    income_perceived: Money | None
    payment_method: PaymentForm | None
    actual_refund: bool = False
    purchase_activity_id: UUID | None = None


class PurchaseReview(BaseModel):
    """The 606 fields a person confirms, before or after approval: every field
    of PurchaseDeclaration but its form. Absent fields stay as they were."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id_type: Literal["1", "2"] | None = None
    modified_ncf: Identifier | None = None
    selective_tax: Money | None = None
    other_taxes: Money | None = None
    legal_tip: Money | None = None
    category: ExpenseType | None = None
    category_suggested: bool = False
    paid_on: date | None = None
    services_amount: Money | None = None
    goods_amount: Money | None = None
    itbis_withheld: Money | None = None
    itbis_proportionality: Money | None = None
    itbis_cost: Money | None = None
    itbis_perceived: Money | None = None
    income_withholding_type: IsrWithholding | None = None
    income_withheld: Money | None = None
    income_perceived: Money | None = None
    payment_method: PaymentForm | None = None
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
    #: The label of each option that has one, by code; empty for a field
    #: whose codes carry no label.
    labels: dict[str, str] = Field(default_factory=dict)


def decimal_money(value: str) -> Decimal:
    return Decimal(value)


def money_text(value: Decimal) -> str:
    return format(value, ".2f")


def amount_or_zero(value: str | None) -> Decimal:
    return Decimal("0" if value is None else value)
