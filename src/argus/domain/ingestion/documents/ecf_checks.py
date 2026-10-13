"""Local checks on a DGII e-CF XML: what the file itself proves, read inertly.

No network: nothing here asks DGII whether the invoice was accepted, and no
certificate authority is trusted by name. A signature that verifies proves
only that the content has not changed since it was signed with the key the
file carries; the checks say exactly that. A failed check never blocks
capture or review: it is shown for a person to resolve.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID
from lxml import etree

from argus.domain.business.contracts.checks import EcfCheck, EcfVerification
from argus.domain.ingestion.documents.models import ReceiptDetails

DS = "http://www.w3.org/2000/09/xmldsig#"
ENVELOPED = "http://www.w3.org/2000/09/xmldsig#enveloped-signature"
#: Canonicalization algorithm -> (exclusive, with_comments). c14n only.
C14N = {
    "http://www.w3.org/TR/2001/REC-xml-c14n-20010315": (False, False),
    "http://www.w3.org/TR/2001/REC-xml-c14n-20010315#WithComments": (False, True),
    "http://www.w3.org/2001/10/xml-exc-c14n#": (True, False),
    "http://www.w3.org/2001/10/xml-exc-c14n#WithComments": (True, True),
}
DIGESTS = {
    "http://www.w3.org/2001/04/xmlenc#sha256": hashlib.sha256,
    "http://www.w3.org/2000/09/xmldsig#sha1": hashlib.sha1,
}
SIGNATURES = {
    "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256": hashes.SHA256,
    "http://www.w3.org/2000/09/xmldsig#rsa-sha1": hashes.SHA1,
}
#: Caps read before any canonicalization, so a hostile file cannot make it costly.
MAX_CERTIFICATE_CHARS = 8192
MAX_SIGNATURE_CHARS = 4096
MAX_SIGNED_INFO_BYTES = 16384
SECURITY_CODE_CHARS = 6
SIGNED_AT_FORMAT = "%d-%m-%Y %H:%M:%S"
ISSUED_ON_FORMAT = "%d-%m-%Y"
TOTAL_PARTS = (
    "MontoGravadoTotal",
    "MontoExento",
    "TotalITBIS",
    "MontoPropinaLegal",
    "TotalISC",
    "TotalOtrosImpuestos",
)

_PARSER = etree.XMLParser(
    resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False
)


@dataclass(frozen=True)
class SignatureReading:
    """What the file's own signature proves, or why it could not be checked."""

    state: str
    code: str | None = None
    detail: dict[str, str] = field(default_factory=dict)
    certificate: x509.Certificate | None = None
    security_code: str | None = None


@dataclass(frozen=True)
class EcfDocument:
    tipo_ecf: str | None
    encf: str | None
    rnc_emisor: str | None
    fecha_emision: str | None
    fecha_hora_firma: str | None
    totals: dict[str, str]
    item_amounts: tuple[str, ...]
    signature: SignatureReading


def _local(tag: object) -> str:
    return str(tag).rsplit("}", 1)[-1]


def _text(node: etree._Element | None) -> str | None:
    if node is None or node.text is None:
        return None
    value = node.text.strip()
    return value or None


def _child(node: etree._Element, *path: str) -> etree._Element | None:
    current: etree._Element | None = node
    for name in path:
        if current is None:
            return None
        current = next(
            (c for c in current if isinstance(c.tag, str) and _local(c.tag) == name),
            None,
        )
    return current


def read_ecf(content: bytes) -> EcfDocument | None:
    """The facts an e-CF states about itself, or None for anything that is
    not a well-formed DGII e-CF. Entities, DTDs and the network stay off."""

    try:
        text = content.decode("utf-8-sig")
    except UnicodeError:
        return None
    upper = text.upper()
    if "<!DOCTYPE" in upper or "<!ENTITY" in upper:
        return None
    try:
        root = etree.fromstring(text.encode("utf-8"), _PARSER)
    except (etree.XMLSyntaxError, ValueError):
        return None
    if _local(root.tag) != "ECF":
        return None
    header = _child(root, "Encabezado")
    totals_node = _child(root, "Encabezado", "Totales")
    totals = (
        {
            _local(c.tag): _text(c) or ""
            for c in totals_node
            if isinstance(c.tag, str) and _text(c)
        }
        if totals_node is not None
        else {}
    )
    items_node = _child(root, "DetallesItems")
    amounts = tuple(
        value
        for item in (items_node if items_node is not None else ())
        if isinstance(item.tag, str)
        for value in [_text(_child(item, "MontoItem"))]
        if value
    )
    return EcfDocument(
        tipo_ecf=_text(_child(root, "Encabezado", "IdDoc", "TipoeCF")),
        encf=_text(_child(root, "Encabezado", "IdDoc", "eNCF")),
        rnc_emisor=_text(_child(root, "Encabezado", "Emisor", "RNCEmisor")),
        fecha_emision=_text(_child(root, "Encabezado", "Emisor", "FechaEmision")),
        fecha_hora_firma=_text(_child(root, "FechaHoraFirma")),
        totals=totals if header is not None else {},
        item_amounts=amounts,
        signature=_read_signature(root),
    )


