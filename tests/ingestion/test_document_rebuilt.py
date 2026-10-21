import hashlib
import io
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from argus.domain.ingestion.documents import rebuilt
from argus.domain.ingestion.documents.models import DocumentExtractionError
from argus.domain.ingestion.documents.objects import SourceStorageUnavailable
from PIL import Image


def image_bytes(image_format="PNG", *, frames=1):
    output = io.BytesIO()
    image = Image.new("RGB", (32, 24), "white")
    options = {}
    if frames > 1:
        options = {"save_all": True, "append_images": [Image.new("RGB", image.size)]}
    image.save(output, format=image_format, **options)
    return output.getvalue()


def source_store(content=None, media_type="image/png"):
    content = image_bytes() if content is None else content
    draft = SimpleNamespace(
        sha256=hashlib.sha256(content).hexdigest(), media_type=media_type
    )
    return Mock(
        draft=Mock(return_value=draft),
        source=Mock(return_value=content),
        rebuilt=Mock(return_value=None),
        save_rebuilt=Mock(return_value=True),
    )


def ensure(store):
    rebuilt.ensure_rebuilt_image(store=store, user_id="owner", connection_id="receipt")


@pytest.mark.parametrize(
    "image_format,media_type", [("PNG", "image/png"), ("JPEG", "image/jpeg")]
)
def test_missing_image_copy_is_built_without_parent_decoding(
    monkeypatch, image_format, media_type
):
    content = image_bytes(image_format)
    store = source_store(content, media_type)
    real_open = Image.open
    monkeypatch.setattr(
        Image, "open", lambda *a, **k: pytest.fail("parent decoded source")
    )
    ensure(store)
    saved = store.save_rebuilt.call_args.kwargs
    assert saved["user_id"] == "owner"
    assert saved["connection_id"] == "receipt"
    assert saved["media_type"] == "image/jpeg"
    with real_open(io.BytesIO(saved["content"]), formats=["JPEG"]) as image:
        assert image.size == (32, 24)
        assert image.mode == "RGB"
    assert store.source.return_value == content
    store.rebuilt.return_value = (saved["media_type"], saved["content"])
    ensure(store)
    assert store.save_rebuilt.call_count == 1
    assert store.source.call_count == 1


@pytest.mark.parametrize(
    "media_type",
    [
        "application/pdf",
        "text/plain",
        "text/csv",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/xml",
        "message/rfc822",
    ],
)
def test_nonimage_is_not_read_or_rebuilt(media_type):
    store = source_store(b"original bytes", media_type)
    ensure(store)
    store.source.assert_not_called()
    store.rebuilt.assert_not_called()
    store.save_rebuilt.assert_not_called()


@pytest.mark.parametrize("missing", ["draft", "source"])
def test_missing_source_is_noop(missing):
    store = source_store()
    getattr(store, missing).return_value = None
    ensure(store)
    store.save_rebuilt.assert_not_called()


def test_deletion_during_build_cannot_restore_source(monkeypatch):
    store = source_store()
    store.draft.side_effect = [store.draft.return_value, None]
    ensure(store)
    store.save_rebuilt.assert_not_called()


def test_source_identity_change_during_build_is_rejected():
    store = source_store()
    store.draft.side_effect = [
        store.draft.return_value,
        SimpleNamespace(sha256="changed", media_type="image/png"),
    ]
    with pytest.raises(SourceStorageUnavailable):
        ensure(store)
    store.save_rebuilt.assert_not_called()


def test_original_integrity_failure_does_not_build(monkeypatch):
    store = source_store()
    store.source.return_value = b"changed source"
    decode = Mock()
    monkeypatch.setattr(rebuilt, "rebuild_image", decode)
    with pytest.raises(SourceStorageUnavailable):
        ensure(store)
    decode.assert_not_called()
    store.save_rebuilt.assert_not_called()


@pytest.mark.parametrize(
    "failure", [False, SourceStorageUnavailable("storage unavailable")]
)
def test_store_deletion_fence_or_failure_is_preserved(failure):
    store = source_store()
    if failure is False:
        store.save_rebuilt.return_value = False
        ensure(store)
    else:
        store.save_rebuilt.side_effect = failure
        with pytest.raises(SourceStorageUnavailable):
            ensure(store)
    assert store.save_rebuilt.call_count == 1


@pytest.mark.parametrize(
    "content,media_type,code",
    [
        (image_bytes(), "image/jpeg", "invalid_document"),
        (image_bytes(frames=2), "image/png", "unsupported_image_frames"),
        (b"invalid", "image/png", "invalid_document"),
    ],
)
def test_invalid_image_never_saves_a_copy(content, media_type, code):
    store = source_store(content, media_type)
    with pytest.raises(DocumentExtractionError, match=code):
        ensure(store)
    store.save_rebuilt.assert_not_called()


@pytest.mark.parametrize("width,height", [(6000, 5000), (20000, 20000)])
def test_pixel_limit_rejects_in_child_before_parent_allocation(
    monkeypatch, width, height
):
    import struct
    import zlib

    import psutil

    content = bytearray(image_bytes())
    content[16:24] = struct.pack(">II", width, height)
    content[29:33] = struct.pack(">I", zlib.crc32(content[12:29]))
    store = source_store(bytes(content))
    monkeypatch.setattr(
        Image, "open", lambda *a, **k: pytest.fail("parent decoded source")
    )
    before = psutil.Process().memory_info().rss
    with pytest.raises(DocumentExtractionError, match="invalid_document"):
        ensure(store)
    assert psutil.Process().memory_info().rss - before < 4 * 1024 * 1024
    store.save_rebuilt.assert_not_called()


def test_producer_child_has_resource_limits_and_no_provider_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "must-not-reach-child")
    monkeypatch.setattr(
        rebuilt,
        "_IMAGE_REBUILD",
        """
import os, resource, sys
assert resource.getrlimit(resource.RLIMIT_CPU) == (20, 20)
assert resource.getrlimit(resource.RLIMIT_FSIZE) == (10485760, 10485760)
if sys.platform == "linux":
    assert resource.getrlimit(resource.RLIMIT_AS) == (536870912, 536870912)
assert "OPENROUTER_API_KEY" not in os.environ
sys.stdout.write("1")
""",
    )
    assert rebuilt.image_pixels(image_bytes(), "image/png") == 1
