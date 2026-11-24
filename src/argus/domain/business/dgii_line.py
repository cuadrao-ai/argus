from __future__ import annotations

from datetime import date

from argus.domain.business.contracts.dgii import (
    PurchaseDeclaration,
    amount_or_zero,
    printed_date,
)
from argus.domain.business.dgii_606_rules import RULES
from argus.domain.business.dgii_validation import FiscalRecord, fact_value, ncf_type
from argus.domain.business.document_type import direction
from argus.domain.business.fiscal_identity import (
    cedula_check_digit_ok,
    identity_digits,
    normalized_ncf,
    rnc_check_digit_ok,
)
from argus.domain.business.missing_reasons import (
    DETAIL_MISSING,
    REASONS,
    registered,
    words,
)
from argus.domain.business.rnc_registry import RncRecord, RncRegistry

# Missing values in these 606 fields are valid and export as zero.
REQUIRED_ZERO_606 = frozenset({"itbis_withheld", "income_withheld"})

COPY = {
    "fiscal_identity_length": {
        "es": "El RNC debe tener 9 dígitos (empresa) u 11 (cédula).",
        "en": "An RNC has 9 digits and a cédula has 11.",
    },
    "fiscal_identity_check_digit": {
        "es": "No se puede exportar hasta corregir el RNC.",
        "en": "The check digit does not match.",
    },
    "fiscal_identity_type_mismatch": {
        "es": "El tipo de identificación no coincide con el número.",
        "en": "The ID type does not match the number.",
    },
    "fiscal_ncf_malformed": {
        "es": "El NCF no tiene el formato de la serie B o E.",
        "en": "The NCF does not match the B-series or E-series format.",
    },
    "fiscal_withholding_payment_date_required": {
        "es": "Agrega la fecha de pago para registrar una retención.",
        "en": "Add the payment date to record a withholding.",
    },
    "fiscal_b01_rnc_required": {
        "es": "Un comprobante B01 necesita el RNC del suplidor.",
        "en": "A B01 needs the supplier RNC.",
    },
    "fiscal_details_missing": {
        "es": "Faltan datos fiscales",
        "en": "Fiscal details missing",
    },
    "rnc_unverified": {
        "es": "Todavía no lo hemos verificado con la DGII.",
        "en": "We have not verified it with the DGII yet.",
    },
    "rnc_check_digit": {
        "es": "El dígito verificador del RNC no coincide. Revisa que esté bien escrito.",
        "en": "The RNC check digit does not match. Check that it is written correctly.",
    },
    "ncf_malformed": {
        "es": "El NCF no tiene el formato correcto. Debe ser B más 10 dígitos, o E más 12 si es e-CF. Revisa lo que dice el comprobante.",
        "en": "The NCF is not in the right format. It is B plus 10 digits, or E plus 12 for an e-CF. Check what the receipt says.",
    },
    "itbis_high": {
        "es": "El ITBIS parece alto para este total. Revisa los montos.",
        "en": "The ITBIS looks high for this total. Check the amounts.",
    },
    "duplicate_comprobante": {
        "es": "Ya registraste este comprobante.",
        "en": "You already recorded this receipt.",
    },
    "duplicate_comprobante_action": {
        "es": "Ver el registrado",
        "en": "See the recorded one",
    },
}


