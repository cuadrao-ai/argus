"""One configuration seam for the Gmail connector.

``GOOGLE_OAUTH_CLIENT_ID``, ``GOOGLE_OAUTH_CLIENT_SECRET`` and
``GOOGLE_OAUTH_REDIRECT_URI`` describe the founder's Google Cloud OAuth web
client. Gmail stays off unless all three are set. The client secret is sent
only in token-endpoint request bodies and is never logged or returned.

The redirect URI is a page of the web app: Google sends the browser there with
``code`` and ``state``, and the app posts both to the authenticated callback
route, so the exchange always happens under the person's own session.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from argus.domain.ingestion.secrets import SecretBox

# The narrowest Gmail scope that can read message bodies and attachments.
# No ``openid email``: users.getProfile returns the address under this scope.
SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
DEFAULT_LOOKBACK_DAYS = 90
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1"})


@dataclass(frozen=True)
class GmailConfig:
    client_id: str = ""
    client_secret: str = field(default="", repr=False)
    redirect_uri: str = ""
    lookback_days: int = DEFAULT_LOOKBACK_DAYS

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.redirect_uri)


def gmail_config_from_env() -> GmailConfig:
    redirect = os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "").strip()
    if redirect:
        parts = urlsplit(redirect)
        secure = parts.scheme == "https" or (
            parts.scheme == "http" and parts.hostname in _LOCAL_HOSTS
        )
        if not secure or not parts.hostname or parts.fragment:
            raise ValueError(
                "GOOGLE_OAUTH_REDIRECT_URI must be an https URL (http only for localhost)"
            )
    return GmailConfig(
        client_id=os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip(),
        client_secret=os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "").strip(),
        redirect_uri=redirect,
    )


def normalize_address(address: str) -> str:
    return address.strip().lower()


def mailbox_ref(address: str, box: SecretBox) -> str:
    """Keyed digest of the mailbox: stable, comparable, not reversible by
    guessing addresses without the server key."""

    return "gm_" + box.digest(normalize_address(address), purpose="gmail_mailbox")


def masked_label(address: str) -> str:
    """``j***@gmail.com``: enough for the person to recognize the mailbox."""

    local, _, domain = normalize_address(address).partition("@")
    head = local[:1] or "*"
    return f"{head}***@{domain}"[:80]
