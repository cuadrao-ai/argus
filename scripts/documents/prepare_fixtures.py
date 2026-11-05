"""Regenerate fictional document fixtures locally without network or model calls."""

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2] / "tests/document_extraction_fixtures"


def write_pdf(path: Path, pages: list[list[str]]) -> None:
    """Extend the synthetic_ingestion renderer's deterministic PDF object layout."""
    page_ids = [4 + index * 2 for index in range(len(pages))]
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{' '.join(f'{n} 0 R' for n in page_ids)}] /Count {len(pages)} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>",
    ]
    for page_id, lines in zip(page_ids, pages, strict=True):
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 842 595] /Resources << /Font << /F1 3 0 R >> >> /Contents {page_id + 1} 0 R >>".encode()
        )
        escaped = [
            line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            for line in lines
        ]
        stream = (
            "BT /F1 11 Tf 30 550 Td 28 TL "
            + " ".join(f"({line}) Tj T*" for line in escaped)
            + " ET"
        ).encode("cp1252")
        objects.append(
            b"<< /Length "
            + str(len(stream)).encode()
            + b" >>\nstream\n"
            + stream
            + b"\nendstream"
        )
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    start = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode()
    )
    path.write_bytes(output)


def generate(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    specification = json.loads((ROOT / "synthetic-source.json").read_text())
    for sample in specification:
        path = output / sample["file"]
        if path.suffix == ".pdf":
            write_pdf(path, sample["pages"])
        else:
            image = Image.new("RGB", (1100, 700), (244, 241, 233))
            draw = ImageDraw.Draw(image)
            # Embedded bitmap glyphs avoid host FreeType rasterization differences.
            font = ImageFont.load_default_imagefont()
            for index, line in enumerate(sample["pages"][0]):
                bounds = font.getbbox(line)
                glyphs = Image.new("L", (bounds[2], bounds[3]))
                ImageDraw.Draw(glyphs).text((0, 0), line, fill=255, font=font)
                glyphs = glyphs.resize(
                    (glyphs.width * 3, glyphs.height * 3), Image.Resampling.NEAREST
                )
                image.paste((40, 40, 40), (35, 35 + index * 65), glyphs)
            if sample["id"] == "unreadable":
                draw.rectangle((30, 155, 1060, 640), fill=(80, 80, 80))
            image.save(path)
    manifest_path = ROOT / "manifest.json"
    if manifest_path.exists() and output == ROOT:
        manifest = json.loads(manifest_path.read_text())
        for sample in manifest["samples"]:
            sample["sha256"] = hashlib.sha256(
                (output / sample["file"]).read_bytes()
            ).hexdigest()
            if "original_labels" in sample:
                sample["labels_sha256"] = hashlib.sha256(
                    (output / sample["original_labels"]).read_bytes()
                ).hexdigest()
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT)
    generate(parser.parse_args().output)
