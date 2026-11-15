"""Keep the site's copies of the phone rule equal to the server owner.

The server owns the area codes and the agreed cases. The site cannot read the
server's files, so it holds generated copies and `--check` proves they match.
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
SOURCE_URL = "https://reports.nanpa.com/public/npa_report.csv"
OWNER_CODES = "src/argus/domain/business/phone_area_codes.py"
OWNER_CASES = "tests/business/phone_rule_cases.json"
SITE_CODES = "marketing/lib/contact-phone-area-codes.ts"
SITE_CASES = "marketing/__tests__/phone-rule-cases.generated.json"
SCOPE = "Geographic, in-service area codes assigned to US or DOMINICAN REPUBLIC."


def report_codes(source: str) -> tuple[str, list[str]]:
    """The report's date and the area codes the rule accepts."""
    lines = io.StringIO(source, newline="")
    report_date = next(csv.reader([lines.readline()]))
    if report_date[0] != "File Date" or len(report_date) < 2:
        raise ValueError("Missing report date")
    datetime.strptime(report_date[1], "%m/%d/%Y")
    rows = csv.DictReader(lines)
    if not {"NPA_ID", "COUNTRY", "USE", "IN_SERVICE"}.issubset(rows.fieldnames or []):
        raise ValueError("Missing required NPA report columns")
    selected = [
        row
        for row in rows
        if row["COUNTRY"] in {"US", "DOMINICAN REPUBLIC"}
        and row["USE"] == "G"
        and row["IN_SERVICE"] == "Y"
    ]
    dominican = {
        row["NPA_ID"] for row in selected if row["COUNTRY"] == "DOMINICAN REPUBLIC"
    }
    if dominican != {"809", "829", "849"}:
        raise ValueError("NPA report is missing Dominican Republic area codes")
    codes = sorted({row["NPA_ID"] for row in selected})
    if not codes or any(len(code) != 3 or not code.isdecimal() for code in codes):
        raise ValueError("NPA report contains no valid area codes")
    return report_date[1], codes


def rows_of(codes: list[str], width: int) -> list[list[str]]:
    return [codes[index : index + width] for index in range(0, len(codes), width)]


def owner_text(file_date: str, codes: list[str]) -> str:
    body = "\n".join("    " + " ".join(row) for row in rows_of(codes, 16))
    return (
        '"""Area codes a phone may use. Generated; do not edit.\n\n'
        f"Source: {SOURCE_URL} (File Date {file_date}).\n"
        "Refresh: python3 scripts/sync_phone_rule.py --refresh "
        "[--input path/to/npa_report.csv]\n"
        f"{SCOPE}\n"
        '"""\n\n'
        f'PHONE_AREA_CODES = frozenset(\n    """\n{body}\n    """.split()\n)\n'
    )


def owner_codes() -> tuple[str, list[str]]:
    text = (ROOT / OWNER_CODES).read_text(encoding="utf-8")
    file_date = re.search(r"File Date (\d{2}/\d{2}/\d{4})", text)
    codes = re.findall(r"\b\d{3}\b", text.split("frozenset(", 1)[1])
    if not file_date or not codes or text != owner_text(file_date[1], codes):
        raise ValueError(f"{OWNER_CODES} is not in its generated form; run --refresh")
    return file_date[1], codes


def site_codes_text(file_date: str, codes: list[str]) -> str:
    entries = "\n".join(
        "  " + ", ".join(f'"{code}"' for code in row) + "," for row in rows_of(codes, 20)
    )
    return (
        f"// Generated from {OWNER_CODES} by scripts/sync_phone_rule.py. Do not edit.\n"
        f"// Source: {SOURCE_URL} (File Date {file_date}).\n"
        f"// {SCOPE}\n"
        f"export const CONTACT_PHONE_AREA_CODES = new Set([\n{entries}\n]);\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check", action="store_true", help="Fail when a site copy differs"
    )
    mode.add_argument(
        "--refresh", action="store_true", help="Rewrite the server list from the report"
    )
    parser.add_argument(
        "--input", type=Path, help="With --refresh, a downloaded report CSV"
    )
    args = parser.parse_args()
    if args.refresh:
        if args.input:
            source = args.input.read_text(encoding="utf-8-sig")
        else:
            with urlopen(SOURCE_URL, timeout=30) as response:
                source = response.read().decode("utf-8-sig")
        (ROOT / OWNER_CODES).write_text(
            owner_text(*report_codes(source)), encoding="utf-8"
        )
    copies = {
        SITE_CODES: site_codes_text(*owner_codes()),
        SITE_CASES: (ROOT / OWNER_CASES).read_text(encoding="utf-8"),
    }
    stale = [
        path
        for path, text in copies.items()
        if not (ROOT / path).is_file()
        or (ROOT / path).read_text(encoding="utf-8") != text
    ]
    if args.check:
        for path in stale:
            print(f"{path} differs from its server owner: run scripts/sync_phone_rule.py")
        return int(bool(stale))
    for path in stale:
        (ROOT / path).write_text(copies[path], encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
