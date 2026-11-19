"""The synthetic receipt set: what each receipt prints and what a correct read returns.

One table owns both. The renderer draws a case and ``expected`` derives its
answers, so an image and its expected-answer file cannot disagree. Every name,
number and identifier here is invented.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal
from urllib.parse import urlencode

from argus.domain.business.dgii_codes import EXPENSE_TYPES, PAYMENT_FORMS
from argus.domain.business.fiscal_identity import rnc_check_digit_ok
from faker import Faker

SEED = 1936
MONTHS_ABBR = (
    "ene",
    "feb",
    "mar",
    "abr",
    "may",
    "jun",
    "jul",
    "ago",
    "sep",
    "oct",
    "nov",
    "dic",
)
MONTHS_FULL = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)
# What the receipt prints about payment, and the forma de pago a correct read
# gives. A card and a purchase on credit terms both say "crédito".
PAYMENTS: dict[str, tuple[str | None, str | None]] = {
    "tarjeta_numero": ("TARJETA ****{last4}", "03"),
    "tarjeta_debito": ("TARJ. DEBITO ****{last4}", "03"),
    "tarjeta": ("Tarjeta de crédito", "03"),
    "efectivo": ("Efectivo", "01"),
    "transferencia": ("Transferencia bancaria", "02"),
    "credito": ("Condición de pago: A crédito", "04"),
    "credito30": ("Condición: Crédito 30 días", "04"),
    "none": (None, None),
}
_CENT = Decimal("0.01")
_SYLLABLES = ("ta", "vi", "re", "lo", "mu", "na", "ce", "do", "pa", "ri", "so", "gue")


ExpenseBasis = Literal["clear", "judgment"]


@dataclass(frozen=True)
class Trade:
    """What a supplier sells. ``expense_type`` is the tipo de gasto a correct
    read gives; None when the receipt alone cannot say. It is scored only when
    ``expense_basis`` is clear. A judgment answer is a build-time guess that no
    accountant has checked, so the read is reported and never scored."""

    name: str
    items: tuple[str, ...]
    expense_type: str | None
    price_cents: tuple[int, int] = (4500, 185000)
    expense_basis: ExpenseBasis = "judgment"


TRADES = {
    "papeleria": Trade(
        "Papelería",
        ("Resma carta", "Bolígrafo azul", "Folder manila", "Grapas 26/6"),
        "02",
        expense_basis="clear",
    ),
    "toner": Trade(
        "Suministros de Oficina",
        ("Tóner negro", "Cable HDMI", "Mouse inalámbrico", "Memoria USB 32GB"),
        "02",
        expense_basis="clear",
    ),
    "servicios": Trade(
        "Servicios Técnicos",
        (
            "Mantenimiento de equipos",
            "Servicio de fumigación",
            "Reparación de impresora",
            "Limpieza de oficina",
        ),
        "02",
        (150000, 900000),
        "clear",
    ),
    "equipos": Trade(
        "Equipos y Computadoras",
        (
            "Computadora portátil 15 pulg",
            "Impresora láser multifuncional",
            "Proyector de sala",
            "Servidor de archivos",
        ),
        "10",
        (2500000, 9500000),
        "clear",
    ),
    "mobiliario": Trade(
        "Muebles de Oficina",
        (
            "Escritorio ejecutivo",
            "Archivo metálico 4 gavetas",
            "Mesa de conferencias",
            "Estante de acero",
        ),
        "10",
        (1200000, 6000000),
        "clear",
    ),
    "restaurante": Trade(
        "Restaurante",
        ("Churrasco", "Mofongo de camarones", "Copa de vino", "Postre de la casa"),
        "05",
        (35000, 240000),
    ),
    "comedor": Trade(
        "Comedor Empresarial",
        (
            "Almuerzo empleados",
            "Plato del día personal",
            "Merienda del personal",
            "Jugo para empleados",
        ),
        "01",
        (25000, 60000),
    ),
    "uniformes": Trade(
        "Uniformes",
        (
            "Uniforme de trabajo",
            "Botas de seguridad",
            "Camisa del personal con logo",
            "Chaleco reflectivo",
        ),
        "01",
        (90000, 450000),
    ),
    "alquiler": Trade(
        "Inmobiliaria",
        ("Alquiler local comercial",),
        "03",
        (3500000, 9000000),
        "clear",
    ),
    "seguros": Trade(
        "Seguros",
        ("Prima póliza de vehículo",),
        "11",
        (1800000, 6000000),
        "clear",
    ),
    "colmado": Trade(
        "Colmado",
        ("Arroz selecto 5 lb", "Aceite 32 oz", "Habichuelas 1 lb", "Café 1 lb"),
        None,
    ),
    "ferreteria": Trade(
        "Ferretería",
        ("Tornillos 1/4", "Cinta métrica", "Brocha 2 pulg", "Lija fina"),
        None,
    ),
    "farmacia": Trade(
        "Farmacia",
        ("Alcohol 70%", "Gasa estéril", "Jabón neutro", "Vitamina C"),
        None,
    ),
}
# The code pairs a reader confuses, as (field, code, code).
HARD_PAIRS = (
    ("payment_form", "03", "04"),
    ("expense_type", "02", "10"),
    ("expense_type", "05", "01"),
)

MonthForm = Literal["number", "abbr", "sept", "full"]
Casing = Literal["upper", "lower", "title"]


@dataclass(frozen=True)
class DateStyle:
    """How one receipt prints a date. ``sept`` is the four-letter September."""

    pattern: str = "{d}/{m}/{y}"
    month: MonthForm = "number"
    casing: Casing = "upper"
    year_digits: Literal[2, 4] = 2

    def render(self, day: date) -> str:
        if self.month == "number":
            month = f"{day.month:02d}"
        else:
            name = (
                MONTHS_FULL[day.month - 1]
                if self.month == "full"
                else "sept"
                if self.month == "sept" and day.month == 9
                else MONTHS_ABBR[day.month - 1]
            )
            month = getattr(name, self.casing)()
        year = f"{day.year:04d}" if self.year_digits == 4 else f"{day.year % 100:02d}"
        return self.pattern.format(d=f"{day.day:02d}", m=month, y=year)


@dataclass(frozen=True)
class Item:
    description: str
    quantity: int
    unit_price: Decimal

    @property
    def total(self) -> Decimal:
        return self.quantity * self.unit_price


@dataclass(frozen=True)
class Case:
    case_id: str
    trade: str
    issued: date
    #: The label beside the issue date; None when the receipt prints no issue date.
    date_label: str | None = "Fecha"
    date_style: DateStyle = DateStyle()
    #: Only another date on the receipt settles day, month and year order.
    date_ambiguous: bool = False
    date_near_qr: bool = False
    with_time: bool = False
    #: The NCF sequence expiry. Never the issue date.
    expiry: date | None = None
    expiry_label: str = "Válido hasta"
    expiry_style: DateStyle | None = None
    expiry_first: bool = False
    signature_line: bool = False
    ncf_series: Literal["E31", "E32", "B01", "B02"] = "E32"
    supplier_rnc_print: Literal["printed", "absent", "smudged"] = "printed"
    rnc_dashed: bool = False
    buyer_rnc_label: str | None = None
    tax: Literal["itbis", "impuesto", "impuesto_zero", "none"] = "itbis"
    payment: str = "tarjeta_numero"
    qr: Literal["dgii", "cropped", "none"] = "dgii"
    merchant_qr: bool = False
    layout: Literal["strip", "collage2", "collage3", "two_receipts", "cut_totals"] = (
        "strip"
    )
    item_count: int = 5
    angle: float = 0.0
    shadow: bool = False
    finger: bool = False
    note: str | None = None
    merchant: str = ""
    address: str = ""
    cashier: str = ""
    supplier_rnc: str = ""
    buyer_rnc: str = ""
    buyer_name: str = ""
    ncf: str = ""
    security_code: str = ""
    card_last4: str = ""
    items: tuple[Item, ...] = ()
    companion: Case | None = None

    @property
    def subtotal(self) -> Decimal:
        return sum((item.total for item in self.items), Decimal(0))

    @property
    def tax_amount(self) -> Decimal:
        if self.tax in ("impuesto_zero", "none"):
            return Decimal("0.00")
        return (self.subtotal * Decimal("0.18")).quantize(_CENT, ROUND_HALF_UP)

    @property
    def total(self) -> Decimal:
        return self.subtotal + self.tax_amount

    @property
    def totals_visible(self) -> bool:
        return self.layout != "cut_totals"

    @property
    def signed_on(self) -> date:
        return self.issued + timedelta(days=1)

    @property
    def dgii_url(self) -> str | None:
        """The consultation link a DGII QR carries; a paper NCF has none."""

        if self.qr == "none":
            return None
        if self.ncf_series == "E32":
            return "https://fc.dgii.gov.do/eCF/ConsultaTimbreFC?" + urlencode(
                {
                    "RncEmisor": self.supplier_rnc,
                    "ENCF": self.ncf,
                    "MontoTotal": f"{self.total:.2f}",
                    "CodigoSeguridad": self.security_code,
                }
            )
        return "https://ecf.dgii.gov.do/ecf/ConsultaTimbre?" + urlencode(
            {
                "RncEmisor": self.supplier_rnc,
                "RncComprador": self.buyer_rnc,
                "ENCF": self.ncf,
                "FechaEmision": self.issued.strftime("%d-%m-%Y"),
                "MontoTotal": f"{self.total:.2f}",
                "FechaFirma": self.signed_on.strftime("%d-%m-%Y") + " 10:15:00",
                "CodigoSeguridad": self.security_code,
            }
        )


@dataclass(frozen=True)
class Expected:
    """What a correct read of the photo returns. None means the photo does not show it."""

    issue_date: str | None
    supplier_rnc: str | None
    buyer_rnc: str | None
    ncf: str | None
    total: str | None
    itbis: str | None
    #: DGII forma de pago code; None when the photo shows no payment.
    payment_form: str | None
    #: DGII tipo de gasto code; None when the receipt alone cannot say.
    expense_type: str | None
    #: "judgment" when the tipo de gasto answer is reported and never scored.
    expense_type_basis: ExpenseBasis
    dgii_qr_readable: bool
    complete: bool
    #: Receipts in the photo. Fields are scored only when there is one.
    purchases: int


def expected(case: Case) -> Expected:
    shown = case.totals_visible
    tax = {
        "itbis": f"{case.tax_amount:.2f}",
        "impuesto": f"{case.tax_amount:.2f}",
        "impuesto_zero": "0.00",
        "none": None,
    }[case.tax]
    return Expected(
        issue_date=case.issued.isoformat() if case.date_label else None,
        supplier_rnc=(
            case.supplier_rnc if case.supplier_rnc_print == "printed" else None
        ),
        buyer_rnc=case.buyer_rnc if case.buyer_rnc_label else None,
        ncf=case.ncf,
        total=f"{case.total:.2f}" if shown else None,
        itbis=tax if shown else None,
        payment_form=(PAYMENTS[case.payment][1] if shown and not case.finger else None),
        expense_type=TRADES[case.trade].expense_type,
        expense_type_basis=TRADES[case.trade].expense_basis,
        dgii_qr_readable=case.qr == "dgii" and shown,
        complete=shown,
        purchases=2 if case.companion else 1,
    )


def shapes(case: Case) -> tuple[str, ...]:
    """The coverage tags of one case. The coverage table counts these."""

    style = case.date_style
    tags = [
        {
            "strip": "single strip",
            "collage2": "collage of pieces",
            "collage3": "collage of pieces",
            "two_receipts": "several receipts in one photo",
            "cut_totals": "totals out of frame",
        }[case.layout]
    ]
    if case.date_label is None:
        tags.append("no issue date printed")
    else:
        tags.append(f"date label {case.date_label}")
        tags.append(f"{style.year_digits}-digit year")
        if style.month != "number":
            form = "full" if style.month == "full" else "short"
            tags.append(f"month name, {form}, {style.casing} case")
    flags = {
        "ambiguous day/month/year order": case.date_ambiguous,
        "issue date near the QR": case.date_near_qr,
        f"expiry line {case.expiry_label}": case.expiry is not None,
        "signature date line": case.signature_line,
        "tax line ITBIS": case.tax == "itbis",
        "tax line Impuesto": case.tax == "impuesto",
        "tax line Impuesto 0.00": case.tax == "impuesto_zero",
        "no tax line": case.tax == "none",
        "supplier and buyer RNC": bool(case.buyer_rnc_label)
        and case.supplier_rnc_print == "printed",
        "buyer RNC only": bool(case.buyer_rnc_label)
        and case.supplier_rnc_print == "absent",
        "smudged supplier RNC": case.supplier_rnc_print == "smudged",
        "RNC printed with dashes": case.rnc_dashed,
        "e-NCF": case.ncf_series.startswith("E"),
        "paper NCF": case.ncf_series.startswith("B"),
        "DGII QR in frame": case.qr == "dgii" and case.totals_visible,
        "DGII QR partly out of frame": case.qr == "cropped",
        "second QR, not DGII": case.merchant_qr,
        "finger over the payment line": case.finger,
        "handwritten note": case.note is not None,
        "shadow": case.shadow,
        "angled": case.angle != 0,
    }
    tags.extend(name for name, present in flags.items() if present)
    answer = expected(case)
    for name, code, labels in (
        ("forma de pago", answer.payment_form, PAYMENT_FORMS),
        ("tipo de gasto", answer.expense_type, EXPENSE_TYPES),
    ):
        tags.append(f"{name} {code} {labels[code]}" if code else f"{name}: none")
    return tuple(tags)


def coverage(cases: tuple[Case, ...]) -> dict[str, int]:
    return dict(sorted(Counter(tag for case in cases for tag in shapes(case)).items()))


def hard_pair_counts(cases: tuple[Case, ...]) -> dict[str, tuple[int, int]]:
    """Scored receipts on each side of every hard pair."""

    answers = [expected(case) for case in cases if not case.companion]
    return {
        f"{field} {first} vs {second}": (
            sum(getattr(answer, field) == first for answer in answers),
            sum(getattr(answer, field) == second for answer in answers),
        )
        for field, first, second in HARD_PAIRS
    }


def _rnc(fake: Faker) -> str:
    """A nine-digit number with a valid check digit. It starts with 9 so it
    stays apart from issued numbers."""

    body = "9" + fake.numerify("#######")
    return next(
        body + str(digit) for digit in range(10) if rnc_check_digit_ok(f"{body}{digit}")
    )


def _name(fake: Faker) -> str:
    return "".join(fake.random_elements(_SYLLABLES, length=3, unique=True)).title()


def _filled(case: Case) -> Case:
    fake = Faker("es_ES")
    fake.seed_instance(f"{SEED}:{case.case_id}")
    trade = TRADES[case.trade]
    series = case.ncf_series
    if series == "E32" and case.buyer_rnc_label:
        series = "E31"
    digits = 10 if series.startswith("E") else 8
    items = tuple(
        Item(
            description=fake.random_element(trade.items),
            quantity=fake.random_int(1, 4),
            unit_price=Decimal(fake.random_int(*trade.price_cents)) / 100,
        )
        for _ in range(case.item_count)
    )
    return replace(
        case,
        ncf_series=series,
        merchant=f"{trade.name} {_name(fake)} SRL",
        address=f"Calle {_name(fake)} #{fake.random_int(2, 180)}, Santo Domingo",
        cashier=fake.first_name(),
        supplier_rnc=_rnc(fake),
        buyer_rnc=_rnc(fake),
        buyer_name=f"{_name(fake)} {_name(fake)} SRL",
        ncf=f"{series}{fake.random_int(1, 99999):0{digits}d}",
        security_code=fake.bothify("??##??"),
        card_last4=fake.numerify("####"),
        items=items,
        expiry_style=case.expiry_style or case.date_style,
    )


def _case(
    case_id: str, trade: str, issued: tuple[int, int, int], **shape: object
) -> Case:
    if shape.get("ncf_series", "E").startswith("B"):
        shape.setdefault("qr", "none")
    return _filled(Case(case_id=case_id, trade=trade, issued=date(*issued), **shape))


def _named(pattern: str, casing: Casing, year: Literal[2, 4] = 4) -> DateStyle:
    return DateStyle(pattern, "abbr", casing, year)


_SLASH4 = DateStyle("{d}/{m}/{y}", year_digits=4)
_DASH2 = DateStyle("{d}-{m}-{y}")
_DASH4 = DateStyle("{d}-{m}-{y}", year_digits=4)
_BUYER = {"buyer_rnc_label": "RNC Cliente"}
_BUYER_ONLY = {**_BUYER, "supplier_rnc_print": "absent"}
_NO_DATE = {"date_label": None, **_BUYER}


def build_cases() -> tuple[Case, ...]:
    cases = (
        _case(
            "fecha-2-digit-year",
            "papeleria",
            (2026, 11, 4),
            expiry=date(2027, 12, 31),
            angle=1.5,
        ),
        _case(
            "emitido-4-digit-year",
            "colmado",
            (2026, 1, 17),
            date_label="Emitido",
            date_style=_SLASH4,
            tax="impuesto",
            payment="efectivo",
            expiry=date(2026, 12, 31),
            shadow=True,
        ),
        _case(
            "fecha-emision-dashes",
            "restaurante",
            (2026, 2, 23),
            date_label="Fecha Emisión",
            date_style=_DASH2,
            payment="tarjeta_debito",
            expiry=date(2027, 12, 31),
            expiry_label="Caduca",
            expiry_first=True,
            date_near_qr=True,
            angle=-2.0,
        ),
        _case(
            "ambiguous-10-11-25",
            "toner",
            (2025, 11, 10),
            date_ambiguous=True,
            with_time=True,
            expiry=date(2026, 12, 31),
            expiry_first=True,
            **_BUYER,
        ),
        _case(
            "ambiguous-05-06-26",
            "ferreteria",
            (2026, 6, 5),
            date_label="Emitido",
            date_ambiguous=True,
            expiry=date(2027, 12, 31),
            expiry_label="Caduca",
            layout="collage2",
            item_count=12,
            shadow=True,
        ),
        _case(
            "ambiguous-10-11-12",
            "colmado",
            (2012, 11, 10),
            date_ambiguous=True,
            expiry=date(2013, 12, 31),
            ncf_series="B02",
            tax="none",
            payment="efectivo",
            angle=2.0,
        ),
        _case(
            "no-date-valido-hasta",
            "servicios",
            (2026, 3, 12),
            expiry=date(2026, 12, 31),
            angle=1.0,
            **_NO_DATE,
        ),
        _case(
            "no-date-caduca-qr-cut",
            "equipos",
            (2026, 5, 20),
            expiry=date(2027, 12, 31),
            expiry_label="Caduca",
            qr="cropped",
            shadow=True,
            **_NO_DATE,
        ),
        _case(
            "no-date-collage",
            "ferreteria",
            (2026, 8, 7),
            expiry=date(2027, 12, 31),
            layout="collage3",
            item_count=18,
            payment="tarjeta_debito",
            **_NO_DATE,
        ),
        _case(
            "no-date-expiry-month-name",
            "comedor",
            (2025, 9, 26),
            expiry=date(2026, 12, 31),
            expiry_style=_named("{d}-{m}-{y}", "upper"),
            tax="impuesto",
            note="sept",
            **_NO_DATE,
        ),
        _case(
            "both-rnc-cliente",
            "mobiliario",
            (2026, 7, 9),
            date_style=_SLASH4,
            signature_line=True,
            rnc_dashed=True,
            **_BUYER,
        ),
        _case(
            "both-rnc-comprador",
            "papeleria",
            (2025, 12, 18),
            date_label="Emitido",
            buyer_rnc_label="RNC Comprador",
            tax="impuesto",
            payment="tarjeta",
            layout="collage2",
            item_count=11,
            angle=1.0,
        ),
        _case(
            "buyer-rnc-only",
            "restaurante",
            (2025, 10, 2),
            date_style=_DASH4,
            expiry=date(2026, 12, 31),
            shadow=True,
            **_BUYER_ONLY,
        ),
        _case(
            "buyer-rnc-only-qr-cut",
            "uniformes",
            (2026, 4, 27),
            date_label="Fecha Emisión",
            buyer_rnc_label="RNC Comprador",
            supplier_rnc_print="absent",
            qr="cropped",
            payment="efectivo",
            angle=-1.5,
        ),
        _case(
            "buyer-rnc-only-collage",
            "colmado",
            (2025, 8, 14),
            layout="collage3",
            item_count=20,
            tax="impuesto",
            merchant_qr=True,
            **_BUYER_ONLY,
        ),
        _case(
            "smudged-supplier-rnc",
            "farmacia",
            (2025, 6, 6),
            date_style=_DASH2,
            supplier_rnc_print="smudged",
            angle=3.0,
        ),
        _case(
            "smudged-supplier-rnc-with-buyer",
            "equipos",
            (2026, 9, 1),
            date_label="Emitido",
            supplier_rnc_print="smudged",
            expiry=date(2027, 12, 31),
            shadow=True,
            **_BUYER,
        ),
        _case(
            "impuesto-zero",
            "farmacia",
            (2025, 5, 22),
            tax="impuesto_zero",
            payment="efectivo",
            angle=-1.0,
        ),
        _case(
            "no-tax-line",
            "colmado",
            (2025, 3, 13),
            date_style=_SLASH4,
            tax="none",
            payment="tarjeta_debito",
            merchant_qr=True,
        ),
        _case(
            "impuesto-under-subtotal-collage",
            "toner",
            (2026, 10, 29),
            date_label="Fecha Emisión",
            tax="impuesto",
            layout="collage2",
            item_count=13,
            shadow=True,
            **_BUYER,
        ),
        _case(
            "paper-b01-both-rnc",
            "servicios",
            (2025, 1, 30),
            date_label="Emitido",
            date_style=_DASH4,
            ncf_series="B01",
            payment="tarjeta",
            expiry=date(2025, 12, 31),
            expiry_label="Caduca",
            note="ENE",
            **_BUYER,
        ),
        _case(
            "finger-over-payment",
            "restaurante",
            (2024, 12, 19),
            date_style=_SLASH4,
            finger=True,
            expiry=date(2025, 12, 31),
            angle=-2.5,
        ),
        _case(
            "month-ENE",
            "seguros",
            (2026, 1, 8),
            date_style=_named("{d}-{m}-{y}", "upper"),
            expiry=date(2026, 12, 31),
        ),
        _case(
            "month-feb",
            "comedor",
            (2026, 2, 14),
            date_label="Emitido",
            date_style=_named("{d}-{m}-{y}", "lower"),
            payment="efectivo",
            finger=True,
            angle=1.5,
        ),
        _case(
            "month-Mar",
            "mobiliario",
            (2026, 3, 21),
            date_style=_named("{d}/{m}/{y}", "title", 2),
            tax="impuesto",
            shadow=True,
            **_BUYER,
        ),
        _case(
            "month-ABR",
            "papeleria",
            (2026, 4, 2),
            date_label="Fecha Emisión",
            date_style=_named("{d} {m} {y}", "upper"),
            expiry=date(2027, 12, 31),
            expiry_label="Caduca",
            layout="collage2",
            item_count=12,
        ),
        _case(
            "month-may",
            "uniformes",
            (2025, 5, 19),
            date_style=_named("{d}-{m}-{y}", "lower", 2),
            payment="tarjeta",
            note="mayo",
        ),
        _case(
            "month-Jun",
            "servicios",
            (2025, 6, 30),
            date_label="Emitido",
            date_style=_named("{d}-{m}-{y}", "title"),
            expiry=date(2026, 12, 31),
            expiry_first=True,
            angle=-3.0,
            **_BUYER_ONLY,
        ),
        _case(
            "month-JUL",
            "farmacia",
            (2025, 7, 7),
            date_style=_named("{d}/{m}/{y}", "upper"),
            tax="impuesto_zero",
            payment="efectivo",
            merchant_qr=True,
        ),
        _case(
            "month-ago-near-qr",
            "equipos",
            (2025, 8, 12),
            date_label="Fecha Emisión",
            date_style=_named("{d}-{m}-{y}", "lower"),
            date_near_qr=True,
            expiry=date(2026, 12, 31),
            shadow=True,
            **_BUYER,
        ),
        _case(
            "month-Sep",
            "restaurante",
            (2025, 9, 25),
            date_style=_named("{d} {m} {y}", "title"),
            payment="tarjeta_debito",
            angle=2.0,
        ),
        _case(
            "month-SEPT",
            "alquiler",
            (2024, 9, 9),
            date_label="Emitido",
            date_style=DateStyle("{d}-{m}-{y}", "sept", "upper", 4),
            expiry=date(2025, 12, 31),
            expiry_label="Caduca",
        ),
        _case(
            "month-OCT",
            "ferreteria",
            (2026, 10, 15),
            date_style=_named("{d}-{m}-{y}", "upper"),
            expiry=date(2027, 12, 31),
            note="oct",
            layout="collage3",
            item_count=19,
            **_BUYER,
        ),
        _case(
            "month-nov",
            "comedor",
            (2025, 11, 3),
            date_label="Fecha Emisión",
            date_style=_named("{d}-{m}-{y}", "lower"),
            tax="none",
            shadow=True,
        ),
        _case(
            "month-Dic",
            "toner",
            (2025, 12, 28),
            date_style=_named("{d}/{m}/{y}", "title", 2),
            expiry=date(2026, 12, 31),
            payment="tarjeta",
            angle=-1.5,
        ),
        _case(
            "month-octubre-full",
            "mobiliario",
            (2024, 10, 15),
            date_label="Emitido",
            date_style=DateStyle("{d} de {m} de {y}", "full", "lower", 4),
            **_BUYER,
        ),
        _case(
            "month-Enero-full",
            "uniformes",
            (2026, 1, 6),
            date_style=DateStyle("{d} {m} {y}", "full", "title", 4),
            expiry=date(2026, 12, 31),
            tax="impuesto",
            shadow=True,
        ),
        _case(
            "month-MARZO-full",
            "colmado",
            (2025, 3, 22),
            date_label="Fecha Emisión",
            date_style=DateStyle("{d} DE {m} DE {y}", "full", "upper", 4),
            payment="efectivo",
            merchant_qr=True,
            angle=1.0,
        ),
        _case(
            "two-receipts-one-photo",
            "papeleria",
            (2025, 7, 11),
            layout="two_receipts",
            item_count=3,
            companion=_case(
                "two-receipts-one-photo-second",
                "colmado",
                (2025, 7, 12),
                date_label="Emitido",
                payment="efectivo",
                item_count=3,
            ),
        ),
        _case(
            "credit-terms-a-credito",
            "equipos",
            (2026, 8, 18),
            date_style=_SLASH4,
            payment="credito",
            item_count=2,
            rnc_dashed=True,
            **_BUYER,
        ),
        _case(
            "credit-terms-30-dias",
            "mobiliario",
            (2025, 4, 9),
            date_label="Emitido",
            payment="credito30",
            item_count=3,
            signature_line=True,
            angle=1.5,
            **_BUYER,
        ),
        _case(
            "credit-terms-collage",
            "servicios",
            (2026, 5, 5),
            date_label="Fecha Emisión",
            date_style=_DASH4,
            payment="credito30",
            layout="collage2",
            item_count=10,
            shadow=True,
            **_BUYER,
        ),
        _case(
            "credit-terms-month-name",
            "toner",
            (2024, 8, 27),
            date_style=_named("{d}-{m}-{y}", "upper"),
            payment="credito",
            expiry=date(2025, 12, 31),
            rnc_dashed=True,
            **_BUYER,
        ),
        _case(
            "bank-transfer",
            "alquiler",
            (2026, 9, 14),
            date_label="Emitido",
            date_style=_SLASH4,
            payment="transferencia",
            item_count=1,
            signature_line=True,
            **_BUYER,
        ),
        _case(
            "no-payment-line",
            "seguros",
            (2025, 10, 20),
            date_style=_DASH2,
            payment="none",
            item_count=1,
            angle=-2.0,
            **_BUYER,
        ),
        _case(
            "totals-out-of-frame",
            "equipos",
            (2024, 11, 21),
            date_style=_SLASH4,
            layout="cut_totals",
            expiry=date(2025, 12, 31),
            **_BUYER,
        ),
    )
    return cases
