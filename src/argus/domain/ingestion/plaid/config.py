"""One credential and configuration seam for every Plaid call.

``PLAID_CLIENT_ID`` and ``PLAID_SECRET`` authenticate as request headers and
are never logged, returned or placed in a request body. ``PLAID_ENV`` picks
the host (sandbox by default). ``PLAID_CREDENTIALS_INJECTED`` is an explicit,
sandbox-only opt-in for environments whose egress proxy adds the credential
headers itself; without it, missing credentials keep the connector off rather
than sending unauthenticated requests.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal

PlaidEnvironment = Literal["sandbox", "production"]
HOSTS: dict[str, str] = {
    "sandbox": "https://sandbox.plaid.com",
    "production": "https://production.plaid.com",
}
API_VERSION = "2020-09-14"
# Plaid's CountryCode enum (API 2020-09-14). Structural validation of a config
# value, not an interpretation of text.
SUPPORTED_COUNTRY_CODES: frozenset[str] = frozenset(
    "US GB ES NL FR IE CA DE IT PL DK NO SE EE LT LV PT BE AT FI".split()
)
CLIENT_NAME = "Cuadrao"
_TRUE = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class PlaidConfig:
    environment: PlaidEnvironment = "sandbox"
    client_id: str = field(default="", repr=False)
    secret: str = field(default="", repr=False)
    credentials_injected: bool = False
    webhook_url: str | None = None
    country_codes: tuple[str, ...] = ("US",)

    @property
    def base_url(self) -> str:
        return HOSTS[self.environment]

    @property
    def configured(self) -> bool:
        """Real credentials, or the sandbox-only injected-credential opt-in."""

        if self.client_id and self.secret:
            return True
        return self.credentials_injected and self.environment == "sandbox"

    def auth_headers(self) -> dict[str, str]:
        if self.client_id and self.secret:
            return {"PLAID-CLIENT-ID": self.client_id, "PLAID-SECRET": self.secret}
        return {}


def plaid_config_from_env() -> PlaidConfig:
    environment = os.getenv("PLAID_ENV", "").strip().lower() or "sandbox"
    if environment not in HOSTS:
        raise ValueError("PLAID_ENV must be sandbox or production")
    codes = tuple(
        code.strip().upper()
        for code in os.getenv("PLAID_COUNTRY_CODES", "US").split(",")
        if code.strip()
    ) or ("US",)
    unknown = [code for code in codes if code not in SUPPORTED_COUNTRY_CODES]
    if unknown:
        raise ValueError("PLAID_COUNTRY_CODES lists a country Plaid does not support")
    webhook = os.getenv("PLAID_WEBHOOK_URL", "").strip() or None
    if webhook is not None and not webhook.startswith("https://"):
        raise ValueError("PLAID_WEBHOOK_URL must be an https URL")
    return PlaidConfig(
        environment=environment,  # type: ignore[arg-type]
        client_id=os.getenv("PLAID_CLIENT_ID", "").strip(),
        secret=os.getenv("PLAID_SECRET", "").strip(),
        credentials_injected=os.getenv("PLAID_CREDENTIALS_INJECTED", "").strip().lower()
        in _TRUE,
        webhook_url=webhook,
        country_codes=codes,
    )
