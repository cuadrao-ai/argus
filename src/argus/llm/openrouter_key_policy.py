from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Literal

OpenRouterTrafficClass = Literal["guest", "registered"]

_HOSTED_APP_ENVS = frozenset({"production", "staging", "preview"})
_HOSTED_KEY_ENV_BY_TRAFFIC_CLASS: dict[OpenRouterTrafficClass, str] = {
    "guest": "CUADRAO_GUEST_ACCESS_OPENROUTER_API_KEY",
    "registered": "CUADRAO_PROD_OPENROUTER_API_KEY",
}
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
    if not _hosted_environment():
        return os.getenv("OPENROUTER_API_KEY", "").strip()

    resolved_kind = kind or _current_traffic_class.get()
    if resolved_kind is None:
        raise RuntimeError("OpenRouter traffic class is required in hosted environments.")
    env_name = _HOSTED_KEY_ENV_BY_TRAFFIC_CLASS[resolved_kind]
    value = os.getenv(env_name, "").strip()
    if not value:
        raise RuntimeError(f"{env_name} is required in hosted environments.")
    return value


def validate_hosted_openrouter_configuration() -> None:
    if not _hosted_environment():
        return
    registered_key = resolve_openrouter_api_key("registered")
    guest_key = resolve_openrouter_api_key("guest")
    if registered_key == guest_key:
        raise RuntimeError(
            "CUADRAO_PROD_OPENROUTER_API_KEY and "
            "CUADRAO_GUEST_ACCESS_OPENROUTER_API_KEY must use distinct "
            "credentials in hosted environments."
        )


def _hosted_environment() -> bool:
    return os.getenv("APP_ENV", "").strip().lower() in _HOSTED_APP_ENVS