#: The reason for each issue raised outside the 606 rule table. A rule in the
#: table carries its own. An issue outside both reads as DETAIL_MISSING.
ISSUE_REASON = {
    ("fiscal_declaration_missing", "declaration"): "expense_type_missing",
    ("fiscal_fact_required", "category"): "expense_type_missing",
    ("fiscal_identity_required", "rnc"): "invalid_rnc",
    ("fiscal_identity_length", "rnc"): "invalid_rnc",
    ("fiscal_b01_rnc_required", "rnc"): "missing_rnc",
    ("fiscal_identity_check_digit", "rnc"): "invalid_rnc",
    ("fiscal_identity_type_mismatch", "id_type"): "invalid_rnc",
    ("fiscal_ncf_malformed", "ncf"): "invalid_ncf",
    ("fiscal_ncf_unsupported", "ncf"): "invalid_ncf",
    ("fiscal_ncf_unsupported", "modified_ncf"): "modified_ncf_invalid",
    ("fiscal_activity_revision_changed", "occurred_on"): "missing_date",
    ("fiscal_fact_required", "ncf"): "missing_ncf",
    ("fiscal_fact_required", "payment_method"): "payment_method_missing",
    ("fiscal_payment_date_required", "paid_on"): "payment_date_missing",
    ("fiscal_withholding_payment_date_required", "paid_on"): "payment_date_missing",
    ("fiscal_duplicate_document", "ncf"): "duplicate_document",
    ("fiscal_supplier_must_match_filer", "rnc"): "own_rnc_required",
    ("fiscal_billed_amount_must_be_positive", "billed_amount"): "billed_amount_zero",
    ("fiscal_itbis_cost_exceeds_tax", "itbis_cost"): "itbis_cost_over_itbis",
    ("fiscal_payment_date_after_period", "paid_on"): "payment_after_month",
    ("fiscal_credit_settlement_required", "purchase_activity_id"): "credit_note_reference",
    ("fiscal_credit_reference_conflict", "modified_ncf"): "credit_note_reference",
    ("fiscal_credit_tax_treatment_required", "occurred_on"): "credit_note_too_late",
    ("fiscal_credit_original_reporting_required", "modified_ncf"): "credit_note_reference",
    ("fiscal_credit_original_unsupported", "modified_ncf"): "credit_note_reference",
    ("fiscal_credit_payment_code_required", "payment_method"): "credit_note_payment_form",
    ("fiscal_credit_reference_not_applicable", "modified_ncf"): "modified_ncf_not_allowed",
    (
        "fiscal_credit_reference_not_applicable",
        "purchase_activity_id",
    ): "modified_ncf_not_allowed",
}
registered((*ISSUE_REASON.values(), *(rule.message_key for rule in RULES)))


#: The issues that hold a purchase's 606 line with no Forma de Pago: the field
#: is blank, or the record has no declaration to hold it.
PAYMENT_FORM_ISSUES = frozenset(
    {
        ("fiscal_fact_required", "payment_method"),
        ("fiscal_declaration_missing", "declaration"),
    }
)


def missing_items(record: FiscalRecord, issues: list[dict]) -> tuple[str, ...]:
    """Every named fix the record needs, in the registry's order, or DETAIL_MISSING."""
    absent = identity_digits(fact_value(record, "rnc")) is None
    found = [
        issue.get("message_key") or ISSUE_REASON.get((issue["code"], issue["field"]))
        for issue in issues
    ]
    found = [
        "missing_rnc" if code == "invalid_rnc" and absent else code for code in found
    ]
    known = tuple(code for code in REASONS if code in found)
    return known or (DETAIL_MISSING,)


def reason(code: str, locale: str = "es") -> str:
    return COPY[code][locale]


def _said(code: str) -> dict:
    return {"reason": reason(code, "es"), "reason_en": reason(code, "en")}


def _missing_said(code: str) -> dict:
    return {"reason": words(code, "es-419"), "reason_en": words(code, "en")}


def _dated(record: RncRecord, locale: str) -> str:
    estado = record.status
    if record.file_date is None:
        filed = ""
    else:
        filed = printed_date(record.file_date)
    if locale == "en":
        if filed:
            return f"The DGII lists this RNC as «{estado}» in the register of {filed}."
        return f"The DGII lists this RNC as «{estado}»."
    if filed:
        return f"La DGII lista este RNC como «{estado}» en el registro del {filed}."
    return f"La DGII lista este RNC como «{estado}»."


