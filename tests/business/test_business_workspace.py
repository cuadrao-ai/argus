from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from argus.domain.business.access import InMemoryAccessStore
from argus.domain.business.spaces import InMemorySpaceStore
from argus.domain.business.workspace import BusinessDetails, SaveWorkspace, WorkspaceError
from pydantic import ValidationError


@pytest.mark.parametrize(
    "field,limit",
    [
        ("address", 200),
        ("province", 80),
        ("municipality", 80),
        ("phone", 40),
        ("description", 280),
    ],
)
def test_detail_limits_apply_after_trimming(field, limit):
    assert (
        getattr(BusinessDetails(**{field: " " + "x" * limit + " "}), field) == "x" * limit
    )
    with pytest.raises(ValidationError):
        BusinessDetails(**{field: "x" * (limit + 1)})


@pytest.mark.parametrize(
    "website",
    [
        "javascript:bad",
        "https://user@shop.example",
        "https://@shop.example",
        "https://user:pass@shop.example",
        "http://localhost",
        "https://bad .example",
        "https://shop.example:invalid",
    ],
)
def test_invalid_websites_are_refused(website):
    with pytest.raises(ValidationError):
        BusinessDetails(website=website)


@pytest.mark.parametrize(
    "email", ["name", "a@host", "a b@host.example", "a@@host.example"]
)
def test_invalid_emails_are_refused(email):
    with pytest.raises(ValidationError):
        BusinessDetails(email=email)


def test_memory_concurrent_commands_and_legacy_name_revision():
    access = InMemoryAccessStore()
    store = InMemorySpaceStore(access)
    actor = str(uuid4())
    first, _ = store.create(actor, "First")
    access.ensure_owner_grant(first.id, actor)
    with ThreadPoolExecutor(max_workers=3) as workers:
        results = list(
            workers.map(
                lambda _: store.create_additional(actor, "Second", "DO", "same"), range(6)
            )
        )
    assert sum(created for _, created in results) == 1
    assert len({space.id for space, _ in results}) == 1
    assert store.open_space(actor).id == first.id
    assert len(access.spaces_for(actor)) == 2
    store.rename(actor, "Renamed", first.id)
    assert store.read_workspace(actor, first.id).revision == 1
    with pytest.raises(WorkspaceError, match="business_workspace_stale"):
        store.save_workspace(
            actor, first.id, SaveWorkspace(expected_revision=0, name="Old"), "stale"
        )


def test_noop_save_does_not_advance_revision():
    store = InMemorySpaceStore()
    first, _ = store.create("owner", "First")
    assert (
        store.save_workspace(
            "owner", first.id, SaveWorkspace(expected_revision=0), "empty"
        ).revision
        == 0
    )


def test_identity_geometry_preserves_fit_fill_and_bounded_extreme_aspect():
    import hashlib
    from io import BytesIO

    from argus.domain.business.workspace_images import (
        Crop,
        WorkspaceAsset,
        normalized_source,
        render,
    )
    from argus.domain.profile_images.objects import InMemoryProfileImageObjects
    from PIL import Image

    objects = InMemoryProfileImageObjects()
    for dimensions in [(160, 80), (1, 1280)]:
        content = BytesIO()
        Image.new("RGB", dimensions, "red").save(content, format="PNG")
        source, width, height = normalized_source(content.getvalue(), "image/png")
        asset = WorkspaceAsset(
            str(uuid4()), str(uuid4()), hashlib.sha256(source).hexdigest(), width, height
        )
        objects.put(asset.source_path, source, "image/webp")
        fit, fill = Crop(mode="fit"), Crop(mode="fill")
        render(objects, asset, fit)
        first = objects.read(asset.render_path(fit))
        render(objects, asset, fill)
        assert objects.read(asset.render_path(fit)) == first
        with Image.open(BytesIO(first)) as image:
            assert image.size == (512, 512)
            assert image.convert("RGBA").getpixel((0, 0))[3] == 0
        with Image.open(BytesIO(objects.read(asset.render_path(fill)))) as image:
            assert image.size == (512, 512)
            assert image.convert("RGBA").getpixel((256, 256))[3] == 255
        assert len(first) <= 1024 * 1024


@pytest.mark.parametrize(
    "crop", [{"zoom": 0}, {"zoom": 5}, {"x": 2}, {"y": float("nan")}, {"mode": "stretch"}]
)
def test_invalid_identity_crop_is_refused(crop):
    from argus.domain.business.workspace_images import Crop

    with pytest.raises(ValidationError):
        Crop(**crop)
