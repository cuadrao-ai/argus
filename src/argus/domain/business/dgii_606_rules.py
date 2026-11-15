"""The 606 rules DGII's tools apply to a row: the one place they live.

Each rule reads the line the Formato DGII file writes, in annex order, plus a
small context. A broken ``block`` rule holds the row: Registros does not call
it Listo and the file does not carry it. ``revisar`` is for a row DGII accepts
that is likely wrong; no rule uses it yet.

``dgii_ref`` is the rule's id in DGII's pre-validator rule list and
``dgii_text`` its message there, kept for reference and never shown. The
person sees ``message_key``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Literal

from argus.domain.business.contracts.dgii import cell_date
from argus.domain.business.fiscal_identity import normalized_ncf

Line = Mapping[str, str]


@dataclass(frozen=True)
class Context:
    today: date
    #: The 606 period the row is filed in, ``YYYYMM``.
    period: str


Condition = Callable[[Line, Context], bool]


@dataclass(frozen=True)
class Rule:
    id: str
    dgii_ref: str
    #: The 606 column the person fixes.
    field: str
    applies_when: Condition
    #: True when the line is acceptable.
    check: Condition
    message_key: str
    dgii_text: str
    severity: Literal["block", "revisar"] = "block"
    #: First and last period the rule is in force, inclusive. None is open.
    from_period: str | None = None
    to_period: str | None = None


_ITBIS_TOLERANCE = Decimal("0.55")
_ITBIS_RATE = Decimal("0.18")
_ITBIS_RATE_BEFORE_2013 = Decimal("0.16")
_TIP_RATE = Decimal("0.10")
_CENT = Decimal("0.01")
#: The first invoice date DGII takes for each comprobante, most specific first.
_SERIES_START = (
    (("B17", "E47"), date(2019, 4, 1)),
    (("E",), date(2019, 1, 1)),
    (("B",), date(2018, 5, 1)),
)


def itbis_limit(base: Decimal, on: date | None = None) -> Decimal:
    """The most ITBIS DGII accepts on a taxable base for an invoice dated ``on``.

    Measured on DGII's pre-validator: it rounds the rate's share of the base
    to cents, half to even, and takes up to 0.55 above that."""

    rate = _ITBIS_RATE_BEFORE_2013 if on and on < date(2013, 1, 1) else _ITBIS_RATE
    return (base * rate).quantize(_CENT, ROUND_HALF_EVEN) + _ITBIS_TOLERANCE


def _amount(line: Line, name: str) -> Decimal:
    return Decimal(line[name] or "0")


def _day(line: Line, name: str) -> date | None:
    return cell_date(line[name])


def _number(line: Line, name: str) -> str | None:
    """The NCF in a cell when it is well formed. A malformed one is another rule's."""

    return normalized_ncf(line[name])


def _has(name: str) -> Condition:
    return lambda line, _: bool(line[name])


def _positive(name: str) -> Condition:
    return lambda line, _: _amount(line, name) > 0


def _at_most(name: str, ceiling: str) -> Condition:
    return lambda line, _: _amount(line, name) <= _amount(line, ceiling)


def _sequence_starts_at_one(name: str) -> Condition:
    return lambda line, _: int(_number(line, name)[3:]) >= 1


def _well_formed(name: str) -> Condition:
    return lambda line, _: _number(line, name) is not None


def _is_type(*kinds: str) -> Condition:
    return lambda line, _: line["ncf"][:3] in kinds


def _always(_line: Line, _context: Context) -> bool:
    return True


def _series_start(line: Line) -> date:
    return next(
        start for prefixes, start in _SERIES_START if line["ncf"].startswith(prefixes)
    )


