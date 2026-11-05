# Synthetic ingestion kit

A small, local rehearsal of **capture → proposal → review → confirmation →
saved record → correction**. Everything here is fictional and provisional.
These fixtures are **not evidence of real Dominican bank extraction accuracy**
and do not promise compatibility with any bank format.

## Run locally

Use the repository Poetry development environment (`poetry install --with dev`).
Faker supplies incidental fictional merchant names; deliberate scenarios determine
financial relationships. Pillow is already in the lockfile. Optional Poppler
`pdftotext` enables actual text extraction for the deliberately simple PDF;
`pdftoppm` renders a preview. Missing Poppler is reported as unsupported, never
as a successful PDF extraction. No credentials or services are required.

Generate a fresh sample set:

```bash
poetry run python -m tests.synthetic_ingestion.generate --seed 71 --output temp/synthetic-ingestion/samples
```

Run the scripted lifecycle rehearsal:

```bash
poetry run python -m tests.synthetic_ingestion run --samples temp/synthetic-ingestion/samples --state temp/synthetic-ingestion/state.json --report temp/synthetic-ingestion/report.json
```

The command simulates explicit reviewer actions. It is not an automatic
acceptance policy. Use a new state path for an independent run; reusing a state
path exercises persisted retry behavior. Local state belongs solely to this
harness and is not an Argus database or an authorization model.

Run focused tests without loading production test fixtures:

```bash
poetry run pytest tests/synthetic_ingestion --confcutdir=tests/synthetic_ingestion --no-cov -q
```

## What the samples establish

| Input | Boundary exercised | What remains untested |
| --- | --- | --- |
| Manual JSON | Loading explicitly entered structured fields | Production form/API integration |
| CSV | Actual bytes, rows, missing/ambiguous values, overlap | Any bank CSV compatibility |
| Text PDF | Actual `pdftotext` output and narrowly defined synthetic row grammar | General statement layout understanding |
| Spanish/English text | Authored stub proposals through review | Natural-language extraction/model quality |
| Spanish voice transcript | Authored stub proposals, self-correction, disfluency | Audio capture and STT |
| Receipt/scanned PNG | Source image and explicitly stubbed partial proposals | OCR accuracy |

The evaluation-only [manifest](samples/manifest.json) describes seed, formats,
scenarios, expected behavior, checksums and limitations. `*.stub.json` files are
separate, deliberately authored proposal inputs. Extraction never consults the
expected-answer manifest. No confidence scores are fabricated.

Known values use explicit currency codes and decimal strings. An unqualified
`$`, ambiguous date or number, missing account/amount/date, and unresolved
personal/household destination must remain visible for review. Transfers are
separate from income and expenses. Opening and closing balances describe a
statement, not additional activity. Totals describe only confirmed harness
records, separated by currency and destination; they are not available balances.

Two purchases can share a date, merchant and amount. Similarity alone must not
silently delete one. Exact-source retries keep their identity; overlapping
imports expose potential matches for a reviewer. Authored stub bytes also have a
digest: editing a stub produces a new review proposal, preserves the confirmed
record, and flags the same source row as a possible overlap even when its
financial fields changed. This scaffolding does not
solve cross-bank identity, general reconciliation or household permissions.

## Anchors to review by hand

- Statement: DOP 1,000.00 opening + 1,200.00 income − 125.50 − 125.50
  purchases + 25.50 refund = **DOP 1,974.50** closing.
- CSV: two separate purchases of DOP 125.50 remain distinct. A USD 40.00
  expense stays in its own currency. The DOP 200.00 transfer is not spending.
- Manual correction: confirming DOP 150.00 then correcting to DOP 175.00
  changes the expense total by DOP 25.00 and retains the old revision.
- Spanish transcript: the speaker corrects 300 to **250 DOP**. This is an
  authored downstream proposal, not proof that speech or language was understood.
- Receipt: one readable DOP 150.00 line cannot establish an unreadable total.

Same-seed generation is checked byte-for-byte in one managed environment.
PDF metadata is controlled; image metadata is omitted. Cross-version Faker,
font or renderer changes can change bytes: regenerate intentionally and inspect
artifacts rather than treating a checksum change as an extraction regression.

## Decisions exposed, not settled

Real implementation still needs contracts for transaction/account identity,
transfer pairing, balance reconciliation, supported locale formats, currency
resolution, source retention, secure upload limits, confirmation/undo, conflict
handling, and household destination versus document visibility. A destination
label here grants no permission and shares nothing.

## Later evaluation with real, consented documents

- Obtain explicit consent and agree retention/deletion before collection.
- Record institution, format, currency, period and page completeness accurately.
- Store originals securely; keep amounts, contents and identifiers out of logs.
- Have a person independently annotate fields and source spans; track disagreements.
- Hold out representative documents, including poor scans and uncommon layouts.
- Report field/row extraction errors separately from review and lifecycle success.
- Check missed/extra rows, currency, decimal/date ambiguity, transfers/refunds,
  overlaps, legitimate similar purchases and reconciliation discrepancies.
- Verify permission and source-document visibility boundaries with approved contracts.
- Name exactly the evaluated institution/format/version; expand coverage only
  when evidence supports it. Synthetic coverage never substitutes for this step.
