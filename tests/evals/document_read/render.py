"""Draws a case as a phone photo of a thermal receipt. Same case, same bytes."""

from __future__ import annotations

import io
import random
import unicodedata
from dataclasses import dataclass, field

import segno
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from tests.evals.document_read.cases import PAYMENTS, SEED, Case

LONG_SIDE = 1600
_WIDTH = 600
_MARGIN = 36
_BODY = 24
_PAPER = (250, 249, 243)
_INK = (38, 38, 46)
_PEN = (28, 58, 170)
_SKIN = (222, 170, 136)
_TABLES = ((96, 76, 58), (58, 60, 68), (120, 112, 100))
_MERCHANT_APP = "https://app.example.test/descarga?tienda=demo"


@dataclass(frozen=True)
class Line:
    left: str = ""
    right: str = ""
    center: bool = False
    size: int = _BODY
    tag: str = ""
    #: Part of ``left`` hidden under a smudge.
    blot: str = ""
    qr: str = ""
    rule: bool = False


@dataclass
class Strip:
    image: Image.Image
    #: Heights where the paper can be cut without cutting a line.
    cuts: list[int] = field(default_factory=list)
    marks: dict[str, tuple[int, int]] = field(default_factory=dict)


def _printed(text: str) -> str:
    """Text as the paper shows it. Pillow's bundled font has no accented
    letters, and many thermal printers print none."""

    folded = unicodedata.normalize("NFKD", text)
    return "".join(char for char in folded if not unicodedata.combining(char))


def money(value: object) -> str:
    return f"{value:,.2f}"


def receipt_lines(case: Case) -> list[Line]:
    electronic = case.ncf_series.startswith("E")
    credit = case.ncf_series in ("E31", "B01")
    rnc = case.supplier_rnc
    if case.rnc_dashed:
        rnc = f"{rnc[0]}-{rnc[1:3]}-{rnc[3:8]}-{rnc[8]}"
    lines = [
        Line(case.merchant, center=True, size=32),
        Line(case.address, center=True, size=20),
    ]
    if case.supplier_rnc_print != "absent":
        lines.append(
            Line(
                f"RNC: {rnc}",
                center=True,
                blot=rnc[2:7] if case.supplier_rnc_print == "smudged" else "",
            )
        )
    lines.append(Line(rule=True))
    title = "FACTURA DE CREDITO FISCAL" if credit else "FACTURA DE CONSUMO"
    lines.append(Line(title + (" ELECTRONICA" if electronic else ""), center=True))
    lines.append(Line(f"{'e-NCF' if electronic else 'NCF'}: {case.ncf}"))
    issue = None
    if case.date_label:
        printed = case.date_style.render(case.issued)
        issue = Line(
            f"{case.date_label}: {printed}" + (" 14:32" if case.with_time else "")
        )
    dates = []
    if case.expiry:
        dates.append(
            Line(f"{case.expiry_label}: {case.expiry_style.render(case.expiry)}")
        )
    if issue and not case.date_near_qr:
        dates.insert(0 if not case.expiry_first else len(dates), issue)
    lines.extend(dates)
    if case.buyer_rnc_label:
        lines.append(Line(f"{case.buyer_rnc_label}: {case.buyer_rnc}"))
        lines.append(Line(f"Cliente: {case.buyer_name}"))
    lines.append(Line(f"Cajero: {case.cashier}"))
    lines.append(Line(rule=True))
    lines.extend(
        Line(f"{item.quantity} x {item.description}", money(item.total))
        for item in case.items
    )
    lines.append(Line(rule=True))
    lines.append(Line("Subtotal", money(case.subtotal), tag="totals"))
    if case.tax == "itbis":
        lines.append(Line("ITBIS 18%", money(case.tax_amount)))
    elif case.tax in ("impuesto", "impuesto_zero"):
        lines.append(Line("Impuesto", money(case.tax_amount)))
    lines.append(Line("TOTAL", "RD$ " + money(case.total), size=30))
    tender = PAYMENTS[case.payment][0]
    if tender:
        paid = "" if case.payment.startswith("credito") else money(case.total)
        lines.append(Line(tender.format(last4=case.card_last4), paid, tag="payment"))
    lines.append(Line(rule=True))
    if case.merchant_qr:
        lines.append(Line("Descarga nuestra app", center=True, size=20))
        lines.append(Line(qr=_MERCHANT_APP))
    if issue and case.date_near_qr:
        lines.append(issue)
    if case.dgii_url:
        lines.append(Line(qr=case.dgii_url, tag="dgii_qr"))
        lines.append(Line(f"Código de Seguridad: {case.security_code}", size=20))
        if case.signature_line:
            signed = case.signed_on.strftime("%d-%m-%Y")
            lines.append(Line(f"Fecha Firma: {signed} 10:15:00", size=20))
    lines.append(Line("Gracias por su compra", center=True, size=20))
    return lines


def _qr(text: str, scale: int) -> Image.Image:
    buffer = io.BytesIO()
    segno.make(text, error="m").save(buffer, kind="png", scale=scale, border=4)
    with Image.open(buffer) as code:
        return code.convert("RGB")


def _smudge(draw: ImageDraw.ImageDraw, box: tuple[float, float, float, float]) -> None:
    left, top, right, bottom = box
    step = (right - left) / 4
    for index in range(4):
        start = left + index * step - 4
        lift = 3 if index % 2 else -2
        draw.ellipse(
            (start, top - 4 + lift, start + step + 8, bottom + 5 + lift),
            fill=(52, 52, 60),
        )


