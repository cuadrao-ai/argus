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
    # ITBIS charged on the sales already marked cobrado.
    itbis_cobrado_minor: int
    itbis_cobrado: str
    by_status: StatusTotals
    # False while a document in this currency is still pendiente.
    net_result_final: bool


FormStatus = Literal[
    "no_aplica", "needs_review", "summary_only", "no_operations", "prepared_candidate"
]


class DgiiForms(_Wire):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    # The export packet's own status word per form, from the same summary
    # that decides whether the TXT file is written.
    form_606: FormStatus = Field(alias="606")
    form_607: FormStatus = Field(alias="607")


class CloseReason(_Wire):
    code: Literal["missing_rnc", "missing_ncf"]
    activity_id: str
    document_kind: Literal["invoice", "receipt"]


class UnreviewedReason(_Wire):
    code: Literal["movimientos_sin_revisar"]
    count: int


class DocumentLine(_Wire):
    activity_id: str
    document_kind: Literal["invoice", "receipt"]
    currency: str
    occurred_on: date
    total_minor: int
    total: str
    before_itbis_minor: int
    before_itbis: str
    itbis_minor: int | None
    itbis: str | None
    counterparty: str | None
    rnc: str | None
    ncf: str | None
    ecf: str | None
    status: str
    # Marked in review as having no comprobante fiscal: counted in the totals,
    # left out of the 606 and 607, and never a missing RNC or NCF.
    sin_comprobante: bool = False
    # The due date set in review; null while unknown. Open items sort on it.
    due_on: date | None


class MonthClose(_Wire):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    month: str
    # The server's day in the recording time zone: the one clock for "today".
    today: date
    starts: date = Field(alias="from")
    to: date
    closed: bool
    reasons: list[CloseReason | UnreviewedReason]
    # The first month with a document this close would show; null while none.
    earliest_month: str | None
    payment_methods: list[str]
    dgii_forms: DgiiForms
    currencies: list[CurrencyBlock]
    missing_rnc: list[DocumentLine]
    missing_ncf: list[DocumentLine]
    cuentas_por_cobrar: list[DocumentLine]
    cuentas_por_pagar: list[DocumentLine]
    # Receipt and note drafts the Bandeja still lists in this month.
    unreviewed_movements_count: int = 0


class OpenTotal(_Wire):
    currency: str
    total_minor: int
    total: str


class OpenOverdue(_Wire):
    count: int
    totals: list[OpenTotal]


class OpenList(_Wire):
    count: int
    totals: list[OpenTotal]
    # Pending past its due date as of ``today``, over every item, not only the page.
    overdue: OpenOverdue
    items: list[DocumentLine]


class OpenItems(_Wire):
    today: date
    cuentas_por_cobrar: OpenList
    cuentas_por_pagar: OpenList
