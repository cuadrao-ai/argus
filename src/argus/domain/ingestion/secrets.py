"""Provider credentials at rest: one key, one envelope, bound to its connection.

Plaid access tokens, Google refresh tokens and Sign in with Apple refresh
tokens (``argus.domain.apple_sign_in``) are server-side only. They are
sealed with AES-256-GCM under ``ARGUS_INGESTION_SECRET_KEY`` (32 random bytes,
URL-safe base64) and the associated data binds each ciphertext to its
``source:connection_id``, so a row copied onto another connection fails to
open. Plaintext never leaves the adapter call that needs it and is never
logged, returned by an API, or stored elsewhere.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from argus.settings_names import setting_value

KEY_ENV = "CUADRAO_INGESTION_SECRET_KEY"
_VERSION = b"\x01"
_NONCE_BYTES = 12
_KEY_ID_LABEL = b"argus-ingestion-key-id:v1"


class SecretBoxUnavailable(RuntimeError):
    """No usable key: connectors that need stored credentials stay off."""


class SecretUnreadable(RuntimeError):
    """Ciphertext is not for this connection, or the key changed."""


class SecretBox:
    def __init__(self, key: bytes) -> None:
        if len(key) != 32:
            raise SecretBoxUnavailable("ingestion secret key must be 32 bytes")
        self._aead = AESGCM(key)
        self._key = key

    @classmethod
    def from_env(cls) -> SecretBox:
        raw = (setting_value("INGESTION_SECRET_KEY") or "").strip()
        if not raw:
            raise SecretBoxUnavailable(f"{KEY_ENV} is not configured")
        try:
            key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
        except (binascii.Error, ValueError):
            raise SecretBoxUnavailable(f"{KEY_ENV} is not base64") from None
        return cls(key)

    @property
    def key_id(self) -> str:
        """Non-secret fingerprint of this key, stored next to every envelope it
        seals (``secret_key_fingerprint``): an HMAC-SHA256 of a fixed label
        under the key, truncated to 128 bits. It names which key sealed a row
        without revealing anything about the key, so account deletion can tell
        "sealed under the key I hold, and it still doesn't open" (dead) from
        "sealed under some other key" (keep it: Lane 6)."""

        return hmac.new(self._key, _KEY_ID_LABEL, hashlib.sha256).hexdigest()[:32]

    def seal(self, plaintext: str, *, source: str, connection_id: str) -> bytes:
        nonce = secrets.token_bytes(_NONCE_BYTES)
        sealed = self._aead.encrypt(
            nonce, plaintext.encode(), _aad(source, connection_id)
        )
        return _VERSION + nonce + sealed

    def open(self, envelope: bytes, *, source: str, connection_id: str) -> str:
        if len(envelope) <= 1 + _NONCE_BYTES or envelope[:1] != _VERSION:
            raise SecretUnreadable("unknown credential envelope")
        nonce = envelope[1 : 1 + _NONCE_BYTES]
        try:
            plain = self._aead.decrypt(
                nonce, envelope[1 + _NONCE_BYTES :], _aad(source, connection_id)
            )
        except InvalidTag:
            raise SecretUnreadable(
                "credential does not open for this connection"
            ) from None
        return plain.decode()

    def digest(self, value: str, *, purpose: str) -> str:
        """Keyed, purpose-separated digest for identifiers that must be
        matched but never stored readable (a mailbox address). Not for
        secrets that need to be opened again."""

        subkey = hmac.new(
            self._key, f"argus-ingestion-digest:{purpose}".encode(), hashlib.sha256
        ).digest()
        return hmac.new(subkey, value.encode(), hashlib.sha256).hexdigest()


def _aad(source: str, connection_id: str) -> bytes:
    return f"argus-ingestion:{source}:{connection_id}".encode()
