"""Verify Svix signatures against unchanged request bytes before decoding JSON."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
from collections.abc import Mapping


class WebhookSignatureError(ValueError):
    pass


def verify_webhook(
    body: bytes, headers: Mapping[str, str], secret: str, now: float
) -> None:
    normalized = {key.lower(): value for key, value in headers.items()}
    try:
        message_id = normalized["svix-id"]
        timestamp = normalized["svix-timestamp"]
        signatures = normalized["svix-signature"]
        if not message_id or len(message_id) > 256 or len(signatures) > 4096:
            raise ValueError
        if not timestamp.isascii() or not timestamp.isdecimal() or len(timestamp) > 12:
            raise ValueError
        if abs(now - int(timestamp)) > 300:
            raise ValueError
        encoded_key = secret.removeprefix("whsec_")
        key = base64.b64decode(encoded_key, validate=True)
        if not key:
            raise ValueError
        content = f"{message_id}.{timestamp}.".encode("utf-8") + body
        expected = hmac.digest(key, content, hashlib.sha256)
        matched = False
        for signature in signatures.split():
            version, separator, encoded = signature.partition(",")
            if version != "v1" or not separator:
                continue
            try:
                candidate = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error):
                continue
            matched |= hmac.compare_digest(expected, candidate)
        if not matched:
            raise ValueError
    except (KeyError, ValueError, UnicodeError, binascii.Error):
        raise WebhookSignatureError("invalid_webhook_signature") from None
