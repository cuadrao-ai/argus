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
from typing import Iterator, Sequence
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from loguru import logger
from PIL import Image, ImageOps
from pydantic import ValidationError

from argus.domain.business.contracts.checks import (
    DGII_HOSTS,
    DgiiQr,
    EcfCheck,
    EcfVerification,
    ReadVsQr,
    dgii_link_host,
)
from argus.domain.business.contracts.facts import BusinessFacts, FiscalFacts, Known
from argus.domain.ingestion.documents.models import ReceiptDetails

__all__ = ["DGII_HOSTS", "parse_dgii_url", "read_dgii_qr"]
MAX_URL_CHARS = 2048
MAX_VALUE_CHARS = 64
MAX_PAGES_SCANNED = 8
MAX_NUMBER_EXPONENT = 30
RETRY_SCALES = (2, 3)
#: A 1600x1200 photo enlarged three times is 17.3 million grey pixels.
MAX_RETRY_PIXELS = 20_000_000
AUTOCONTRAST_CUTOFF = 2
_ENCF = re.compile(r"^E(\d{2})\d{10}$")
_DATE_FORMATS = ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d")


def _passes(grey: Image.Image) -> Iterator[tuple[str, Image.Image]]:
    """The page as shot, then the retries for a code the plain pass missed: a
    small or soft code decodes once enlarged, a faded one once its contrast is
    stretched. An enlargement over ``MAX_RETRY_PIXELS`` is skipped."""

    yield "plain", grey
    for scale in RETRY_SCALES:
        size = (grey.width * scale, grey.height * scale)
        if size[0] * size[1] <= MAX_RETRY_PIXELS:
            yield f"x{scale}", grey.resize(size, Image.Resampling.LANCZOS)
    yield "autocontrast", ImageOps.autocontrast(grey, cutoff=AUTOCONTRAST_CUTOFF)


def _decode(image: bytes) -> Iterator[tuple[str, str]]:
    """Each QR text on the page with the pass that found it. Lazy: a caller
    that stops at the first DGII link never pays for the later passes."""

    import zxingcpp

    with Image.open(io.BytesIO(image)) as source:
        source.load()
        grey = source.convert("L")
    for name, page in _passes(grey):
        found = zxingcpp.read_barcodes(
            page, formats=zxingcpp.BarcodeFormat.QRCode, try_rotate=True
        )
        for result in found:
            if result.valid and result.text:
                yield name, result.text


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
            for attempt, text in _decode(image):
                qr = parse_dgii_url(text)
                if qr is None:
                    continue
                if attempt != "plain":
                    logger.info("dgii_qr_decoded_on_retry attempt={}", attempt)
                return qr
        except Exception as exc:  # noqa: BLE001
            logger.debug("QR decode skipped a page", failure_mode=type(exc).__name__)
    return None


def tipo_ecf_of(encf: str | None) -> str | None:
    """The document type the e-NCF encodes (E31…, E32…), when it has that shape."""

    if encf is None:
        return None
    match = _ENCF.match(encf.strip().upper())
    return match.group(1) if match else None


def _stated(qr: DgiiQr) -> dict[str, str | None]:
    """What the QR states, under the name the match row gives each field."""

    return {
        "rnc": qr.rnc_emisor,
        "ecf": qr.encf,
        "total": qr.monto_total,
        "occurred_on": qr.fecha_emision.isoformat() if qr.fecha_emision else None,
    }


def _same(name: str, held: object, stated: str) -> bool:
    """The one equality of a held value and the QR's: the total by its number,
    anything else as text without case or outer spaces."""

    if name != "total":
        return str(held).strip().upper() == stated.strip().upper()
    try:
        return Decimal(str(held)) == Decimal(stated)
    except (DecimalException, ValueError):
        return False


def _match_row(qr: DgiiQr, held: dict[str, object] | None) -> EcfCheck:
    """Whether what the QR names equals the values held, field by field and
    only where both exist; ``read_vs_qr`` carries both values of each."""

    stated = _stated(qr)
    compared: dict[str, ReadVsQr] = {}
    differing: list[str] = []
    for name, value in (held or {}).items():
        if value is None or stated[name] is None:
            continue
        compared[name] = ReadVsQr(read=str(value)[:64], qr=stated[name][:64])
        if not _same(name, value, stated[name]):
            differing.append(name)
    if not compared:
        return EcfCheck(name="qr_matches_read", state="not_checked", code="no_read")
    if differing:
        return EcfCheck(
            name="qr_matches_read",
            state="failed",
            code="qr_differs",
            read_vs_qr={name: compared[name] for name in differing},
        )
    return EcfCheck(name="qr_matches_read", state="verified", read_vs_qr=compared)


