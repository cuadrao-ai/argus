from __future__ import annotations

import hashlib
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from .contracts import Case

API_ORIGIN = "https://sandbox.alanube.co/dom/v1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CUADRAO_FISCAL_SANDBOX_", extra="ignore"
    )
    enabled: bool = False
    contact_enabled: bool = False
    business_id: str = ""
    manifest_path: str = ""
    manifest_sha256: str = ""
    api_token: SecretStr = SecretStr("")
    callback_secret: SecretStr = SecretStr("")
    poll_seconds: int = Field(default=30, ge=5, le=300)
    poll_limit: int = Field(default=5, ge=1, le=10)
    # Deployment installs exact observed hosts; wildcards are not supported.
    storage_host: str = ""
    storage_path_prefix: str = ""

    def cases(self) -> dict[str, Case]:
        import json

        if not self.enabled:
            return {}
        if not all(
            (
                self.business_id,
                self.manifest_path,
                self.manifest_sha256,
                self.api_token.get_secret_value(),
                self.callback_secret.get_secret_value(),
                self.storage_host,
                self.storage_path_prefix,
            )
        ):
            raise ValueError("fiscal_configuration_incomplete")
        raw = Path(self.manifest_path).read_bytes()
        if len(raw) > 65536 or hashlib.sha256(raw).hexdigest() != self.manifest_sha256:
            raise ValueError("fiscal_manifest_digest")
        cases = [Case.model_validate(item) for item in json.loads(raw)]
        if not 1 <= len(cases) <= 2 or any(
            str(c.business_id) != self.business_id for c in cases
        ):
            raise ValueError("fiscal_manifest_scope")
        identities = {(c.account_key, c.company_id, c.issuer) for c in cases}
        if len(identities) != 1 or len({c.case_id for c in cases}) != len(cases):
            raise ValueError("fiscal_manifest_alias")
        return {c.case_id: c for c in cases}
