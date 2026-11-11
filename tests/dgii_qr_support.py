"""Fake DGII QR fixtures for tests, generated here and nowhere else: a type 32
consultation link encoded with segno on a PNG, a JPEG, a one-page PDF and an
email with the image attached. Nothing here is a real taxpayer or invoice."""

from __future__ import annotations

import io
from email.message import EmailMessage

import segno
from PIL import Image, ImageDraw, ImageFont

RNC = "131111222"
ENCF = "E320000001234"
TOTAL = "33254.91"
CODE = "AbC123"
URL = (
    "https://fc.dgii.gov.do/eCF/ConsultaTimbreFC"
    f"?RncEmisor={RNC}&ENCF={ENCF}&MontoTotal={TOTAL}&CodigoSeguridad={CODE}"
)


def qr_png(text: str = URL, *, scale: int = 6, border: int = 4) -> bytes:
    buffer = io.BytesIO()
    segno.make(text, error="m").save(buffer, kind="png", scale=scale, border=border)
    return buffer.getvalue()


def _page(text: str = URL, *, size: tuple[int, int] = (1000, 1400)) -> Image.Image:
    """A receipt-like page: white, with the QR placed low on the right."""

    page = Image.new("RGB", size, "white")
    with Image.open(io.BytesIO(qr_png(text, scale=5))) as code:
        page.paste(
            code.convert("RGB"), (size[0] - code.width - 80, size[1] - code.height - 120)
        )
    return page


def qr_jpeg(text: str = URL) -> bytes:
    buffer = io.BytesIO()
    _page(text).save(buffer, format="JPEG", quality=92)
    return buffer.getvalue()


def qr_page_png(text: str = URL) -> bytes:
    buffer = io.BytesIO()
    _page(text).save(buffer, format="PNG")
    return buffer.getvalue()


def qr_pdf(text: str = URL) -> bytes:
    buffer = io.BytesIO()
    _page(text).save(buffer, format="PDF", resolution=150)
    return buffer.getvalue()


def qr_email(text: str = URL) -> bytes:
    message = EmailMessage()
    message["From"] = "ventas@hotel.example"
    message["To"] = "recibos-ab12@example.test"
    message["Subject"] = "Factura"
    message.set_content("Adjunto la factura.")
    message.add_attachment(
        qr_jpeg(text), maintype="image", subtype="jpeg", filename="factura.jpg"
    )
    return bytes(message)


def blank_png(size: tuple[int, int] = (800, 600)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, format="PNG")
    return buffer.getvalue()


ISSUE_DAY = "05-11-2026"
VALID_UNTIL = "31-12-2027"
ISSUE_DATE_RECEIPT = (
    "FICTICIO / SINTETICO",
    "FERRETERIA EJEMPLO SRL",
    f"RNC {RNC}",
    f"Fecha: {ISSUE_DAY}",
    "Cemento gris 1 saco        RD$ 28,182.13",
    "ITBIS 18%                  RD$  5,072.78",
    f"TOTAL                      RD$ {float(TOTAL):,.2f}",
    "Pagado en efectivo",
    f"e-NCF {ENCF}",
    f"Valido hasta: {VALID_UNTIL}",
)


def issue_date_receipt_png() -> bytes:
    """A synthetic e-CF receipt whose issue date is printed at the top and
    whose sequence expiry ("Valido hasta") sits beside the QR, which carries
    the issue date as FechaEmision."""

    page = Image.new("RGB", (1100, 1000), "white")
    font = ImageFont.load_default_imagefont()
    for index, line in enumerate(ISSUE_DATE_RECEIPT):
        glyphs = Image.new("L", font.getbbox(line)[2:])
        ImageDraw.Draw(glyphs).text((0, 0), line, fill=255, font=font)
        glyphs = glyphs.resize(
            (glyphs.width * 3, glyphs.height * 3), Image.Resampling.NEAREST
        )
        page.paste((30, 30, 30), (40, 40 + index * 60), glyphs)
    with Image.open(
        io.BytesIO(qr_png(f"{URL}&FechaEmision={ISSUE_DAY}", scale=5))
    ) as code:
        page.paste(code.convert("RGB"), (page.width - code.width - 60, 560))
    buffer = io.BytesIO()
    page.save(buffer, format="PNG")
    return buffer.getvalue()
