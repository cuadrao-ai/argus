"""Fake DGII QR fixtures for tests, generated here and nowhere else: a type 32
consultation link encoded with segno on a PNG, a JPEG, a one-page PDF and an
email with the image attached. Nothing here is a real taxpayer or invoice."""

from __future__ import annotations

import io
from email.message import EmailMessage

import segno
from PIL import Image

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
