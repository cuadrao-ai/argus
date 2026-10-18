from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BeforeValidator,
    Field,
    PlainSerializer,
    WithJsonSchema,
    field_validator,
    model_validator,
)

from .facts import Contract, rnc_has_number

CollectionStatus = Literal["cobrado", "por_cobrar"]
CustomerIdType = Literal["rnc", "cedula"]
_CENT = Decimal("0.01")
_MONEY_PATTERN = re.compile(r"^[0-9]+\.[0-9]{2}$")


def _decimal_money(value: object) -> Decimal:
    if isinstance(value, str):
        if _MONEY_PATTERN.fullmatch(value) is None:
            raise ValueError("money must be a decimal string with two places")
        raw = value
    elif isinstance(value, Decimal):
        raw = str(value)
    else:
        raise ValueError("money must be a decimal string")
    try:
        amount = Decimal(raw)
    except InvalidOperation:
        raise ValueError("money must be a finite decimal") from None
    if not amount.is_finite() or amount.as_tuple().exponent < -2:
        raise ValueError("money must have at most two decimal places")
    return amount.quantize(_CENT)


Money = Annotated[
    Decimal,
    BeforeValidator(_decimal_money),
    Field(max_digits=18, decimal_places=2),
    PlainSerializer(lambda value: format(value, ".2f"), return_type=str),
    WithJsonSchema({"type": "string", "pattern": r"^[0-9]+\.[0-9]{2}$"}),
]


class Customer(Contract):
    id_type: CustomerIdType
    id_number: str

    @model_validator(mode="after")
    def exact_identifier(self) -> Customer:
        expected = 9 if self.id_type == "rnc" else 11
        if len(self.id_number) != expected or not self.id_number.isascii():
            raise ValueError("customer identifier has the wrong shape")
        if not self.id_number.isdigit():
            raise ValueError("customer identifier must contain only digits")
        if not rnc_has_number(self.id_number):
            raise ValueError("customer identifier needs a nonzero digit")
        return self


class MarkVenta(Contract):
    draft_id: UUID
    invoice_total: Money
    itbis_charged: Money
    customer: Customer
    ncf: str = Field(pattern=r"^(B[0-9]{10}|E[0-9]{12})$")
    issued_on: date
    collection_status: CollectionStatus

    @field_validator("invoice_total")
    @classmethod
    def positive_total(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("invoice total must be positive")
        return value

    @model_validator(mode="after")
    def bounded_itbis(self) -> MarkVenta:
        if self.itbis_charged < 0 or self.itbis_charged > self.invoice_total:
            raise ValueError("ITBIS must be between zero and the invoice total")
        return self


class SetVentaCollection(Contract):
    collection_status: CollectionStatus


class MarkVentaCommand(Contract):
    action: Literal["mark_venta"] = "mark_venta"
    request: MarkVenta


class SetVentaCollectionCommand(Contract):
    action: Literal["set_venta_collection"] = "set_venta_collection"
    sale_id: UUID
    request: SetVentaCollection


class Sale(Contract):
    id: UUID
    space_id: UUID
    draft_id: UUID
    invoice_total: Money
    itbis_charged: Money
    customer: Customer
    ncf: str = Field(pattern=r"^(B[0-9]{10}|E[0-9]{12})$")
    issued_on: date
    collection_status: CollectionStatus
    currency: Literal["DOP"]
    created_at: datetime
    updated_at: datetime


class Form607Row(Contract):
    """One 607 line. Unknown filing columns stay null. They are not zeros."""

    buyer_id: str
    buyer_id_type: Literal[1, 2]
    ncf: str
    modified_ncf: None = None
    income_type: None = None
    issued_on: date
    withheld_on: None = None
    invoiced_amount: Money
    itbis_invoiced: Money
    itbis_withheld: None = None
    itbis_perceived: None = None
    rent_withheld: None = None
    isr_perceived: None = None
    selective_tax: None = None
    other_tax: None = None
    legal_tip: None = None
    cash: None = None
    transfer: None = None
    card: None = None
    credit_sale: None = None
    gift: None = None
    barter: None = None
    other_payment: None = None


class SalesPeriod(Contract):
    start: date
    end: date
    sales: tuple[Sale, ...]
    income: Money
    itbis_charged: Money
    itbis_cobrado: Money
    por_cobrar: Money
    rows: tuple[Form607Row, ...]


class SaleWrite(Contract):
    sale: Sale
    created: bool
