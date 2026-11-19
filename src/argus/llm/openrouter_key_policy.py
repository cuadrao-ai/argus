from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Literal, NoReturn

from loguru import logger
from pydantic import Field, SecretStr, create_model
from pydantic_settings import BaseSettings, SettingsConfigDict

OpenRouterTrafficClass = Literal["registered"]

_NAME_BY_APP_ENV: dict[str, str] = {
    **dict.fromkeys(
        ("", "local", "development", "dev", "test", "local-smoke"),
        "CUADRAO_OPENROUTER_API_KEY_DEV",
    ),
    **dict.fromkeys(("staging", "preview"), "CUADRAO_OPENROUTER_API_KEY_STG"),
    "production": "CUADRAO_OPENROUTER_API_KEY_PROD",
}
_LOCAL_NAME = _NAME_BY_APP_ENV[""]

MODEL_CREDENTIAL_ENV_NAMES: tuple[str, ...] = tuple(
    dict.fromkeys(_NAME_BY_APP_ENV.values())
)
# No code reads these. A hosted service that still holds one is told to delete it.
RETIRED_MODEL_CREDENTIAL_ENV_NAMES: tuple[str, ...] = (
    "OPENROUTER_API_KEY",
    "CUADRAO_PROD_OPENROUTER_API_KEY",
    "CUADRAO_GUEST_ACCESS_OPENROUTER_API_KEY",
    "ARGUS_PROD_OPENROUTER_API_KEY",
    "ARGUS_GUEST_ACCESS_OPENROUTER_API_KEY",
)


class _Environment(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, hide_input_in_errors=True)

    app_env: str = ""
    render: str = ""
    render_service_id: str = ""


_Credentials = create_model(  # type: ignore[call-overload]
    "_Credentials",
    __base__=_Environment,
    **{
        name.lower(): (SecretStr, Field(default=SecretStr(""), validation_alias=name))
        for name in (*MODEL_CREDENTIAL_ENV_NAMES, *RETIRED_MODEL_CREDENTIAL_ENV_NAMES)
    },
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


def model_credential_env_name(app_env: str) -> str:
    try:
        return _NAME_BY_APP_ENV[app_env.strip().lower()]
    except KeyError:
        raise RuntimeError("Unsupported APP_ENV for model credentials.") from None


def _selected() -> tuple[str, dict[str, str]]:
    settings = _Credentials()
    name = model_credential_env_name(settings.app_env)
    on_host = settings.render.strip().lower() == "true" or bool(
        settings.render_service_id.strip()
    )
    if name == _LOCAL_NAME and on_host:
        raise RuntimeError("A hosted APP_ENV is required on a hosted service.")
    held = {
        field.validation_alias: value
        for attribute, field in _Credentials.model_fields.items()
        if isinstance(secret := getattr(settings, attribute), SecretStr)
        and (value := secret.get_secret_value().strip())
    }
    return name, held


def resolve_openrouter_api_key(
    kind: OpenRouterTrafficClass | None = None,
) -> str:
    name, held = _selected()
    hosted = name != _LOCAL_NAME
    resolved_kind = kind or _current_traffic_class.get()
    if hosted and resolved_kind is None:
        raise RuntimeError("OpenRouter traffic class is required in hosted environments.")
    value = held.get(name, "")
    if not value and (hosted or resolved_kind == "registered"):
        raise RuntimeError(f"{name} is required for registered traffic.")
    return value


def validate_hosted_openrouter_configuration() -> None:
    name, held = _selected()
    if name == _LOCAL_NAME:
        return
    other_environments = sorted(set(held) & set(MODEL_CREDENTIAL_ENV_NAMES) - {name})
    if name not in held:
        _refuse(f"{name} is required on this service.")
    if other_environments:
        _refuse(
            f"This service reads only {name}. Remove {', '.join(other_environments)}."
        )
    for leftover in sorted(set(held) & set(RETIRED_MODEL_CREDENTIAL_ENV_NAMES)):
        logger.warning("retired_model_credential_setting{{name={}}}", leftover)


def _refuse(reason: str) -> NoReturn:
    logger.error("startup_config_refused{{reason={}}}", reason)
    raise RuntimeError(reason)
