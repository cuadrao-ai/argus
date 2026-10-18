"""Practice Formato 606 and 607 rows, bank lines, and the layout checks.

The field rules live in ``fixtures/dgii/README.md``. This module builds the
September 2026 practice catalog, shifts it into a requested period, and
describes which bank lines should match which documents. It does not export
a file from product data: Cuadrao has no Formato 606/607 exporter yet.
"""

from __future__ import annotations

import csv
import io
import json
import random
import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "dgii"
ITBIS_RATE = Decimal("0.18")
CENT = Decimal("0.01")
B02_THRESHOLD = Decimal("250000")
MATCH_WINDOW_DAYS = 5
EMPRESA_NAME = "Práctica Cuadrao SRL"
CANON_START = date(2026, 9, 1)
CANON_END = date(2026, 9, 30)
DRY_RUN_START = date(2026, 10, 1)
DRY_RUN_END = date(2026, 10, 17)
OUTPUT_ROOT = Path("temp") / "qa-seed"

RX_NCF_606 = re.compile(
    r"^(((B|b)((0[1-4])|(1[1-5])|17)[0-9]{8})|((E|e)((3[1-4])|(4[1-5])|47)[0-9]{10}))$"
)
RX_NCF_607 = re.compile(r"^((B|b)((0[1-4])|(1[1-6]))[0-9]{8})$")
RX_FECHA = re.compile(
    r"^(19[5-9][0-9]|20[0-9][0-9])(((01|03|05|0[7-8]|10|12)(0[1-9]|[1-2][0-9]|3[0-1]))"
    r"|((04|06|09|11)(0[1-9]|[1-2][0-9]|30))|(02(0[1-9]|[1-2][0-9])))$"
)
RX_AMOUNT = re.compile(r"^\d+\.\d{2}$")
PAGO_COLS = ("efectivo", "cheque", "tarjeta", "credito", "bonos", "permuta", "otras")


def q(value: Decimal | int | str) -> Decimal:
    return Decimal(value).quantize(CENT, ROUND_HALF_UP)


def dv_rnc(base8: str) -> int:
    """RNC check digit. Weights 7-9-8-6-5-4-3-2, mod 11."""

    total = sum(
        int(digit) * int(weight) for digit, weight in zip(base8, "79865432", strict=False)
    )
    remainder = total % 11
    if remainder == 0:
        return 2
    if remainder == 1:
        return 1
    return 11 - remainder


def rnc(base8: str) -> str:
    digit = dv_rnc(base8)
    if digit > 9:
        raise ValueError(f"base {base8} does not yield a single check digit")
    return base8 + str(digit)


def dv_cedula(base10: str) -> int:
    """Cédula check digit. Luhn weights 1-2-1-2 on the first 10 digits."""

    total = 0
    for digit, weight in zip(base10, "1212121212", strict=False):
        product = int(digit) * int(weight)
        total += product // 10 + product % 10
    return (10 - total % 10) % 10


def cedula(base10: str) -> str:
    return base10 + str(dv_cedula(base10))


def valid_rnc(value: str) -> bool:
    return len(value) == 9 and value.isdigit() and dv_rnc(value[:8]) == int(value[8])


def valid_cedula(value: str) -> bool:
    return (
        len(value) == 11
        and value.isdigit()
        and value != "0" * 11
        and dv_cedula(value[:10]) == int(value[10])
    )


def mk_rnc(prefix: str) -> str:
    for index in range(100):
        try:
            return rnc(f"{prefix}{index:02d}")
        except ValueError:
            continue
    raise RuntimeError(f"no check digit for prefix {prefix}")


def ncf(kind: str, number: int) -> str:
    return f"B{kind}{number:08d}"


def encf(kind: str, number: int) -> str:
    return f"E{kind}{number:010d}"


EMPRESA = mk_rnc("139999")
SUPPLIERS = {
    name: mk_rnc(prefix)
    for name, prefix in {
        "isp": "138888",
        "local": "138887",
        "mayorista": "138886",
        "seguros": "138885",
        "resto": "138884",
        "capacitacion": "138883",
        "taller": "138882",
        "banco": "138881",
        "tienda": "138880",
        "ferreteria": "138879",
    }.items()
}
GOBIERNO = mk_rnc("438878")
CEDULA_PROFESIONAL = cedula("0019999901")
CEDULA_INFORMAL = cedula("0019999902")
CEDULA_CLIENTE = cedula("0019999903")
CUSTOMERS = {
    name: mk_rnc(prefix)
    for name, prefix in {
        "a": "137777",
        "b": "137776",
        "c": "137775",
        "d": "137774",
        "zf": "137773",
        "inq": "137772",
        "e": "137771",
    }.items()
}


def fmt(value: Decimal | str | None) -> str:
    if value == "" or value is None:
        return ""
    if isinstance(value, Decimal):
        return "" if value == 0 else f"{value:.2f}"
    return str(value)


def compra(
    identity: str,
    tipo_bienes: int,
    comprobante: str,
    fecha: str,
    forma: int,
    *,
    servicios: int | Decimal = 0,
    bienes: int | Decimal = 0,
    itbis: Decimal | None = None,
    modificado: str = "",
    fecha_pago: str = "",
    retencion_itbis: int | Decimal = 0,
    costo: int | Decimal = 0,
    tipo_retencion: int | None = None,
    retencion_isr: int | Decimal = 0,
    isc: int | Decimal = 0,
    otros: int | Decimal = 0,
    propina: int | Decimal = 0,
    nota: str = "",
    role: str = "",
) -> dict:
    servicios_q, bienes_q = q(servicios), q(bienes)
    itbis_q = q((servicios_q + bienes_q) * ITBIS_RATE) if itbis is None else q(itbis)
    return {
        "id": identity,
        "tipo_id": 1 if len(identity) == 9 else 2,
        "tb": tipo_bienes,
        "ncf": comprobante,
        "mod": modificado,
        "fc": fecha,
        "fpago": fecha_pago,
        "serv": servicios_q,
        "bienes": bienes_q,
        "total": servicios_q + bienes_q,
        "itbis": itbis_q,
        "ret_itbis": q(retencion_itbis),
        "costo": q(costo),
        "adelantar": itbis_q - q(costo),
        "tret": tipo_retencion,
        "ret_isr": q(retencion_isr),
        "isc": q(isc),
        "otros": q(otros),
        "propina": q(propina),
        "fp": forma,
        "nota": nota,
        "role": role,
        "formato": "606",
    }


