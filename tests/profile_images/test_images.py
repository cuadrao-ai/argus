"""The one stored shape: a 256 px WebP square, oriented, with no metadata."""

from __future__ import annotations

import io

import pytest
from argus.domain.profile_images.images import (
    MAX_PIXELS,
    SIZE,
    InvalidImage,
    square_webp,
)
from PIL import ExifTags, Image

from tests.profile_images.pictures import (
    BLUE,
    RED,
    animated_webp,
    jpeg_with_gps,
    png,
    webp,
)


def _open(stored: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(stored))
    image.load()
    return image


def _close_to(pixel: tuple, color: tuple) -> bool:
    return all(abs(a - b) <= 24 for a, b in zip(pixel[:3], color, strict=False))


@pytest.mark.parametrize(
    "content,media_type",
    [(png(), "image/png"), (jpeg_with_gps(), "image/jpeg"), (webp(), "image/webp")],
)
def test_every_accepted_type_becomes_a_webp_square(content: bytes, media_type: str) -> None:
    stored = _open(square_webp(content, media_type))
    assert stored.format == "WEBP"
    assert stored.size == (SIZE, SIZE)


def test_a_wide_picture_is_center_cropped() -> None:
    stored = _open(square_webp(png(300, 200), "image/png"))
    assert _close_to(stored.getpixel((10, 128)), RED)
    assert _close_to(stored.getpixel((245, 128)), BLUE)


def test_exif_orientation_is_applied_and_every_tag_is_dropped() -> None:
    source = jpeg_with_gps(orientation=6)
    uploaded = _open(source)
    assert uploaded.getexif().get_ifd(ExifTags.IFD.GPSInfo) and uploaded.info["icc_profile"]
    stored = _open(square_webp(source, "image/jpeg"))
    # Orientation 6 turns the left (red) half into the top.
    assert _close_to(stored.getpixel((128, 10)), RED)
    assert _close_to(stored.getpixel((128, 245)), BLUE)
    assert dict(stored.getexif()) == {}
    assert not stored.getexif().get_ifd(ExifTags.IFD.GPSInfo)
    assert "icc_profile" not in stored.info and "xmp" not in stored.info


def test_transparency_survives_for_logos() -> None:
    stored = _open(square_webp(png(alpha=True), "image/png"))
    assert stored.mode == "RGBA"


@pytest.mark.parametrize(
    "content,media_type,reason",
    [
        (png(), "image/jpeg", "undecodable"),
        (b"not a picture", "image/png", "undecodable"),
        (png(300, 40), "image/png", "too_small"),
        (animated_webp(), "image/webp", "animated"),
    ],
)
def test_pictures_that_are_not_one_still_image_are_refused(
    content: bytes, media_type: str, reason: str
) -> None:
    with pytest.raises(InvalidImage) as refused:
        square_webp(content, media_type)
    assert refused.value.reason == reason


def test_a_picture_over_the_pixel_ceiling_is_refused_before_decoding() -> None:
    side = int(MAX_PIXELS**0.5) + 1
    # A valid one-bit picture: a few KB on disk, 25 million pixels decoded,
    # and under Pillow's own bomb threshold, so only the ceiling refuses it.
    output = io.BytesIO()
    Image.new("1", (side, side), 1).save(output, format="PNG")
    with pytest.raises(InvalidImage) as refused:
        square_webp(output.getvalue(), "image/png")
    assert refused.value.reason == "too_many_pixels"
