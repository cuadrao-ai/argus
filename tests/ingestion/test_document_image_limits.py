import io
import struct
import time
import zlib
from types import SimpleNamespace

import psutil
import pytest
from argus.domain.ingestion.documents import rebuilt
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
    if width * height == 30_000_000:

        def chunk(kind, value):
            return (
                struct.pack(">I", len(value))
                + kind
                + value
                + struct.pack(">I", zlib.crc32(kind + value))
            )

        compressor = zlib.compressobj()
        compressed = b"".join(
            compressor.compress(b"\0" * (width + 1)) for _ in range(height)
        )
        compressed += compressor.flush()
        header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
        return (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", header)
            + chunk(b"IDAT", compressed)
            + chunk(b"IEND", b"")
        )
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
            rebuilt.rebuild_image(content, media_type)
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
    monkeypatch.setattr(rebuilt.tempfile, "tempdir", str(tmp_path))

    def parent_parse(*args, **kwargs):
        pytest.fail("untrusted image reached the API process parser")

    monkeypatch.setattr(Image, "open", parent_parse)
    image_bytes = rebuilt.rebuild_image(content, "image/png")
    with real_open(io.BytesIO(image_bytes), formats=["JPEG"]) as image:
        assert image.size == (1600, 800)
        assert image.mode == "RGB"
    assert not list(tmp_path.iterdir())


def test_email_dimension_check_does_not_open_source_in_parent(monkeypatch):
    content = png()

    def parent_parse(*args, **kwargs):
        pytest.fail("untrusted image reached the API process parser")

    monkeypatch.setattr(Image, "open", parent_parse)
    assert rebuilt.image_pixels(content, "image/png") == 24 * 16


def test_child_has_cpu_memory_file_limits_and_no_provider_environment(monkeypatch):
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
    assert rebuilt.image_pixels(png(), "image/png") == 1


def test_signal_exit_is_logged_and_child_is_reaped(monkeypatch, tmp_path):
    monkeypatch.setattr(rebuilt.tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(
        rebuilt,
        "_IMAGE_REBUILD",
        "import os,signal; os.kill(os.getpid(), signal.SIGTERM)",
    )
    records = []
    sink = logger.add(lambda message: records.append(message.record))
    processes = []
    spawn = rebuilt.subprocess.Popen

    def track(*args, **kwargs):
        process = spawn(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(rebuilt.subprocess, "Popen", track)
    try:
        with pytest.raises(DocumentExtractionError, match="invalid_document"):
            rebuilt.rebuild_image(png(), "image/png")
    finally:
        logger.remove(sink)
    assert len(processes) == 1
    assert processes[0].returncode == -15
    assert not list(tmp_path.iterdir())
    assert records[-1]["extra"]["signal"] == 15
    assert records[-1]["extra"]["alert"] is True
    assert records[-1]["level"].name == "ERROR"


def test_child_file_limit_rejects_oversized_output(monkeypatch, tmp_path):
    monkeypatch.setattr(rebuilt.tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(
        rebuilt,
        "_IMAGE_REBUILD",
        """
import sys
with open(sys.argv[2], "wb") as output:
    for _ in range(11):
        output.write(b"x" * 1048576)
""",
    )
    with pytest.raises(DocumentExtractionError, match="invalid_document"):
        rebuilt.rebuild_image(png(), "image/png")
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("reason", ["memory", "timeout"])
def test_resource_failure_kills_child_and_emits_alert(monkeypatch, reason):
    monkeypatch.setattr(rebuilt, "_IMAGE_REBUILD", "import time; time.sleep(60)")
    records = []
    processes = []
    sink = logger.add(lambda message: records.append(message.record))
    spawn = rebuilt.subprocess.Popen

    def track(*args, **kwargs):
        process = spawn(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(rebuilt.subprocess, "Popen", track)
    if reason == "memory":
        monkeypatch.setattr(
            rebuilt.psutil,
            "Process",
            lambda pid: SimpleNamespace(
                memory_info=lambda: SimpleNamespace(rss=536870913)
            ),
        )
    else:
        clock = iter([0.0, 21.0])
        monkeypatch.setattr(
            rebuilt, "time", SimpleNamespace(monotonic=lambda: next(clock))
        )
    started = time.monotonic()
    try:
        with pytest.raises(DocumentExtractionError):
            rebuilt.rebuild_image(png(), "image/png")
    finally:
        logger.remove(sink)
    assert time.monotonic() - started < 5
    assert len(processes) == 1 and processes[0].returncode is not None
    assert records[-1]["extra"]["reason"] == reason
    assert records[-1]["extra"]["alert"] is True
