"""In-app DKIM. The webhook does not carry authentication results.

SPF needs the connecting address, which this path does not have, so SPF does
not pass. A missing signature is unknown. A signature that does not verify, or
whose d= domain is not the From domain, is failed. Keys come from the caller.
This module does not query DNS.
"""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Callable
from email.utils import getaddresses, parseaddr

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

KeyLookup = Callable[[str, str], bytes | None]


def bare_address(value: str | None) -> str | None:
    if not value:
        return None
    address = parseaddr(value)[1].strip().lower()
    if "@" in address and " " not in address:
        return address
    return None


def from_address(raw: bytes) -> str | None:
    _headers, _body = _split(raw)
    for name, value in _parse_headers(_headers):
        if name.lower() == "from":
            address = bare_address(value)
            if address is not None:
                return address
    return None


def ambiguous_from(raw: bytes) -> bool:
    headers, _body = _split(raw)
    header_count = 0
    addresses: list[str] = []
    for name, value in _parse_headers(headers):
        if name.lower() != "from":
            continue
        header_count += 1
        for _display, address in getaddresses([value]):
            cleaned = address.strip().lower()
            if cleaned:
                addresses.append(cleaned)
    return header_count > 1 or len(addresses) > 1


def from_domain(raw: bytes) -> str | None:
    address = from_address(raw)
    if address is None:
        return None
    return address.rsplit("@", 1)[1]


def provider_verdict(
    authentication: dict | None,
    *,
    raw: bytes | None = None,
    provider_from: str | None = None,
) -> str:
    """Map provider authentication and the stored From to one verdict.

    - ``ambiguous``: ``raw`` has more than one From header or address, a
      malformed ``From :`` header, or a provider From that is missing or not
      the stored From. Checked first, whatever the authentication says.
    - ``no_result``: the provider gave no authentication result at all. The
      block is null or absent, or every one of ``spf``, ``dkim`` and ``dmarc``
      is missing, null or ``processing_failed``.
    - ``aligned``: ``dmarc`` pass, or ``dmarc`` neither pass nor fail and
      ``dkim`` pass.
    - ``failed``: ``dmarc`` fail, or ``dmarc`` neither pass nor fail and
      ``dkim`` fail.
    - ``none``: a result came back but neither DMARC nor DKIM passed or failed
      (``gray``, ``unknown``, ``processing_failed`` or missing on both, with
      at least one field holding a real value). Typically the sender's domain
      has no DMARC policy and the mail has no DKIM signature of its own.

    SPF is never a pass, only evidence that a result came back.
    """

    if raw is not None and (
        ambiguous_from(raw) or _preview_from_differs(provider_from, raw)
    ):
        return "ambiguous"
    if not isinstance(authentication, dict) or all(
        authentication.get(field) in (None, "processing_failed")
        for field in ("spf", "dkim", "dmarc")
    ):
        return "no_result"
    dmarc = authentication.get("dmarc")
    dkim = authentication.get("dkim")
    if dmarc == "pass":
        return "aligned"
    if dmarc == "fail":
        return "failed"
    if dkim == "pass":
        return "aligned"
    if dkim == "fail":
        return "failed"
    return "none"


def _preview_from_differs(provider_from: str | None, raw: bytes) -> bool:
    reported = bare_address(provider_from) if isinstance(provider_from, str) else None
    return reported is None or reported != from_address(raw)


def assess(raw: bytes, keys: KeyLookup) -> str:
    domain = from_domain(raw)
    signatures = [header for header in _parse_headers(_split(raw)[0]) if header[0].lower() == "dkim-signature"]
    if not signatures:
        return "unknown"
    for _name, value in signatures:
        checked = _verify_one(raw, value, keys)
        if checked == "aligned" and domain is not None:
            return "aligned"
        if checked == "verified-other":
            return "failed"
    return "failed"


def sign_relaxed(
    raw: bytes, private_key: RSAPrivateKey, *, domain: str, selector: str
) -> tuple[bytes, bytes]:
    public = private_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    signed = _sign(raw, private_key, domain=domain, selector=selector)
    return signed, public


