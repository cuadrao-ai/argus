# Receipt read eval

This folder measures the AI document read on synthetic receipt photos. It scores
each field apart, so a change to the reader prompt can show what it fixed and
what it broke. It follows the Test Tiers in `tests/evals/README.md`.

Nothing here is a real receipt. Names are invented words, and every RNC starts
with 9 and has a valid check digit.

## The set

`cases.py` is one table. Each row says what a receipt prints and how the photo
was taken. The renderer draws the photo from the row, and `expected` derives the
answers from the same row. No image is committed. The set is drawn again on each
run, and the same row always gives the same bytes.

To look at the photos and their expected-answer files:

```bash
PYTHONPATH=src:web:. poetry run python -m tests.evals.document_read.dataset
```

It writes `temp/document_read_eval/<case>.jpg` and `<case>.expected.json`, and
prints the coverage table.

An expected answer holds the issue date, supplier RNC, buyer RNC, NCF or e-NCF,
total, ITBIS, forma de pago code, tipo de gasto code, whether a DGII QR is
readable, and whether the read is complete. `null` means the photo does not show
the value. Forma de pago and tipo de gasto codes come from
`src/argus/domain/business/dgii_codes.py`.

## Outcomes

| Outcome | Meaning |
| --- | --- |
| `correct` | The reader returned the printed value. |
| `correct_empty` | The photo does not show the value and the reader left it empty. |
| `false_fill` | The reader returned a value that is wrong, or a value for something the photo does not show. |
| `blank` | The photo shows the value and the reader left it empty. |
| `unsupported` | The reader has no field for it yet. `read_fields` in `scoring.py` is the one place to map a new field. |
| `judgment` | The expected tipo de gasto is a judgment. The read is reported and never scored. |
| `not_scored` | The photo holds several receipts. Only the purchase count is scored. |

A false fill with a known cause is also counted under `mistakes`, for example
`expiry_as_issue_date` and `buyer_rnc_as_supplier`.

The scorecard also reports the QR decode rate, the rate of reads that came back
incomplete or with an issue, and whether the complete judgment was right. A
provider failure is an `infrastructure_error` and is left out of every rate.

Every receipt read is scored on its purchase count, under `purchases`. A read
that returns one receipt from a photo of two counts as `wrong` there.

## Tipo de gasto

No accountant has checked the expected tipo de gasto codes. Each one carries a
basis, set per trade in `cases.py`:

| Basis | Trades | Scoring |
| --- | --- | --- |
| `clear` | Rent 03, insurance 11, computers and office furniture 10, office supplies and repair or maintenance service 02. | Scored as `correct`, `false_fill` or `blank`. |
| `judgment` | Every other trade: restaurant, staff meals, uniforms, grocery, hardware, pharmacy. | Reported with the read value. Never scored. |

The scorecard holds both under `expense_type`. `clear` gives the counts, the
accuracy and the false fill rate of the clear answers. `judgment` lists each
judgment receipt with its expected and read code. A blank on a clear answer
counts apart from a false fill, so a reader that leaves a hard one empty does
better than one that guesses. A later change to the reader prompt ships on the
`clear` numbers: high accuracy and few false fills.

## Mocked run

```bash
PYTHONPATH=src:web:. OPENROUTER_API_KEY= poetry run pytest \
  tests/evals/document_read -q --no-cov
```

This run is free and takes seconds. The image rebuild and the QR decoder run for
real. The provider call is replaced by a scripted read from `scripted.py`. A
green run shows that the set is well formed and that the scorer tells a correct
value, a false fill and a blank apart. It says nothing about how well a model
reads.

## Live run

Every read is a real provider call. Run it only at a gate in
`tests/evals/README.md`, with the spend approved.

```bash
PYTHONPATH=src:web:. poetry run python -m tests.evals.document_read.run_live \
  --out docs/reports/evidence/<name> \
  --env-file <untracked env file> --key-name OPENROUTER_API_KEY \
  --cap-usd 2.00
```

The key is the one `--key-name` names in the env file. The model is
`CUADRAO_VISION_MODEL` from the env file, or `--model`. Before the first read
the runner blanks every other model credential and document model that the
shell or the project `.env` holds. It stops if a read would use a different key
or model, and it never takes either from the shell. The run
makes one read per receipt and stops when the known cost reaches the cap. It
writes `scorecard.json` with schema `document_read_scorecard_v1`: the commit,
the model, digests of the prompt, the schema and the set, the cost, the totals
per field and per shape, and each receipt's expected and read values. Two
scorecards compare only when their `set_sha256` is equal.

## Limits

- The photos are drawn, not photographed. Paper curl, glare, blur and thermal
  fading are not in the set.
- The printed text has no accents, because the bundled font has none.
- Only the clear tipo de gasto answers are scored. See Tipo de gasto above.
  Receipts whose type depends on the buyer's business expect `null`.
- A photo of several receipts is scored on its purchase count only. Its fields,
  QR and complete judgment are `not_scored`, because the reader returns one
  receipt block.
- Forma de pago covers codes 01 to 04. Codes 05 to 07 are not in the set.
