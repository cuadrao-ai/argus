import io
import struct
import sys
import threading
import time
import zlib
from types import SimpleNamespace

import psutil
import pytest
from argus.domain.ingestion.documents import rebuilt
from argus.domain.ingestion.documents.models import DocumentExtractionError
from loguru import logger
from PIL import Image, ImageDraw


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


@pytest.mark.skipif(sys.platform != "linux", reason="Linux OOM killer only")
def test_out_of_memory_kernel_kills_the_child_before_the_api(monkeypatch):
    """A large transparent image can exhaust a 512 MB instance; the kernel
    must then kill the child, which maps to a rejected image, not the API."""

    monkeypatch.setattr(
        rebuilt,
        "_IMAGE_REBUILD",
        "import sys; sys.stdout.write(open('/proc/self/oom_score_adj').read().strip())",
    )
    with open("/proc/self/oom_score_adj") as api:
        api_score = api.read()
    assert rebuilt.image_pixels(png(), "image/png") == 1000
    with open("/proc/self/oom_score_adj") as api:
        assert api.read() == api_score


@pytest.mark.parametrize("signal_number", [9, 15], ids=["SIGKILL", "SIGTERM"])
def test_killed_child_is_a_retryable_server_failure_logged_and_reaped(
    monkeypatch, tmp_path, signal_number
):
    """The kernel or the host killed the image child: the file is not judged,
    the read can be tried again, and the alert names the signal."""

    monkeypatch.setattr(rebuilt.tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(
        rebuilt,
        "_IMAGE_REBUILD",
        f"import os; os.kill(os.getpid(), {signal_number})",
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
        with pytest.raises(DocumentExtractionError) as failure:
            rebuilt.rebuild_image(png(), "image/png")
    finally:
        logger.remove(sink)
    assert failure.value.code == "document_preparation_interrupted"
    assert failure.value.retryable is True
    assert len(processes) == 1
    assert processes[0].returncode == -signal_number
    assert not list(tmp_path.iterdir())
    assert records[-1]["extra"]["signal"] == signal_number
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


def test_phone_photo_rebuild_fits_beside_the_api_on_a_512_mb_instance():
    """Staging runs the API at about 354 MB on a 512 MB instance, so the
    child rebuilding a 12 MP phone photo must stay under 150 MB."""

    photo = Image.new("RGB", (4032, 3024), "white")
    ImageDraw.Draw(photo).rectangle((400, 300, 3600, 2700), fill=(30, 90, 60))
    content = io.BytesIO()
    photo.save(content, format="JPEG", quality=85)
    del photo
    peak, done = 0, threading.Event()

    def sample():
        nonlocal peak
        while not done.is_set():
            for child in psutil.Process().children(recursive=True):
                try:
                    # Before exec a forked child still reports this process.
                    if "image/jpeg" in child.cmdline():
                        peak = max(peak, child.memory_info().rss)
                except psutil.Error:
                    pass
            time.sleep(0.001)

    sampler = threading.Thread(target=sample)
    sampler.start()
    try:
        copy = rebuilt.rebuild_image(content.getvalue(), "image/jpeg")
    finally:
        done.set()
        sampler.join()
    with Image.open(io.BytesIO(copy)) as image:
        assert image.size == (1600, 1200)
    assert 0 < peak < 150 * 1024 * 1024


def truncated_png() -> bytes:
    """A whole header, so the size reads, and half the pixel data."""

    content = png(400, 300)
    return content[: len(content) * 2 // 3]


@pytest.mark.parametrize(
    "content,media_type,code",
    [
        (oversized_png(6000, 5000), "image/png", "invalid_document"),
        (oversized_png(20000, 20000), "image/png", "invalid_document"),
        (png(frames=2), "image/png", "unsupported_image_frames"),
        (png(), "image/jpeg", "invalid_document"),
        (b"not an image", "image/png", "invalid_document"),
        (b"", "image/png", "document_empty"),
    ],
    ids=[
        "30-million-pixels",
        "decompression-bomb",
        "animated-png",
        "wrong-type",
        "not-an-image",
        "empty",
    ],
)
def test_upload_validation_still_refuses_what_the_rebuild_refused(
    monkeypatch, content, media_type, code
):
    from argus.domain.ingestion.documents.preparation import validate_source

    monkeypatch.setattr(
        Image, "open", lambda *a, **k: pytest.fail("parent decoded source")
    )
    with pytest.raises(DocumentExtractionError) as failure:
        validate_source(content, media_type)
    assert failure.value.code == code


def test_upload_validation_reads_the_header_and_leaves_the_rebuild_to_the_read(
    monkeypatch,
):
    """A photo whose header is sound passes the upload check from its header
    alone; a cut-off body is caught when the receipt is read, as before."""

    from argus.domain.ingestion.documents.preparation import (
        prepare_document,
        validate_source,
    )

    modes = []
    spawn = rebuilt.subprocess.Popen

    def track(args, **kwargs):
        modes.append(args[-1])
        return spawn(args, **kwargs)

    monkeypatch.setattr(rebuilt.subprocess, "Popen", track)
    validate_source(png(), "image/png")
    validate_source(truncated_png(), "image/png")
    assert modes == ["pixels", "pixels"]
    with pytest.raises(DocumentExtractionError) as failure:
        prepare_document(truncated_png(), "image/png")
    assert failure.value.code == "invalid_document"