def venta(
    identity: str,
    tipo_id: int,
    comprobante: str,
    tipo_ingreso: int,
    fecha: str,
    monto: int | Decimal,
    *,
    itbis: Decimal | None = None,
    modificado: str = "",
    fecha_retencion: str = "",
    retencion_itbis: int | Decimal = 0,
    retencion_isr: int | Decimal = 0,
    pago: str | None = None,
    nota: str = "",
    role: str = "",
) -> dict:
    monto_q = q(monto)
    itbis_q = q(monto_q * ITBIS_RATE) if itbis is None else q(itbis)
    pagos = {name: Decimal(0) for name in PAGO_COLS}
    if pago:
        pagos[pago] = monto_q + itbis_q
    return {
        "id": identity,
        "tipo_id": tipo_id,
        "ncf": comprobante,
        "mod": modificado,
        "ti": tipo_ingreso,
        "fc": fecha,
        "fret": fecha_retencion,
        "monto": monto_q,
        "itbis": itbis_q,
        "ret_itbis": q(retencion_itbis),
        "ret_isr": q(retencion_isr),
        "isc": q(0),
        "otros": q(0),
        "propina": q(0),
        "pagos": pagos,
        "pago": pago or "",
        "nota": nota,
        "role": role,
        "formato": "607",
    }


def purchases() -> list[dict]:
    return [
        compra(
            SUPPLIERS["isp"],
            2,
            ncf("01", 1201),
            "20260903",
            2,
            servicios=3000,
            isc=300,
            otros=60,
            fecha_pago="20260905",
            nota="Internet",
            role="isp",
        ),
        compra(
            SUPPLIERS["local"],
            3,
            ncf("01", 455),
            "20260901",
            2,
            servicios=25000,
            fecha_pago="20260901",
            nota="Alquiler local",
            role="local",
        ),
        compra(
            SUPPLIERS["mayorista"],
            9,
            ncf("01", 9876),
            "20260904",
            4,
            bienes=48000,
            nota="Mercancía a crédito",
            role="mayorista",
        ),
        compra(
            CEDULA_PROFESIONAL,
            2,
            ncf("01", 31),
            "20260910",
            2,
            servicios=20000,
            fecha_pago="20260915",
            retencion_itbis=3600,
            tipo_retencion=2,
            retencion_isr=2000,
            nota="Honorarios",
            role="profesional",
        ),
        compra(
            SUPPLIERS["seguros"],
            11,
            ncf("01", 7001),
            "20260912",
            2,
            servicios=8000,
            itbis=Decimal(0),
            isc=1280,
            fecha_pago="20260912",
            nota="Seguro",
            role="seguros",
        ),
        compra(
            SUPPLIERS["resto"],
            5,
            ncf("01", 22110),
            "20260914",
            3,
            bienes=3500,
            propina=350,
            fecha_pago="20260914",
            nota="Almuerzo",
            role="resto",
        ),
        compra(
            SUPPLIERS["capacitacion"],
            1,
            ncf("01", 640),
            "20260915",
            3,
            servicios=6000,
            fecha_pago="20260915",
            nota="Capacitación",
            role="capacitacion",
        ),
        compra(
            SUPPLIERS["taller"],
            4,
            ncf("01", 3302),
            "20260917",
            7,
            servicios=4500,
            bienes=7000,
            fecha_pago="20260917",
            nota="Mantenimiento",
            role="taller",
        ),
        compra(
            SUPPLIERS["banco"],
            7,
            ncf("01", 88001),
            "20260930",
            2,
            servicios=850,
            itbis=Decimal(0),
            fecha_pago="20260930",
            nota="Comisiones bancarias",
            role="banco",
        ),
        compra(
            SUPPLIERS["tienda"],
            10,
            encf("31", 1234),
            "20260918",
            3,
            bienes=65000,
            fecha_pago="20260918",
            nota="Laptop e-CF",
            role="tienda",
        ),
        compra(
            EMPRESA,
            2,
            ncf("13", 12),
            "20260919",
            1,
            bienes=1200,
            itbis=Decimal(0),
            fecha_pago="20260919",
            nota="Gastos menores",
            role="menores",
        ),
        compra(
            CEDULA_INFORMAL,
            2,
            ncf("11", 45),
            "20260920",
            1,
            servicios=5000,
            itbis=Decimal(0),
            fecha_pago="20260920",
            nota="Proveedor informal",
            role="informal",
        ),
        compra(
            GOBIERNO,
            6,
            ncf("15", 501),
            "20260922",
            2,
            servicios=1500,
            itbis=Decimal(0),
            fecha_pago="20260922",
            nota="Tasa gubernamental",
            role="gobierno",
        ),
        compra(
            SUPPLIERS["ferreteria"],
            8,
            ncf("01", 7712),
            "20260924",
            1,
            bienes=2000,
            costo=360,
            fecha_pago="20260924",
            nota="Gasto extraordinario",
            role="ferreteria",
        ),
        compra(
            SUPPLIERS["mayorista"],
            9,
            ncf("04", 310),
            "20260926",
            6,
            bienes=4800,
            modificado=ncf("01", 9876),
            nota="Nota de crédito",
            role="nota-compra",
        ),
    ]


