import io

import pytest
from argus.domain.ingestion.documents.models import DocumentExtractionError
from argus.domain.ingestion.documents.preparation import prepare_document
from PIL import Image, PngImagePlugin


def test_image_preparation_strips_metadata():
    source = io.BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("private", "private gps and owner")
    Image.new("RGB", (40, 40), "white").save(source, format="PNG", pnginfo=metadata)
    result = prepare_document(source.getvalue(), "image/png")
    assert result.pages == 1
    assert result.text is None
    assert b"private" not in result.images[0]


@pytest.mark.parametrize(
    "content,media_type,code",
    [
        (b"", "image/png", "empty_document"),
        (b"not an image", "image/png", "invalid_document"),
        (b"hello", "application/zip", "unsupported_media_type"),
    ],
)
def test_invalid_inputs_fail_safely(content, media_type, code):
    with pytest.raises(DocumentExtractionError) as error:
        prepare_document(content, media_type)
    assert error.value.code == code


def test_pdf_preparation_preserves_all_pages_and_cleans_temporary_source(
    monkeypatch, tmp_path
):
    import shutil
    from pathlib import Path

    from argus.domain.ingestion.documents import preparation

    if not all(shutil.which(tool) for tool in ("pdfinfo", "pdftotext", "pdftoppm")):
        pytest.skip("Poppler runtime unavailable")
    monkeypatch.setattr(preparation.tempfile, "tempdir", str(tmp_path))
    content = (
        Path(__file__).parents[1] / "document_extraction_fixtures" / "statement-dop.pdf"
    ).read_bytes()
    result = prepare_document(content, "application/pdf")
    assert result.pages == 2
    assert len(result.images) == result.pages
    assert result.text
    assert not list(tmp_path.iterdir())


def test_pdf_page_limit_before_render(monkeypatch):
    from argus.domain.ingestion.documents import preparation
    from argus.domain.ingestion.documents.config import DocumentExtractionSettings

    calls = []

    def run(args, output):
        calls.append(args)
        output.write_text("Pages: 9\nEncrypted: no\n")

    monkeypatch.setattr(preparation, "_run", run)
    with pytest.raises(DocumentExtractionError, match="document_page_limit"):
        prepare_document(b"%PDF-source", "application/pdf", DocumentExtractionSettings())
    assert len(calls) == 1


def test_encrypted_pdf_never_reaches_vision(monkeypatch):
    from argus.domain.ingestion.documents import preparation

    monkeypatch.setattr(
        preparation,
        "_run",
        lambda args, output: output.write_text("Pages: 1\nEncrypted: yes (print:yes)\n"),
    )
    with pytest.raises(DocumentExtractionError, match="encrypted_document"):
        prepare_document(b"%PDF-source", "application/pdf")


def test_subprocess_output_is_capped_before_it_can_fill_disk(tmp_path):
    import sys

    from argus.domain.ingestion.documents.preparation import MAX_TEXT_BYTES, _run

    output = tmp_path / "output.txt"
    with pytest.raises(DocumentExtractionError, match="document_text_limit"):
        _run(
            [sys.executable, "-c", 'import sys; sys.stdout.write("x" * 1000000)'], output
        )
    assert output.stat().st_size <= MAX_TEXT_BYTES


def test_transparent_photos_are_composited_on_white():
    source = io.BytesIO()
    Image.new("RGBA", (5, 5), (0, 0, 0, 0)).save(source, format="PNG")
    result = prepare_document(source.getvalue(), "image/png")
    with Image.open(io.BytesIO(result.images[0])) as rendered:
        assert rendered.getpixel((0, 0)) == (255, 255, 255)
