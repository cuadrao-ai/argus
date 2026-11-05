"""Real byte parsers and explicitly authored stubs, never expected-answer readers."""

import csv
import hashlib
import io
import json
import re
import shutil
import subprocess
from pathlib import Path

FIELDS = (
    "source_id",
    "date",
    "description",
    "amount",
    "currency",
    "kind",
    "account",
    "destination",
)


def load_input(path: Path, stub_path: Path | None = None) -> dict:
    path = Path(path)
    result = {"mode": "unsupported", "source_digest": "", "proposals": [], "errors": []}
    try:
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        result["source_digest"] = digest
        if stub_path is not None:
            stub_bytes = Path(stub_path).read_bytes()
            stub_digest = hashlib.sha256(stub_bytes).hexdigest()
            stub = json.loads(stub_bytes)
            if (
                stub.get("extraction_mode") != "stub"
                or stub.get("source_file") != path.name
            ):
                raise ValueError("Stub must declare stub mode and matching source_file")
            rows = stub["proposals"]
            result["mode"] = "stub"
        elif path.suffix == ".csv":
            reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
            if not reader.fieldnames or not set(FIELDS).issubset(reader.fieldnames):
                raise ValueError("CSV header missing required structural fields")
            rows = list(reader)
            result["mode"] = "actual_csv"
        elif path.suffix == ".json":
            rows = json.loads(content)["rows"]
            result["mode"] = "actual_manual_json"
        elif path.suffix == ".pdf" and shutil.which("pdftotext"):
            text = subprocess.run(
                ["pdftotext", "-layout", str(path), "-"],
                check=True,
                capture_output=True,
                text=True,
                timeout=20,
            ).stdout
            if "SYNTHETIC STATEMENT ROWS" not in text:
                raise ValueError("Unsupported PDF layout: synthetic table marker missing")
            table = text.split("SYNTHETIC STATEMENT ROWS", 1)[1].split(
                "END SYNTHETIC STATEMENT ROWS", 1
            )[0]
            for line in text.splitlines():
                match = re.fullmatch(
                    r"Opening (DOP|USD) ([0-9]+\.[0-9]{2}); Closing \1 ([0-9]+\.[0-9]{2})",
                    line.strip(),
                )
                if match:
                    result["balances"] = {
                        "currency": match[1],
                        "opening": match[2],
                        "closing": match[3],
                    }
            rows = list(
                csv.DictReader(
                    [line.strip() for line in table.splitlines() if "|" in line],
                    delimiter="|",
                )
            )
            rows = [
                {
                    key.strip() if isinstance(key, str) else key: value.strip()
                    if isinstance(value, str)
                    else value
                    for key, value in row.items()
                }
                for row in rows
            ]
            result["mode"] = "actual_synthetic_pdf_text"
        else:
            result["errors"].append(
                "Extraction unavailable; OCR/STT and natural-language interpretation are untested"
            )
            return result
        if not isinstance(rows, list):
            raise ValueError("Rows must be a list")
        for index, row in enumerate(rows, 1):
            if (
                not isinstance(row, dict)
                or None in row
                or not all(key in row and row[key] is not None for key in FIELDS)
            ):
                result["errors"].append(f"Row {index}: missing structural fields")
                continue
            ref = {"digest": digest, "file": path.name, "row": index}
            if result["mode"] == "actual_synthetic_pdf_text":
                ref["page"] = 1
            if result["mode"] == "stub":
                ref["stub_digest"] = stub_digest
                location = row.get("source_ref", {})
                ref.update(
                    {
                        key: location[key]
                        for key in (
                            "page",
                            "span",
                            "char_start",
                            "char_end",
                            "quote",
                            "region",
                        )
                        if key in location
                    }
                )
            result["proposals"].append(
                {"fields": {key: row[key] for key in FIELDS}, "source_ref": ref}
            )
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        result["errors"].append(f"{type(exc).__name__}: {exc}")
    return result
