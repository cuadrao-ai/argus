"""Apple client-secret inputs, read from the environment.

``CUADRAO_APPLE_TEAM_ID`` and ``CUADRAO_APPLE_SIGN_IN_KEY_ID`` are the 10-character
Apple Developer team and key ids. ``CUADRAO_APPLE_SIGN_IN_PRIVATE_KEY`` is the
contents of the ``.p8`` key file (PEM; literal ``\\n`` escapes are accepted for
single-line secret stores). ``CUADRAO_APPLE_BUNDLE_ID`` is the native app's
bundle id, the Apple client that issues the authorization codes the app sends.

The key is a secret and lives only in the deployment's environment. A missing
or malformed value raises ``AppleSignInUnconfigured``; nothing falls back.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import load_pem_private_key

TEAM_ID_ENV = "CUADRAO_APPLE_TEAM_ID"
KEY_ID_ENV = "CUADRAO_APPLE_SIGN_IN_KEY_ID"
PRIVATE_KEY_ENV = "CUADRAO_APPLE_SIGN_IN_PRIVATE_KEY"
BUNDLE_ID_ENV = "CUADRAO_APPLE_BUNDLE_ID"

ISSUER = "https://appleid.apple.com"
TOKEN_URL = "https://appleid.apple.com/auth/token"
REVOKE_URL = "https://appleid.apple.com/auth/revoke"

_APPLE_ID = re.compile(r"^[A-Z0-9]{10}$")
_CLIENT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,154}$")


class AppleSignInUnconfigured(RuntimeError):
    """A client-secret input is missing or malformed; Apple calls stay off."""


@dataclass(frozen=True)
class AppleSignInConfig:
    team_id: str
    key_id: str
    client_id: str
    private_key: ec.EllipticCurvePrivateKey = field(repr=False)

    @classmethod
    def from_env(cls) -> AppleSignInConfig:
        team_id = os.getenv(TEAM_ID_ENV, "").strip()
        key_id = os.getenv(KEY_ID_ENV, "").strip()
        client_id = os.getenv(BUNDLE_ID_ENV, "").strip()
        pem = os.getenv(PRIVATE_KEY_ENV, "").strip().replace("\\n", "\n")
        if not _APPLE_ID.match(team_id):
            raise AppleSignInUnconfigured(f"{TEAM_ID_ENV} is missing or malformed")
        if not _APPLE_ID.match(key_id):
            raise AppleSignInUnconfigured(f"{KEY_ID_ENV} is missing or malformed")
        if not _CLIENT_ID.match(client_id) or "." not in client_id:
            raise AppleSignInUnconfigured(f"{BUNDLE_ID_ENV} is missing or malformed")
        return cls(
            team_id=team_id,
            key_id=key_id,
            client_id=client_id,
            private_key=load_private_key(pem),
        )


def load_private_key(pem: str) -> ec.EllipticCurvePrivateKey:
    """Apple Sign in with Apple keys are P-256 (ES256). Anything else is refused."""

    if not pem:
        raise AppleSignInUnconfigured(f"{PRIVATE_KEY_ENV} is not configured")
    try:
        key = load_pem_private_key(pem.encode(), password=None)
    except (TypeError, ValueError):
        raise AppleSignInUnconfigured(f"{PRIVATE_KEY_ENV} is not a PEM key") from None
    if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(
        key.curve, ec.SECP256R1
    ):
        raise AppleSignInUnconfigured(f"{PRIVATE_KEY_ENV} is not a P-256 key")
    return key