def _unchecked(code: str, **detail: str) -> SignatureReading:
    return SignatureReading("not_checked", code, dict(detail))


def _canonical(node: etree._Element, algorithm: str) -> bytes:
    exclusive, comments = C14N[algorithm]
    return etree.tostring(
        node, method="c14n", exclusive=exclusive, with_comments=comments
    )


def _without(root: etree._Element, signature: etree._Element, algorithm: str) -> bytes:
    """The document canonicalized with the signature element removed (the
    enveloped-signature transform); the element's tail text stays with the
    parent, and the tree is put back as it was."""

    parent = signature.getparent()
    if parent is None:
        raise ValueError("signature at root")
    index = parent.index(signature)
    previous = signature.getprevious()
    tail = signature.tail or ""
    kept_previous_tail = previous.tail if previous is not None else None
    kept_parent_text = parent.text
    parent.remove(signature)
    try:
        if tail:
            if previous is not None:
                previous.tail = (previous.tail or "") + tail
            else:
                parent.text = (parent.text or "") + tail
        return _canonical(root, algorithm)
    finally:
        if previous is not None:
            previous.tail = kept_previous_tail
        else:
            parent.text = kept_parent_text
        parent.insert(index, signature)
        signature.tail = tail or None


def _read_signature(root: etree._Element) -> SignatureReading:
    signatures = [node for node in root.iter(f"{{{DS}}}Signature")]
    if not signatures:
        return _unchecked("no_signature")
    if len(signatures) > 1:
        return _unchecked("several_signatures", count=str(len(signatures)))
    signature = signatures[0]
    signed_info = signature.find(f"{{{DS}}}SignedInfo")
    value_node = signature.find(f"{{{DS}}}SignatureValue")
    certificate_node = signature.find(
        f"{{{DS}}}KeyInfo/{{{DS}}}X509Data/{{{DS}}}X509Certificate"
    )
    if signed_info is None or value_node is None:
        return _unchecked("signature_incomplete")
    if len(etree.tostring(signed_info)) > MAX_SIGNED_INFO_BYTES:
        return _unchecked("signed_info_too_large")
    value_text = "".join((value_node.text or "").split())
    if not value_text or len(value_text) > MAX_SIGNATURE_CHARS:
        return _unchecked("signature_value_unreadable")
    security_code = (
        value_text[:SECURITY_CODE_CHARS]
        if len(value_text) >= SECURITY_CODE_CHARS
        else None
    )
    certificate_text = (
        "".join((certificate_node.text or "").split())
        if certificate_node is not None
        else ""
    )
    if not certificate_text:
        return _unchecked("no_certificate", security_code=security_code or "")
    if len(certificate_text) > MAX_CERTIFICATE_CHARS:
        return _unchecked("certificate_too_large")
    try:
        certificate = x509.load_der_x509_certificate(base64.b64decode(certificate_text))
    except (ValueError, binascii.Error):
        return _unchecked("certificate_unreadable")
    public_key = certificate.public_key()
    if not isinstance(public_key, rsa.RSAPublicKey):
        return SignatureReading(
            "not_checked", "unsupported_key", {}, certificate, security_code
        )
    c14n_node = signed_info.find(f"{{{DS}}}CanonicalizationMethod")
    method_node = signed_info.find(f"{{{DS}}}SignatureMethod")
    references = signed_info.findall(f"{{{DS}}}Reference")
    c14n_algorithm = c14n_node.get("Algorithm", "") if c14n_node is not None else ""
    signature_algorithm = (
        method_node.get("Algorithm", "") if method_node is not None else ""
    )
    if c14n_algorithm not in C14N or signature_algorithm not in SIGNATURES:
        return SignatureReading(
            "not_checked",
            "unsupported_algorithm",
            {"canonicalization": c14n_algorithm, "signature": signature_algorithm},
            certificate,
            security_code,
        )
    if len(references) != 1 or references[0].get("URI", "") != "":
        return SignatureReading(
            "not_checked",
            "reference_unsupported",
            {"references": str(len(references))},
            certificate,
            security_code,
        )
    reference = references[0]
    transforms = [
        node.get("Algorithm", "")
        for node in reference.findall(f"{{{DS}}}Transforms/{{{DS}}}Transform")
    ]
    digest_node = reference.find(f"{{{DS}}}DigestMethod")
    digest_value = reference.find(f"{{{DS}}}DigestValue")
    digest_algorithm = digest_node.get("Algorithm", "") if digest_node is not None else ""
    if (
        ENVELOPED not in transforms
        or any(t != ENVELOPED and t not in C14N for t in transforms)
        or digest_algorithm not in DIGESTS
        or digest_value is None
    ):
        return SignatureReading(
            "not_checked",
            "unsupported_transform",
            {"transforms": " ".join(transforms), "digest": digest_algorithm},
            certificate,
            security_code,
        )
    document_c14n = next((t for t in transforms if t in C14N), c14n_algorithm)
    try:
        digest = DIGESTS[digest_algorithm](
            _without(root, signature, document_c14n)
        ).digest()
    except ValueError:
        return SignatureReading(
            "not_checked", "signature_misplaced", {}, certificate, security_code
        )
    expected = "".join((digest_value.text or "").split())
    if base64.b64encode(digest).decode("ascii") != expected:
        return SignatureReading(
            "failed", "digest_mismatch", {}, certificate, security_code
        )
    try:
        public_key.verify(
            base64.b64decode(value_text),
            _canonical(signed_info, c14n_algorithm),
            padding.PKCS1v15(),
            SIGNATURES[signature_algorithm](),
        )
    except (InvalidSignature, ValueError, binascii.Error):
        return SignatureReading(
            "failed", "signature_invalid", {}, certificate, security_code
        )
    return SignatureReading(
        "verified",
        None,
        {"signature": signature_algorithm, "digest": digest_algorithm},
        certificate,
        security_code,
    )