def sales() -> list[dict]:
    return [
        venta(
            CUSTOMERS["a"],
            1,
            ncf("01", 1),
            1,
            "20260902",
            50000,
            pago="cheque",
            nota="Crédito fiscal",
            role="cliente-a",
        ),
        venta(
            CUSTOMERS["b"],
            1,
            ncf("01", 2),
            1,
            "20260905",
            120000,
            fecha_retencion="20260930",
            retencion_itbis=6480,
            pago="cheque",
            nota="Cliente retuvo ITBIS",
            role="cliente-b",
        ),
        venta(
            CUSTOMERS["c"],
            1,
            ncf("01", 3),
            1,
            "20260908",
            18000,
            pago="tarjeta",
            nota="Tarjeta",
            role="cliente-c",
        ),
        venta(
            CUSTOMERS["d"],
            1,
            ncf("01", 4),
            1,
            "20260911",
            75000,
            pago="credito",
            nota="Venta a crédito",
            role="cliente-d",
        ),
        venta(
            GOBIERNO,
            1,
            ncf("15", 1),
            1,
            "20260914",
            200000,
            fecha_retencion="20260929",
            retencion_isr=10000,
            pago="credito",
            nota="Gubernamental",
            role="venta-gobierno",
        ),
        venta(
            CUSTOMERS["zf"],
            1,
            ncf("14", 1),
            1,
            "20260916",
            60000,
            itbis=Decimal(0),
            pago="cheque",
            nota="Zona franca",
            role="zona-franca",
        ),
        venta(
            CEDULA_CLIENTE,
            2,
            ncf("02", 1),
            1,
            "20260918",
            300000,
            pago="cheque",
            nota="Consumo sobre el umbral",
            role="consumo-grande",
        ),
        venta(
            CUSTOMERS["inq"],
            1,
            ncf("01", 5),
            4,
            "20260920",
            15000,
            pago="cheque",
            nota="Subarriendo",
            role="alquiler",
        ),
        venta(
            CUSTOMERS["e"],
            1,
            ncf("01", 6),
            5,
            "20260925",
            8000,
            pago="efectivo",
            nota="Venta de activo",
            role="activo",
        ),
        venta(
            CUSTOMERS["a"],
            1,
            ncf("04", 1),
            1,
            "20260928",
            5000,
            modificado=ncf("01", 1),
            nota="Nota de crédito",
            role="nota-venta",
        ),
    ]


def consumo_amounts() -> list[Decimal]:
    """B02 invoices under RD$250,000. They stay out of the 607 detail."""

    generator = random.Random(202609)
    return [q(generator.randrange(500, 9000, 50)) for _ in range(40)]


def line_606(row: dict) -> str:
    return "|".join(
        [
            row["id"],
            str(row["tipo_id"]),
            f"{row['tb']:02d}",
            row["ncf"],
            row["mod"],
            row["fc"],
            row["fpago"],
            fmt(row["serv"]),
            fmt(row["bienes"]),
            f"{row['total']:.2f}",
            f"{row['itbis']:.2f}",
            fmt(row["ret_itbis"]),
            "",
            fmt(row["costo"]),
            f"{row['adelantar']:.2f}",
            "",
            f"{row['tret']:02d}" if row["tret"] else "",
            fmt(row["ret_isr"]),
            "",
            fmt(row["isc"]),
            fmt(row["otros"]),
            fmt(row["propina"]),
            f"{row['fp']:02d}",
        ]
    )


def line_607(row: dict) -> str:
    return "|".join(
        [
            row["id"],
            str(row["tipo_id"]),
            row["ncf"],
            row["mod"],
            str(row["ti"]),
            row["fc"],
            row["fret"],
            f"{row['monto']:.2f}",
            f"{row['itbis']:.2f}",
            fmt(row["ret_itbis"]),
            "",
            fmt(row["ret_isr"]),
            "",
            fmt(row["isc"]),
            fmt(row["otros"]),
            fmt(row["propina"]),
            *[fmt(row["pagos"][name]) for name in PAGO_COLS],
        ]
    )


def render_txt(formato: str, periodo: str, lines: list[str]) -> bytes:
    header = f"{formato}|{EMPRESA}|{periodo}|{len(lines)}"
    return "\r\n".join([header, *lines]).encode("ascii")


def practice_606() -> bytes:
    return render_txt("606", "202609", [line_606(row) for row in purchases()])


def practice_607() -> bytes:
    return render_txt("607", "202609", [line_607(row) for row in sales()])


def signed(row: dict, amount: Decimal) -> Decimal:
    """A credit note subtracts in the monthly totals and stays positive in the file."""

    kind = row["ncf"][1:3]
    return -amount if kind == "04" else amount


def summary() -> dict[str, Decimal]:
    buys, sells = purchases(), sales()
    small = consumo_amounts()
    small_itbis = [q(amount * ITBIS_RATE) for amount in small]

    def net(rows: list[dict], key: str) -> Decimal:
        return sum((signed(row, row[key]) for row in rows), Decimal(0))

    sales_amount = net(sells, "monto")
    sales_itbis = net(sells, "itbis")
    purchases_amount = net(buys, "total")
    purchases_itbis = net(buys, "itbis")
    adelantar = net(buys, "adelantar")
    costo = net(buys, "costo")
    ret_itbis_606 = net(buys, "ret_itbis")
    ret_isr_606 = net(buys, "ret_isr")
    extras = net(buys, "isc") + net(buys, "otros") + net(buys, "propina")
    ret_itbis_607 = net(sells, "ret_itbis")
    ret_isr_607 = net(sells, "ret_isr")
    itbis_ventas = sales_itbis + sum(small_itbis, Decimal(0))
    ingresos = sales_amount + sum(small, Decimal(0))
    neto = itbis_ventas - adelantar - ret_itbis_607
    activos = sum((row["total"] for row in buys if row["tb"] == 10), Decimal(0))
    gastos = purchases_amount + costo + extras
    large_b02 = [row for row in sells if row["ncf"][1:3] == "02"]
    return {
        "ventas_monto": sales_amount,
        "consumo_monto": sum(small, Decimal(0)),
        "ingresos": ingresos,
        "ventas_itbis": sales_itbis,
        "consumo_itbis": sum(small_itbis, Decimal(0)),
        "itbis_facturado": itbis_ventas,
        "itbis_retenido_clientes": ret_itbis_607,
        "isr_retenido_clientes": ret_isr_607,
        "consumo_ncf": Decimal(len(small) + len(large_b02)),
        "consumo_ofv_monto": sum(small, Decimal(0))
        + sum((row["monto"] for row in large_b02), Decimal(0)),
        "consumo_ofv_itbis": sum(small_itbis, Decimal(0))
        + sum((row["itbis"] for row in large_b02), Decimal(0)),
        "compras_monto": purchases_amount,
        "compras_itbis": purchases_itbis,
        "itbis_costo": costo,
        "itbis_adelantar": adelantar,
        "itbis_retenido_proveedores": ret_itbis_606,
        "isr_retenido_proveedores": ret_isr_606,
        "otros_pagados": extras,
        "itbis_neto": neto,
        "itbis_enterar": neto + ret_itbis_606,
        "gastos": gastos,
        "resultado": ingresos - gastos,
        "activos": activos,
        "resultado_sin_activos": ingresos - (gastos - activos),
    }


