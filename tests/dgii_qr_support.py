"""Fake DGII QR fixtures for tests, generated here and nowhere else: a type 32
consultation link encoded with segno on a PNG, a JPEG, a one-page PDF and an
email with the image attached, and photos whose code a plain decode misses.
Nothing here is a real taxpayer or invoice."""

from __future__ import annotations

import io
from datetime import date
from email.message import EmailMessage

import segno
from argus.domain.business.fiscal_identity import rnc_check_digit_ok
from faker import Faker
from PIL import Image, ImageChops, ImageDraw, ImageFilter

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


def fake_rnc(faker: Faker) -> str:
    """A made-up RNC whose check digit holds, by the rule's own owner."""

    body = faker.numerify("1#######")
    return next(
        body + digit for digit in "0123456789" if rnc_check_digit_ok(body + digit)
    )


def timbre_url(faker: Faker, *, issued: date) -> str:
    """A made-up e-CF consultation link with every field a printed QR carries."""

    return (
        "https://ecf.dgii.gov.do/ecf/ConsultaTimbre"
        f"?RncEmisor={fake_rnc(faker)}&RncComprador={fake_rnc(faker)}"
        f"&ENCF=E31{faker.numerify('##########')}"
        f"&FechaEmision={issued:%d-%m-%Y}"
        f"&MontoTotal={faker.pydecimal(left_digits=5, right_digits=2, positive=True)}"
        f"&FechaFirma={issued:%d-%m-%Y}%2010:11:12"
        f"&CodigoSeguridad={faker.bothify('??##??')}"
    )


PHOTO = (1600, 1200)


def _photo(
    text: str, *, scale: int, blur: float, ink: int, paper: int, band: bool, shadow: bool
) -> bytes:
    with Image.open(io.BytesIO(qr_png(text, scale=scale))) as code:
        mark = code.convert("L").point(lambda value: ink + (paper - ink) * value // 255)
    page = Image.new("L", PHOTO, paper)
    if band:
        ImageDraw.Draw(page).rectangle((0, 0, PHOTO[0], PHOTO[1] // 7), fill=ink)
    page.paste(mark, (PHOTO[0] - mark.width - 120, PHOTO[1] - mark.height - 160))
    if shadow:
        shade = Image.linear_gradient("L").resize(PHOTO)
        page = ImageChops.multiply(page, shade.point(lambda value: 255 - value // 3))
    buffer = io.BytesIO()
    page.filter(ImageFilter.GaussianBlur(blur)).convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def small_soft_photo(text: str) -> bytes:
    """A phone photo of a long receipt: the code is a small, soft patch under
    a shadow. A plain decode misses it; the same photo enlarged decodes."""

    return _photo(text, scale=2, blur=0.95, ink=60, paper=200, band=False, shadow=True)


def washed_out_photo(text: str) -> bytes:
    """A faded thermal print: ink and paper a few grey levels apart. A plain
    or an enlarged decode misses it; the same photo with its contrast
    stretched decodes."""

    return _photo(text, scale=3, blur=0.8, ink=122, paper=130, band=True, shadow=False)
