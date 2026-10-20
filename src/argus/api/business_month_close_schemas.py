"""Wire shapes for month close. The domain owns which values are legal."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Wire(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SettlementUpdate(_Wire):
    status: str
    settled_on: date | None = None
    payment_method: str | None = None


class SettlementResult(_Wire):
    activity_id: str
    document_kind: Literal["invoice", "receipt"]
    status: str
    settled_on: date | None
    payment_method: str | None
    changed: bool


class StatusCell(_Wire):
    count: int
    before_itbis_minor: int


class InvoiceStatuses(_Wire):
    pendiente: StatusCell
    cobrado: StatusCell


class ReceiptStatuses(_Wire):
    pendiente: StatusCell
    pagado: StatusCell


class StatusTotals(_Wire):
    invoices: InvoiceStatuses
    receipts: ReceiptStatuses


class CurrencyBlock(_Wire):
    currency: str
    income_before_itbis_minor: int
    income_before_itbis: str
    expense_before_itbis_minor: int
    expense_before_itbis: str
    net_result_minor: int
    net_result: str
    itbis_charged_minor: int
    itbis_charged: str
    itbis_paid_minor: int
    itbis_paid: str
    itbis_owed_minor: int
    itbis_owed: str
    cuentas_por_cobrar_minor: int
    cuentas_por_cobrar: str
    cuentas_por_pagar_minor: int
    cuentas_por_pagar: str
    by_status: StatusTotals


class CloseReason(_Wire):
    code: Literal["missing_rnc", "missing_ncf"]
    activity_id: str
    document_kind: Literal["invoice", "receipt"]


class DocumentLine(_Wire):
    activity_id: str
    document_kind: Literal["invoice", "receipt"]
    currency: str
    occurred_on: date
    total_minor: int
    before_itbis_minor: int
    itbis_minor: int | None
    status: str


class MonthClose(_Wire):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    month: str
    starts: date = Field(alias="from")
    to: date
    closed: bool
    reasons: list[CloseReason]
    currencies: list[CurrencyBlock]
    missing_rnc: list[DocumentLine]
    missing_ncf: list[DocumentLine]
    cuentas_por_cobrar: list[DocumentLine]
    cuentas_por_pagar: list[DocumentLine]
