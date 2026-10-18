from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

import httpx

LOGIN_PROVIDER_TIMEOUT_SECONDS = 30.0


class CaptchaVerificationError(Exception):
    pass


def _provider_verification_failed(exc: BaseException) -> bool:
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if getattr(current, "code", None) == "captcha_failed":
            return True
        if isinstance(current, httpx.TimeoutException):
            return True
        current = current.__cause__
    return False


def _await_provider(call: Callable[[], Any], timeout_seconds: float) -> Any:
    outcome: dict[str, Any] = {}

    def run() -> None:
        try:
            outcome["value"] = call()
        except Exception as exc:
            outcome["error"] = exc

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(timeout_seconds)
    if worker.is_alive():
        raise CaptchaVerificationError("The browser check did not finish.")
    if "error" in outcome:
        raise outcome["error"]
    return outcome.get("value")


def complete_password_login(
    sign_in: Callable[[], Any],
    timeout_seconds: float = LOGIN_PROVIDER_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    try:
        response = _await_provider(sign_in, timeout_seconds)
        if not response.session:
            raise RuntimeError("Login failed: No session returned.")
        return response.model_dump(mode="json")
    except CaptchaVerificationError:
        raise
    except Exception as exc:
        if _provider_verification_failed(exc):
            raise CaptchaVerificationError("The browser check did not complete.") from exc
        raise RuntimeError(f"Login failed: {exc}") from exc
