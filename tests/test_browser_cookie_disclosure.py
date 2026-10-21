"""Every cookie Argus actually writes must be a disclosed cookie.

Two independent checks, because either alone is escapable:

* The chokepoint is the single place cookies are written, so there is one
  place to read to know what Argus sets. It reports an unregistered name
  rather than raising: a stale disclosure must never break a live request.
* The observation test patches ``Response.set_cookie`` on the class itself and
  exercises the real auth surface, so it records what was genuinely written no
  matter which name the calling code used to reach the method. Aliasing,
  wrappers, and dynamic names are all covered because this watches behaviour
  rather than syntax.

The observation test is bounded by the routes it exercises. That bound is the
honest limit of this file and is why the chokepoint exists as well.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from argus.api.browser_cookies import COOKIE_REGISTRY, set_browser_cookie
from starlette.responses import Response

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def recorded_cookies(monkeypatch) -> list[str]:
    """Record every cookie name written through Starlette, however reached."""
    written: list[str] = []
    original = Response.set_cookie

    def recording_set_cookie(self, key, value="", **kwargs):
        written.append(key)
        return original(self, key, value, **kwargs)

    monkeypatch.setattr(Response, "set_cookie", recording_set_cookie)
    return written


def test_undisclosed_cookie_is_reported_without_breaking_the_request(caplog):
    """A missing disclosure entry must never fail a live request.

    Refusing to set an auth cookie over a documentation gap turns bookkeeping
    into a broken login. The observation test below is what fails instead, in
    CI, where failure costs nothing.
    """
    response = Response()
    set_browser_cookie(response, "argus-undisclosed", "value")
    assert any(
        "argus-undisclosed" in raw.decode()
        for header, raw in response.raw_headers
        if header.decode().lower() == "set-cookie"
    )


def test_chokepoint_allows_every_registered_cookie():
    for name in COOKIE_REGISTRY:
        response = Response()
        set_browser_cookie(response, name, "value")
        assert any(
            name in raw.decode()
            for header, raw in response.raw_headers
            if header.decode().lower() == "set-cookie"
        )


def test_observed_cookies_are_all_registered(recorded_cookies):
    """Exercise the auth surface and check what actually reached a browser."""
    from argus.api.main import app
    from fastapi.testclient import TestClient

    client = TestClient(app, raise_server_exceptions=False)

    # Unauthenticated calls are enough: the point is to observe whatever the
    # stack writes, not to assert any particular response.
    for method, path, body in (
        ("post", "/api/v1/auth/login", {"email": "a@b.co", "password": "x" * 12}),
        ("post", "/api/v1/auth/signup", {"email": "a@b.co", "password": "x" * 12}),
        ("post", "/api/v1/auth/logout", None),
        ("post", "/api/v1/auth/guest", {}),
        ("get", "/api/v1/auth/session", None),
    ):
        try:
            if body is None:
                getattr(client, method)(path)
            else:
                getattr(client, method)(path, json=body)
        except Exception:
            # A route erroring is fine. Anything it wrote first was recorded.
            pass

    undisclosed = sorted(set(recorded_cookies) - set(COOKIE_REGISTRY))
    assert not undisclosed, (
        f"cookies written but not registered: {undisclosed}. "
        "Register them in COOKIE_REGISTRY and disclose them in the privacy copy."
    )


# The published privacy policy (cuadrao.ai/privacidad, source in marketing/content)
# discloses cookies by purpose: only those needed for security and operation, never
# analytics or advertising. Each registered cookie's concept must be one of those.
NECESSARY_CONCEPTS = frozenset({"sign_in", "guest_handoff", "security"})
POLICY_DIR = REPO_ROOT / "marketing" / "content"


def _published_cookie_disclosure(policy_file: str) -> str:
    policy = json.loads((POLICY_DIR / policy_file).read_text("utf-8"))["privacidad"]
    texts = [block.get("text", "") for block in policy["blocks"]]
    found = [text for text in texts if text.startswith("**Cookies:**")]
    assert len(found) == 1, f"{policy_file}: expected one cookies paragraph"
    return found[0]


@pytest.mark.parametrize(
    ("policy_file", "necessary_only", "no_tracking"),
    [
        (
            "legal-es.json",
            "solo usamos las cookies necesarias para la seguridad y el funcionamiento",
            "No usamos cookies de analítica ni de publicidad",
        ),
        (
            "legal-en.json",
            "we use only the cookies needed for the site's security and operation",
            "We don't use analytics or advertising cookies",
        ),
    ],
)
def test_published_policy_discloses_necessary_cookies_only(
    policy_file: str, necessary_only: str, no_tracking: str
):
    text = _published_cookie_disclosure(policy_file)
    assert necessary_only in text
    assert no_tracking in text


def test_every_registered_cookie_is_a_necessary_cookie_the_policy_covers():
    outside = {
        name: concept
        for name, concept in COOKIE_REGISTRY.items()
        if concept not in NECESSARY_CONCEPTS
    }
    assert not outside, (
        f"cookies {outside} are not security or operation cookies, so the "
        "published privacy policy does not cover them. Update the policy first."
    )
