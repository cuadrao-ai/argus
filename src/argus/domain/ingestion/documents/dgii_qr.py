"""The DGII QR on a Dominican e-invoice, decoded deterministically from the
page images, and what it lets Cuadrao say.

The decoder is a plain library, never a model, and never a gate: it runs
beside the read, after preparation, and a page without a usable QR changes
nothing. Only a link to DGII's own consultation pages counts; anything
else decodes to nothing and the capture goes on. Nothing here contacts DGII:
the stored link is for the person to open.
"""

from __future__ import annotations

import io
import re
from datetime import date, datetime
from decimal import Decimal, DecimalException
from typing import Sequence
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from loguru import logger
from PIL import Image

from argus.domain.business.contracts.checks import (
    DGII_HOSTS,
    DgiiQr,
    EcfCheck,
    EcfVerification,
    dgii_link_host,
)
from argus.domain.ingestion.documents.models import ReceiptDetails

__all__ = ["DGII_HOSTS", "parse_dgii_url", "read_dgii_qr"]
MAX_URL_CHARS = 2048
MAX_VALUE_CHARS = 64
MAX_PAGES_SCANNED = 8
MAX_NUMBER_EXPONENT = 30
_ENCF = re.compile(r"^E(\d{2})\d{10}$")
_DATE_FORMATS = ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d")


def _decode(image: bytes) -> list[str]:
    import zxingcpp

    with Image.open(io.BytesIO(image)) as source:
        source.load()
        grey = source.convert("L")
    found = zxingcpp.read_barcodes(
        grey, formats=zxingcpp.BarcodeFormat.QRCode, try_rotate=True
    )
    return [result.text for result in found if result.valid and result.text]


def _value(query: dict[str, str], name: str) -> str | None:
    value = (query.get(name) or "").strip()
    return value if value and len(value) <= MAX_VALUE_CHARS else None


