from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar

from argus.llm.openrouter_tasks import OpenRouterTask

RequestGuard = Callable[[OpenRouterTask, dict[str, object]], dict[str, object]]
_REQUEST_GUARDS: ContextVar[tuple[tuple[RequestGuard, bool], ...]] = ContextVar(
    "openrouter_request_guards", default=()
)


@contextmanager
def openrouter_request_guard(
    guard: RequestGuard, *, final: bool = False
) -> Iterator[None]:
    token = _REQUEST_GUARDS.set((*_REQUEST_GUARDS.get(), (guard, final)))
    try:
        yield
    finally:
        _REQUEST_GUARDS.reset(token)


def guard_openrouter_request(
    task: OpenRouterTask, payload: dict[str, object]
) -> dict[str, object]:
    guards = _REQUEST_GUARDS.get()
    for final in (False, True):
        for guard, is_final in guards:
            if is_final == final:
                payload = guard(task, payload)
    return payload


def openrouter_payload_route(payload: Mapping[str, object]) -> dict[str, object]:
    route = {"model": payload.get("model"), "provider": payload.get("provider")}
    for key in ("models", "route", "plugins"):
        if key in payload:
            route[key] = payload[key]
    return json.loads(json.dumps(route))


def validate_openrouter_route(
    payload: Mapping[str, object], routes: Sequence[Mapping[str, object]]
) -> None:
    if openrouter_payload_route(payload) not in routes:
        raise PermissionError("openrouter_consent_route_changed")
