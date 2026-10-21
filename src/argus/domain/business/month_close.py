"""Month close over the same recorded activities the export already reads.

Amounts stay on the activity. ITBIS, RNC, and the fiscal number stay on the
draft. This module only settles a document and adds those stored parts.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Literal

from loguru import logger
from pydantic import ValidationError

from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.dgii import SalesDeclaration
from argus.domain.business.contracts.facts import (
    BusinessResolution,
    Known,
    fiscal_inclusion,
    is_personal,
    is_sin_comprobante,
)
from argus.domain.business.dgii_validation import credit_note, reportable_607
from argus.domain.business.fiscal_identity import normalized_ncf
from argus.domain.business.ledger import occurred_on
from argus.domain.recording.currency import (
    currency_exponent,
    format_minor_units,
    parse_minor_units,
)
from argus.domain.recording.errors import RecordingInputError

DocumentKind = Literal["invoice", "receipt"]
PAYMENT_METHODS = frozenset({"efectivo", "transferencia", "tarjeta", "credito", "otro"})
_STATUS = {
    "invoice": frozenset({"pendiente", "cobrado"}),
    "receipt": frozenset({"pendiente", "pagado"}),
}


@dataclass(frozen=True)
class MonthDocument:
    activity_id: str
    space_id: str
    role: DocumentKind
    currency: str
    total_minor: int
    itbis_minor: int | None
    occurred_on: date
    rnc: str | None
    ncf: str | None
    ecf: str | None
    personal: bool
    include_606: bool | None
    status: str
    settled_on: date | None
    payment_method: str | None
    declared_base_minor: int | None = None
    counterparty: str | None = None
    sin_comprobante: bool = False
    due_on: date | None = None


@dataclass(frozen=True)
class Settlement:
    status: str
    settled_on: date | None
    payment_method: str | None


IMPLICIT = Settlement("pendiente", None, None)
Write = Callable[[Settlement, Settlement], None]


def month_period(month: str) -> tuple[date, date]:
    if len(month) != 7 or month[4] != "-":
        raise ValueError("month_invalid")
    year_text, month_text = month[:4], month[5:]
    if not (year_text.isdigit() and month_text.isdigit()):
        raise ValueError("month_invalid")
    year, number = int(year_text), int(month_text)
    if not 1 <= number <= 12:
        raise ValueError("month_invalid")
    start = date(year, number, 1)
    end = (
        date(year + 1, 1, 1) - timedelta(days=1)
        if number == 12
        else date(year, number + 1, 1) - timedelta(days=1)
    )
    return start, end


def to_minor(text: str, currency: str) -> int:
    """Round half up to the currency's digits, then take the integer minor units.

    The source string is not written back. Extra digits exist only inside this
    conversion.
    """

    exponent = currency_exponent(currency)
    quantum = Decimal(1).scaleb(-exponent)
    rounded = Decimal(text).quantize(quantum, rounding=ROUND_HALF_UP)
    return parse_minor_units(format(rounded, "f"), currency)


def before_itbis(total_minor: int, itbis_minor: int | None) -> int:
    return total_minor - (itbis_minor or 0)


def expense_base(document: MonthDocument) -> int:
    """A purchase's cost before creditable ITBIS. ITBIS without a comprobante
    cannot be credited, so a sin comprobante purchase costs its whole total."""

    if document.sin_comprobante:
        return document.total_minor
    return before_itbis(document.total_minor, document.itbis_minor)


def net_result(income_before: int, expense_before: int) -> int:
    return income_before - expense_before


def itbis_owed(charged: int, paid: int) -> int:
    return charged - paid


def _fiscal(document: MonthDocument) -> bool:
    return bool(document.ncf or document.ecf)


def in_month(document: MonthDocument, start: date, end: date) -> bool:
    return start <= document.occurred_on <= end


def in_close(document: MonthDocument) -> bool:
    if document.role == "receipt":
        return document.include_606 is True if document.personal else True
    return not document.personal


def in_606(document: MonthDocument) -> bool:
    if (
        document.role != "receipt"
        or normalized_ncf(document.ecf or document.ncf) is None
    ):
        return False
    if document.personal:
        return document.include_606 is True
    return True


def in_607(document: MonthDocument) -> bool:
    return (
        document.role == "invoice"
        and not document.personal
        and reportable_607(document.ecf or document.ncf)
    )


def sales_base(document: MonthDocument) -> int:
    """607 Monto Facturado when the draft declares it, otherwise total minus ITBIS.

    A credit note is stored positive and subtracted, the same way the 607 export nets it.
    """

    base = (
        document.declared_base_minor
        if document.declared_base_minor is not None
        else before_itbis(document.total_minor, document.itbis_minor)
    )
    if credit_note(document.ecf or document.ncf):
        return -base
    return base


@dataclass(frozen=True)
class FormatoCurrency:
    income_before_itbis: int = 0
    expense_before_itbis: int = 0
    itbis_charged: int = 0
    itbis_paid: int = 0


def formato_totals(
    documents: Sequence[MonthDocument], start: date, end: date
) -> dict[str, FormatoCurrency]:
    """Income and expense from the 607 and 606 lines plus the business
    documents marked sin comprobante. ITBIS stated on a sin comprobante sale
    is charged; a sin comprobante purchase pays no creditable ITBIS."""

    totals: dict[str, list[int]] = {}
    for document in documents:
        if not in_month(document, start, end):
            continue
        bucket = totals.setdefault(document.currency, [0, 0, 0, 0])
        if in_607(document):
            bucket[0] += sales_base(document)
            tax = document.itbis_minor or 0
            bucket[2] += -tax if credit_note(document.ecf or document.ncf) else tax
        elif in_606(document):
            bucket[1] += before_itbis(document.total_minor, document.itbis_minor)
            bucket[3] += document.itbis_minor or 0
        elif document.sin_comprobante and in_close(document):
            if document.role == "invoice":
                bucket[0] += sales_base(document)
                bucket[2] += document.itbis_minor or 0
            else:
                bucket[1] += expense_base(document)
    return {
        currency: FormatoCurrency(*parts)
        for currency, parts in sorted(totals.items())
        if any(parts)
    }


def plan_settlement(
    kind: DocumentKind, current: Settlement, command: Settlement
) -> Settlement | None:
    allowed = _STATUS[kind]
    if command.status not in allowed:
        raise ActionError("invalid_input", "business_status_invalid")
    if (
        command.payment_method is not None
        and command.payment_method not in PAYMENT_METHODS
    ):
        raise ActionError("invalid_input", "business_payment_method_invalid")
    pending = command.status == "pendiente"
    if pending and (command.settled_on is not None or command.payment_method is not None):
        raise ActionError("invalid_input", "business_settlement_incomplete")
    if not pending and (command.settled_on is None or command.payment_method is None):
        raise ActionError("invalid_input", "business_settlement_incomplete")
    if command == current:
        return None
    return command


def set_document_status(
    auth,
    documents: Sequence[MonthDocument],
    space_id: str,
    activity_id: str,
    command: Settlement,
    current: Settlement,
    write: Write,
) -> tuple[DocumentKind, Settlement, bool]:
    auth.require("prepare")
    match = next(
        (
            document
            for document in documents
            if document.activity_id == activity_id and document.space_id == space_id
        ),
        None,
    )
    if match is None:
        raise ActionError("not_found", "business_record_not_found")
    planned = plan_settlement(match.role, current, command)
    if planned is None:
        return match.role, current, False
    write(current, planned)
    return match.role, planned, True


def _line(document: MonthDocument) -> dict:
    currency = document.currency
    before = (
        expense_base(document)
        if document.role == "receipt"
        else before_itbis(document.total_minor, document.itbis_minor)
    )
    itbis = document.itbis_minor
    return {
        "activity_id": document.activity_id,
        "document_kind": document.role,
        "currency": currency,
        "occurred_on": document.occurred_on.isoformat(),
        "total_minor": document.total_minor,
        "total": format_minor_units(document.total_minor, currency),
        "before_itbis_minor": before,
        "before_itbis": format_minor_units(before, currency),
        "itbis_minor": itbis,
        "itbis": None if itbis is None else format_minor_units(itbis, currency),
        "counterparty": document.counterparty,
        "rnc": document.rnc,
        "ncf": document.ncf,
        "ecf": document.ecf,
        "status": document.status,
        "sin_comprobante": document.sin_comprobante,
        "due_on": None if document.due_on is None else document.due_on.isoformat(),
    }


def _pair(minor: int, currency: str) -> dict[str, int | str]:
    return {"minor": minor, "amount": format_minor_units(minor, currency)}


def summarize(documents: Sequence[MonthDocument], start: date, end: date) -> dict:
    chosen = [
        document
        for document in documents
        if in_month(document, start, end) and in_close(document)
    ]
    money = formato_totals(documents, start, end)
    reasons = []
    missing_rnc = []
    missing_ncf = []
    for document in sorted(chosen, key=lambda item: (item.occurred_on, item.activity_id)):
        if document.sin_comprobante:
            continue
        if not document.rnc:
            reasons.append(
                {
                    "code": "missing_rnc",
                    "activity_id": document.activity_id,
                    "document_kind": document.role,
                }
            )
            missing_rnc.append(_line(document))
        if (
            not _fiscal(document)
            or normalized_ncf(document.ecf or document.ncf) is None
        ):
            reasons.append(
                {
                    "code": "missing_ncf",
                    "activity_id": document.activity_id,
                    "document_kind": document.role,
                }
            )
            missing_ncf.append(_line(document))
    receivables = [
        _line(document)
        for document in chosen
        if document.role == "invoice" and document.status == "pendiente"
    ]
    payables = [
        _line(document)
        for document in chosen
        if document.role == "receipt" and document.status == "pendiente"
    ]
    currencies = sorted({document.currency for document in chosen} | set(money))
    blocks = []
    for currency in currencies:
        part = money.get(currency, FormatoCurrency())
        status = {
            "invoices": {
                "pendiente": {"count": 0, "before_itbis_minor": 0},
                "cobrado": {"count": 0, "before_itbis_minor": 0},
            },
            "receipts": {
                "pendiente": {"count": 0, "before_itbis_minor": 0},
                "pagado": {"count": 0, "before_itbis_minor": 0},
            },
        }
        for document in chosen:
            if document.currency != currency:
                continue
            group = "invoices" if document.role == "invoice" else "receipts"
            cell = status[group][document.status]
            cell["count"] += 1
            cell["before_itbis_minor"] += (
                sales_base(document)
                if document.role == "invoice"
                else expense_base(document)
            )
        income = part.income_before_itbis
        expense = part.expense_before_itbis
        charged = part.itbis_charged
        paid = part.itbis_paid
        receivable = sum(
            item["total_minor"] for item in receivables if item["currency"] == currency
        )
        payable = sum(
            item["total_minor"] for item in payables if item["currency"] == currency
        )
        shown = {
            "income_before_itbis": _pair(income, currency),
            "expense_before_itbis": _pair(expense, currency),
            "net_result": _pair(net_result(income, expense), currency),
            "itbis_charged": _pair(charged, currency),
            "itbis_paid": _pair(paid, currency),
            "itbis_owed": _pair(itbis_owed(charged, paid), currency),
            "cuentas_por_cobrar": _pair(receivable, currency),
            "cuentas_por_pagar": _pair(payable, currency),
        }
        blocks.append(
            {
                "currency": currency,
                "income_before_itbis_minor": shown["income_before_itbis"]["minor"],
                "income_before_itbis": shown["income_before_itbis"]["amount"],
                "expense_before_itbis_minor": shown["expense_before_itbis"]["minor"],
                "expense_before_itbis": shown["expense_before_itbis"]["amount"],
                "net_result_minor": shown["net_result"]["minor"],
                "net_result": shown["net_result"]["amount"],
                "itbis_charged_minor": shown["itbis_charged"]["minor"],
                "itbis_charged": shown["itbis_charged"]["amount"],
                "itbis_paid_minor": shown["itbis_paid"]["minor"],
                "itbis_paid": shown["itbis_paid"]["amount"],
                "itbis_owed_minor": shown["itbis_owed"]["minor"],
                "itbis_owed": shown["itbis_owed"]["amount"],
                "cuentas_por_cobrar_minor": shown["cuentas_por_cobrar"]["minor"],
                "cuentas_por_cobrar": shown["cuentas_por_cobrar"]["amount"],
                "cuentas_por_pagar_minor": shown["cuentas_por_pagar"]["minor"],
                "cuentas_por_pagar": shown["cuentas_por_pagar"]["amount"],
                "by_status": status,
            }
        )
    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "closed": not reasons,
        "reasons": reasons,
        "currencies": blocks,
        "missing_rnc": missing_rnc,
        "missing_ncf": missing_ncf,
        "cuentas_por_cobrar": receivables,
        "cuentas_por_pagar": payables,
    }


OPEN_ITEMS_CAP = 100


def open_items(documents: Sequence[MonthDocument], cap: int = OPEN_ITEMS_CAP) -> dict:
    """Every pending document the month close would list, from any month.

    Soonest due date first; documents with no due date follow, oldest first.
    ``count`` and the per-currency totals cover every pending document,
    including the ones past ``cap``.
    """

    pending = sorted(
        (
            document
            for document in documents
            if in_close(document) and document.status == "pendiente"
        ),
        key=lambda document: (
            document.due_on is None,
            document.due_on or date.min,
            document.occurred_on,
            document.activity_id,
        ),
    )
    return {
        "cuentas_por_cobrar": _open_list(
            [document for document in pending if document.role == "invoice"], cap
        ),
        "cuentas_por_pagar": _open_list(
            [document for document in pending if document.role == "receipt"], cap
        ),
    }


def _open_list(documents: Sequence[MonthDocument], cap: int) -> dict:
    totals: dict[str, int] = {}
    for document in documents:
        currency = document.currency
        totals[currency] = totals.get(currency, 0) + document.total_minor
    return {
        "count": len(documents),
        "totals": [
            {
                "currency": currency,
                "total_minor": minor,
                "total": format_minor_units(minor, currency),
            }
            for currency, minor in sorted(totals.items())
        ],
        "items": [_line(document) for document in documents[:cap]],
    }


def itbis_or_none(text: str | None, currency: str) -> int | None:
    if text is None:
        return None
    try:
        return to_minor(text, currency)
    except (RecordingInputError, InvalidOperation):
        return None


@dataclass(frozen=True)
class FiscalParts:
    rnc: str | None
    ncf: str | None
    ecf: str | None
    itbis_minor: int | None
    personal: bool
    include_606: bool | None
    declared_base_minor: int | None = None
    counterparty: str | None = None
    sin_comprobante: bool = False
    due_on: date | None = None


_NO_FISCAL = FiscalParts(None, None, None, None, False, None)


def _known(fact: object) -> object | None:
    return fact.value if isinstance(fact, Known) else None


def read_fiscal(resolution: Mapping | None, currency: str) -> FiscalParts:
    """RNC, fiscal number, ITBIS, marks, counterparty, and due date from one draft.

    An unreadable draft contributes no fiscal parts. The activity total is not
    read from the draft.
    """

    typed = resolution.get("business") if isinstance(resolution, Mapping) else None
    if not isinstance(typed, Mapping):
        return _NO_FISCAL
    try:
        parsed = BusinessResolution.model_validate(typed)
    except ValidationError:
        logger.info("month_close_resolution_unreadable")
        return _NO_FISCAL
    facts = parsed.facts
    fiscal = facts.fiscal
    rnc = ncf = ecf = None
    itbis_minor = None
    if fiscal is not None:
        rnc = _text(_known(fiscal.rnc))
        ncf = _text(_known(fiscal.ncf))
        ecf = _text(_known(fiscal.ecf))
        itbis_minor = itbis_or_none(_text(_known(fiscal.itbis)), currency)
    declared = None
    if isinstance(parsed.dgii, SalesDeclaration) and parsed.dgii.billed_amount is not None:
        declared = itbis_or_none(parsed.dgii.billed_amount, currency)
    return FiscalParts(
        rnc,
        ncf,
        ecf,
        itbis_minor,
        is_personal(facts),
        fiscal_inclusion(facts),
        declared,
        _text(_known(facts.counterparty)),
        is_sin_comprobante(facts),
        parsed.due_on,
    )


def _text(value: object) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _as_date(value: object) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def project_documents(
    activities: Sequence[Mapping],
    resolutions: Sequence[Mapping],
    settlements: Mapping[str, Mapping],
    space_id: str,
) -> list[MonthDocument]:
    """One document per recorded income or expense. Transfers stay out.

    ``resolutions`` is newest first. The first draft for an activity wins.
    Status comes only from ``settlements``.
    """

    latest: dict[str, Mapping] = {}
    for row in resolutions:
        latest.setdefault(str(row["activity_id"]), row)
    documents = []
    for activity in activities:
        kind = activity.get("kind")
        if kind not in {"income", "expense"}:
            continue
        activity_id = str(activity["activity_id"])
        parts = read_fiscal(
            latest.get(activity_id, {}).get("resolution"), activity["currency"]
        )
        settlement = settlements.get(activity_id)
        if settlement is None:
            status, settled_on, method = IMPLICIT.status, None, None
        else:
            status = str(settlement["status"])
            settled_on = _as_date(settlement.get("settled_on"))
            method = _text(settlement.get("payment_method"))
        documents.append(
            MonthDocument(
                activity_id=activity_id,
                space_id=space_id,
                role="invoice" if kind == "income" else "receipt",
                currency=str(activity["currency"]),
                total_minor=int(activity["amount_minor"]),
                itbis_minor=parts.itbis_minor,
                occurred_on=occurred_on(activity),
                rnc=parts.rnc,
                ncf=parts.ncf,
                ecf=parts.ecf,
                personal=parts.personal,
                include_606=parts.include_606,
                declared_base_minor=parts.declared_base_minor,
                counterparty=parts.counterparty,
                sin_comprobante=parts.sin_comprobante,
                due_on=parts.due_on,
                status=status,
                settled_on=settled_on,
                payment_method=method,
            )
        )
    return documents
