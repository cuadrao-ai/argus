"""Webhook signatures, keyed digests and one-time link codes.

Phone numbers, provider message ids and link codes are only ever stored as
HMAC-SHA256 digests under ``ARGUS_WHATSAPP_SENDER_KEY``. A plain hash of a
phone number is reversible by enumeration; a keyed one is not without the key.
Logs carry ``ref``, a short prefix of a digest, and never the value itself.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

SIGNATURE_PREFIX = "sha256="
LINK_WORD = "CUADRAO"
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTVWXYZ23456789"
CODE_LENGTH = 8
_EDGE_PUNCTUATION = ".,;:!?¡¿()[]\"'*_-"


def signature_matches(app_secret: str, header: str | None, body: bytes) -> bool:
    """``X-Hub-Signature-256`` is HMAC-SHA256 of the raw body under the app secret."""

    if not header or not header.startswith(SIGNATURE_PREFIX):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    supplied = header[len(SIGNATURE_PREFIX) :].strip().lower()
    return hmac.compare_digest(expected.encode(), supplied.encode("utf-8", "replace"))


class WhatsAppKeys:
    def __init__(self, sender_key: str) -> None:
        self._key = sender_key.encode()

    def _digest(self, domain: str, value: str) -> bytes:
        return hmac.new(
            self._key, f"argus-whatsapp-{domain}:v1:{value}".encode(), hashlib.sha256
        ).digest()

    def sender(self, wa_id: str) -> bytes:
        return self._digest("sender", wa_id)

    def message(self, provider_message_id: str) -> bytes:
        return self._digest("message", provider_message_id)

    def code(self, code: str) -> bytes:
        return self._digest("link-code", code)


def ref(digest: bytes) -> str:
    return digest.hex()[:12]


def last4(wa_id: str) -> str:
    return wa_id[-4:]


def mint_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def link_message(code: str) -> str:
    return f"{LINK_WORD} {code}"


def code_candidates(text: str, *, limit: int = 4) -> tuple[str, ...]:
    """Tokens in ``text`` shaped like a link code, upper-cased, in order.

    This is structure, not language: a code is ``CODE_LENGTH`` characters from
    ``CODE_ALPHABET``. Whether a candidate is a real code is decided only by the
    digest lookup, and only for a sender with no active link.
    """

    found: list[str] = []
    for token in text.split():
        candidate = token.strip(_EDGE_PUNCTUATION).upper()
        if (
            len(candidate) == CODE_LENGTH
            and all(ch in CODE_ALPHABET for ch in candidate)
            and candidate not in found
        ):
            found.append(candidate)
    return tuple(found[:limit])