# A rule waits for the value it judges: a row with no Servicios or Bienes yet,
# or no RNC, is held for that, not for a ceiling of zero or a missing cédula.
RULES: tuple[Rule, ...] = (
    Rule(
        id="ncf_sequence_zero",
        dgii_ref="C4",
        field="ncf",
        applies_when=_well_formed("ncf"),
        check=_sequence_starts_at_one("ncf"),
        message_key="ncf_invalid",
        dgii_text="Detalle:Linea: <n>:NCF: Secuencia (0) No Valida !",
    ),
    Rule(
        id="modified_ncf_sequence_zero",
        dgii_ref="G7",
        field="modified_ncf",
        applies_when=_well_formed("modified_ncf"),
        check=_sequence_starts_at_one("modified_ncf"),
        message_key="modified_ncf_invalid",
        dgii_text="Detalle:Linea: <n>:NCF MODIFICADO: Secuencia (0) No Valida !",
    ),
    Rule(
        id="invoice_date_in_future",
        dgii_ref="B5",
        field="occurred_on",
        applies_when=_always,
        check=lambda line, context: _day(line, "occurred_on") <= context.today,
        message_key="date_in_future",
        dgii_text="Detalle:Linea:<n>: Fecha Comprobante:(<x>),NO Valida",
    ),
    # Covers B5's year 2004 floor: only B and E comprobantes reach a line.
    Rule(
        id="invoice_date_before_series",
        dgii_ref="B5, F8",
        field="occurred_on",
        applies_when=_well_formed("ncf"),
        check=lambda line, _: _day(line, "occurred_on") >= _series_start(line),
        message_key="date_too_old",
        dgii_text="Detalle:Linea: <n>:NCF NO válido para este periodo: <p>",
    ),
    # F1's year 2004 floor follows from payment_before_invoice and the series floor.
    Rule(
        id="payment_date_in_future",
        dgii_ref="F1",
        field="paid_on",
        applies_when=_has("paid_on"),
        check=lambda line, context: _day(line, "paid_on") <= context.today,
        message_key="payment_date_in_future",
        dgii_text="Detalle:Linea:<n>: Fecha Pago:(<x>),NO Valida",
    ),
    Rule(
        id="payment_before_invoice",
        dgii_ref="F2",
        field="paid_on",
        applies_when=_has("paid_on"),
        check=lambda line, _: _day(line, "paid_on") >= _day(line, "occurred_on"),
        message_key="payment_before_invoice",
        dgii_text=(
            "Detalle:Linea:<n> Fecha de Pago no puede ser menor a la fecha de comprobante"
        ),
    ),
    Rule(
        id="itbis_over_cap",
        dgii_ref="E1",
        field="itbis",
        applies_when=_positive("billed_amount"),
        check=lambda line, _: _amount(line, "itbis")
        <= itbis_limit(
            _amount(line, "billed_amount") + _amount(line, "selective_tax"),
            _day(line, "occurred_on"),
        ),
        message_key="itbis_over_limit",
        dgii_text=(
            "Detalle:Linea:<n> ITBIS Facturado:(<x>), NO Puede ser Mayor que el"
            " 18 % de la base imponible  (<base>) "
        ),
    ),
    Rule(
        id="itbis_over_total",
        dgii_ref="E2",
        field="itbis",
        applies_when=_positive("billed_amount"),
        check=_at_most("itbis", "billed_amount"),
        message_key="itbis_over_limit",
        dgii_text=(
            "Detalle:Linea:<n> ITBIS Facturado:(<x>), NO Puede ser Mayor que el"
            " Monto Facturado (<t>) "
        ),
    ),
    Rule(
        id="itbis_proportionality_over_itbis",
        dgii_ref="E6",
        field="itbis_proportionality",
        applies_when=_positive("itbis_proportionality"),
        check=_at_most("itbis_proportionality", "itbis"),
        message_key="itbis_proportionality_over_itbis",
        dgii_text=(
            "Detalle:Linea:<n> ITBIS sujeto a Proporcionalidad (Art. 349), no"
            " puede ser mayor al ITBIS Facturado"
        ),
    ),
    Rule(
        id="itbis_withheld_without_itbis",
        dgii_ref="E7",
        field="itbis_withheld",
        applies_when=_positive("itbis_withheld"),
        check=_positive("itbis"),
        message_key="itbis_withheld_over_itbis",
        dgii_text=(
            "Detalle:Linea:<n> Para tener ITBIS Retenido debe Especificar ITBIS Facturado "
        ),
    ),
    Rule(
        id="itbis_withheld_over_itbis",
        dgii_ref="E8",
        field="itbis_withheld",
        applies_when=_positive("itbis_withheld"),
        check=_at_most("itbis_withheld", "itbis"),
        message_key="itbis_withheld_over_itbis",
        dgii_text=(
            "Detalle:Linea:<n> El ITBIS Retenido no puede ser Mayor que el ITBIS Facturado "
        ),
    ),
    # Measured on DGII's pre-validator: the 10% is not rounded, so a tip of
    # exactly 10% passes and one cent above 10% of 1234.57 does not.
    Rule(
        id="tip_over_limit",
        dgii_ref="E9",
        field="legal_tip",
        applies_when=lambda line, _: _amount(line, "legal_tip") > 0
        and _amount(line, "billed_amount") > 0,
        check=lambda line, _: _amount(line, "legal_tip")
        <= _amount(line, "billed_amount") * _TIP_RATE,
        message_key="tip_over_limit",
        dgii_text=(
            "Detalle:Linea:<n>Error en Monto de Propina Legal: (<x>), NO puede ser"
            " mayor al 10% del Total Monto Facturado:(<t>) "
        ),
    ),
    Rule(
        id="purchase_receipt_needs_cedula",
        dgii_ref="G1",
        field="rnc",
        applies_when=lambda line, _: line["ncf"][:3] == "B11" and bool(line["rnc"]),
        check=lambda line, _: len(line["rnc"]) == 11,
        message_key="purchase_receipt_needs_cedula",
        dgii_text=(
            "Detalle:Linea: <n>:Debe ingresar una cédula: (<ncf>), para este tipo"
            " de comprobante"
        ),
    ),
    Rule(
        id="minor_expense_has_itbis",
        dgii_ref="G2",
        field="itbis",
        applies_when=_is_type("B13", "E43"),
        check=lambda line, _: _amount(line, "itbis") == 0,
        message_key="minor_expense_has_itbis",
        dgii_text=(
            "Detalle:Linea: <n>:Tipo de Comprobante: (<ncf>), NO puede contener ITBIS"
        ),
    ),
)


def _in_force(rule: Rule, period: str) -> bool:
    return (rule.from_period is None or rule.from_period <= period) and (
        rule.to_period is None or period <= rule.to_period
    )


def broken(line: Line, context: Context) -> tuple[Rule, ...]:
    """Every rule in force for the line's period that the line does not meet."""

    return tuple(
        rule
        for rule in RULES
        if _in_force(rule, context.period)
        and rule.applies_when(line, context)
        and not rule.check(line, context)
    )
