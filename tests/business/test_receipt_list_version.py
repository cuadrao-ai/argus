"""GET /business/receipts answers "no change" without the list (#2033)."""

from __future__ import annotations

from tests.business.test_business_api import BASE, Owner, alice  # noqa: F401


def _check(owner: Owner, version: str | None = None, view: str = "inbox"):
    headers = {**owner.auth, **({"If-None-Match": version} if version else {})}
    return owner.client.get(f"{BASE}/receipts", params={"view": view}, headers=headers)


def test_no_change_answers_304_with_no_list_and_a_change_sends_the_page(
    alice: Owner,  # noqa: F811
) -> None:
    first = _check(alice)
    version = first.headers["ETag"]
    assert first.status_code == 200 and first.json()["items"] == []

    same = _check(alice, version)
    assert (same.status_code, same.content, same.headers["ETag"]) == (304, b"", version)
    # A proxy that compressed the first answer may hand the version back weak.
    assert _check(alice, f"W/{version}").status_code == 304

    assert alice.upload().status_code == 200
    changed = _check(alice, version)
    assert changed.status_code == 200
    assert len(changed.json()["items"]) == 1
    assert changed.headers["ETag"] != version
    assert _check(alice, changed.headers["ETag"]).status_code == 304


def test_a_check_without_a_version_always_sends_the_page(alice: Owner) -> None:  # noqa: F811
    assert _check(alice).status_code == 200
    assert _check(alice, '"not-a-version"').status_code == 200


def test_the_web_can_read_the_version_across_origins(alice: Owner) -> None:  # noqa: F811
    answer = alice.client.get(
        f"{BASE}/receipts", headers={**alice.auth, "Origin": "http://localhost:3000"}
    )
    assert "ETag" in answer.headers["access-control-expose-headers"]
