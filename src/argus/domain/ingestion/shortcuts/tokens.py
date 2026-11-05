"""Device tokens: shown once, kept only as a digest, checked in constant time.

A token is ``sct1.<device id>.<secret>``. The device id is the connection's
``external_ref`` and lets the server find the one candidate row without a
scan; the 256-bit secret is what proves possession. Only SHA-256 of the whole
token is stored. With a 256-bit random secret a keyed hash adds nothing an
attacker could not already brute-force, and nothing here ever needs the token
back, so it is not sealed with the ``SecretBox``.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass

PREFIX = "sct1"
_DEVICE_ID_BYTES = 16
_SECRET_BYTES = 32
_MAX_TOKEN_LENGTH = 128
_DIGEST_DOMAIN = b"argus-shortcuts-device-token:v1:"


@dataclass(frozen=True)
class MintedToken:
    device_id: str
    token: str
    digest: bytes

    def __repr__(self) -> str:  # never let the token reach a log line
        return f"MintedToken(device_id={self.device_id!r}, token=<redacted>)"


def mint() -> MintedToken:
    device_id = secrets.token_hex(_DEVICE_ID_BYTES)
    secret = secrets.token_urlsafe(_SECRET_BYTES)
    token = f"{PREFIX}.{device_id}.{secret}"
    return MintedToken(device_id=device_id, token=token, digest=digest(token))


def digest(token: str) -> bytes:
    return hashlib.sha256(_DIGEST_DOMAIN + token.encode()).digest()


def device_id_of(token: str | None) -> str | None:
    """The device id a well-formed token names; ``None`` for anything else."""

    if not token or len(token) > _MAX_TOKEN_LENGTH or not token.isascii():
        return None
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != PREFIX:
        return None
    device_id, secret = parts[1], parts[2]
    if len(device_id) != 2 * _DEVICE_ID_BYTES or not _is_hex(device_id):
        return None
    if len(secret) < 40:
        return None
    return device_id


def matches(token: str, stored: bytes | None) -> bool:
    """Constant-time comparison; a missing row still costs one comparison."""

    expected = stored if stored is not None else b"\x00" * 32
    return hmac.compare_digest(digest(token), expected) and stored is not None


def bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, value = authorization.strip().partition(" ")
    if scheme.lower() != "bearer":
        return None
    value = value.strip()
    return value or None


def _is_hex(value: str) -> bool:
    return all(c in "0123456789abcdef" for c in value)