def draw_strip(case: Case) -> Strip:
    lines = receipt_lines(case)
    blocks = []
    for line in lines:
        if line.qr:
            code = _qr(line.qr, 5 if line.tag else 4)
            blocks.append((line, code, code.height + 16))
        elif line.rule:
            blocks.append((line, None, 22))
        else:
            blocks.append((line, None, int(line.size * 1.5)))
    top = 110 if case.note else 40
    height = top + sum(block[2] for block in blocks) + 40
    image = Image.new("RGB", (_WIDTH, height), _PAPER)
    draw = ImageDraw.Draw(image)
    strip = Strip(image)
    y = top
    for line, code, tall in blocks:
        if code is not None:
            image.paste(code, ((_WIDTH - code.width) // 2, y + 8))
        elif line.rule:
            dash = "- " * 40
            draw.text((_MARGIN, y), dash, fill=_INK, font=ImageFont.load_default(18))
        else:
            font = ImageFont.load_default(line.size)
            left = _printed(line.left)
            x = _MARGIN
            if line.center:
                x = (_WIDTH - draw.textlength(left, font=font)) / 2
            draw.text((x, y), left, fill=_INK, font=font)
            if line.right:
                width = draw.textlength(line.right, font=font)
                draw.text((_WIDTH - _MARGIN - width, y), line.right, fill=_INK, font=font)
            if line.blot:
                before = left[: left.index(line.blot)]
                start = x + draw.textlength(before, font=font)
                end = start + draw.textlength(line.blot, font=font)
                _smudge(draw, (start, y, end, y + line.size))
        if line.tag:
            strip.marks[line.tag] = (y, y + tall)
        y += tall
        if code is None:
            strip.cuts.append(y)
    if case.finger:
        low, high = strip.marks["payment"]
        draw.ellipse((-140, low - 8, _WIDTH * 0.72, high + 10), fill=_SKIN)
    if case.note:
        layer = Image.new("RGBA", (260, 90), (0, 0, 0, 0))
        ImageDraw.Draw(layer).text(
            (8, 8), case.note, fill=(*_PEN, 255), font=ImageFont.load_default(58)
        )
        layer = layer.rotate(9, expand=True, resample=Image.BICUBIC)
        image.paste(layer, (_WIDTH - layer.width - 30, 4), layer)
    return strip


def _pieces(strip: Strip, count: int) -> list[Image.Image]:
    """The paper cut into ``count`` pieces at the line gaps nearest equal lengths."""

    height = strip.image.height
    edges = [0]
    for index in range(1, count):
        target = height * index / count
        edges.append(min(strip.cuts, key=lambda cut: abs(cut - target)))
    edges.append(height)
    return [
        strip.image.crop((0, start, _WIDTH, end))
        for start, end in zip(edges, edges[1:], strict=False)
    ]


def _table(size: tuple[int, int], rng: random.Random) -> Image.Image:
    base = Image.new("RGB", size, rng.choice(_TABLES))
    grain = Image.frombytes("L", size, rng.randbytes(size[0] * size[1]))
    return Image.blend(base, Image.merge("RGB", (grain, grain, grain)), 0.07)


def _photo(
    pieces: list[Image.Image],
    rng: random.Random,
    *,
    angle: float,
    shadow: bool,
    out_of_frame: int,
) -> bytes:
    """Lay the pieces left to right on a table and take the picture.
    ``out_of_frame`` is how much of the paper falls below the bottom edge."""

    turned = []
    for index, piece in enumerate(pieces):
        tilt = angle + (rng.uniform(-1.2, 1.2) if index else 0.0)
        turned.append(
            piece.convert("RGBA").rotate(tilt, expand=True, resample=Image.BICUBIC)
        )
    overlap = 10 if len(turned) > 1 else 0
    width = sum(piece.width for piece in turned) - overlap * (len(turned) - 1) + 90
    height = max(piece.height for piece in turned) + 45 - out_of_frame
    height += 0 if out_of_frame else 45
    photo = _table((width, height), rng)
    x = 45
    for piece in turned:
        photo.paste(piece, (x, 45 + rng.randint(0, 12 if len(turned) > 1 else 0)), piece)
        x += piece.width - overlap
    if shadow:
        patches = Image.new("L", (3, 3))
        patches.putdata([rng.randint(125, 255) for _ in range(9)])
        ramp = patches.resize(photo.size, Image.BICUBIC)
        photo = ImageChops.multiply(photo, Image.merge("RGB", (ramp, ramp, ramp)))
    photo = photo.filter(ImageFilter.GaussianBlur(0.5))
    photo.thumbnail((LONG_SIDE, LONG_SIDE))
    buffer = io.BytesIO()
    photo.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()


def render(case: Case) -> bytes:
    """The JPEG photo of one case, at most LONG_SIDE pixels on its long side."""

    rng = random.Random(f"{SEED}:{case.case_id}:photo")
    strip = draw_strip(case)
    out_of_frame = 0
    if case.layout == "cut_totals":
        out_of_frame = strip.image.height - strip.marks["totals"][0]
    elif case.qr == "cropped":
        low, high = strip.marks["dgii_qr"]
        out_of_frame = strip.image.height - (low + (high - low) * 45 // 100)
    if case.layout in ("collage2", "collage3"):
        pieces = _pieces(strip, int(case.layout[-1]))
    elif case.companion:
        pieces = [strip.image, draw_strip(case.companion).image]
    else:
        pieces = [strip.image]
    return _photo(
        pieces, rng, angle=case.angle, shadow=case.shadow, out_of_frame=out_of_frame
    )
