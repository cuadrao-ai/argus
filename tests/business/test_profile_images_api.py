"""Profile photos and Business logos through the real app on the in-memory stores."""

from __future__ import annotations

from uuid import uuid4

import pytest
from argus.api.business_spaces import business_access
from argus.api.profile_images import profile_images
from argus.domain.profile_images import business, person
from argus.domain.profile_images.images import MAX_BYTES
from fastapi.testclient import TestClient

from tests.business.conftest import ALICE, BOB
from tests.business.test_business_api import BASE, Owner, bob  # noqa: F401
from tests.ingestion.conftest import GUEST
from tests.profile_images.pictures import jpeg_with_gps, png, webp

ME = "/api/v1/me"
PHOTO = "/api/v1/me/photo"
LOGO = BASE + "/logo"


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _put(client: TestClient, url: str, content: bytes, media_type: str, **headers: str):
    return client.put(url, content=content, headers={"Content-Type": media_type, **headers})


def _me(client: TestClient, token: str) -> dict:
    read = client.get(ME, headers=_bearer(token))
    assert read.status_code == 200, read.text
    return read.json()


@pytest.fixture(autouse=True)
def _no_apple_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    # The profile read checks the linked Apple identity in Postgres; in memory there is none.
    monkeypatch.setattr("argus.api.routers.profile._apple_identity", lambda *_: None)


@pytest.fixture
def alice(biz: TestClient, identities) -> Owner:
    owner = Owner(biz, ALICE, identities[ALICE]["id"])
    assert owner.start({"name": "Colmado La Esquina"}).status_code == 201
    return owner


@pytest.fixture
def member(alice: Owner, bob: Owner) -> dict[str, str]:  # noqa: F811
    """Bob holds a read and prepare grant on Alice's Business; the header he sends."""

    store = business_access()
    assert store is not None
    store.confirm(bob.person, "bob@example.test")
    given = alice.post("/access", {"email": "bob@example.test"})
    assert given.status_code == 201, given.text
    grant = next(g for g in given.json()["grants"] if not g["owner"])
    return {"X-Business-Grant": grant["id"]}


# --------------------------------------------------------------------------- #
# The person's photo
# --------------------------------------------------------------------------- #


def test_upload_replace_and_remove_the_own_photo(biz: TestClient, identities) -> None:
    assert _me(biz, ALICE)["photo_url"] is None
    first = _put(biz, PHOTO, jpeg_with_gps(), "image/jpeg", **_bearer(ALICE))
    assert first.status_code == 200, first.text
    url = first.json()["photo_url"]
    assert url and url == _me(biz, ALICE)["photo_url"]
    assert first.json()["user"]["id"] == identities[ALICE]["id"]

    replaced = _put(biz, PHOTO, png(), "image/png", **_bearer(ALICE))
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["photo_url"] != url, "a replaced photo is a new URL"
    stored = profile_images()
    assert stored is not None and stored.url(person(identities[ALICE]["id"]))

    gone = biz.delete(PHOTO, headers=_bearer(ALICE))
    assert gone.status_code == 204
    assert _me(biz, ALICE)["photo_url"] is None
    assert stored.url(person(identities[ALICE]["id"])) is None
    assert biz.delete(PHOTO, headers=_bearer(ALICE)).status_code == 204


@pytest.mark.parametrize(
    "content,media_type,status,code",
    [
        (b"%PDF-1.4", "application/pdf", 415, "image_media_type_unsupported"),
        (b"\x89PNG" + b"\0" * MAX_BYTES, "image/png", 413, "image_too_large"),
        (b"not a picture", "image/png", 422, "image_invalid"),
        (png(300, 40), "image/png", 422, "image_invalid"),
    ],
)
def test_a_wrong_type_an_oversized_body_or_bad_bytes_are_refused(
    biz: TestClient, content: bytes, media_type: str, status: int, code: str
) -> None:
    refused = _put(biz, PHOTO, content, media_type, **_bearer(ALICE))
    assert refused.status_code == status, refused.text
    assert refused.json()["code"] == code
    assert _me(biz, ALICE)["photo_url"] is None


def test_a_guest_cannot_upload_or_remove_a_photo(biz: TestClient) -> None:
    refused = _put(biz, PHOTO, png(), "image/png", **_bearer(GUEST))
    assert refused.status_code == 403, refused.text
    assert biz.delete(PHOTO, headers=_bearer(GUEST)).status_code == 403
    assert _me(biz, GUEST)["photo_url"] is None