@dataclass(frozen=True)
class Period:
    start: date
    end: date

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError("period end is before the start")
        if (self.start.year, self.start.month) != (self.end.year, self.end.month):
            raise ValueError("the period must stay inside one calendar month")

    @property
    def periodo(self) -> str:
        return f"{self.start:%Y%m}"

    @property
    def canonical(self) -> bool:
        return self.start == CANON_START and self.end == CANON_END


def parse_period(start: str, end: str) -> Period:
    return Period(date.fromisoformat(start), date.fromisoformat(end))


def place(original: date, period: Period) -> date:
    """Keep September 2026 dates. Any other window maps that span into itself."""

    if period.canonical and CANON_START <= original <= CANON_END:
        return original
    span_in = (CANON_END - CANON_START).days
    span_out = (period.end - period.start).days
    offset = round((original - CANON_START).days * span_out / span_in)
    offset = min(max(offset, 0), span_out)
    return period.start + timedelta(days=offset)


def _stamp(value: str) -> date:
    return date(int(value[:4]), int(value[4:6]), int(value[6:8]))


def _money(value: Decimal) -> str:
    return f"{q(value):.2f}"


@dataclass(frozen=True)
class SeedDocument:
    filename: str
    kind: str
    direction: str
    counterparty: str
    occurred_on: date
    amount: Decimal
    subtotal: Decimal
    itbis: Decimal
    isc: Decimal
    otros: Decimal
    propina: Decimal
    rnc: str | None
    ncf: str | None
    ecf: str | None
    tag: str | None
    formato: str
    bank: str
    body: str

    @property
    def approval(self) -> str:
        if self.kind in {"expense", "income"}:
            return self.kind
        return "unsupported"


@dataclass(frozen=True)
class BankLine:
    line_id: str
    occurred_on: date
    description: str
    amount: Decimal
    type: str
    tag: str | None
    filename: str | None


def _names(seed: int) -> dict[str, str]:
    from faker import Faker

    fake = Faker("es_ES")
    fake.seed_instance(seed)
    named: dict[str, str] = {}
    for identity in (*SUPPLIERS.values(), *CUSTOMERS.values(), GOBIERNO, EMPRESA):
        named[identity] = fake.company().replace(",", " ")
    for identity in (CEDULA_PROFESIONAL, CEDULA_INFORMAL, CEDULA_CLIENTE):
        named[identity] = fake.name().replace(",", " ")
    return named


def _body(document: dict) -> str:
    lines = [
        "QA-SEED",
        "PRÁCTICA / DATOS FICTICIOS — NO ENVIAR A LA DGII",
        f"Emisor: {EMPRESA_NAME}",
        f"RNC emisor: {EMPRESA}",
        f"Tipo: {document['tipo']}",
        f"Contraparte: {document['counterparty']}",
        f"RNC o cédula: {document['rnc'] or ''}",
        f"NCF: {document['ncf'] or ''}",
        f"e-CF: {document['ecf'] or ''}",
        f"Fecha: {document['occurred_on'].isoformat()}",
        f"Subtotal: {_money(document['subtotal'])}",
        f"ITBIS: {_money(document['itbis'])}",
        f"ISC: {_money(document['isc'])}",
        f"Otros: {_money(document['otros'])}",
        f"Propina: {_money(document['propina'])}",
        f"Total: {_money(document['amount'])}",
    ]
    if document["tag"]:
        lines.append(f"Marca: {document['tag']}")
    if document.get("nota"):
        lines.append(document["nota"])
    return "\n".join(lines) + "\n"


def _document(
    *,
    filename: str,
    kind: str,
    direction: str,
    counterparty: str,
    occurred_on: date,
    subtotal: Decimal,
    itbis: Decimal,
    isc: Decimal = Decimal(0),
    otros: Decimal = Decimal(0),
    propina: Decimal = Decimal(0),
    rnc: str | None,
    ncf: str | None,
    ecf: str | None,
    tag: str | None,
    formato: str,
    bank: str,
    nota: str,
    tipo: str,
) -> SeedDocument:
    amount = q(subtotal + itbis + isc + otros + propina)
    payload = {
        "tipo": tipo,
        "counterparty": counterparty,
        "rnc": rnc,
        "ncf": ncf,
        "ecf": ecf,
        "occurred_on": occurred_on,
        "subtotal": subtotal,
        "itbis": itbis,
        "isc": isc,
        "otros": otros,
        "propina": propina,
        "amount": amount,
        "tag": tag,
        "nota": nota,
    }
    label = counterparty if tag is None else f"QA-SEED roto:{tag} {counterparty}"
    return SeedDocument(
        filename=filename,
        kind=kind,
        direction=direction,
        counterparty=label[:300],
        occurred_on=occurred_on,
        amount=amount,
        subtotal=subtotal,
        itbis=itbis,
        isc=isc,
        otros=otros,
        propina=propina,
        rnc=rnc,
        ncf=ncf,
        ecf=ecf,
        tag=tag,
        formato=formato,
        bank=bank,
        body=_body(payload),
    )


