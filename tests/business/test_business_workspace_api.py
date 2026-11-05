from io import BytesIO
from uuid import uuid4

import pytest
from argus.api.business_spaces import business_access
from argus.domain.business.roles import BusinessRole
from PIL import Image

from tests.business.conftest import ALICE, BOB

BASE = "/api/v1/business"
AUTH = {"Authorization": f"Bearer {ALICE}"}


def test_additional_creation_replays_without_changing_default(biz):
    first = biz.post(BASE + "/space", headers=AUTH, json={"name": "Zulu"}).json()
    headers = {**AUTH, "Idempotency-Key": str(uuid4())}
    body = {"name": "Alpha", "country": "DO"}
    created = biz.post(BASE + "/spaces", headers=headers, json=body)
    assert created.status_code == 201, created.text
    again = biz.post(BASE + "/spaces", headers=headers, json=body)
    assert again.status_code == 200, again.text
    assert again.json() == created.json()
    assert created.json()["id"] != first["id"]
    assert biz.get(BASE + "/space", headers=AUTH).json() == first
    listed = biz.get(BASE + "/spaces", headers=AUTH).json()["spaces"]
    assert [s["space_id"] for s in listed] == [first["id"], created.json()["id"]]
    assert all(s["business_role"] == "owner" for s in listed)


def test_profile_save_is_canonical_and_stale_write_cannot_overwrite(biz):
    first = biz.post(BASE + "/space", headers=AUTH, json={"name": "Colmado"}).json()
    path = BASE + f"/spaces/{first['id']}/profile"
    before = biz.get(path, headers=AUTH)
    assert before.status_code == 200, before.text
    body = {
        "expected_revision": before.json()["revision"],
        "name": " Colmado Sol ",
        "details": {"address": " Calle Sol 10 ", "website": "colmado.example"},
    }
    headers = {**AUTH, "Idempotency-Key": str(uuid4())}
    saved = biz.patch(path, headers=headers, json=body)
    assert saved.status_code == 200, saved.text
    assert saved.json()["name"] == "Colmado Sol"
    assert saved.json()["details"]["address"] == "Calle Sol 10"
    assert saved.json()["details"]["website"] == "https://colmado.example"
    assert biz.get(path, headers=AUTH).json() == saved.json()
    assert biz.patch(path, headers=headers, json=body).json() == saved.json()
    stale = biz.patch(path, headers={**AUTH, "Idempotency-Key": str(uuid4())}, json=body)
    assert stale.status_code == 409, stale.text
    assert stale.json()["code"] == "business_workspace_stale"
    assert biz.get(BASE + "/space", headers=AUTH).json()["name"] == "Colmado Sol"


@pytest.mark.parametrize(
    "role,expected",
    [
        (BusinessRole.OWNER, 200),
        (BusinessRole.ADMIN, 200),
        (BusinessRole.EDITOR, 403),
        (BusinessRole.VIEWER, 403),
    ],
)
def test_saved_profile_uses_live_canonical_permissions(biz, identities, role, expected):
    first = biz.post(BASE + "/space", headers=AUTH, json={"name": "Colmado"}).json()
    access = business_access()
    actor, other = identities[ALICE]["id"], identities[BOB]["id"]
    access.confirm(other, "other@example.test")
    _, listing = access.give(first["id"], actor, "other@example.test", role)
    access.accept_invite(other, first["id"], listing.invites[0].id)
    grant = access.spaces_for(other)[0].grant_id
    headers = {
        "Authorization": f"Bearer {BOB}",
        "Idempotency-Key": "save",
        "X-Business-Grant": grant,
    }
    path = BASE + f"/spaces/{first['id']}/profile"
    body = {"expected_revision": 0, "details": {"phone": "809-555-0100"}}
    assert biz.patch(path, headers=headers, json=body).status_code == expected
    access.revoke_grant(first["id"], actor, grant)
    assert biz.patch(path, headers=headers, json=body).status_code == 403
    assert biz.get(path, headers=headers).status_code == 403


