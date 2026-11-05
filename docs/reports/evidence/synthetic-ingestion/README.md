# Synthetic ingestion verification report

This is evidence of local mechanics using fictional data. It is **not evidence
of real Dominican bank extraction accuracy**, supported bank formats, OCR/STT
quality, household authorization, or production ingestion readiness.

## Scope and provenance

- Original integration base: `ab9143c18740c28f582646d405445c01c4c8aff4`.
- Lane: `codex/synthetic-ingestion-harness`, dedicated managed worktree.
- Scope: `tests/synthetic_ingestion/`, its lane spec and this evidence directory.
- No production routes, schemas, RLS, auth, prompts, financial calculations,
  analytics, CI configuration, security work or disposable demo changed.
- Sample seed: **71**. Runtime: Python 3.10.20, Faker 30.10.0.
- See the PR terminal audit for final head, current integration, CI and review
  disposition. This checked-in report describes the acceptance procedure;
  it does not assert a terminal PR state ahead of review.

## Actual extraction results

The local loader reads input bytes and never reads the expected-answer manifest.
Tests remove the manifest and mutate input bytes independently to verify that
separation. No pre-existing local document/OCR ingestion implementation was
found in the inspected production/test code; existing extraction helpers concern
chat interpretation and asset discovery, so they were not repurposed.

| Path | Actual result in this environment | Limit |
| --- | --- | --- |
| Manual JSON | 3 structured proposals loaded | Manual fields, not language extraction |
| CSV | 11 rows plus 2 overlap rows parsed | Our explicit synthetic column grammar only |
| Text statement PDF | 4 rows and opening/closing balance extracted | Poppler plus our narrow text grammar |
| Overlapping PDF | 5 rows parsed, repeated references flagged | Synthetic period and identifiers only |
| Spanish/English text | Unsupported without authored stub | No model evaluation |
| Voice transcript | Unsupported without authored stub | Text is not audio |
| Receipt and scan PNG | Unsupported without authored stub | No OCR |

`pdftotext` is optional. When absent, the PDF path reports unsupported and the
PDF-specific tests skip with a reason. CSV and lifecycle tests remain runnable.
The saved [first run](lifecycle-run.json) and [persisted retry](lifecycle-retry.json)
report these statuses separately from successful stub-driven mechanics.

## Working lifecycle mechanics

The scripted rehearsal loads inputs, creates proposals, reviews exceptions,
explicitly confirms reliable batches, rejects a repeated entry, resolves a
currency by a labeled simulated user decision, reloads persisted records, retries
an identical source and corrects a confirmed expense with history.

A fresh run confirms **20 records**. Repeating the command on the same state
keeps **20 records**. The actual PDF reconciliation yields:

`DOP 1000.00 + 1200.00 - 125.50 - 125.50 + 25.50 = DOP 1974.50`.

The scripted correction from DOP 150.00 to 175.00 changes confirmed net expense
from DOP 1351.00 to 1376.00. USD expense stays 40.00 and USD income stays 90.00.
These are corpus totals, not a claim of a person's complete financial position.
Unresolved entries, rejected entries and source balances do not enter totals.
Transfers remain separate from spending and income. Local writes use atomic
replacement with memory rollback on failure; this is single-process scaffolding.

## Verification and visual review

- Focused pytest checks cover independent anchors, actual parsing, identical
  generation bytes, ambiguity, partial failure, batch confirmation, rejection,
  retries, overlap, legitimate similar purchases, reload, correction history,
  persistence failure, changed-stub provenance and production-import isolation.
- Generated the complete corpus twice with seed 71 and compared every byte.
  Controlled PDF metadata and metadata-free PNGs keep local runs reproducible.
- Opened both PDF renders, the receipt and scanned page. Labels and fields were
  readable; deliberate unreadable fields remained visibly marked. Durable PDF
  renders: [statement](statement-preview.png),
  [overlap](statement-overlap-preview.png). PNG originals are in the committed
  [sample set](../../../../tests/synthetic_ingestion/samples/).
- Independent review caught and corrected scan source-location/date disagreement
  by deriving the rendered rows and authored proposals from one fixture owner.
- Hosted review caught stale proposal reuse after an authored stub edit. Stub
  digests now version extraction identity; changed proposals return to review
  and cannot overwrite or silently duplicate confirmed records. Regression
  tests first reproduced amount, source-location and identity-field changes.
- No browser/product surface was changed; no real API, paid evaluation or
  customer document was used.

## Mocked and untested boundaries

All conversation interpretation, transcript interpretation and image extraction
use explicit `*.stub.json` authored proposals. They have no confidence scores and
are never counted as extraction success. Image/character locations link back to
the source, but do not turn a stub into OCR/STT evidence.

Local macOS speech synthesis was attempted; the output contained zero audio
bytes, so no usable audio is included. Audio capture, synthesis quality and STT
remain untested. No provider was selected or installed.

## Environment and broad-check limitations

Faker was verified in the repository-managed Poetry environment. The dedicated
worktree initially had an empty environment; validation reused the existing
managed environment without changing it. Full-suite collection exposed an
existing SciPy macOS binary loader error. The locked SciPy 1.15.3 macOS 12 arm64
wheel was installed only under `/private/tmp` and put first on `PYTHONPATH` for
broad local checks; both `scipy` and `scipy.linalg` imports then passed.

The existing backend suite finished with 9,036 passes, 617 skips and 20
failures caused by a missing local frontend dependency. After installing
`bun install --frozen-lockfile` in this dedicated worktree, the affected
`tests/test_result_card_gain.py` file passed all 20 tests. Broad-suite coverage
was 89%. The mocked eval harness checks ran within that suite. The isolated
ingestion suite passes all 46 checks.

The blanket `ruff check .` encountered 390 existing errors in archived evidence
scripts. Those files were preserved. The actual CI lint scope is
`ruff check src tests workflows scripts`; final results are in the PR audit.
Ownership verification reports no registered policy for this branch. Integration
reconciliation and merged-tree modularity are checked before the final PR audit.

## Decisions exposed

This rehearsal leaves production identity/deduplication, transfer pairing,
reconciliation, locale parsing, storage/retention, concurrent edits, and household
visibility/permission contracts unresolved. The destination label does not grant
access or share a document. The future consented-document evaluation checklist
and reproducible commands are in the [kit instructions](../../../../tests/synthetic_ingestion/README.md).