def _purchase_bank(row: dict) -> str:
    if row["role"] == "capacitacion":
        return "partial"
    if row["fp"] in {4, 6} or row["ncf"][1:3] == "04":
        return "none"
    return "pair"


def _sale_bank(row: dict) -> str:
    if row["ncf"][1:3] == "04" or row["pago"] in {"", "credito"}:
        return "none"
    return "pair"


def _counterparty(row: dict, names: dict[str, str]) -> str:
    return names.get(row["id"], row["role"])


def documents_for(period: Period, seed: int = 202609) -> list[SeedDocument]:
    names = _names(seed)
    built: list[SeedDocument] = []
    for row in purchases():
        electronic = row["ncf"].startswith("E")
        built.append(
            _document(
                filename=f"qa-seed-606-{row['ncf']}.txt",
                kind="refund" if row["ncf"][1:3] == "04" else "expense",
                direction="inflow" if row["ncf"][1:3] == "04" else "outflow",
                counterparty=_counterparty(row, names),
                occurred_on=place(_stamp(row["fc"]), period),
                subtotal=row["total"],
                itbis=row["itbis"],
                isc=row["isc"],
                otros=row["otros"],
                propina=row["propina"],
                rnc=row["id"],
                ncf=None if electronic else row["ncf"],
                ecf=row["ncf"] if electronic else None,
                tag=None,
                formato="606",
                bank=_purchase_bank(row),
                nota=row["nota"],
                tipo="compra",
            )
        )
    for row in sales():
        built.append(
            _document(
                filename=f"qa-seed-607-{row['ncf']}.txt",
                kind="refund" if row["ncf"][1:3] == "04" else "income",
                direction="outflow" if row["ncf"][1:3] == "04" else "inflow",
                counterparty=_counterparty(row, names),
                occurred_on=place(_stamp(row["fc"]), period),
                subtotal=row["monto"],
                itbis=row["itbis"],
                rnc=row["id"],
                ncf=row["ncf"],
                ecf=None,
                tag=None,
                formato="607",
                bank=_sale_bank(row),
                nota=row["nota"],
                tipo="venta",
            )
        )
    span = (period.end - period.start).days
    for index, amount in enumerate(consumo_amounts()):
        offset = round(index * span / 39) if span else 0
        built.append(
            _document(
                filename=f"qa-seed-607-consumo-{index + 1:02d}.txt",
                kind="income",
                direction="inflow",
                counterparty="Consumo mostrador",
                occurred_on=period.start + timedelta(days=offset),
                subtotal=amount,
                itbis=q(amount * ITBIS_RATE),
                rnc=None,
                ncf=ncf("02", 1000 + index),
                ecf=None,
                tag="consumo-ofv",
                formato="607",
                bank="none",
                nota="Factura de consumo bajo RD$250,000. Queda fuera del 607 y entra al resumen de la OFV.",
                tipo="venta",
            )
        )
    built.extend(_defects(period, names))
    return built


def _defects(period: Period, names: dict[str, str]) -> list[SeedDocument]:
    """Rows that break one README rejection each. They are not in the practice TXT."""

    day = period.start
    supplier = names[SUPPLIERS["ferreteria"]]
    customer = names[CUSTOMERS["e"]]
    shared = dict(
        subtotal=Decimal(1000), itbis=q(180), formato="606", bank="none", nota=""
    )
    return [
        _document(
            filename="qa-seed-roto-id-longitud.txt",
            kind="expense",
            direction="outflow",
            counterparty=supplier,
            occurred_on=day,
            rnc="13887900",
            ncf=ncf("01", 9001),
            ecf=None,
            tag="id-longitud",
            tipo="compra",
            **shared,
        ),
        _document(
            filename="qa-seed-roto-id-tipo.txt",
            kind="expense",
            direction="outflow",
            counterparty=supplier,
            occurred_on=day,
            rnc=SUPPLIERS["ferreteria"],
            ncf=ncf("01", 9002),
            ecf=None,
            tag="id-tipo",
            tipo="compra",
            **shared,
        ),
        _document(
            filename="qa-seed-roto-ncf-longitud.txt",
            kind="expense",
            direction="outflow",
            counterparty=supplier,
            occurred_on=day,
            rnc=SUPPLIERS["ferreteria"],
            ncf="B010000001",
            ecf=None,
            tag="ncf-longitud",
            tipo="compra",
            **shared,
        ),
        _document(
            filename="qa-seed-roto-encf-en-607.txt",
            kind="income",
            direction="inflow",
            counterparty=customer,
            occurred_on=day,
            rnc=CUSTOMERS["e"],
            ncf=None,
            ecf=encf("31", 1),
            tag="encf-en-607",
            tipo="venta",
            formato="607",
            bank="none",
            nota="",
            subtotal=Decimal(1000),
            itbis=q(180),
        ),
        _document(
            filename="qa-seed-roto-b02-bajo-umbral.txt",
            kind="income",
            direction="inflow",
            counterparty=customer,
            occurred_on=day,
            rnc=CEDULA_CLIENTE,
            ncf=ncf("02", 50),
            ecf=None,
            tag="b02-bajo-umbral",
            tipo="venta",
            formato="607",
            bank="none",
            nota="B02 bajo RD$250,000 colado en el detalle 607.",
            subtotal=Decimal(1000),
            itbis=q(180),
        ),
        _document(
            filename="qa-seed-roto-pagos-no-cuadran.txt",
            kind="income",
            direction="inflow",
            counterparty=customer,
            occurred_on=day,
            rnc=CUSTOMERS["e"],
            ncf=ncf("01", 9050),
            ecf=None,
            tag="pagos-no-cuadran",
            tipo="venta",
            formato="607",
            bank="none",
            nota="La forma de pago no suma el total.",
            subtotal=Decimal(1000),
            itbis=q(180),
        ),
        _document(
            filename="qa-seed-roto-retencion-sin-fecha-607.txt",
            kind="income",
            direction="inflow",
            counterparty=customer,
            occurred_on=day,
            rnc=CUSTOMERS["e"],
            ncf=ncf("01", 9051),
            ecf=None,
            tag="retencion-sin-fecha",
            tipo="venta",
            formato="607",
            bank="none",
            nota="ITBIS retenido sin fecha de retención.",
            subtotal=Decimal(1000),
            itbis=q(180),
        ),
        _document(
            filename="qa-seed-roto-retencion-sin-fecha-606.txt",
            kind="expense",
            direction="outflow",
            counterparty=supplier,
            occurred_on=day,
            rnc=SUPPLIERS["ferreteria"],
            ncf=ncf("01", 9052),
            ecf=None,
            tag="retencion-sin-fecha",
            tipo="compra",
            formato="606",
            bank="none",
            nota="ITBIS retenido sin fecha de pago.",
            subtotal=Decimal(1000),
            itbis=q(180),
        ),
        _document(
            filename="qa-seed-roto-sin-rnc.txt",
            kind="expense",
            direction="outflow",
            counterparty=supplier,
            occurred_on=day,
            rnc=None,
            ncf=ncf("01", 9053),
            ecf=None,
            tag="sin-rnc",
            tipo="compra",
            **shared,
        ),
        _document(
            filename="qa-seed-roto-ncf-duplicado-a.txt",
            kind="expense",
            direction="outflow",
            counterparty=supplier,
            occurred_on=day,
            rnc=SUPPLIERS["ferreteria"],
            ncf=ncf("01", 99),
            ecf=None,
            tag="ncf-duplicado",
            tipo="compra",
            **shared,
        ),
        _document(
            filename="qa-seed-roto-ncf-duplicado-b.txt",
            kind="expense",
            direction="outflow",
            counterparty=supplier,
            occurred_on=day,
            rnc=SUPPLIERS["local"],
            ncf=ncf("01", 99),
            ecf=None,
            tag="ncf-duplicado",
            tipo="compra",
            **shared,
        ),
        _document(
            filename="qa-seed-roto-rnc-digito.txt",
            kind="expense",
            direction="outflow",
            counterparty=supplier,
            occurred_on=day,
            rnc="139999000",
            ncf=ncf("01", 9054),
            ecf=None,
            tag="rnc-digito",
            tipo="compra",
            **shared,
        ),
    ]


