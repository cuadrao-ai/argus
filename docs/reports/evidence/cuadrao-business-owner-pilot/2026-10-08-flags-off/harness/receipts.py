"""Synthetic receipts per seeded owner tag, and the stub's fixed reads keyed by sha256."""

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
FONT = ImageFont.load_default(size=22)
KINDS = {
    "personal": ["SUPERMERCADO NACIONAL (SYNTHETIC)", "Fecha: 2026-10-06", "TOTAL RD$ 1,200.00"],
    "bizconfirm": ["FERRETERIA LA ESQUINA SRL (SYNTHETIC)", "Fecha: 2026-10-06", "Pintura 1 gal 1,850.00", "TOTAL RD$ 1,850.00"],
    "bizinbox": ["FARMACIA CAROL (SYNTHETIC)", "Fecha: 2026-10-05", "TOTAL RD$ 498.00"],
    "wa": ["COLMADO DON PEDRO (SYNTHETIC)", "Fecha: 2026-10-07", "TOTAL RD$ 706.10"],
}
READS = {
    "bizconfirm": ("FERRETERIA LA ESQUINA SRL", "2026-10-06", "1850.00"),
    "wa": ("COLMADO DON PEDRO", "2026-10-07", "706.10"),
}


def _read(merchant: str, day: str, total: str) -> dict:
    purchase = {"page": 1, "row": 1, "evidence": "transaction", "status": "posted", "amount": total,
                "currency": "DOP", "occurred_on": day, "direction": "outflow", "kind_hint": "expense",
                "merchant": merchant}
    details = {"merchant": merchant, "occurred_on": day, "currency": "DOP",
               "items": [{"id": "1", "description": merchant, "total": total}], "tax": "0.00", "total": total}
    return {"complete": True, "readable": True, "pages_read": [1], "observations": [purchase], "receipt": details}


def make(tag: str, media_id: str) -> dict[str, bytes]:
    out = {}
    for kind, lines in KINDS.items():
        lines = [*lines, "", "SAMPLE DATA - NOT A REAL RECEIPT", f"owner {tag}"]
        image = Image.new("RGB", (560, 60 + 34 * len(lines)), "#fffdf7")
        draw = ImageDraw.Draw(image)
        for index, line in enumerate(lines):
            draw.text((24, 30 + index * 34), line, fill="#191c1f", font=FONT)
        path = HERE / "receipts" / f"{tag}-{kind}.png"
        path.parent.mkdir(exist_ok=True)
        image.save(path, format="PNG")
        out[kind] = path.read_bytes()
    reads_path = HERE / "reads.json"
    reads = json.loads(reads_path.read_text()) if reads_path.exists() else {}
    for kind, args in READS.items():
        reads[hashlib.sha256(out[kind]).hexdigest()] = _read(*args)
    reads_path.write_text(json.dumps(reads, indent=1))
    (HERE / "media").mkdir(exist_ok=True)
    (HERE / "media" / f"{media_id}.png").write_bytes(out["wa"])
    return out
