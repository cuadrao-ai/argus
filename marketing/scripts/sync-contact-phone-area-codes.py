"""Build the contact phone area-code allowlist from the public NPA report."""

import argparse
import csv
import io
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen

SOURCE_URL = "https://reports.nanpa.com/public/npa_report.csv"
OUTPUT = Path(__file__).resolve().parents[1] / "lib/contact-phone-area-codes.ts"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Use a downloaded CSV instead of fetching it")
    args = parser.parse_args()
    if args.input:
        source = args.input.read_text(encoding="utf-8-sig")
    else:
        with urlopen(SOURCE_URL, timeout=30) as response:
            source = response.read().decode("utf-8-sig")

    lines = io.StringIO(source, newline="")
    report_date = next(csv.reader([lines.readline()]))
    if report_date[0] != "File Date" or len(report_date) < 2:
        raise ValueError("Missing report date")
    datetime.strptime(report_date[1], "%m/%d/%Y")
    rows = csv.DictReader(lines)
    required = {"NPA_ID", "COUNTRY", "USE", "IN_SERVICE"}
    if not required.issubset(rows.fieldnames or []):
        raise ValueError("Missing required NPA report columns")
    selected = [
        row for row in rows
        if row["COUNTRY"] in {"US", "DOMINICAN REPUBLIC"}
        and row["USE"] == "G"
        and row["IN_SERVICE"] == "Y"
    ]
    if {row["NPA_ID"] for row in selected if row["COUNTRY"] == "DOMINICAN REPUBLIC"} != {"809", "829", "849"}:
        raise ValueError("NPA report is missing Dominican Republic area codes")
    codes = sorted({row["NPA_ID"] for row in selected})
    if not codes or any(len(code) != 3 or not code.isdecimal() for code in codes):
        raise ValueError("NPA report contains no valid area codes")

    groups = [codes[index:index + 20] for index in range(0, len(codes), 20)]
    entries = "\n".join("  " + ", ".join(f'"{code}"' for code in group) + "," for group in groups)
    OUTPUT.write_text(
        f"// Source: {SOURCE_URL} (File Date {report_date[1]}).\n"
        "// Refresh: python3 marketing/scripts/sync-contact-phone-area-codes.py [--input path/to/npa_report.csv]\n"
        "// Geographic, in-service area codes assigned to US or DOMINICAN REPUBLIC.\n"
        f"export const CONTACT_PHONE_AREA_CODES = new Set([\n{entries}\n]);\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
