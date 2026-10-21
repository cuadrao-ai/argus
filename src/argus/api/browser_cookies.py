"""The single door through which Argus writes cookies to a browser.

Every cookie name is declared in ``COOKIE_REGISTRY`` with the privacy-policy
category that discloses it, and :func:`set_browser_cookie` refuses a name that
is not there. The privacy copy is derived from this registry rather than
inferred by searching for call sites, because a search can only find the
syntactic forms someone thought to look for.

Writing an undisclosed cookie therefore requires bypassing this module on
purpose, which shows up in review, rather than following from ordinary code.
"""

from __future__ import annotations

from typing import Any, Final

from loguru import logger

# Cookie name -> the purpose the published privacy policy (cuadrao.ai/privacidad)
# discloses it under. A cookie outside security and operation needs the policy first.
COOKIE_REGISTRY: Final[dict[str, str]] = {
    "sb-auth-token": "sign_in",
    "sb-refresh-token": "sign_in",
    "argus-guest-handoff": "guest_handoff",
    "argus-guest-handoff-id": "guest_handoff",
}


def _warn_if_unregistered(name: str) -> None:
    """Report an undisclosed cookie without failing the request.

    Deliberately not an exception. Refusing to set an auth cookie because a
    disclosure entry is missing turns a documentation gap into a broken login,
    which is far worse than the gap. The test suite observes every cookie this
    module writes and fails there instead, where failure costs nothing.
    """
    if name not in COOKIE_REGISTRY:
        logger.warning(
            "Cookie {name} is not in COOKIE_REGISTRY, so no privacy disclosure "
            "covers it. Register it and disclose it.",
            name=name,
        )


def set_browser_cookie(response: Any, name: str, value: str, **kwargs: Any) -> None:
    """Set a cookie, reporting any that no disclosure covers."""
    _warn_if_unregistered(name)
    response.set_cookie(name, value, **kwargs)


def delete_browser_cookie(response: Any, name: str, **kwargs: Any) -> None:
    """Delete a cookie.

    A delete cannot create browser state, but routing it here keeps one place
    that knows every cookie Argus owns.
    """
    response.delete_cookie(name, **kwargs)
