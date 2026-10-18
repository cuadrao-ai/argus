# Receipt payment truth, issue 1212

Status is WIP. Deterministic proof is separate from model interpretation proof.
The source change must not merge or deploy until the scoped Standard 12 live
scorecard, no-regression comparison, fingerprint and independent exact-head Eval
are complete. No live model call was made for this lane.

## Problem and ownership

A private order confirmation was read as a posted expense. Its printed tax
estimate lost its qualifier. The private source and captured output were inspected
offline. They are not committed. The public tests use a fictional shop and different
amounts.

The shared extractor requires a printed final paid total. Its old receipt schema
could not retain payment evidence or estimated tax. Its projection trusted a posted
model row when the receipt total agreed. Business preparation could also recover
that row after projection rejected it, then fill purchase facts from a QR.

`ReceiptDetails` now carries `payment_status` and `estimated_tax`. Unknown payment
is the default for a new read. The existing `tax` field is final tax only. The prompt
keeps order dates separate from paid purchase dates and asks for no unsupported
purchase row. The original source and raw read remain retained.

The extractor owns the `receipt_payment_unproven` decision. Business consumes that
issue before raw-row recovery or QR filling. An unpaid attachment cannot clear an
existing draft's read purchases or facts. A frozen legacy batch keeps its stored
candidates; this change does not reinterpret or automatically reread it. Paid
scripted provider responses in existing tests now state payment evidence explicitly.

Only `prepare_attachment` and its import change in Business mutations. The root
coordinator approved that bounded shared-method scope. Business Eval must recheck
that method before landing. No recording, approval, migration, environment,
production, staging-write or UI change is included.

## Verification

The lane starts from integration `f3899f4aa0d84060e0afaf270f7a983a9f8aa89c`.
The last local refresh returned the same SHA. Root then reported iOS-only
integration `ab326feb61825000b6bf176434c54c9a27622124` and directed this WIP
freeze without another reconciliation. No merge-ready claim is made. Root owns
fresh reconciliation and semantic-overlap review before any landing. The three
production files and their focused tests are the affected owners.

- Existing focused baseline. 51 passed.
- Synthetic regression before the fix. 4 failed and 1 legacy preservation passed.
- Focused payment, legacy, existing-draft, multiple-purchase and QR checks. 26 passed.
- Ingestion and Business regression, excluding the separately checked WhatsApp API
  fixture. 1440 passed and 23 optional checks skipped.
- Additional e-CF draft and Postgres files. 2 passed and 35 skipped without a
  disposable Postgres DSN. This supplies no new Postgres proof.
- Required free mocked eval harness. 276 passed.
- Prompt freeze. 5 passed and 1 expected failure for the two changed document
  owners. The old fingerprint and live scorecard are preserved. This failure is
  the Standard 12 hold, not a waiver.
- Ruff check, Ruff format and diff whitespace checks passed. Modularity budgets
  passed on the current would-be merged tree.

The separate WhatsApp API file returns the same 10 failures and 16 passes on this
lane and on the exact unchanged integration base, with the same local namespace
configuration. Without an outbound override its fixture first reports 23 setup
errors because the canonical Cuadrao value outranks its legacy Argus test value.
These tests and configuration were not changed. No WhatsApp readiness is claimed.

The isolated lane uses the existing Python 3.10.20 runtime at
`/private/tmp/cuadrao-lane6c-parsers-deps/.venv/bin/python`; `lxml` and `scipy.linalg`
imports were verified there. The older shared runtime lacks `lxml`. Backend env
topology is canonical-linked. The canonical frontend env file is missing; no
frontend service or check was run. No shared environment value was changed.

Run free checks with provider keys empty and synthetic market data. The regression
command is:

```sh
PYTHONPATH=src:web python -m pytest tests/ingestion tests/business \
  tests/test_business_attachment_preparation.py tests/test_business_multi_purchase.py \
  tests/test_business_receipt_payment_truth.py \
  --ignore=tests/ingestion/test_whatsapp_api.py -q --no-cov
```

The required mocked command is the unchanged Mocked Run in
[`tests/evals/README.md`](../../../../tests/evals/README.md#mocked-run).
`tests/test_interpreter_prompt_freeze.py` must continue to fail until authorized
live evidence supports the new document prompt and schema descriptions.

## Remaining proof and rollback

The mocked tests prove the typed branch and saved state. They do not prove that the
configured extraction model reads an order or tax estimate correctly. Root must
approve any later named-model calls and budget. A fresh independent exact-head
Eval, including the Business method, remains required. CI can report the expected
fingerprint failure while the PR stays draft.

Revert the code and its tests together before rollout if rejected. No migration or
hosted change needs rollback. If future batches have already been stored, preserve
the new receipt fields and issue contract during rollback so old code does not
reject retained evidence or recover unsupported raw purchase rows.
