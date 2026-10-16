import io
import struct
import zlib

import psutil
import pytest
from argus.domain.ingestion.documents import preparation
from argus.domain.ingestion.documents.models import DocumentExtractionError
from loguru import logger
from PIL import Image


def png(width=24, height=16, *, frames=1):
    output = io.BytesIO()
    image = Image.new("RGB", (width, height), "white")
    options = {}
    if frames > 1:
        options = {"save_all": True, "append_images": [Image.new("RGB", image.size)]}
    image.save(output, format="PNG", **options)
    return output.getvalue()


def oversized_png(width, height):
    data = bytearray(png())
    data[16:24] = struct.pack(">II", width, height)
    data[29:33] = struct.pack(">I", zlib.crc32(data[12:29]))
    return bytes(data)


@pytest.mark.parametrize(
    "content,media_type,reason,code",
    [
        (oversized_png(6000, 5000), "image/png", "pixels", "invalid_document"),
        (oversized_png(20000, 20000), "image/png", "pixels", "invalid_document"),
        (png(frames=2), "image/png", "frames", "unsupported_image_frames"),
        (png(), "image/jpeg", "format", "invalid_document"),
    ],
    ids=["30-million-pixels", "decompression-bomb", "animated-png", "wrong-type"],
)
def test_rejection_happens_in_child_without_parent_image_decode(
    monkeypatch, content, media_type, reason, code
):
    def parent_parse(*args, **kwargs):
        pytest.fail("untrusted image reached the API process parser")

    monkeypatch.setattr(Image, "open", parent_parse)
    records = []
    sink = logger.add(lambda message: records.append(message.record))
    before = psutil.Process().memory_info().rss
    try:
        with pytest.raises(DocumentExtractionError) as error:
            preparation._image(content, media_type)
    finally:
        logger.remove(sink)
    assert error.value.code == code
    assert psutil.Process().memory_info().rss - before < 4 * 1024 * 1024
    rejected = [
        r["extra"]
        for r in records
        if r["extra"].get("metric") == "document_image_rejected"
    ]
    assert len(rejected) == 1
    assert rejected[0]["reason"] == reason
    assert rejected[0]["value"] == 1


def test_good_image_rebuild_never_opens_source_in_parent(monkeypatch, tmp_path):
    content = png(2000, 1000)
    real_open = Image.open
    monkeypatch.setattr(preparation.tempfile, "tempdir", str(tmp_path))

    def parent_parse(*args, **kwargs):
        pytest.fail("untrusted image reached the API process parser")

    monkeypatch.setattr(Image, "open", parent_parse)
    rebuilt = preparation._image(content, "image/png")
    with real_open(io.BytesIO(rebuilt), formats=["JPEG"]) as image:
        assert image.size == (1600, 800)
        assert image.mode == "RGB"
    assert not list(tmp_path.iterdir())


def test_email_dimension_check_does_not_open_source_in_parent(monkeypatch):
    content = png()

    def parent_parse(*args, **kwargs):
        pytest.fail("untrusted image reached the API process parser")

    monkeypatch.setattr(Image, "open", parent_parse)
    assert preparation.image_pixels(content, "image/png") == 24 * 16