def defect_rows() -> dict[str, list[dict]]:
    """The same breaks, as 606/607 detail rows the layout validator can flag."""

    base_606 = compra(
        SUPPLIERS["ferreteria"],
        2,
        ncf("01", 9001),
        "20260903",
        2,
        servicios=1000,
        fecha_pago="20260903",
    )
    short_id = {**base_606, "id": "13887900", "tipo_id": 1}
    wrong_type = {**base_606, "ncf": ncf("01", 9002), "tipo_id": 2}
    short_ncf = {**base_606, "ncf": "B010000001"}
    missing = {**base_606, "id": "", "tipo_id": 1, "ncf": ncf("01", 9053)}
    bad_digit = {**base_606, "id": "139999000", "tipo_id": 1, "ncf": ncf("01", 9054)}
    held = {
        **base_606,
        "ncf": ncf("01", 9052),
        "ret_itbis": q(180),
        "fpago": "",
        "tret": None,
    }
    duplicate = {**base_606, "ncf": ncf("01", 99)}
    duplicate_b = {**duplicate, "id": SUPPLIERS["local"]}
    leaked = venta(CEDULA_CLIENTE, 2, ncf("02", 50), 1, "20260903", 1000, pago="efectivo")
    electronic = venta(
        CUSTOMERS["e"], 1, encf("31", 1), 1, "20260903", 1000, pago="efectivo"
    )
    unpaid = venta(
        CUSTOMERS["e"], 1, ncf("01", 9050), 1, "20260903", 1000, pago="efectivo"
    )
    unpaid["pagos"] = {
        **unpaid["pagos"],
        "efectivo": unpaid["pagos"]["efectivo"] - Decimal(1),
    }
    undated = venta(
        CUSTOMERS["e"],
        1,
        ncf("01", 9051),
        1,
        "20260903",
        1000,
        retencion_itbis=180,
        pago="efectivo",
    )
    return {
        "id-longitud": [short_id],
        "id-tipo": [wrong_type],
        "ncf-longitud": [short_ncf],
        "encf-en-607": [electronic],
        "b02-bajo-umbral": [leaked],
        "pagos-no-cuadran": [unpaid],
        "retencion-sin-fecha": [undated, held],
        "sin-rnc": [missing],
        "ncf-duplicado": [duplicate, duplicate_b],
        "rnc-digito": [bad_digit],
    }


def _payment_sum(row: dict) -> Decimal:
    return sum((value for value in row["pagos"].values() if value != ""), Decimal(0))