def _amount(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        number = Decimal(value)
    except (DecimalException, ValueError):
        return None
    if not number.is_finite() or abs(number.adjusted()) > MAX_NUMBER_EXPONENT:
        return None
    return value


def _day(value: str | None) -> date | None:
    if value is None:
        return None
    for layout in _DATE_FORMATS:
        try:
            return datetime.strptime(value, layout).date()
        except ValueError:
            continue
    return None


def parse_dgii_url(text: str) -> DgiiQr | None:
    """A DGII consultation link as typed facts, or None for any other text:
    another host, another scheme, a link without the issuer and the e-NCF."""

    if not text or len(text) > MAX_URL_CHARS:
        return None
    # Text that does not split as a URL (a bad port, a broken IPv6 bracket) is
    # not a link; QR parsing never fails a capture.
    try:
        parts = urlsplit(text.strip())
        query_pairs = parse_qsl(parts.query, keep_blank_values=False)
    except ValueError:
        return None
    host = dgii_link_host(text.strip())
    if host is None:
        return None
    query = {}
    for key, value in query_pairs:
        query.setdefault(key.lower(), value)
    rnc = _value(query, "rncemisor")
    encf = _value(query, "encf")
    if rnc is None or encf is None:
        return None
    try:
        link = DgiiQr(
            url=urlunsplit(("https", host, parts.path or "/", parts.query, "")),
            host=host,
            rnc_emisor=rnc,
            encf=encf,
            monto_total=_amount(_value(query, "montototal")),
            codigo_seguridad=_value(query, "codigoseguridad"),
            fecha_emision=_day(_value(query, "fechaemision")),
            fecha_firma=_value(query, "fechafirma"),
            rnc_comprador=_value(query, "rnccomprador"),
        )
    except ValueError:
        return None
    return link


def read_dgii_qr(images: Sequence[bytes]) -> DgiiQr | None:
    """The first DGII QR on the page images, or None. Never raises: a page
    the decoder cannot read is a page without a QR."""

    for image in list(images)[:MAX_PAGES_SCANNED]:
        try:
            texts = _decode(image)
        except Exception as exc:  # noqa: BLE001
            logger.debug("QR decode skipped a page", failure_mode=type(exc).__name__)
            continue
        for text in texts:
            qr = parse_dgii_url(text)
            if qr is not None:
                return qr
    return None


def tipo_ecf_of(encf: str | None) -> str | None:
    """The document type the e-NCF encodes (E31…, E32…), when it has that shape."""

    if encf is None:
        return None
    match = _ENCF.match(encf.strip().upper())
    return match.group(1) if match else None


def _same_number(read: str | None, stated: str | None) -> bool | None:
    if read is None or stated is None:
        return None
    try:
        return Decimal(str(read)) == Decimal(stated)
    except (DecimalException, ValueError):
        return False


def qr_checks(qr: DgiiQr | None, receipt: ReceiptDetails | None) -> list[EcfCheck]:
    """Two rows: whether a DGII QR was there, and whether what it names
    (issuer RNC, e-NCF, total) equals what the read found, field by field
    and only where both exist. A mismatch fills nothing and is a row to
    review with both values."""

    if qr is None:
        return [
            EcfCheck(name="qr_present", state="not_checked", code="no_qr"),
            EcfCheck(name="qr_matches_read", state="not_checked", code="no_qr"),
        ]
    present = EcfCheck(
        name="qr_present",
        state="verified",
        detail={"host": qr.host, "encf": qr.encf, "rnc_emisor": qr.rnc_emisor},
    )
    if receipt is None:
        return [
            present,
            EcfCheck(name="qr_matches_read", state="not_checked", code="no_read"),
        ]
    pairs = {
        "rnc": (receipt.rnc, qr.rnc_emisor, False),
        "ecf": (receipt.ecf or receipt.ncf, qr.encf, False),
        "total": (receipt.total, qr.monto_total, True),
    }
    compared: dict[str, str] = {}
    differing: list[str] = []
    for name, (read, stated, numeric) in pairs.items():
        if read is None or stated is None:
            continue
        same = (
            _same_number(read, stated)
            if numeric
            else str(read).strip().upper() == str(stated).strip().upper()
        )
        compared[name] = f"read={read} qr={stated}"
        if not same:
            differing.append(name)
    if not compared:
        return [
            present,
            EcfCheck(name="qr_matches_read", state="not_checked", code="no_read"),
        ]
    if differing:
        return [
            present,
            EcfCheck(
                name="qr_matches_read",
                state="failed",
                code="qr_differs",
                detail={name: compared[name] for name in differing},
            ),
        ]
    return [present, EcfCheck(name="qr_matches_read", state="verified", detail=compared)]


def with_qr(
    verification: EcfVerification | None,
    qr: DgiiQr | None,
    receipt: ReceiptDetails | None,
    now: datetime,
) -> EcfVerification | None:
    """The verification with the QR rows beside the e-CF rows. A document with
    a QR and no XML gets a verification of its own: the QR rows, the DGII row
    (never claimed) and the e-NCF the QR names. No XML and no QR: none."""

    if verification is None and qr is None:
        return None
    rows = qr_checks(qr, receipt)
    if verification is not None:
        checks = [
            c
            for c in verification.checks
            if c.name not in {"qr_present", "qr_matches_read"}
        ]
        if qr is not None:
            security = next((c for c in checks if c.name == "security_code"), None)
            expected = (security.detail or {}).get("expected") if security else None
            if expected and qr.codigo_seguridad:
                same = expected == qr.codigo_seguridad
                rows[0] = rows[0].model_copy(
                    update={
                        "detail": {
                            **rows[0].detail,
                            "security_code": "same_as_xml"
                            if same
                            else "differs_from_xml",
                        }
                    }
                )
        return verification.model_copy(update={"checks": tuple([*checks, *rows])})
    assert qr is not None
    return EcfVerification(
        encf=qr.encf,
        tipo_ecf=tipo_ecf_of(qr.encf),
        checked_at=now,
        checks=(
            *rows,
            EcfCheck(
                name="dgii_accepted", state="not_checked", code="network_not_in_tier_a"
            ),
        ),
    )


def fill_from_qr(
    facts: dict, qr: DgiiQr | None, source_id: object, *, fill_amount: bool
) -> dict:
    """The typed merge step after decode and read: the QR fills only what the
    read left unknown (issuer RNC, e-NCF, total, issue date), each filled fact
    carrying the origin ``qr_decoded`` and the attachment as its source. A
    value the read found stays, equal or not: a mismatch is a row to review,
    never an overwrite. The amount is filled only for a read with at most one
    purchase and stays a draft value a person approves."""

    if qr is None:
        return facts

    def fill(fact: dict, value: object) -> dict:
        if value is None or fact.get("state") == "known":
            return fact
        return {
            "state": "known",
            "value": value,
            "origin": "qr_decoded",
            "verified": False,
            "source_ids": [str(source_id)],
        }

    if fill_amount:
        facts["amount"] = fill(facts["amount"], qr.monto_total)
    facts["occurred_on"] = fill(
        facts["occurred_on"], qr.fecha_emision.isoformat() if qr.fecha_emision else None
    )
    fiscal = facts.get("fiscal")
    if isinstance(fiscal, dict):
        fiscal["rnc"] = fill(fiscal["rnc"], qr.rnc_emisor)
        fiscal["ecf"] = fill(fiscal["ecf"], qr.encf)
    return facts