def test_absent_default_foreign_id_and_changed_key_are_refused(biz):
    headers = {**AUTH, "Idempotency-Key": "create"}
    body = {"name": "Second", "country": "DO"}
    refused = biz.post(BASE + "/spaces", headers=headers, json=body)
    assert refused.status_code == 409
    assert refused.json()["code"] == "business_default_required"
    assert biz.get(BASE + f"/spaces/{uuid4()}/profile", headers=AUTH).status_code == 404
    biz.post(BASE + "/space", headers=AUTH, json={"name": "First"})
    assert biz.post(BASE + "/spaces", headers=headers, json=body).status_code == 201
    conflict = biz.post(
        BASE + "/spaces", headers=headers, json={**body, "name": "Changed"}
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "idempotency_conflict"


def test_identity_upload_cancel_save_crop_and_reset_preserve_other_business_and_logo(biz):
    from argus.api.profile_images import profile_images

    first = biz.post(BASE + "/space", headers=AUTH, json={"name": "First"}).json()
    second = biz.post(
        BASE + "/spaces",
        headers={**AUTH, "Idempotency-Key": "second"},
        json={"name": "Second", "country": "DO"},
    ).json()
    objects = profile_images().objects
    logo = f"business/{first['id']}/256.webp"
    objects.put(logo, b"unchanged-logo", "image/webp")
    content = BytesIO()
    Image.new("RGB", (180, 90), "red").save(content, format="PNG")
    path = BASE + f"/spaces/{first['id']}/profile"
    asset_path = BASE + f"/spaces/{first['id']}/appearance/assets"
    headers = {**AUTH, "Idempotency-Key": "upload", "Content-Type": "image/png"}
    uploaded = biz.post(asset_path, headers=headers, content=content.getvalue())
    assert uploaded.status_code == 200, uploaded.text
    assert (
        biz.post(asset_path, headers=headers, content=content.getvalue()).json()
        == uploaded.json()
    )
    assert biz.get(path, headers=AUTH).json()["appearance"] == {"kind": "default"}
    body = {
        "expected_revision": 0,
        "appearance": {
            "kind": "image",
            "asset_id": uploaded.json()["asset_id"],
            "crop": {"mode": "fit", "zoom": 1, "x": 0, "y": 0},
        },
    }
    saved = biz.patch(path, headers={**AUTH, "Idempotency-Key": "save-image"}, json=body)
    assert saved.status_code == 200, saved.text
    original_paths = dict(objects.objects)
    stale = biz.patch(
        path,
        headers={**AUTH, "Idempotency-Key": "stale-crop"},
        json={
            **body,
            "appearance": {
                **body["appearance"],
                "crop": {"mode": "fill", "zoom": 2, "x": 1, "y": 0},
            },
        },
    )
    assert stale.status_code == 409
    assert objects.objects == original_paths
    other = BASE + f"/spaces/{second['id']}/profile"
    foreign = biz.patch(other, headers={**AUTH, "Idempotency-Key": "foreign"}, json=body)
    assert foreign.status_code == 404, foreign.text
    reset = biz.patch(
        path,
        headers={**AUTH, "Idempotency-Key": "remove"},
        json={
            "expected_revision": saved.json()["revision"],
            "appearance": {"kind": "default"},
        },
    )
    assert reset.status_code == 200
    assert reset.json()["appearance"] == {"kind": "default"}
    assert reset.json()["image"] is None
    assert objects.objects[logo] == b"unchanged-logo"
    assert biz.get(other, headers=AUTH).json()["appearance"] == {"kind": "default"}


def test_appearance_storage_failure_keeps_saved_revision(biz, monkeypatch):
    from argus.api.profile_images import profile_images
    from argus.domain.profile_images.objects import ProfileImageStorageUnavailable

    first = biz.post(BASE + "/space", headers=AUTH, json={"name": "First"}).json()
    content = BytesIO()
    Image.new("RGB", (120, 80), "green").save(content, format="PNG")
    uploaded = biz.post(
        BASE + f"/spaces/{first['id']}/appearance/assets",
        headers={**AUTH, "Idempotency-Key": "upload", "Content-Type": "image/png"},
        content=content.getvalue(),
    ).json()

    def fail(*args):
        raise ProfileImageStorageUnavailable("offline")

    monkeypatch.setattr(profile_images().objects, "put", fail)
    response = biz.patch(
        BASE + f"/spaces/{first['id']}/profile",
        headers={**AUTH, "Idempotency-Key": "save"},
        json={
            "expected_revision": 0,
            "appearance": {
                "kind": "image",
                "asset_id": uploaded["asset_id"],
                "crop": {"mode": "fill"},
            },
        },
    )
    assert response.status_code == 503, response.text
    current = biz.get(BASE + f"/spaces/{first['id']}/profile", headers=AUTH).json()
    assert current["revision"] == 0
    assert current["appearance"] == {"kind": "default"}


@pytest.mark.parametrize("role", list(BusinessRole))
def test_profile_image_source_requires_download_permission(
    biz, identities, role, monkeypatch
):
    from urllib.parse import urlsplit

    from argus.api.profile_images import profile_images
    from argus.domain.business.roles import ROLE_PERMISSIONS

    first = biz.post(BASE + "/space", headers=AUTH, json={"name": "Colmado"}).json()
    content = BytesIO()
    Image.new("RGB", (180, 90), "red").save(content, format="PNG")
    uploaded = biz.post(
        BASE + f"/spaces/{first['id']}/appearance/assets",
        headers={**AUTH, "Idempotency-Key": "upload", "Content-Type": "image/png"},
        content=content.getvalue(),
    )
    assert uploaded.status_code == 200
    path = BASE + f"/spaces/{first['id']}/profile"
    saved = biz.patch(
        path,
        headers={**AUTH, "Idempotency-Key": "save"},
        json={
            "expected_revision": 0,
            "appearance": {
                "kind": "image",
                "asset_id": uploaded.json()["asset_id"],
                "crop": {"mode": "fill", "zoom": 2},
            },
        },
    )
    assert saved.status_code == 200
    access = business_access()
    actor, other = identities[ALICE]["id"], identities[BOB]["id"]
    access.confirm(other, "other@example.test")
    _, listing = access.give(first["id"], actor, "other@example.test", role)
    access.accept_invite(other, first["id"], listing.invites[0].id)
    headers = {
        "Authorization": f"Bearer {BOB}",
        "X-Business-Grant": access.spaces_for(other)[0].grant_id,
    }
    objects = profile_images().objects
    signed_paths = []
    original_sign = objects.signed_urls

    def sign(paths, expires_in):
        signed_paths.extend(paths)
        return original_sign(paths, expires_in)

    monkeypatch.setattr(objects, "signed_urls", sign)
    response = biz.get(path, headers=headers)
    assert response.status_code == 200
    image = response.json()["image"]
    objects = profile_images().objects
    rendered = objects.read(urlsplit(image["rendered_url"]).path.lstrip("/"))
    assert Image.open(BytesIO(rendered)).size == (512, 512)
    source_available = bool(image.get("source_url"))
    if source_available:
        source = objects.read(urlsplit(image["source_url"]).path.lstrip("/"))
        assert Image.open(BytesIO(source)).size == (180, 90)
    can_download = "download" in ROLE_PERMISSIONS[role]
    assert source_available == can_download
    source_signed = any(path.endswith("-source.webp") for path in signed_paths)
    assert source_signed == can_download
