"""The ES256 JWT Apple accepts as ``client_secret``.

Apple's token and revoke endpoints authenticate the client with a JWT signed by
the team's Sign in with Apple key: header ``alg=ES256`` and ``kid`` (key id);
claims ``iss`` (team id), ``iat``, ``exp`` (at most six months later),
``aud=https://appleid.apple.com`` and ``sub`` (the client id). A fresh,
five-minute secret is minted per call, so a leaked one is short-lived and no
secret is cached.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from argus.domain.apple_sign_in.config import ISSUER, AppleSignInConfig

LIFETIME = timedelta(minutes=5)


def client_secret(
    config: AppleSignInConfig,
    *,
    client_id: str | None = None,
    now: datetime | None = None,
) -> str:
    """``client_id`` defaults to the configured native client; revocation
    passes the client the stored token was issued to."""

    issued = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    issued_at = int(issued.timestamp())
    return jwt.encode(
        {
            "iss": config.team_id,
            "iat": issued_at,
            "exp": issued_at + int(LIFETIME.total_seconds()),
            "aud": ISSUER,
            "sub": client_id or config.client_id,
        },
        config.private_key,
        algorithm="ES256",
        headers={"kid": config.key_id},
    )