def _sign(raw: bytes, private_key: RSAPrivateKey, *, domain: str, selector: str) -> bytes:
    headers, body = _split(raw)
    parsed = _parse_headers(headers)
    names = []
    chosen = []
    for name, value in parsed:
        lowered = name.lower()
        if lowered in {"from", "to", "subject", "date"} and lowered not in names:
            names.append(lowered)
            chosen.append((lowered, value))
    if "from" not in names:
        raise ValueError("dkim_from_required")
    body_hash = base64.b64encode(hashlib.sha256(_canonical_body(body)).digest()).decode()
    signed_names = ":".join(names)
    unsigned = (
        f"v=1; a=rsa-sha256; c=relaxed/relaxed; d={domain}; s={selector}; "
        f"h={signed_names}; bh={body_hash}; b="
    )
    data = _signed_header_bytes(chosen, unsigned)
    signature = base64.b64encode(
        private_key.sign(data, padding.PKCS1v15(), hashes.SHA256())
    ).decode()
    line = f"DKIM-Signature: {unsigned}{signature}"
    newline = b"\r\n" if raw.startswith(headers) and b"\r\n" in raw else b"\n"
    return line.encode() + newline + raw


def _verify_one(raw: bytes, value: str, keys: KeyLookup) -> str:
    tags = _tags(value)
    if tags.get("v", "1") != "1" or tags.get("a") != "rsa-sha256":
        return "failed"
    if tags.get("c", "simple/simple") != "relaxed/relaxed":
        return "failed"
    domain = tags.get("d", "")
    selector = tags.get("s", "")
    signed_names = [item for item in tags.get("h", "").split(":") if item]
    body_hash = tags.get("bh", "")
    signature = tags.get("b", "")
    if not domain or not selector or not signed_names or not body_hash or not signature:
        return "failed"
    headers, body = _split(raw)
    if base64.b64encode(hashlib.sha256(_canonical_body(body)).digest()).decode() != body_hash:
        return "failed"
    parsed = _parse_headers(headers)
    chosen = []
    for signed in signed_names:
        found = next((value for name, value in parsed if name.lower() == signed), None)
        if found is None:
            return "failed"
        chosen.append((signed, found))
    unsigned = _empty_b(value)
    pem = keys(domain, selector)
    if not pem:
        return "failed"
    try:
        public = serialization.load_pem_public_key(pem)
        public.verify(
            base64.b64decode(signature),
            _signed_header_bytes(chosen, unsigned),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except Exception:
        return "failed"
    sender = from_domain(raw)
    if sender is not None and sender == domain.lower():
        return "aligned"
    return "verified-other"


def _signed_header_bytes(chosen: list[tuple[str, str]], signature_value: str) -> bytes:
    lines = [_relax(name, value) for name, value in chosen]
    lines.append(_relax("dkim-signature", signature_value))
    return ("\r\n".join(lines)).encode()


def _relax(name: str, value: str) -> str:
    return f"{name.lower()}:{' '.join(value.split())}"


def _empty_b(value: str) -> str:
    tags = _tags(value)
    tags["b"] = ""
    order = [key for key in ("v", "a", "c", "d", "s", "h", "bh", "b") if key in tags]
    rendered = []
    for key in order:
        rendered.append(f"{key}={tags[key]}" if key != "b" else "b=")
    return "; ".join(rendered)


def _tags(value: str) -> dict[str, str]:
    found = {}
    for part in value.split(";"):
        if "=" not in part:
            continue
        key, raw = part.split("=", 1)
        found[key.strip().lower()] = "".join(raw.split())
    return found


def _canonical_body(body: bytes) -> bytes:
    text = body.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    lines = [_relax_line(line) for line in text.split(b"\n")]
    while lines and lines[-1] == b"":
        lines.pop()
    if not lines:
        return b"\r\n"
    return b"\r\n".join(lines) + b"\r\n"


def _relax_line(line: bytes) -> bytes:
    line = line.replace(b"\t", b" ")
    while b"  " in line:
        line = line.replace(b"  ", b" ")
    return line.rstrip(b" ")


def _split(raw: bytes) -> tuple[bytes, bytes]:
    for separator in (b"\r\n\r\n", b"\n\n"):
        if separator in raw:
            head, body = raw.split(separator, 1)
            return head, body
    return raw, b""


def _parse_headers(head: bytes) -> list[tuple[str, str]]:
    text = head.replace(b"\r\n", b"\n").replace(b"\r", b"\n").decode("utf-8", "replace")
    headers: list[tuple[str, str]] = []
    name: str | None = None
    value: list[str] = []
    for line in text.split("\n"):
        if name and line.startswith((" ", "\t")):
            value.append(line)
            continue
        if ":" in line:
            if name:
                headers.append((name, "".join(value)))
            name, first = line.split(":", 1)
            name = name.strip()
            value = [first]
    if name:
        headers.append((name, "".join(value)))
    return headers
