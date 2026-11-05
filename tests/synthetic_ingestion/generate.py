"""Generate a compact synthetic corpus. No extraction or persistence occurs here."""

import argparse
import hashlib
import json
from decimal import Decimal
from pathlib import Path

from .factories import build_corpus, row
from .renderers import csv_bytes, write_image, write_pdf


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def generate(output: Path, seed: int = 71) -> dict:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    corpus = build_corpus(seed)
    write_json(output / "manual.json", {"synthetic": True, "rows": corpus["manual"]})
    for file, key in (
        ("transactions.csv", "transactions"),
        ("overlapping.csv", "overlap"),
    ):
        (output / file).write_bytes(csv_bytes(corpus[key]))
    write_pdf(output / "statement.pdf", corpus["statement"], corpus["balances"])
    write_pdf(
        output / "statement-overlap.pdf",
        [
            *corpus["statement"],
            row(
                "statement-05",
                Decimal("60"),
                date="2026-10-01",
                account="statement-dop",
                description="Synthetic new purchase",
            ),
        ],
        {"opening": "1000.00", "closing": "1914.50"},
        period="2026-09-10 to 2026-10-10",
    )
    write_image(output / "receipt.png")
    scan_locations = write_image(
        output / "scanned-statement.png",
        scanned_rows=corpus["stubs"]["scanned-statement.png"],
    )
    for file, text in corpus["texts"].items():
        (output / file).write_text(text, encoding="utf-8")
    quotes = {
        "conversation-es.txt": [
            "Gasté RD$350 en comida el 10 de septiembre de 2026, de mi efectivo personal.",
            "También pagué $20; no dije la moneda ni la cuenta.",
        ],
        "conversation-en.txt": [
            "I received USD 90 on 2026-09-10 in my personal cash account."
        ],
        "voice-transcript-es.txt": [
            "Eh... gasté trescientos, no, doscientos cincuenta pesos dominicanos ayer... bueno, fue el diez de septiembre de 2026, de mi efectivo personal.",
            "Y setecientos de la compra de casa, no sé si ponerlo personal o del hogar.",
        ],
    }

    def source_ref(file, index):
        if file in quotes:
            quote = quotes[file][index]
            start = corpus["texts"][file].index(quote)
            return {"char_start": start, "char_end": start + len(quote), "quote": quote}
        if file == "receipt.png":
            return {
                "page": 1,
                "region": [35, 425, 1050, 475],
                "label": "TOTAL DOP [ILEGIBLE]",
            }
        return scan_locations[index]

    for file, proposals in corpus["stubs"].items():
        write_json(
            output / f"{file}.stub.json",
            {
                "synthetic": True,
                "extraction_mode": "stub",
                "source_file": file,
                "limitations": "Authored proposals for lifecycle tests; not extraction or confidence evidence.",
                "proposals": [
                    {**proposal, "source_ref": source_ref(file, index)}
                    for index, proposal in enumerate(proposals)
                ],
            },
        )
    specs = [
        (
            "manual.json",
            "JSON",
            "manual cash expense, income and transfer",
            "actual",
            "Three explicit proposals; nothing saved until confirmation.",
        ),
        (
            "transactions.csv",
            "CSV",
            "mixed reliable rows and explicit ambiguities",
            "actual",
            "Six reliable rows; five exceptions. Preserve both identical purchases.",
        ),
        (
            "overlapping.csv",
            "CSV",
            "overlapping statement import",
            "actual",
            "tx-dop-01 repeats an existing source ID; overlap-new is distinct.",
        ),
        (
            "statement.pdf",
            "text PDF",
            "reconcilable fictional statement",
            "actual-when-pdftotext-available",
            "Opening DOP 1000.00 + 1200.00 - 125.50 - 125.50 + 25.50 = 1974.50.",
        ),
        (
            "statement-overlap.pdf",
            "text PDF",
            "overlapping statement periods",
            "actual-when-pdftotext-available",
            "September 10 to October 10 overlaps September statement; statement-01 through statement-04 repeat, statement-05 is new.",
        ),
        (
            "conversation-es.txt",
            "Spanish text",
            "explicit cash expense and ambiguous dollars",
            "stub",
            "One resolvable expense and one ambiguous currency/account proposal.",
        ),
        (
            "conversation-en.txt",
            "English text",
            "income versus hypothetical spending",
            "stub",
            "Only USD 90 income; hypothetical question is not a proposal.",
        ),
        (
            "voice-transcript-es.txt",
            "Spanish transcript",
            "disfluency, correction and household ambiguity",
            "stub",
            "Self-corrected amount is DOP 250; household destination remains unresolved.",
        ),
        (
            "receipt.png",
            "PNG receipt",
            "partially unreadable total",
            "stub",
            "Missing total prevents confirmation; visible item does not determine total.",
        ),
        (
            "scanned-statement.png",
            "PNG scanned-looking page",
            "partial extraction failure",
            "stub",
            "Reliable income can be confirmed; unreadable expense remains visible.",
        ),
    ]
    manifest = {
        "synthetic": True,
        "seed": seed,
        "schema_status": "provisional evaluation-only scaffolding",
        "disclaimer": "Fictional institutions and formats. No evidence of Dominican bank extraction accuracy.",
        "fixtures": [
            {
                "file": file,
                "format": fmt,
                "scenario": scenario,
                "seed": seed,
                "extraction_mode": mode,
                "expected_behavior": behavior,
                "sha256": hashlib.sha256((output / file).read_bytes()).hexdigest(),
                "limitations": "Synthetic only; authored stubs are separate from this expected-answer manifest.",
            }
            for file, fmt, scenario, mode, behavior in specs
        ],
        "anchors": {
            "statement_balances": corpus["balances"],
            "legitimate_twins": ["tx-dop-02", "tx-dop-03"],
            "ambiguous_currency": "tx-currency",
            "ambiguous_date": "tx-date",
            "ambiguous_number": "tx-number",
            "missing_fields": "tx-missing",
            "household_resolution": "tx-household",
            "post_confirmation_correction": {
                "source_id": "manual-expense",
                "original": "150.00",
                "corrected": "175.00",
                "currency": "DOP",
            },
        },
        "limitations": [
            "OCR and STT are untested. Local macOS say yielded zero audio bytes in the sandbox; voice fixtures remain transcripts only.",
            "No household permissions, canonical schema, FX conversion or real-bank support is modeled.",
            "Source IDs deliberately represent source provenance; similar merchant/amount values are not identity.",
            "Generated PDF format is intentionally simple; parsing it proves only this synthetic text path.",
        ],
    }
    write_json(output / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=71)
    args = parser.parse_args()
    generate(args.output, args.seed)
    print(f"Synthetic fixtures written to {args.output}; no extraction accuracy claim.")


if __name__ == "__main__":
    main()
