"""A fake signed DGII e-CF for tests: a throwaway RSA key, a self-signed
certificate whose subject serial is the issuer's RNC, and an enveloped XML
signature over the fixture, built the way the verifier reads it. Nothing
here is a real taxpayer, certificate or authority."""

from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID
from lxml import etree

DS = "http://www.w3.org/2000/09/xmldsig#"
C14N = "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"
EXCLUSIVE_C14N = "http://www.w3.org/2001/10/xml-exc-c14n#"
ENVELOPED = "http://www.w3.org/2000/09/xmldsig#enveloped-signature"
RSA_SHA256 = "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
SHA256 = "http://www.w3.org/2001/04/xmlenc#sha256"
FIXTURE = Path(__file__).parent / "document_extraction_fixtures" / "hotel-ecf.xml"
RNC = "131111222"
SIGNED_AT = "09-10-2026 14:05:00"


def fake_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def fake_certificate(
    key: rsa.RSAPrivateKey,
    *,
    rnc: str | None = RNC,
    not_before: datetime | None = None,
    not_after: datetime | None = None,
    issuer: str = "Autoridad Ficticia de Prueba",
) -> x509.Certificate:
    start = not_before or datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = not_after or start + timedelta(days=730)
    attributes = [x509.NameAttribute(NameOID.COMMON_NAME, "Hotel Brisa del Este SRL")]
    if rnc is not None:
        attributes.append(x509.NameAttribute(NameOID.SERIAL_NUMBER, rnc))
    subject = x509.Name(attributes)
    issuer_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer)])
    return (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer_name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(start)
        .not_valid_after(end)
        .sign(key, hashes.SHA256())
    )


def signed_ecf(
    xml: bytes | None = None,
    *,
    key: rsa.RSAPrivateKey | None = None,
    certificate: x509.Certificate | None = None,
    signed_at: str | None = SIGNED_AT,
    sign_with: rsa.RSAPrivateKey | None = None,
    digest_of: bytes | None = None,
    signed_info_c14n: str = C14N,
) -> bytes:
    """The fixture (or ``xml``) with FechaHoraFirma and one enveloped
    signature appended. ``sign_with`` signs with another key than the
    certificate's; ``digest_of`` digests another document than the one
    returned, so the digest no longer matches."""

    key = key or fake_key()
    certificate = certificate or fake_certificate(key)
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    root = etree.fromstring(xml or FIXTURE.read_bytes(), parser)
    namespace = root.nsmap.get(None)
    if signed_at is not None:
        stamp = etree.SubElement(
            root, f"{{{namespace}}}FechaHoraFirma" if namespace else "FechaHoraFirma"
        )
        stamp.text = signed_at
        stamp.tail = "\n"
    digested = (
        etree.tostring(etree.fromstring(digest_of, parser), method="c14n")
        if digest_of is not None
        else etree.tostring(root, method="c14n")
    )
    digest = base64.b64encode(hashlib.sha256(digested).digest()).decode("ascii")
    signature = etree.SubElement(root, f"{{{DS}}}Signature", nsmap={"ds": DS})
    signed_info = etree.SubElement(signature, f"{{{DS}}}SignedInfo")
    etree.SubElement(
        signed_info, f"{{{DS}}}CanonicalizationMethod", Algorithm=signed_info_c14n
    )
    etree.SubElement(signed_info, f"{{{DS}}}SignatureMethod", Algorithm=RSA_SHA256)
    reference = etree.SubElement(signed_info, f"{{{DS}}}Reference", URI="")
    transforms = etree.SubElement(reference, f"{{{DS}}}Transforms")
    etree.SubElement(transforms, f"{{{DS}}}Transform", Algorithm=ENVELOPED)
    etree.SubElement(reference, f"{{{DS}}}DigestMethod", Algorithm=SHA256)
    etree.SubElement(reference, f"{{{DS}}}DigestValue").text = digest
    signer = sign_with or key
    value = signer.sign(
        etree.tostring(
            signed_info, method="c14n", exclusive=signed_info_c14n == EXCLUSIVE_C14N
        ),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    etree.SubElement(signature, f"{{{DS}}}SignatureValue").text = base64.b64encode(
        value
    ).decode("ascii")
    key_info = etree.SubElement(signature, f"{{{DS}}}KeyInfo")
    data = etree.SubElement(key_info, f"{{{DS}}}X509Data")
    etree.SubElement(data, f"{{{DS}}}X509Certificate").text = base64.b64encode(
        certificate.public_bytes(serialization.Encoding.DER)
    ).decode("ascii")
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8")
