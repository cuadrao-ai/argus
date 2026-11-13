from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

OpenRouterTrafficClass = Literal["guest", "registered"]

_HOSTED_APP_ENVS = frozenset({"production", "staging", "preview"})
_LOCAL_APP_ENVS = frozenset({"", "local", "development", "dev", "test", "local-smoke"})


class _KeySettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, hide_input_in_errors=True)

    app_env: str = ""
    render: str = ""
    render_service_id: str = ""
    local_key: SecretStr = Field(
        default=SecretStr(""), validation_alias="OPENROUTER_API_KEY"
    )
    registered_key: SecretStr = Field(
        default=SecretStr(""), validation_alias="CUADRAO_PROD_OPENROUTER_API_KEY"
    )
    guest_key: SecretStr = Field(
        default=SecretStr(""), validation_alias="CUADRAO_GUEST_ACCESS_OPENROUTER_API_KEY"
    )
    dev_key: SecretStr = Field(
        default=SecretStr(""), validation_alias="CUADRAO_OPENROUTER_API_KEY_DEV"
    )
    stg_key: SecretStr = Field(
        default=SecretStr(""), validation_alias="CUADRAO_OPENROUTER_API_KEY_STG"
    )
    prod_key: SecretStr = Field(
        default=SecretStr(""), validation_alias="CUADRAO_OPENROUTER_API_KEY_PROD"
    )

    @property
    def environment(self) -> str:
        return self.app_env.strip().lower()

    def registered(self, *, required: bool) -> str:
        if self.environment in _LOCAL_APP_ENVS:
            if self.render.strip().lower() == "true" or self.render_service_id.strip():
                raise RuntimeError("A hosted APP_ENV is required on a hosted service.")
            suffix, selected, fallback = "DEV", self.dev_key, self.local_key
            fallback_name = "OPENROUTER_API_KEY"
        elif self.environment in {"staging", "preview"}:
            suffix, selected, fallback = "STG", self.stg_key, self.registered_key
            fallback_name = "CUADRAO_PROD_OPENROUTER_API_KEY"
        elif self.environment == "production":
            suffix, selected, fallback = "PROD", self.prod_key, self.registered_key
            fallback_name = "CUADRAO_PROD_OPENROUTER_API_KEY"
        else:
            raise RuntimeError("Unsupported APP_ENV for registered model credentials.")
        value = selected.get_secret_value().strip() or fallback.get_secret_value().strip()
        if required and not value:
            raise RuntimeError(
                f"CUADRAO_OPENROUTER_API_KEY_{suffix} or {fallback_name} is required "
                "for registered traffic."
            )
        return value


MODEL_CREDENTIAL_ENV_NAMES = tuple(
    field.validation_alias
    for field in _KeySettings.model_fields.values()
    if field.annotation is SecretStr
)

_current_traffic_class: ContextVar[OpenRouterTrafficClass | None] = ContextVar(
    "argus_openrouter_traffic_class",
    default=None,
)


@contextmanager
def openrouter_traffic_class(kind: OpenRouterTrafficClass) -> Iterator[None]:
    token = _current_traffic_class.set(kind)
    try:
        yield
    finally:
        _current_traffic_class.reset(token)


def resolve_openrouter_api_key(
    kind: OpenRouterTrafficClass | None = None,
) -> str:
    settings = _KeySettings()
    resolved_kind = kind or _current_traffic_class.get()
    hosted = settings.environment in _HOSTED_APP_ENVS
    if resolved_kind == "guest":
        key = settings.guest_key if hosted else settings.local_key
        value = key.get_secret_value().strip()
        if hosted and not value:
            raise RuntimeError(
                "CUADRAO_GUEST_ACCESS_OPENROUTER_API_KEY is required in hosted environments."
            )
        return value
    if hosted and resolved_kind is None:
        raise RuntimeError("OpenRouter traffic class is required in hosted environments.")
    return settings.registered(required=hosted or resolved_kind == "registered")


def validate_hosted_openrouter_configuration() -> None:
    if not _hosted_environment():
        return
    registered_key = resolve_openrouter_api_key("registered")
    guest_key = resolve_openrouter_api_key("guest")
    if registered_key == guest_key:
        raise RuntimeError(
            "The selected registered credential (CUADRAO_PROD_OPENROUTER_API_KEY fallback) and "
            "CUADRAO_GUEST_ACCESS_OPENROUTER_API_KEY must use distinct "
            "credentials in hosted environments."
        )


def _hosted_environment() -> bool:
    return _KeySettings().environment in _HOSTED_APP_ENVS