def issues_for(rows: list[dict], formato: str, *, periodo: str = "202609") -> list[str]:
    """README rejection codes for one detail list. Header count is the list length."""

    found: list[str] = []
    seen: dict[str, int] = {}
    if not re.fullmatch(r"20\d{4}", periodo) or periodo < "201805":
        found.append("periodo")
    for row in rows:
        comprobante = row["ncf"]
        identity = row["id"]
        tipo = row["tipo_id"]
        if identity == "":
            found.append("sin-rnc")
        elif not identity.isdigit() or len(identity) not in {9, 11}:
            found.append("id-longitud")
        elif (
            (tipo == 1 and len(identity) != 9)
            or (tipo == 2 and len(identity) != 11)
            or tipo not in {1, 2, 3}
        ):
            found.append("id-tipo")
        elif tipo == 1 and not valid_rnc(identity):
            found.append("rnc-digito")
        elif tipo == 2 and not valid_cedula(identity):
            found.append("rnc-digito")
        pattern = RX_NCF_606 if formato == "606" else RX_NCF_607
        if formato == "607" and comprobante[:1] in {"E", "e"}:
            found.append("encf-en-607")
        elif not pattern.match(comprobante):
            found.append("ncf-longitud")
        fecha = row["fc"]
        pago = row.get("fpago", row.get("fret", ""))
        if not RX_FECHA.match(fecha) or (pago and not RX_FECHA.match(pago)):
            found.append("fecha")
        retained = row["ret_itbis"] or row["ret_isr"] or row.get("tret")
        if retained and not pago:
            found.append("retencion-sin-fecha")
        if formato == "606" and comprobante[1:3] == "13" and identity != EMPRESA:
            found.append("b13-rnc")
        if formato == "607" and comprobante[1:3] == "12" and identity != EMPRESA:
            found.append("b12-rnc")
        if comprobante[1:3] in {"03", "04"} and not row["mod"]:
            found.append("nota-sin-modificado")
        if formato == "606" and row["total"] <= 0:
            found.append("monto")
        if formato == "607" and comprobante[1:3] == "02" and row["monto"] < B02_THRESHOLD:
            found.append("b02-bajo-umbral")
        if formato == "607" and comprobante[1:3] != "04":
            expected = (
                row["monto"] + row["itbis"] + row["isc"] + row["otros"] + row["propina"]
            )
            paid = _payment_sum(row)
            if paid == 0 or paid != expected:
                found.append("pagos-no-cuadran")
        seen[comprobante] = seen.get(comprobante, 0) + 1
    if any(count > 1 for count in seen.values()):
        found.append("ncf-duplicado")
    return found


def layout_issues(payload: bytes) -> list[str]:
    """Column order, widths, and the header line. Amount values are not compared."""

    problems: list[str] = []
    if payload.endswith(b"\n") or payload.endswith(b"\r"):
        problems.append("trailing-break")
    try:
        text = payload.decode("ascii")
    except UnicodeError:
        return ["encoding"]
    if "\n" in text.replace("\r\n", ""):
        problems.append("line-break")
    rows = text.split("\r\n")
    if not rows or rows[-1] == "":
        problems.append("empty-line")
        return problems
    header, *details = rows
    parts = header.split("|")
    if len(parts) != 4 or parts[0] not in {"606", "607"}:
        problems.append("header")
        return problems
    formato, issuer, periodo, count = parts
    if not re.fullmatch(r"\d{9}", issuer):
        problems.append("header-rnc")
    if not re.fullmatch(r"\d{6}", periodo):
        problems.append("header-period")
    if count != str(len(details)):
        problems.append("header-count")
    for line in details:
        fields = line.split("|")
        if len(fields) != 23:
            problems.append("columns")
            continue
        identity, tipo, *rest = fields
        if identity and not re.fullmatch(r"\d{9}|\d{11}", identity):
            problems.append("id-width")
        if tipo and tipo not in {"1", "2", "3"}:
            problems.append("tipo-id")
        if formato == "606":
            _layout_606(fields, problems)
        else:
            _layout_607(fields, problems)
    return problems


def _layout_606(fields: list[str], problems: list[str]) -> None:
    tipo_bienes, comprobante, modificado, fecha, pago = fields[2:7]
    amounts = fields[7:16] + fields[17:22]
    tipo_retencion, forma = fields[16], fields[22]
    if tipo_bienes and not re.fullmatch(r"\d{2}", tipo_bienes):
        problems.append("tipo-bienes")
    _ncf_width(comprobante, problems, electronic=True)
    _ncf_width(modificado, problems, electronic=True)
    _date_width(fecha, problems, required=True)
    _date_width(pago, problems, required=False)
    for value in amounts:
        if value and not RX_AMOUNT.match(value):
            problems.append("amount-width")
    if tipo_retencion and not re.fullmatch(r"\d{2}", tipo_retencion):
        problems.append("tipo-retencion")
    if not re.fullmatch(r"\d{2}", forma):
        problems.append("forma-pago")


def _layout_607(fields: list[str], problems: list[str]) -> None:
    _, _, comprobante, modificado, ingreso, fecha, retencion, *amounts = fields
    _ncf_width(comprobante, problems, electronic=False)
    _ncf_width(modificado, problems, electronic=False)
    if ingreso and not re.fullmatch(r"[1-6]", ingreso):
        problems.append("tipo-ingreso")
    _date_width(fecha, problems, required=True)
    _date_width(retencion, problems, required=False)
    for value in amounts:
        if value and not RX_AMOUNT.match(value):
            problems.append("amount-width")


def _ncf_width(value: str, problems: list[str], *, electronic: bool) -> None:
    if not value:
        return
    allowed = {11, 13, 19} if electronic else {11, 19}
    if len(value) not in allowed:
        problems.append("ncf-width")


def _date_width(value: str, problems: list[str], *, required: bool) -> None:
    if not value and not required:
        return
    if not re.fullmatch(r"\d{8}", value):
        problems.append("date-width")