def test_the_media_type_is_read_case_insensitively(biz: TestClient) -> None:
    accepted = _put(biz, PHOTO, png(), "IMAGE/PNG; charset=binary", **_bearer(ALICE))
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["photo_url"]


def test_another_person_sees_nothing_and_changes_only_their_own(
    biz: TestClient, identities
) -> None:
    alice_url = _put(biz, PHOTO, png(), "image/png", **_bearer(ALICE)).json()["photo_url"]
    assert _me(biz, BOB)["photo_url"] is None
    bob_url = _put(biz, PHOTO, webp(), "image/webp", **_bearer(BOB)).json()["photo_url"]
    assert bob_url != alice_url
    assert _me(biz, ALICE)["photo_url"] == alice_url
    assert biz.delete(PHOTO, headers=_bearer(BOB)).status_code == 204
    assert _me(biz, ALICE)["photo_url"] == alice_url
    stored = profile_images()
    assert stored is not None
    assert stored.url(person(identities[BOB]["id"])) is None


def test_a_member_photo_reaches_the_owner_only_once_the_member_opened_the_grant(
    biz: TestClient, alice: Owner, bob: Owner, member: dict[str, str]  # noqa: F811
) -> None:
    """An owner can grant any confirmed email without the person's say, so the
    reply shows a stranger's name only; the photo follows the person's own
    access_seen receipt. The access list is the one response that shows
    members to another person."""

    bob_url = _put(biz, PHOTO, png(), "image/png", **bob.auth).json()["photo_url"]
    grants = alice.get("/access").json()["grants"]
    assert [(g["owner"], g["photo_url"]) for g in grants] == [(True, None), (False, None)]
    assert [s["access_seen"] for s in bob.get("/spaces").json()["spaces"] if s["role"] != "owner"] == [False]

    opened = biz.post(f"{BASE}/spaces/{member['X-Business-Grant']}/seen", headers=bob.auth)
    assert opened.status_code == 204
    grants = alice.get("/access").json()["grants"]
    assert [(g["owner"], g["photo_url"]) for g in grants] == [(True, None), (False, bob_url)]
    # The owner's own photo reaches the list without a receipt.
    alice_url = _put(biz, PHOTO, webp(), "image/webp", **alice.auth).json()["photo_url"]
    assert [g["photo_url"] for g in alice.get("/access").json()["grants"]] == [alice_url, bob_url]
    # No other member-listing response exists: the Business list carries no people.
    assert all("photo_url" not in s for s in bob.get("/spaces").json()["spaces"])


# --------------------------------------------------------------------------- #
# The Business logo
# --------------------------------------------------------------------------- #


def test_the_owner_uploads_replaces_and_removes_the_logo(
    biz: TestClient, alice: Owner
) -> None:
    assert alice.get("/space").json()["logo_url"] is None
    first = _put(biz, LOGO, png(alpha=True), "image/png", **alice.auth)
    assert first.status_code == 200, first.text
    space_id = alice.scope().owner.space_id
    url = first.json()["logo_url"]
    assert first.json()["id"] == space_id and url
    assert alice.get("/space").json()["logo_url"] == url
    assert alice.get("/workspace").json()["logo_url"] == url
    assert [s["logo_url"] for s in alice.get("/spaces").json()["spaces"]] == [url]
    assert alice.get("/space/name").json()["logo_url"] == url

    replaced = _put(biz, LOGO, jpeg_with_gps(), "image/jpeg", **alice.auth)
    assert replaced.status_code == 200 and replaced.json()["logo_url"] != url

    assert biz.delete(LOGO, headers=alice.auth).status_code == 204
    assert alice.get("/space").json()["logo_url"] is None
    stored = profile_images()
    assert stored is not None and stored.url(business(space_id)) is None
    assert biz.delete(LOGO, headers=alice.auth).status_code == 204


def test_a_member_sees_the_logo_and_can_replace_it_with_editar(
    biz: TestClient, alice: Owner, bob: Owner, member: dict[str, str]  # noqa: F811
) -> None:
    url = _put(biz, LOGO, png(), "image/png", **alice.auth).json()["logo_url"]
    listed = {s["space_id"]: s["logo_url"] for s in bob.get("/spaces").json()["spaces"]}
    assert listed == {alice.scope().owner.space_id: url, bob.scope().owner.space_id: None}
    seen = biz.get(BASE + "/workspace", headers={**bob.auth, **member})
    assert seen.status_code == 200 and seen.json()["logo_url"] == url

    replaced = _put(biz, LOGO, webp(), "image/webp", **bob.auth, **member)
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["id"] == alice.scope().owner.space_id
    assert replaced.json()["logo_url"] != url
    assert alice.get("/space").json()["logo_url"] == replaced.json()["logo_url"]
    # Bob's own Business kept its (absent) logo.
    assert bob.get("/space").json()["logo_url"] is None