def _decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _totals_check(document: EcfDocument) -> EcfCheck:
    total = _decimal(document.totals.get("MontoTotal"))
    if total is None:
        return EcfCheck(
            name="totals_arithmetic", state="not_checked", code="totals_missing"
        )
    parts = {name: _decimal(document.totals.get(name)) for name in TOTAL_PARTS}
    if any(
        document.totals.get(name) is not None and value is None
        for name, value in parts.items()
    ):
        return EcfCheck(
            name="totals_arithmetic", state="not_checked", code="totals_unreadable"
        )
    expected = sum((value for value in parts.values() if value is not None), Decimal(0))
    detail = {"monto_total": str(total), "sum_of_parts": str(expected)}
    if expected != total:
        return EcfCheck(
            name="totals_arithmetic",
            state="failed",
            code="totals_mismatch",
            detail=detail,
        )
    amounts = [_decimal(value) for value in document.item_amounts]
    if amounts:
        if any(value is None for value in amounts):
            return EcfCheck(
                name="totals_arithmetic",
                state="not_checked",
                code="totals_unreadable",
                detail=detail,
            )
        taxable = sum(
            (
                value
                for name, value in parts.items()
                if value is not None and name in ("MontoGravadoTotal", "MontoExento")
            ),
            Decimal(0),
        )
        items = sum(amounts, Decimal(0))  # type: ignore[arg-type]
        detail["sum_of_items"] = str(items)
        if items != taxable:
            return EcfCheck(
                name="totals_arithmetic",
                state="failed",
                code="items_mismatch",
                detail=detail,
            )
    return EcfCheck(name="totals_arithmetic", state="verified", detail=detail)