def bank_lines(docs: list[SeedDocument], period: Period) -> list[BankLine]:
    lines: list[BankLine] = []
    number = 1

    def add(
        description: str,
        amount: Decimal,
        kind: str,
        when: date,
        tag: str | None,
        filename: str | None,
    ) -> None:
        nonlocal number
        lines.append(
            BankLine(
                f"qa-seed-bank-{number:03d}",
                when,
                description,
                q(amount),
                kind,
                tag,
                filename,
            )
        )
        number += 1

    for document in docs:
        if document.bank == "none" or document.tag not in {None}:
            continue
        verb = "Depósito" if document.direction == "inflow" else "Transferencia"
        if (
            document.kind == "expense"
            and document.ncf
            and document.ncf.startswith("B01")
            and document.amount < Decimal(5000)
        ):
            verb = "Compra tarjeta"
        label = document.ncf or document.ecf or document.filename
        description = f"{verb} {document.counterparty} {label} QA-SEED"
        if document.bank == "partial":
            add(
                f"{description} pago parcial QA-SEED ruido:pago-parcial",
                document.amount / 2,
                "débito",
                document.occurred_on,
                "ruido:pago-parcial",
                document.filename,
            )
            continue
        add(
            description,
            document.amount,
            "crédito" if document.direction == "inflow" else "débito",
            document.occurred_on,
            None,
            document.filename,
        )
    anchor = next(
        document
        for document in docs
        if document.tag is None and document.formato == "606" and document.bank == "pair"
    )
    add(
        "Compra tarjeta COLMADO LA ESQUINA QA-SEED sin comprobante",
        Decimal("4321.00"),
        "débito",
        period.start + timedelta(days=min(2, (period.end - period.start).days)),
        "sin-comprobante",
        None,
    )
    add(
        "Transferencia particular QA-SEED sin comprobante",
        Decimal("8765.50"),
        "débito",
        period.start + timedelta(days=min(6, (period.end - period.start).days)),
        "sin-comprobante",
        None,
    )
    add(
        "Comisión mantenimiento QA-SEED ruido:comision",
        Decimal("175.00"),
        "débito",
        period.end,
        "ruido:comision",
        None,
    )
    add(
        f"Transferencia {anchor.counterparty} QA-SEED ruido:cerca",
        anchor.amount - Decimal("1.00"),
        "débito",
        anchor.occurred_on,
        "ruido:cerca",
        None,
    )
    return lines


def plaid_transactions(lines: list[BankLine]) -> list[dict]:
    """Sandbox transactions for the same lines. Positive amount is money out."""

    payload = []
    for line in lines:
        signed_amount = line.amount if line.type == "débito" else -line.amount
        payload.append(
            {
                "amount": float(signed_amount),
                "date_transacted": line.occurred_on.isoformat(),
                "date_posted": line.occurred_on.isoformat(),
                "description": line.description,
                "iso_currency_code": "DOP",
            }
        )
    return payload


def build_manifest(
    docs: list[SeedDocument], lines: list[BankLine], period: Period
) -> dict:
    by_name = {document.filename: document for document in docs}
    pairs = []
    unmatched_lines = []
    paired: set[str] = set()
    for line in lines:
        entry = {
            "line_id": line.line_id,
            "date": line.occurred_on.isoformat(),
            "description": line.description,
            "amount": _money(line.amount),
            "type": line.type,
            "filename": line.filename,
        }
        if line.tag is None and line.filename:
            document = by_name[line.filename]
            pairs.append(
                {
                    **entry,
                    "kind": document.kind,
                    "document_date": document.occurred_on.isoformat(),
                }
            )
            paired.add(line.filename)
        else:
            unmatched_lines.append({**entry, "tag": line.tag})
    unmatched_documents = []
    for document in docs:
        if document.filename in paired:
            continue
        reason = document.tag or (
            "pago-parcial" if document.bank == "partial" else "sin-movimiento"
        )
        unmatched_documents.append(
            {
                "filename": document.filename,
                "reason": reason,
                "kind": document.kind,
                "date": document.occurred_on.isoformat(),
                "amount": _money(document.amount),
            }
        )
    return {
        "period": {
            "from": period.start.isoformat(),
            "to": period.end.isoformat(),
            "periodo": period.periodo,
        },
        "match_window_days": MATCH_WINDOW_DAYS,
        "pairs": pairs,
        "unmatched_lines": unmatched_lines,
        "unmatched_documents": unmatched_documents,
    }


def csv_text(lines: list[BankLine]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["date", "description", "amount", "type"])
    for line in lines:
        writer.writerow(
            [
                line.occurred_on.isoformat(),
                line.description,
                _money(line.amount),
                line.type,
            ]
        )
    return buffer.getvalue()


@dataclass(frozen=True)
class SeedPlan:
    period: Period
    seed: int
    documents: list[SeedDocument]
    lines: list[BankLine]
    manifest: dict
    csv_body: str
    practica_606: bytes
    practica_607: bytes


def build_plan(period: Period, seed: int = 202609) -> SeedPlan:
    docs = documents_for(period, seed)
    lines = bank_lines(docs, period)
    valid_606 = [row for row in purchases()]
    valid_607 = [row for row in sales()]
    return SeedPlan(
        period=period,
        seed=seed,
        documents=docs,
        lines=lines,
        manifest=build_manifest(docs, lines, period),
        csv_body=csv_text(lines),
        practica_606=render_txt(
            "606",
            period.periodo,
            [_shifted_606(row, period) for row in valid_606],
        ),
        practica_607=render_txt(
            "607",
            period.periodo,
            [_shifted_607(row, period) for row in valid_607],
        ),
    )


def _shifted_606(row: dict, period: Period) -> str:
    moved = dict(row)
    moved["fc"] = place(_stamp(row["fc"]), period).strftime("%Y%m%d")
    if row["fpago"]:
        moved["fpago"] = place(_stamp(row["fpago"]), period).strftime("%Y%m%d")
    return line_606(moved)


def _shifted_607(row: dict, period: Period) -> str:
    moved = dict(row)
    moved["fc"] = place(_stamp(row["fc"]), period).strftime("%Y%m%d")
    if row["fret"]:
        moved["fret"] = place(_stamp(row["fret"]), period).strftime("%Y%m%d")
    return line_607(moved)


def write_outputs(plan: SeedPlan, root: Path | None = None) -> dict[str, Path]:
    folder = (
        root or OUTPUT_ROOT
    ) / f"{plan.period.start.isoformat()}_{plan.period.end.isoformat()}"
    folder.mkdir(parents=True, exist_ok=True)
    paths = {
        "csv": folder / "estado-cuenta.csv",
        "manifest": folder / "conciliacion.json",
        "practica_606": folder / "practica-606.txt",
        "practica_607": folder / "practica-607.txt",
    }
    paths["csv"].write_text(plan.csv_body, encoding="utf-8")
    paths["manifest"].write_text(
        json.dumps(plan.manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    paths["practica_606"].write_bytes(plan.practica_606)
    paths["practica_607"].write_bytes(plan.practica_607)
    return paths