def confirmed_declaration(record: FiscalRecord):
    """The declaration the record's form reads. Data saved for the other form
    is no declaration of this record, and a suggested tipo de gasto nobody
    confirmed counts as missing."""

    declaration = record.declaration
    found = direction(record.document_type)
    if declaration is None or found is None or declaration.form != found.form:
        return None
    if isinstance(declaration, PurchaseDeclaration) and declaration.category_suggested:
        return declaration.model_copy(update={"category": None})
    return declaration


def _reject(record: FiscalRecord, code: str, field: str) -> dict:
    return {
        "code": code,
        "activity_id": record.activity_id,
        "field": field,
        **_said(code),
    }


def hard_rejects(record: FiscalRecord, registry: RncRegistry) -> list[dict]:
    declaration = confirmed_declaration(record)
    if not isinstance(declaration, PurchaseDeclaration):
        return []
    digits = identity_digits(fact_value(record, "rnc"))
    number = normalized_ncf(fact_value(record, "ecf") or fact_value(record, "ncf"))
    presented = fact_value(record, "ecf") or fact_value(record, "ncf")
    issues = []
    if digits is None or len(digits) not in {9, 11}:
        issues.append(_reject(record, "fiscal_identity_length", "rnc"))
    elif registry.lookup(digits) is None and not (
        rnc_check_digit_ok(digits) if len(digits) == 9 else cedula_check_digit_ok(digits)
    ):
        issues.append(_reject(record, "fiscal_identity_check_digit", "rnc"))
    if (declaration.id_type == "1" and (digits is None or len(digits) != 9)) or (
        declaration.id_type == "2" and (digits is None or len(digits) != 11)
    ):
        issues.append(_reject(record, "fiscal_identity_type_mismatch", "id_type"))
    if presented and number is None:
        issues.append(_reject(record, "fiscal_ncf_malformed", "ncf"))
    withheld = amount_or_zero(declaration.itbis_withheld) + amount_or_zero(
        declaration.income_withheld
    )
    if withheld > 0 and declaration.paid_on is None:
        issues.append(
            _reject(record, "fiscal_withholding_payment_date_required", "paid_on")
        )
    if (
        ncf_type(number or "") == "01"
        and number
        and number.startswith("B")
        and not digits
    ):
        issues.append(_reject(record, "fiscal_b01_rnc_required", "rnc"))
    return issues


def _warning(record: FiscalRecord, code: str, **said) -> dict:
    return {"code": code, "line": record.activity_id, **said}


def line_review(record: FiscalRecord, registry: RncRegistry) -> tuple[dict, list[dict]]:
    declaration = confirmed_declaration(record)
    if not isinstance(declaration, PurchaseDeclaration):
        return {}, []
    digits = identity_digits(fact_value(record, "rnc"))
    found = registry.lookup(digits) if digits else None
    if found is None:
        status = "sin_verificar"
        name = trade_name = estado = None
        file_date = None
    elif found.verification == "verificado":
        status = "verificado"
        name, trade_name, estado, file_date = (
            found.name,
            found.trade_name,
            found.status,
            found.file_date,
        )
    else:
        status = "no_activo"
        name, trade_name, estado, file_date = (
            found.name,
            found.trade_name,
            found.status,
            found.file_date,
        )
    check = {
        "line": record.activity_id,
        "status": status,
        "name": name,
        "trade_name": trade_name,
        "estado": estado,
        "file_date": file_date.isoformat() if isinstance(file_date, date) else None,
    }
    warnings = []
    if status == "sin_verificar" and digits:
        warnings.append(_warning(record, "rnc_unverified", **_said("rnc_unverified")))
    elif status == "no_activo" and found is not None:
        text = _dated(found, "es")
        english = _dated(found, "en")
        warnings.append(
            _warning(
                record,
                "rnc_inactive",
                reason=text,
                reason_en=english,
                estado=found.status,
                file_date=check["file_date"],
                trade_name=found.trade_name,
                name=found.name,
            )
        )
    for code, answer in (
        ("expense_type_missing", declaration.category),
        ("payment_method_missing", declaration.payment_method),
    ):
        if answer is None:
            warnings.append(_warning(record, code, **_missing_said(code)))
    return check, warnings