def qr_checks(qr: DgiiQr | None, receipt: ReceiptDetails | None) -> list[EcfCheck]:
    """Two rows: whether a DGII QR was there, and whether what it names
    (issuer RNC, e-NCF, total, issue date) equals what the read found. This
    is the read on its own, before the merge; ``record_qr_checks`` makes the
    row the record saves."""

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
        return [present, _match_row(qr, None)]
    held = {
        "rnc": receipt.rnc,
        "ecf": receipt.ecf or receipt.ncf,
        "total": receipt.total,
        "occurred_on": receipt.occurred_on,
    }
    return [present, _match_row(qr, held)]


def record_qr_checks(
    verification: EcfVerification | None,
    qr: DgiiQr | None,
    facts: BusinessFacts,
    read_total: str | None,
    *,
    amount_is_total: bool,
) -> EcfVerification | None:
    """The verification as the record saves it: the match row made again over
    what the record holds after the merge, so it never asks for review of a
    value the QR replaced. A fact the QR gave is not compared with itself.
    The amount of a read with several purchases is not a total; the total
    that read showed is compared in its place."""

    if verification is None or qr is None:
        return verification

    def held(fact: object) -> object:
        mine = isinstance(fact, Known) and fact.origin != "qr_decoded"
        return fact.value if mine else None

    fiscal = facts.fiscal or FiscalFacts()
    row = _match_row(
        qr,
        {
            "rnc": held(fiscal.rnc),
            "ecf": held(fiscal.ecf) or held(fiscal.ncf),
            "total": held(facts.amount) if amount_is_total else read_total,
            "occurred_on": held(facts.occurred_on),
        },
    )
    checks = tuple(row if c.name == row.name else c for c in verification.checks)
    return verification.model_copy(update={"checks": checks})


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


def _holds(model: type[BusinessFacts | FiscalFacts], name: str, fact: dict) -> bool:
    """Whether the fact's contract takes the value as a known fact."""

    try:
        return isinstance(getattr(model.model_validate({name: fact}), name), Known)
    except ValidationError:
        return False


def fill_from_qr(
    facts: dict,
    qr: DgiiQr | None,
    source_id: object,
    *,
    fill_amount: bool,
    fill_rnc: bool,
) -> dict:
    """The typed merge step after decode and read. The QR is the document's
    own printed statement, so what it carries (e-NCF, issue date, the issuer
    RNC of a purchase, and the total of a read with at most one purchase)
    replaces what the reader found or left unknown, with the origin
    ``qr_decoded`` and the attachment as its source. A reader's value that
    agrees stands as read. A value anyone but the reader gave is never
    replaced, and neither is one whose QR value the fact cannot hold. The
    amount stays a draft value a person approves. Each disagreement is logged
    by field name."""

    if qr is None:
        return facts
    stated = _stated(qr)
    targets = [(BusinessFacts, facts, "occurred_on", "occurred_on")]
    if fill_amount:
        targets.append((BusinessFacts, facts, "amount", "total"))
    fiscal = facts.get("fiscal")
    if isinstance(fiscal, dict):
        targets.append((FiscalFacts, fiscal, "ecf", "ecf"))
        if fill_rnc:
            targets.append((FiscalFacts, fiscal, "rnc", "rnc"))
    replaced: list[str] = []
    kept: list[str] = []
    for model, holder, name, field in targets:
        fact, value = holder[name], stated[field]
        if value is None:
            continue
        known = fact.get("state") == "known"
        if known and _same(field, fact["value"], value):
            continue
        candidate = {
            "state": "known",
            "value": value,
            "origin": "qr_decoded",
            "verified": False,
            "source_ids": [str(source_id)],
        }
        if fact.get("origin") in (None, "extracted") and _holds(model, name, candidate):
            holder[name] = candidate
            if known:
                replaced.append(name)
        elif known:
            kept.append(name)
    if replaced or kept:
        logger.info(
            "business_post_read_rule rule=qr_over_read replaced={} kept={}"
            " replaced_fields={} kept_fields={}",
            len(replaced),
            len(kept),
            replaced,
            kept,
        )
    return facts
