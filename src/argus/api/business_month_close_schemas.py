"""Wire shapes for month close. The domain owns which values are legal."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Wire(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _settlement() -> Any:  # noqa: ANN401
    """A field only settlement gives: absent from the answer while
    ``CUADRAO_BUSINESS_SETTLEMENT_ENABLED`` is off."""

    return Field(
        default=None,
        exclude_if=lambda value: value is None,
        description="Settlement only: absent while settlement is off.",
    )


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
    # Settlement only, absent while it is off: what is still to collect and pay,
    # the ITBIS charged on the sales already marked cobrado, and the counts by
    # status. While it is off the web shows itbis_charged in ITBIS cobrado's place.
    cuentas_por_cobrar_minor: int | None = _settlement()
    cuentas_por_cobrar: str | None = _settlement()
    cuentas_por_pagar_minor: int | None = _settlement()
    cuentas_por_pagar: str | None = _settlement()
    itbis_cobrado_minor: int | None = _settlement()
    itbis_cobrado: str | None = _settlement()
    by_status: StatusTotals | None = _settlement()
    # False only while settlement is on and a document in this currency is
    # still pendiente. The net is in its own currency: no rate holds it.
    net_result_final: bool
    # The month's documents in this currency, from the same list as the
    # figures: how many the figures count, how many there are in all (the
    # Bandeja's included), and how many the Bandeja still holds. A Bandeja
    # draft that names no currency yet counts in the Business's own.
    documents_counted: int = 0
    documents_total: int = 0
    documents_in_bandeja: int = 0


FormStatus = Literal[
    "no_aplica", "needs_review", "summary_only", "no_operations", "prepared_candidate"
]


class DgiiForms(_Wire):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    # The DGII summary's own status word per form.
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
    # pendiente, cobrado or pagado; absent while settlement is off.
    status: str | None = _settlement()
    # Marked in review as having no comprobante fiscal: counted in the totals,
    # left out of the 606 and 607, and never a missing RNC or NCF.
    sin_comprobante: bool = False
    # The due date set in review; null while unknown. Open items sort on it.
    due_on: date | None
    # A receipt's 606 Forma de Pago code from its declaration, the same value
    # the review shows and the export prints; null for an invoice or while
    # no one has chosen it.
    payment_form: str | None = None


class HeldLine(DocumentLine):
    # What the 606 or 607 still needs before it carries this document as a
    # line, first fix first, in the export's own words: the same words
    # Registros shows as export_missing.
    missing: list[str]


class FiscalDataRow(_Wire):
    # One "Faltan datos fiscales" row: the held documents of one Registros tab
    # in one currency. `by_currency` is true when that tab's held documents
    # this month span more than one currency, so the row names its currency.
    family: Literal["purchase", "sale"]
    currency: str
    count: int
    by_currency: bool


class ForeignCurrencyForm(_Wire):
    # Foreign-currency lines left out of this form until a rate exists.
    pending_rate_count: int = 0
    # "Moneda extranjera: pendiente de tasa" when the count is above zero.
    reason: Literal["Moneda extranjera: pendiente de tasa"] | None = None


class DgiiForeignCurrency(_Wire):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    form_606: ForeignCurrencyForm = Field(
        alias="606", default_factory=ForeignCurrencyForm
    )
    form_607: ForeignCurrencyForm = Field(
        alias="607", default_factory=ForeignCurrencyForm
    )


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
    # The Business holds documents in more than one currency in some month
    # (approved ones in any month, or this month's Bandeja drafts), so Inicio
    # keeps its currency choice in view even in a month of one currency.
    more_than_one_currency: bool = False
    # The methods a cobrado or pagado mark may carry; absent while settlement is off.
    payment_methods: list[str] | None = _settlement()
    dgii_forms: DgiiForms
    dgii_foreign_currency: DgiiForeignCurrency = Field(
        default_factory=DgiiForeignCurrency
    )
    currencies: list[CurrencyBlock]
    missing_rnc: list[DocumentLine]
    # The missing_ncf lines whose NCF is present but malformed, as read.
    ncf_malformed: list[DocumentLine] = Field(default_factory=list)
    missing_ncf: list[DocumentLine]
    # Purchases the 606 holds until a person sets Forma de Pago, paid or not.
    missing_payment_form: list[DocumentLine] = Field(default_factory=list)
    # Every document the 606 or 607 holds this month, with what it needs. The
    # export's verdict, not month completion: `closed` never reads into it.
    missing_fiscal_data: list[HeldLine] = Field(default_factory=list)
    # The same documents counted per Registros tab and currency, in order:
    # Compras, then Ventas.
    missing_fiscal_rows: list[FiscalDataRow] = Field(default_factory=list)
    # The month's documents still pendiente; absent while settlement is off.
    cuentas_por_cobrar: list[DocumentLine] | None = _settlement()
    cuentas_por_pagar: list[DocumentLine] | None = _settlement()
    # Receipt and note drafts the Bandeja still lists in this month: the sum of
    # the currency blocks' documents_in_bandeja.
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
