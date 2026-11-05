# What the synthetic ingestion kit proves

This file is the evaluation for [issue 717](https://github.com/lagarcess/argus/issues/717). The kit is `tests/synthetic_ingestion/` on `codex/private-alpha-next`, merged from pull request 709 as `61ef59d1`. `docs/reports/evidence/synthetic-ingestion/README.md` is the kit author's run record. This file evaluates that merged kit.

## A passing run proves review mechanics

A run takes fictional files through a proposal, an explicit confirmation, a local JSON record, a retry, and a correction. `Harness` in `harness.py` owns those steps. `load_input` in `extract.py` owns the byte read. Extraction never opens `samples/manifest.json`.

Manual JSON and the CSV files are parsed from their own bytes. The modes are `actual_manual_json` and `actual_csv`. The statement PDF reaches mode `actual_synthetic_pdf_text` only when `pdftotext` is installed and its layout text contains all three of these. The marker is `SYNTHETIC STATEMENT ROWS`. The pipe table header is `source_id`, `date`, `description`, `amount`, `currency`, `kind`, `account`, and `destination`. The balance line is `Opening DOP 1000.00; Closing DOP 1974.50`.

Conversation text, the voice transcript, the receipt PNG, and the scanned PNG return mode `unsupported` and an empty proposal list. If the caller passes the sibling stub, the mode becomes `stub`. A stub must set `extraction_mode` to `stub` and must name the source file. Passing the manifest as a stub produces an error and an empty proposal list.

`field_issues` admits a row only when every field is inside the harness literals. The date is ISO. The amount is a positive dot-decimal with at most two places. The currency is `DOP` or `USD`. The kind is `expense`, `refund`, `income`, or `transfer`. Account, description, and source id are non-blank. Destination is `personal` or `household`. Rejected rows and unresolved rows stay out of `Harness.totals`. DOP and USD stay in separate groups. A refund subtracts from the expense group. A transfer stays in its own group.

Row identity is the SHA-256 of `digest:row`, plus the stub digest when a stub is present. A second ingest of the same bytes reuses that id. `confirm` on an existing record adds nothing. A changed stub gets a new id, stays proposed, and leaves the saved record and its totals in place. If `os.replace` fails during save, `Harness` restores the last committed state.

Importing `tests.synthetic_ingestion.harness` does not load the `argus` package.

This evaluation ran the 46 checks in `tests/synthetic_ingestion` with `--confcutdir=tests/synthetic_ingestion` and coverage addopts cleared. All 46 passed. `pdftotext` 24.02.0 was present, so the PDF checks ran. The interpreter was Python 3.12.3. The repo pins Python 3.10.20. Faker 30.10.0 and Pillow 12.2.0 match `poetry.lock`.

The script in `__main__.py`, pointed at the committed samples, confirmed 20 records. A second `Harness` on the same state file reproduced the totals. Reconciliation read the PDF bytes. Opening `1000.00` plus activity `974.50` equaled closing `1974.50` DOP. The script then changed the manual lunch from `150.00` to `175.00`. DOP personal expense moved from `1351.00` to `1376.00`. USD expense stayed `40.00`. USD income stayed `90.00`.

`run` contains those three decisions. It rejects overlapping `tx-dop-01`, sets the `$` row to `DOP`, and writes the `175.00` correction. The report labels each action `explicit_simulated_*`. This execution had no separate human review.

## The fixtures already speak the harness schema

`build_corpus` in `factories.py` chooses the money. Faker `es_ES` with seed 71 supplies one surname. The CSV merchant is `Comercio Ficticio Morante`. Every reliable amount is a `Decimal` printed with two places and a dot. Reliable dates are `2026-09-10`. Reliable currencies are `DOP` or `USD`. Destination on those rows is `personal`.

The five CSV exceptions each break one rule.

- `tx-currency` uses `$`.
- `tx-date` uses `03/04/2026`.
- `tx-number` uses `1.234,56`.
- `tx-missing` leaves the date, amount, and account empty.
- `tx-household` sets destination to the string `personal or household`.

`write_pdf` in `renderers.py` emits one Courier page in WinAnsi. The closing balance is the sum of the four statement rows in the same corpus. `1000.00 + 1200.00 - 125.50 - 125.50 + 25.50 = 1974.50`. The purchase lines are `Synthetic purchase A` and `Synthetic purchase B`. The descriptions differ. The identical pair is the CSV twins in the next paragraph. The institution line reads `Banco Nube de Papel (fictional)`. The account label is `statement-dop`. The page contains the balance line and those movement rows. It has no debit column, credit column, running balance, commission, ITBIS, or interest.

`tx-dop-02` and `tx-dop-03` share the date, the merchant, the amount, and the currency. Both confirm on the first ingest of that CSV. `Harness._issues` skips signature comparison for two rows of the same file digest, and each row has its own `source_id`. A later file is marked `possible_overlap` in two cases. One case is a match on source id, account, and currency against a row from another file. The other case is a match on date, description, amount, currency, kind, and account. The overlap PDF repeats `statement-01` through `statement-04` under the same source ids, so those four stay proposed. `statement-05` has a new id and confirms.

`generate.py` writes the conversation, voice, receipt, and scan proposals from the same dictionaries that write the source files. The voice file begins `TRANSCRIPCIÓN SINTÉTICA, NO AUDIO.` The receipt draws `TOTAL DOP [ILEGIBLE]`, and the stub amount is empty. The scan draws each amount from the stub, then covers an empty amount with a rectangle. The grain is `random.Random(71)`. No OCR function and no speech function run.

## A real Dominican statement has to show these facts

The figures above describe this corpus. They describe a real account after the statement supplies the facts the corpus invents, and after a person maps each movement into the eight fields. The fields are `source_id`, `date`, `description`, `amount`, `currency`, `kind`, `account`, and `destination`. A CSV without that header fails before any total is computed. A PDF without the synthetic marker fails in the same way. A bank PDF with a complete text layer still fails that check.

The page has to show the institution, the product, the account, and whether the account is pesos or dollars. The kit accepts only the currency codes `DOP` and `USD`. It reads neither `RD$` nor a bank name as a currency.

The page has to include the statement period and every page of that period. The PDF path stores page `1` on every row. Pages absent from the file never enter the closing check.

The page has to show the opening balance, the closing balance, and every posted movement between them. The list covers commissions, ITBIS, interest, ATM fees, and reversals. The `1974.50` match holds because `build_corpus` wrote the closing line and the four movements together. On a bank page that match covers the account when both balances and the full movement list come from that page.

Each movement has to show the printed date, the printed description, the amount, and whether the bank presents a debit, a credit, or a transfer. The kit also requires `kind` and `destination`. Bank pages print neither `expense` nor `personal`. A person assigns those from the printed line. Until that assignment is reviewed on the bank's lines, the confirmed totals remain the script's totals.

When two purchases share a date, a merchant, and an amount, the page has to show a reference, a time, or an authorization if those purchases are distinct. The kit separates `tx-dop-02` from `tx-dop-03` by row index and `source_id`. A page that prints only the date, the merchant, and the amount has no field for that twin result to match.

An amount written as `RD$`, `$`, or `US$` has to carry a currency the account or the line states. `field_issues` accepts digits with an optional dot and one or two decimal places. A thousands comma, an `RD$` prefix, or the form `1.234,56` stays unresolved. The script sets the one `$` row to `DOP`. A real line needs a currency a person can confirm.

Lines that are not movements have to be identifiable. Pending authorizations, a minimum payment, and informational text are examples. The English proposal file contains the income sentence and leaves the hypothetical question out. The kit has no reader for those lines.

`destination` is a label on the row. Who may see the document belongs to a permission contract this kit leaves undefined.

Lucas gathers the consented statements. The later measurement checklist already lives in `tests/synthetic_ingestion/README.md`.