def test_a_member_without_editar_sees_the_logo_but_cannot_change_it(
    biz: TestClient, alice: Owner, bob: Owner, member: dict[str, str]  # noqa: F811
) -> None:
    url = _put(biz, LOGO, png(), "image/png", **alice.auth).json()["logo_url"]
    store = business_access()
    assert store is not None
    # No product path makes a read-only grant yet; the rule is pinned by hand.
    grant = next(g for g in store._grants if g["id"] == member["X-Business-Grant"])
    grant["capabilities"] = ("read",)
    seen = biz.get(BASE + "/workspace", headers={**bob.auth, **member})
    assert seen.status_code == 200 and seen.json()["logo_url"] == url
    refused = _put(biz, LOGO, webp(), "image/webp", **bob.auth, **member)
    assert refused.status_code == 403, refused.text
    assert refused.json()["code"] == "business_permission_denied"
    assert biz.delete(LOGO, headers={**bob.auth, **member}).status_code == 403
    assert alice.get("/space").json()["logo_url"] == url


def test_a_non_member_cannot_see_or_change_the_logo(
    biz: TestClient, alice: Owner, bob: Owner  # noqa: F811
) -> None:
    url = _put(biz, LOGO, png(), "image/png", **alice.auth).json()["logo_url"]
    assert [s["logo_url"] for s in bob.get("/spaces").json()["spaces"]] == [None]
    foreign = {"X-Business-Grant": alice.get("/access").json()["grants"][0]["id"]}
    seen = biz.get(BASE + "/workspace", headers={**bob.auth, **foreign})
    assert seen.status_code == 403 and seen.json()["code"] == "business_grant_not_live"
    refused = _put(biz, LOGO, png(), "image/png", **bob.auth, **foreign)
    assert refused.status_code == 403
    # Bob's upload without a grant lands on Bob's own Business.
    own = _put(biz, LOGO, png(), "image/png", **bob.auth)
    assert own.status_code == 200 and own.json()["id"] == bob.scope().owner.space_id
    assert alice.get("/space").json()["logo_url"] == url
    assert biz.delete(LOGO, headers={**bob.auth, **foreign}).status_code == 403
    assert alice.get("/space").json()["logo_url"] == url


def test_a_revoked_member_loses_the_logo_at_once(
    biz: TestClient, alice: Owner, bob: Owner, member: dict[str, str]  # noqa: F811
) -> None:
    _put(biz, LOGO, png(), "image/png", **alice.auth)
    grant_id = member["X-Business-Grant"]
    assert biz.delete(f"{BASE}/access/grants/{grant_id}", headers=alice.auth).status_code == 204
    assert [s["logo_url"] for s in bob.get("/spaces").json()["spaces"]] == [None]
    refused = _put(biz, LOGO, png(), "image/png", **bob.auth, **member)
    assert refused.status_code == 403 and refused.json()["code"] == "business_grant_not_live"


def test_the_logo_needs_a_started_business(biz: TestClient) -> None:
    refused = _put(biz, LOGO, png(), "image/png", **_bearer(ALICE))
    assert refused.status_code == 404 and refused.json()["code"] == "business_space_missing"


def test_erasing_a_subject_removes_only_its_object(biz: TestClient, identities) -> None:
    """What account deletion and the Business purge call: the object goes,
    other subjects keep theirs, and a second erase is a no-op."""

    _put(biz, PHOTO, png(), "image/png", **_bearer(ALICE))
    _put(biz, PHOTO, png(), "image/png", **_bearer(BOB))
    stored = profile_images()
    assert stored is not None
    objects = stored._objects.objects
    alice_path, bob_path = (person(identities[t]["id"]).path for t in (ALICE, BOB))
    assert set(objects) == {alice_path, bob_path}
    stored.erase(person(identities[ALICE]["id"]))
    stored.erase(person(identities[ALICE]["id"]))
    assert set(objects) == {bob_path}
    stored.erase(business(str(uuid4())))
    assert set(objects) == {bob_path}
