from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Literal

from loguru import logger

OpenRouterTrafficClass = Literal["guest", "registered"]

_HOSTED_APP_ENVS = frozenset({"production", "staging", "preview"})
_LOCAL_KEY_CANDIDATES = (
    "CUADRAO_OPENROUTER_API_KEY_DEV",
    "OPENROUTER_API_KEY",
)
_GUEST_KEY_CANDIDATES = ("ARGUS_GUEST_ACCESS_OPENROUTER_API_KEY",)
_REGISTERED_KEY_CANDIDATES = {
    "production": (
        "CUADRAO_OPENROUTER_API_KEY_PROD",
        "ARGUS_PROD_OPENROUTER_API_KEY",
    ),
    "staging": (
        "CUADRAO_OPENROUTER_API_KEY_STG",
        "ARGUS_PROD_OPENROUTER_API_KEY",
    ),
    "preview": ("ARGUS_PROD_OPENROUTER_API_KEY",),
}
_current_traffic_class: ContextVar[OpenRouterTrafficClass | None] = ContextVar(
    "argus_openrouter_traffic_class",
    default=None,
)
_selected_key_names: dict[str, str] = {}


@contextmanager
def openrouter_traffic_class(kind: OpenRouterTrafficClass) -> Iterator[None]:
    token = _current_traffic_class.set(kind)
    try:
        yield
    finally:
        _current_traffic_class.reset(token)


def openrouter_key_candidates(
    app_env: str,
    kind: OpenRouterTrafficClass | None,
) -> tuple[str, ...]:
    normalized = app_env.strip().lower()
    if normalized not in _HOSTED_APP_ENVS:
        return _LOCAL_KEY_CANDIDATES
    if kind == "guest":
        return _GUEST_KEY_CANDIDATES
    return _REGISTERED_KEY_CANDIDATES[normalized]


def resolve_openrouter_api_key(
    kind: OpenRouterTrafficClass | None = None,
) -> str:
    app_env = os.getenv("APP_ENV", "")
    hosted = app_env.strip().lower() in _HOSTED_APP_ENVS
    resolved_kind = kind or _current_traffic_class.get()
    if hosted and resolved_kind is None:
        raise RuntimeError("OpenRouter traffic class is required in hosted environments.")
    names = openrouter_key_candidates(app_env, resolved_kind)
    selected = _first_set_key(names)
    if selected is None:
        if not hosted:
            return ""
        raise RuntimeError(
            f"{', '.join(names)} is required in hosted environments."
        )
    key_name, value = selected
    _log_selected_key(resolved_kind or "local", key_name)
    return value


def validate_hosted_openrouter_configuration() -> None:
    if not _hosted_environment():
        return
    registered_key = resolve_openrouter_api_key("registered")
    guest_key = resolve_openrouter_api_key("guest")
    if registered_key == guest_key:
        raise RuntimeError(
            "ARGUS_PROD_OPENROUTER_API_KEY and "
            "ARGUS_GUEST_ACCESS_OPENROUTER_API_KEY must use distinct "
            "credentials in hosted environments."
        )


def _hosted_environment() -> bool:
    return os.getenv("APP_ENV", "").strip().lower() in _HOSTED_APP_ENVS


def _first_set_key(names: tuple[str, ...]) -> tuple[str, str] | None:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return name, value
    return None


def _log_selected_key(traffic_class: str, key_name: str) -> None:
    if _selected_key_names.get(traffic_class) == key_name:
        return
    _selected_key_names[traffic_class] = key_name
    logger.info(
        "openrouter_key_selected traffic_class={} key_name={}",
        traffic_class,
        key_name,
    )
