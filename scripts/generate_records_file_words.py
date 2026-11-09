"""Copy the es-419 words the Registros file uses from the web locale.

The locale owns the words; the server reads this generated copy so the file
says what the screen says. Run with --check in CI to prove they agree.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCALE = ROOT / "web" / "public" / "locales" / "es-419" / "common.json"
TARGET = (
    ROOT / "src" / "argus" / "domain" / "business" / "records_file_words.generated.json"
)
PATHS = (
    "business.dossier.placeholder.expense_type",
    "business.dossier.placeholder.payment_form",
    "business.dossier.standing.missing",
    "business.export.form_no_aplica",
    "business.transactions.columns.contraparte",
    "business.transactions.columns.cuenta",
    "business.transactions.columns.fecha",
    "business.transactions.columns.itbis",
    "business.transactions.columns.moneda",
    "business.transactions.columns.monto",
    "business.transactions.columns.ncf",
    "business.transactions.columns.notas",
    "business.transactions.layout.column_attachment",
    "business.transactions.layout.column_state",
    "business.transactions.layout.overview.purchases",
    "business.transactions.layout.overview.sales",
    "business.transactions.layout.workflow.exported",
    "business.transactions.layout.workflow.missing",
    "business.transactions.layout.workflow.ready",
    "business.transactions.layout.workflow.review",
    "common.no",
    "common.yes",
)


def build() -> str:
    locale = json.loads(LOCALE.read_text(encoding="utf-8"))
    words = {}
    for path in PATHS:
        value = locale
        for part in path.split("."):
            value = value[part]
        words[path] = value
    return json.dumps(words, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    expected = build()
    if parser.parse_args().check:
        if TARGET.read_text(encoding="utf-8") != expected:
            sys.stderr.write(f"{TARGET} is stale; run {Path(__file__).name}\n")
            return 1
        return 0
    TARGET.write_text(expected, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