def _issued_on(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return datetime.strptime(value, ISSUED_ON_FORMAT).date().isoformat()
    except ValueError:
        return None


def _read_check(document: EcfDocument, receipt: ReceiptDetails | None) -> EcfCheck:
    if receipt is None:
        return EcfCheck(name="read_matches_xml", state="not_checked", code="no_read")
    pairs = {
        "total": (receipt.total, document.totals.get("MontoTotal"), True),
        "itbis": (receipt.itbis, document.totals.get("TotalITBIS"), True),
        "rnc": (receipt.rnc, document.rnc_emisor, False),
        "ecf": (receipt.ecf, document.encf, False),
        "occurred_on": (
            receipt.occurred_on.isoformat() if receipt.occurred_on else None,
            _issued_on(document.fecha_emision),
            False,
        ),
    }
    compared, differing = {}, []
    for name, (read, stated, numeric) in pairs.items():
        if read is None or stated is None:
            continue
        if numeric:
            same = _decimal(str(read)) is not None and _decimal(str(read)) == _decimal(
                stated
            )
        else:
            same = str(read).strip() == str(stated).strip()
        compared[name] = f"read={read} xml={stated}"
        if not same:
            differing.append(name)
    if not compared:
        return EcfCheck(name="read_matches_xml", state="not_checked", code="no_read")
    if differing:
        return EcfCheck(
            name="read_matches_xml",
            state="failed",
            code="read_differs",
            detail={name: compared[name] for name in differing},
        )
    return EcfCheck(name="read_matches_xml", state="verified", detail=compared)


def _window(certificate: x509.Certificate, at: datetime | None) -> str:
    if at is None:
        return "unknown"
    if at < certificate.not_valid_before_utc:
        return "not_yet_valid"
    if at > certificate.not_valid_after_utc:
        return "expired"
    return "valid"


def _signed_at(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.strptime(value, SIGNED_AT_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _name(name: x509.Name) -> str:
    for oid in (NameOID.COMMON_NAME, NameOID.ORGANIZATION_NAME):
        found = name.get_attributes_for_oid(oid)
        if found:
            return str(found[0].value)
    return name.rfc4514_string()


def _certificate_checks(document: EcfDocument, now: datetime) -> list[EcfCheck]:
    certificate = document.signature.certificate
    if certificate is None:
        missing = document.signature.code or "no_certificate"
        return [
            EcfCheck(name="certificate_validity", state="not_checked", code=missing),
            EcfCheck(name="certificate_issuer", state="not_checked", code=missing),
            EcfCheck(name="subject_rnc", state="not_checked", code=missing),
        ]
    signed_at = _signed_at(document.fecha_hora_firma)
    at_signature, today = _window(certificate, signed_at), _window(certificate, now)
    detail = {
        "not_before": certificate.not_valid_before_utc.date().isoformat(),
        "not_after": certificate.not_valid_after_utc.date().isoformat(),
        "signed_at": document.fecha_hora_firma or "",
        "at_signature": at_signature,
        "today": today,
        "revocation": "not_checked",
    }
    if at_signature == "unknown":
        validity = EcfCheck(
            name="certificate_validity",
            state="not_checked",
            code="signature_time_missing",
            detail=detail,
        )
    elif at_signature != "valid":
        validity = EcfCheck(
            name="certificate_validity",
            state="failed",
            code="certificate_not_valid_at_signature",
            detail=detail,
        )
    else:
        validity = EcfCheck(
            name="certificate_validity",
            state="verified",
            code="revocation_not_checked",
            detail=detail,
        )
    issuer = EcfCheck(
        name="certificate_issuer",
        state="not_checked",
        code="issuer_not_on_trust_list",
        detail={
            "issuer": _name(certificate.issuer),
            "subject": _name(certificate.subject),
        },
    )
    serials = certificate.subject.get_attributes_for_oid(NameOID.SERIAL_NUMBER)
    serial = str(serials[0].value) if serials else None
    digits = "".join(ch for ch in (serial or "") if ch.isdigit())
    if serial is None:
        subject = EcfCheck(
            name="subject_rnc", state="not_checked", code="no_subject_serial"
        )
    elif document.rnc_emisor is None:
        subject = EcfCheck(
            name="subject_rnc",
            state="not_checked",
            code="no_issuer_rnc",
            detail={"subject_serial": serial},
        )
    elif digits == document.rnc_emisor.strip():
        subject = EcfCheck(
            name="subject_rnc",
            state="verified",
            detail={"subject_serial": serial, "rnc_emisor": document.rnc_emisor},
        )
    else:
        subject = EcfCheck(
            name="subject_rnc",
            state="failed",
            code="subject_rnc_differs",
            detail={"subject_serial": serial, "rnc_emisor": document.rnc_emisor},
        )
    return [validity, issuer, subject]


def ecf_checks(
    document: EcfDocument, receipt: ReceiptDetails | None, now: datetime
) -> EcfVerification:
    """Every Tier A check on one e-CF, in the order the record shows them."""

    reading = document.signature
    integrity = EcfCheck(
        name="signature_integrity",
        state=reading.state,  # type: ignore[arg-type]
        code=reading.code,
        detail={k: v for k, v in reading.detail.items() if k != "security_code"},
    )
    security = EcfCheck(
        name="security_code",
        state="not_checked",
        code="no_printed_code"
        if reading.security_code
        else (reading.code or "no_signature"),
        detail={"expected": reading.security_code} if reading.security_code else {},
    )
    checks = [
        integrity,
        _totals_check(document),
        _read_check(document, receipt),
        *_certificate_checks(document, now),
        EcfCheck(name="dgii_accepted", state="not_checked", code="network_not_in_tier_a"),
        security,
    ]
    return EcfVerification(
        encf=document.encf,
        tipo_ecf=document.tipo_ecf,
        checked_at=now,
        checks=tuple(checks),
    )
