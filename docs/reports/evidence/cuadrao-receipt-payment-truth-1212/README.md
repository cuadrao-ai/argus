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
is the default for a new read. The existing `tax` field is final tax only. The
fields carry no descriptions and the prompt is unchanged. The original source and
raw read remain retained.

Payment status is evidence, not a gate (founder decision, October 19, 2026). An
unpaid bill or order confirmation keeps its read amount on the draft, marked
unverified, the same as any other read, and is never auto-approved. A frozen
legacy batch keeps its stored candidates; this change does not reinterpret or
automatically reread it. Paid scripted provider responses in existing tests state
payment evidence explicitly.

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

## October 18 offline pickup

The published source `fee6cfc58c88e484da442e6af994dd4903355dbf` was clean.
Fresh integration is `651870a54be4e5506dbb38f3902fef1a97eef8df`. The one-way
reconciliation merge is `0dccc587b1ebe1ffb76a5f9e3a2c5f57c09f4309`. There was
no rebase. The original integration base remains
`f3899f4aa0d84060e0afaf270f7a983a9f8aa89c`.

Integration added iOS scan and accessibility work and account deletion changes.
It did not change the extraction, Business preparation or directly affected test
owners. The API and data document merges concern unrelated sections. Earlier
deterministic evidence is retained. No live receipt acceptance is claimed.

The free regression command above passed again on the reconciled code with
1,440 passes and 23 optional skips. The unchanged required mocked command and
the prompt freeze produced 281 passes and one expected failure. Of the passes,
276 are mocked eval checks and five are fingerprint checks. The failing
fingerprint identifies exactly `documents/extractor.py` and
`documents/models.py`. It remains a required hold. Whitespace and modularity
checks passed on the reconciled tree. No runtime code changed during pickup.

Backend topology is canonical-linked and frontend topology is missing. The
coordinator authorized synthetic backend processes with provider keys blank,
without changing environment files. No frontend service ran. No disposable
Postgres test ran during pickup, so there is no new actual Postgres proof.

## Pending three-call measurement

The [pending manifest](pending-measurement-manifest.json) names three synthetic
fixtures, their exact paths, hashes and assertions. The two baseline cases are
`receipt-dop` and `unreadable`, exactly as recorded in the existing
[document scorecard](../cuadrao-receipt-extraction-20261011/live-measurement.json).
Every baseline check must remain true. The new order confirmation has a Payment
heading, no proof of completed payment, and printed estimated tax. Its expected
result has unknown payment, no purchase or paid date, null final tax, and the
separate printed estimate. Its source text and rendered image are committed.
No private document is part of this manifest.

The proposed model is the same `google/gemini-3.8-flash`. The proposed allocation
is three serial requests, zero retries, 12,000 maximum output tokens per request,
and the canonical 90-second timeout. No paid judge is proposed because the
assertions concern exact typed facts. These requests are not authorized or run.

Execution is BLOCKED before a spending request. The existing
`scripts/documents/budget.py` rejects all endpoints in the public pricing
metadata fetched on October 18 with `no_bounded_endpoint`. Current metadata
contains nonzero image, audio, audio-cache and internal-reasoning price entries
outside the guard's accepted categories. The guard was not changed. The existing
benchmark runner also requires exactly six fixtures and reserves the model's
whole context window. It has no validated input-token limit for these three
actual fixtures. A small file or an earlier usage count is not such a limit.

The manifest therefore records no approved dollar cap or input-token bound.
Before any paid approval, a separately scoped runner plan must establish the
actual fixture input bound, accepted price semantics, strict provider and
privacy settings, duplicate-safe reservations, and the three-call limit without
weakening the existing guard. No alternative provider path was attempted.

After authorized measurement, commit its scorecard, compare every baseline
case, update only the document scope's fingerprint, and rerun the freeze check.
Keep other scopes and legacy evidence unchanged. Fresh Priya exact-head Eval
must include Business `prepare_attachment` before any receipt-fix squash.
The PR stays draft. Any Apple-source acceptance still needs approval to read
that source, a safe bounded runner, model proof and the authorized hosted
customer path after landing. These offline checks prove none of those steps.
