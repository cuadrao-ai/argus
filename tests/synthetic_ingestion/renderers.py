"""Small deterministic renderers, with no production imports or PDF dependencies."""

import csv
import io
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .factories import FIELDS


def csv_bytes(rows: list[dict], delimiter: str = ",") -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer, fieldnames=FIELDS, lineterminator="\n", delimiter=delimiter
    )
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def write_pdf(
    path: Path, rows: list[dict], balances: dict, *, period="2026-09-01 to 2026-09-30"
) -> None:
    """One text-bearing page. No timestamps, random IDs or platform font metadata."""
    lines = [
        "SYNTHETIC - FICTIONAL - NOT A REAL BANK FORMAT",
        "Banco Nube de Papel (fictional)",
        f"Statement period: {period}; account statement-dop",
        f"Opening DOP {balances['opening']}; Closing DOP {balances['closing']}",
        "SYNTHETIC STATEMENT ROWS",
        *[
            line.replace("|", " | ")
            for line in csv_bytes(rows, "|").decode().splitlines()
        ],
        "END SYNTHETIC STATEMENT ROWS",
        "Positive amounts; expense subtracts, income/refund adds.",
    ]
    escaped = [
        line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        for line in lines
    ]
    commands = (
        "BT /F1 8 Tf 30 760 Td 15 TL "
        + " ".join(f"({line}) Tj T*" for line in escaped)
        + " ET"
    )
    stream = commands.encode("cp1252")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 842 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>",
        b"<< /Length "
        + str(len(stream)).encode()
        + b" >>\nstream\n"
        + stream
        + b"\nendstream",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    start = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode()
    )
    path.write_bytes(output)


def write_image(path: Path, *, scanned_rows: list[dict] | None = None) -> list[dict]:
    """Render authored scan rows and return their actual page locations together."""
    scanned = scanned_rows is not None
    image = Image.new("RGB", (1100, 700), (244, 241, 233) if scanned else "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=23)
    lines = ["SYNTHETIC / FICTICIO", "No actual bank format; fictional institution."]
    scan_line_indices = []
    if scanned_rows is not None:
        lines += [
            "Banco Nube de Papel - SCANNED-LOOKING PAGE",
            "Period 2026-09-01 to 2026-09-30",
            f"Account {scanned_rows[0]['account']}; {scanned_rows[0]['currency']}",
        ]
        for entry in scanned_rows:
            scan_line_indices.append(len(lines))
            kind = "Ingreso" if entry["kind"] == "income" else "Gasto"
            amount = entry["amount"] if entry["amount"] else "[ILEGIBLE]"
            lines.append(
                f"{entry['date']} {kind}: {amount} | destino: {entry['destination']}"
            )
        lines.append("Saldo inicial: 1000.00; Saldo final: [ILEGIBLE]")
    else:
        lines += [
            "Colmado Ficticio La Nube",
            "2026-09-10 | cash-dop | personal",
            "Arroz DOP 150.00",
            "Otro producto [ILEGIBLE]",
            "TOTAL DOP [ILEGIBLE]",
            "No deducir el total de los productos visibles.",
        ]
    locations = []
    for i, line in enumerate(lines):
        y = 35 + i * 65
        draw.text((40, y), line, fill=(45, 45, 45), font=font)
        if i in scan_line_indices:
            locations.append({"page": 1, "region": [35, y, 1050, y + 40], "label": line})
    draw.rectangle((20, 20, 1080, 655), outline=(110, 105, 100), width=2)
    draw.line((35, 190, 1060, 190), fill=(110, 105, 100), width=2)
    if scanned_rows is not None:
        # Deterministic grain and partial occlusion emulate a scanned page.
        rng = random.Random(71)
        for _ in range(18000):
            point = (rng.randrange(1100), rng.randrange(700))
            shade = rng.randrange(170, 235)
            draw.point(point, fill=(shade, shade, shade))
        for entry, location in zip(scanned_rows, locations, strict=True):
            if not entry["amount"]:
                y = location["region"][1]
                kind = "Ingreso" if entry["kind"] == "income" else "Gasto"
                prefix = f"{entry['date']} {kind}: "
                left = draw.textbbox((40, y), prefix, font=font)[2]
                amount_bounds = draw.textbbox((left, y), "[ILEGIBLE]", font=font)
                draw.rectangle(amount_bounds, fill=(170, 166, 155))
        # Fixed streaks emulate scanning; no stochastic metadata or noise.
        for y in (153, 326, 521):
            draw.line((15, y, 1080, y + 2), fill=(180, 178, 170), width=2)
    image.save(path, format="PNG", optimize=False)
    return locations
