"""Actividad behind one server switch, off by default.

Off, the feed route refuses before authentication and the workspace says so.
On, it is what it was. Recording stays out of the switch: the one reader of it
is the route guard and the workspace answer, so actions keep writing entries."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from argus.domain.business.config import business_activity_enabled

from tests.business.test_business_api import BASE, Owner, alice  # noqa: F401

SWITCH = "CUADRAO_BUSINESS_ACTIVITY_ENABLED"
SRC = Path(__file__).resolve().parents[2] / "src" / "argus"


@pytest.fixture
def activity_off(monkeypatch: pytest.MonkeyPatch) -> None:
    # Set, not deleted: an absent name would be refilled from a worktree .env.
    monkeypatch.setenv(SWITCH, "false")


def test_the_switch_is_off_unless_the_server_says_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(SWITCH, raising=False)
    monkeypatch.setenv("ARGUS_ENV_FILE", "")
    for value, expected in [("true", True), ("false", False), ("", False), ("maybe", False)]:
        monkeypatch.setenv(SWITCH, value)
        assert business_activity_enabled() is expected, value


def test_off_the_feed_refuses_before_auth_and_the_workspace_says_false(
    alice: Owner, activity_off  # noqa: F811, ANN001
) -> None:
    assert alice.get("/workspace").json()["activity_available"] is False
    for headers in (alice.auth, {}):
        refused = alice.client.get(BASE + "/activity", headers=headers)
        assert (refused.status_code, refused.json()["code"]) == (
            404,
            "business_activity_disabled",
        )
        assert refused.headers["cache-control"] == "no-store"
    cursor = alice.get("/activity", cursor="not-a-cursor")
    assert (cursor.status_code, cursor.json()["code"]) == (404, "business_activity_disabled")


def test_on_the_feed_answers_as_before(alice: Owner, activity_on) -> None:  # noqa: F811, ANN001
    assert alice.get("/workspace").json()["activity_available"] is True
    page = alice.get("/activity")
    assert (page.status_code, page.json()) == (
        200,
        {"items": [], "next_cursor": None, "actors": []},
    )


def test_only_the_route_and_the_workspace_read_the_switch() -> None:
    """Recording an entry never asks the switch, so turning it on later shows the whole history."""

    readers = {
        str(path.relative_to(SRC))
        for path in SRC.rglob("*.py")
        if re.search(r"business_activity_enabled|BUSINESS_ACTIVITY_ENABLED", path.read_text())
    }
    assert readers == {
        "domain/business/config.py",
        "api/routers/business.py",
        "api/routers/business_activity.py",
    }
