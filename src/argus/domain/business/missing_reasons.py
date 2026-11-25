"""The one vocabulary for what a document still needs.

Each reason has one code, the field a person fixes and the locale path of its
words. Registros (`readiness()`) and the Bandeja's Listo rule (`ListoGap`)
both name their gaps with these codes. The order is the order a person fixes
them in: a missing value, then a wrong one.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

#: The locale block that holds the words Registros shows and its file writes.
REGISTROS_WORDS = "business.transactions.layout.workflow.missing"
_DOSSIER_WORDS = "business.dossier.gap"
_DOSSIER_PLACEHOLDER_WORDS = "business.dossier.placeholder.gap"
# Shown when a hold has no named fix yet. Never a raw code.
DETAIL_MISSING = "detail_missing"


@dataclass(frozen=True)
class MissingReason:
    code: str
    #: The field a person fixes. None when no single field holds the gap.
    field: str | None
    #: Locale path of the words, the same in every language.
    words: str


def _registros(code: str, field: str | None) -> MissingReason:
    return MissingReason(code, field, f"{REGISTROS_WORDS}.{code}")


def _bandeja(code: str, field: str | None, block: str) -> MissingReason:
    return MissingReason(code, field, f"{block}.{code}.title")


REASONS: dict[str, MissingReason] = {
    reason.code: reason
    for reason in (
        _registros("expense_type_missing", "category"),
        _registros("missing_rnc", "rnc"),
        _registros("invalid_rnc", "rnc"),
        _registros("invalid_ncf", "ncf"),
        _registros("missing_date", "occurred_on"),
        _registros("missing_ncf", "ncf"),
        _registros("payment_method_missing", "payment_method"),
        _registros("payment_date_missing", "paid_on"),
        _registros("duplicate_document", "ncf"),
        _registros("own_rnc_required", "rnc"),
        _registros("billed_amount_zero", "billed_amount"),
        _registros("itbis_cost_over_itbis", "itbis_cost"),
        _registros("payment_after_month", "paid_on"),
        _registros("credit_note_reference", "modified_ncf"),
        _registros("credit_note_too_late", "occurred_on"),
        _registros("credit_note_payment_form", "payment_method"),
        _registros("modified_ncf_not_allowed", "modified_ncf"),
        _registros("modified_ncf_invalid", "modified_ncf"),
        _registros("date_in_future", "occurred_on"),
        _registros("date_too_old", "occurred_on"),
        _registros("payment_date_in_future", "paid_on"),
        _registros("payment_before_invoice", "paid_on"),
        _registros("itbis_over_limit", "itbis"),
        _registros("itbis_proportionality_over_itbis", "itbis_proportionality"),
        _registros("itbis_withheld_over_itbis", "itbis_withheld"),
        _registros("tip_over_limit", "legal_tip"),
        _registros("purchase_receipt_needs_cedula", "rnc"),
        _registros("minor_expense_has_itbis", "itbis"),
        _registros(DETAIL_MISSING, None),
        _registros("duplicate", None),
        # Gaps only a document in the Bandeja has. The dossier holds their words.
        _bandeja("reading", None, _DOSSIER_PLACEHOLDER_WORDS),
        _bandeja("not_read", None, _DOSSIER_PLACEHOLDER_WORDS),
        _bandeja("check_details", None, _DOSSIER_PLACEHOLDER_WORDS),
        _bandeja("no_purchase_found", None, _DOSSIER_PLACEHOLDER_WORDS),
        _bandeja("several_purchases", None, _DOSSIER_PLACEHOLDER_WORDS),
        _bandeja("credit_note", None, _DOSSIER_PLACEHOLDER_WORDS),
        _bandeja("missing_merchant", "counterparty", _DOSSIER_PLACEHOLDER_WORDS),
        _bandeja("missing_amount", "amount", _DOSSIER_WORDS),
        _bandeja("missing_currency", "currency", _DOSSIER_PLACEHOLDER_WORDS),
        _bandeja("sin_comprobante", "ncf", _DOSSIER_PLACEHOLDER_WORDS),
        _bandeja("ecf_check_failed", "ncf", _DOSSIER_PLACEHOLDER_WORDS),
        _bandeja("missing_itbis", "itbis", _DOSSIER_PLACEHOLDER_WORDS),
        _bandeja("review_flag", None, _DOSSIER_PLACEHOLDER_WORDS),
        _bandeja("blocked", None, _DOSSIER_PLACEHOLDER_WORDS),
        _bandeja("unverified_sender", None, _DOSSIER_PLACEHOLDER_WORDS),
    )
}


def registered(codes: Iterable[str]) -> None:
    """Refuse a table that names a reason the registry does not hold."""

    unknown = sorted(set(codes) - set(REASONS))
    if unknown:
        raise KeyError(f"missing reasons outside the registry: {unknown}")


_FILE_WORDS = json.loads(
    Path(__file__).with_name("records_file_words.generated.json").read_text("utf-8")
)


def words(code: str, locale: Literal["es-419", "en"]) -> str:
    """The Registros words of a reason, as the locale holds them."""

    return _FILE_WORDS[locale][REGISTROS_WORDS][code]
