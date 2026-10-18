from __future__ import annotations

from datetime import date

from argus.domain.business.contracts.dgii import PurchaseDeclaration, amount_or_zero
from argus.domain.business.dgii_validation import FiscalRecord, fact_value, ncf_type
from argus.domain.business.fiscal_identity import (
    cedula_check_digit_ok,
    identity_digits,
    normalized_ncf,
    rnc_check_digit_ok,
)
from argus.domain.business.rnc_registry import RncRecord, RncRegistry

COPY = {
    "fiscal_identity_length": {
        "es": "El RNC debe tener 9 dígitos (empresa) u 11 (cédula).",
        "en": "An RNC has 9 digits and a cédula has 11.",
    },
    "fiscal_identity_check_digit": {
        "es": "El dígito verificador no coincide.",
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
    "expense_type_missing": {
        "es": "Falta el tipo de gasto",
        "en": "Expense type is missing",
    },
    "payment_method_missing": {
        "es": "Falta la forma de pago",
        "en": "Payment method is missing",
    },
    "rnc_unverified": {
        "es": "Todavía no lo hemos verificado con la DGII.",
        "en": "We have not verified it with the DGII yet.",
    },
}


def reason(code: str, locale: str = "es") -> str:
    return COPY[code][locale]


def _dated(record: RncRecord, locale: str) -> str:
    estado = record.status
    if record.file_date is None:
        filed = ""
    else:
        filed = record.file_date.strftime("%d/%m/%Y")
    if locale == "en":
        if filed:
            return f"The DGII lists this RNC as «{estado}» in the register of {filed}."
        return f"The DGII lists this RNC as «{estado}»."
    if filed:
        return f"La DGII lista este RNC como «{estado}» en el registro del {filed}."
    return f"La DGII lista este RNC como «{estado}»."


def confirmed_declaration(record: FiscalRecord):
    declaration = record.declaration
    if isinstance(declaration, PurchaseDeclaration) and declaration.category_suggested:
        return declaration.model_copy(update={"category": None})
    return declaration


def _reject(record: FiscalRecord, code: str, field: str) -> dict:
    return {
        "code": code,
        "activity_id": record.activity_id,
        "field": field,
        "reason": reason(code, "es"),
        "reason_en": reason(code, "en"),
    }


def hard_rejects(record: FiscalRecord, registry: RncRegistry) -> list[dict]:
    declaration = confirmed_declaration(record)
    if not isinstance(declaration, PurchaseDeclaration):
        return []
    raw = fact_value(record, "rnc")
    digits = identity_digits(raw)
    found = registry.lookup(digits) if digits else None
    number = normalized_ncf(fact_value(record, "ecf") or fact_value(record, "ncf"))
    presented = fact_value(record, "ecf") or fact_value(record, "ncf")
    issues = []
    if digits is None or len(digits) not in {9, 11}:
        issues.append(_reject(record, "fiscal_identity_length", "rnc"))
    elif not (
        rnc_check_digit_ok(digits) if len(digits) == 9 else cedula_check_digit_ok(digits)
    ):
        if found is None:
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


def _warning(record: FiscalRecord, code: str, **extra) -> dict:
    return {
        "code": code,
        "line": record.activity_id,
        "reason": reason(code, "es") if code in COPY else extra.get("reason", ""),
        "reason_en": reason(code, "en") if code in COPY else extra.get("reason_en", ""),
        **extra,
    }


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
        warnings.append(_warning(record, "rnc_unverified"))
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
    if declaration.category is None:
        warnings.append(_warning(record, "expense_type_missing"))
    if declaration.payment_method is None:
        warnings.append(_warning(record, "payment_method_missing"))
    return check, warnings
