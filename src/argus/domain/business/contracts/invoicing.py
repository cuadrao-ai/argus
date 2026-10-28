from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from argus.domain.business.fiscal_sandbox.contracts import FiscalOperation, Strict

Currency = Literal["DOP", "USD", "EUR"]


class CustomerInput(Strict):
    name: str = Field(default="", max_length=200)
    email: str = Field(default="", max_length=254)
    tax_id: str = Field(default="", max_length=32)
    address: str = Field(default="", max_length=500)
    phone: str = Field(default="", max_length=40)
    notes: str = Field(default="", max_length=500)


class CustomerWrite(Strict):
    data: CustomerInput
    archived: bool = False
    expected_version: int | None = Field(default=None, ge=1)


class Customer(Strict):
    id: UUID
    business_id: UUID
    version: int
    data: CustomerInput
    archived: bool
    created_at: datetime
    updated_at: datetime


class InvoiceItem(Strict):
    id: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=160)
    quantity: str = Field(default="", max_length=32)
    price: str = Field(default="", max_length=32)
    tax: str = Field(default="", max_length=32)
    discount: str = Field(default="", max_length=32)
    classification: Literal["goods", "services"] | None = None
    tax_treatment: Literal["taxable", "exempt"] | None = None


class DeliveryPreparation(Strict):
    to: str = Field(default="", max_length=254)
    cc: tuple[str, ...] = Field(default=(), max_length=5)
    message: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def bounded_recipients(self) -> DeliveryPreparation:
        if any(len(value) > 254 for value in self.cc):
            raise ValueError("invoice_recipient_length")
        return self


class InvoiceDraft(Strict):
    customer_id: UUID | None = None
    customer_input: CustomerInput = CustomerInput()
    document_type: Literal["E31", "E32"] = "E32"
    currency: Currency = "DOP"
    issued_on: str = Field(default="", max_length=10)
    due_on: str = Field(default="", max_length=10)
    items: tuple[InvoiceItem, ...] = Field(default=(), max_length=50)
    terms: str = Field(default="", max_length=500)
    instructions: str = Field(default="", max_length=500)
    notes: str = Field(default="", max_length=500)
    delivery: DeliveryPreparation = DeliveryPreparation()
    payment_type: Literal["cash", "credit", "free"] | None = None
    income_type: Literal[1, 2, 3, 4, 5, 6] | None = None
    tax_inclusion: Literal["excluded", "included"] | None = None

    @model_validator(mode="after")
    def stable_items(self) -> InvoiceDraft:
        if len({item.id for item in self.items}) != len(self.items):
            raise ValueError("invoice_item_identity_duplicate")
        return self


class InvoiceWrite(Strict):
    data: InvoiceDraft
    expected_version: int | None = Field(default=None, ge=1)


class InvoicePrepare(Strict):
    expected_version: int = Field(ge=1)


class InvoiceAmounts(Strict):
    subtotal: str
    discount: str
    tax: str
    total: str


class Invoice(Strict):
    id: UUID
    business_id: UUID
    version: int
    revision_id: UUID
    data: InvoiceDraft
    field_errors: dict[str, str]
    amounts: InvoiceAmounts | None
    operation: FiscalOperation | None = None
    payment_state: Literal["unknown"] = "unknown"
    paid_amount: None = None
    outstanding_amount: None = None
    delivery_state: Literal["not_sent"] = "not_sent"
    created_at: datetime
    updated_at: datetime


class InvoiceSummary(Strict):
    currency: Currency
    billed: str
    collected: None = None
    outstanding: None = None


class InvoicePage(Strict):
    items: tuple[Invoice, ...]
    total: int
    page: int
    page_size: Literal[25, 50, 100]
    stage_counts: dict[str, int]
    summaries: tuple[InvoiceSummary, ...]
    query_version: str
    issuance_available: bool


class CustomerPage(Strict):
    items: tuple[Customer, ...]
    total: int
    page: int
    page_size: Literal[25, 50, 100]
