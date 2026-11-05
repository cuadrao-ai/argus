# Import reconciliation evidence (wave 2)

**Date:** October 1, 2026. **Branch:** `claude/ingestion-reconciliation`.
**Lane spec:** [financial-ingestion-connectors](../../../specs/lanes/financial-ingestion-connectors.md).
**API:** [Import review queue](../../../API_CONTRACT.md#import-review-queue-default-off).
**Data:** [Import reconciliation](../../../DATA_MODEL.md#import-reconciliation).

Reconciliation is the single `CandidateSink` behind Plaid, Gmail and Apple
Shortcuts. It groups observations into events, keeps distinct purchases
distinct, holds the review queue and records canonical activity only through
`MoneyService` after the person confirms. Code:
`src/argus/domain/ingestion/reconcile/` (model, matching, intake, render,
service, recording, store, store_postgres), routes in
`src/argus/api/routers/financial_imports.py`, migration
`supabase/migrations/20261002120300_financial_import_reconciliation.sql`.

## What is proven, and how

| Claim | Level | Evidence |
| --- | --- | --- |
| The same purchase seen as a Wallet tap, a bank email, a Plaid pending row that posts, and a statement line stays one event with four sources' evidence and records one activity | Hermetic and real Postgres | `test_same_purchase_from_four_sources_is_one_event_and_one_record` |
| Equal amount and date never merge distinct purchases; several equal matches are flagged `ambiguous_match`; one source's two observations can never be merged | Hermetic and real Postgres | `test_equal_amount_and_date_never_merge_distinct_purchases` |
| Without a person-confirmed account a match is only a `possible_duplicate` | Hermetic and real Postgres | `test_unconfirmed_account_is_only_a_possible_duplicate` |
| Re-delivery is unchanged; six concurrent retries record once | Hermetic and real Postgres | `test_redelivery_is_unchanged_and_concurrent_retries_record_once` |
| A source removal before review withdraws the draft | Hermetic and real Postgres | `test_source_removal_before_review_withdraws_the_draft` |
| A source change or removal after acceptance flags the event and never edits the record | Hermetic and real Postgres | `test_source_change_after_acceptance_flags_but_never_edits_the_record` |
| Acceptance is idempotent; six concurrent accepts with different keys record one activity | Hermetic and real Postgres | `test_acceptance_is_idempotent_and_single_under_concurrency` |
| Currency is never guessed or converted | Hermetic and real Postgres | `test_currency_is_never_guessed_or_converted` |
| An already-recorded (manual) purchase is linked instead of recorded twice; one import per activity | Hermetic and real Postgres | `test_already_recorded_purchase_links_instead_of_recording_twice` |
| Due-date notices and balances are evidence, not activity | Hermetic and real Postgres | `test_notices_and_balances_are_evidence_not_activity` |
| Disconnect drops drafts and keeps the recorded event's provenance only | Hermetic and real Postgres | `test_disconnect_drops_drafts_and_keeps_recorded_provenance` |
| Reviewed batches record only items without open questions; retries replay | Hermetic and real Postgres | `test_reviewed_batch_records_clear_items_and_returns_exceptions` |
| People are isolated; a connector cannot submit for another connection | Hermetic and real Postgres | `test_people_are_isolated` |
| Owner-only reads, no client writes; the database refuses a second import for one activity | Real Postgres | `test_owner_reads_and_no_client_writes`, `test_database_refuses_two_imports_for_one_record` |
| Household scope is shown before confirming; importing creates no grant | Real Postgres | `test_household_scope_is_shown_and_never_granted_by_importing` |
| Review regressions: reconnecting a source cannot re-record an accepted purchase; duplicate warnings are two-way and block batches until resolved; the match window follows a person-supplied date; withdrawn-then-replaced evidence returns to review and clears `source_removed`; money refusals stay per batch item; invalid resolutions are refused before storage; evidence after disconnect is ignored; merges check both versions and refuse dismissed events; an interrupted acceptance resumes without a second record; linking waits while an import is being recorded; deleted events leave no dangling duplicate references | Hermetic and real Postgres | `test_reconnected_source_cannot_record_an_accepted_purchase_again` and the eleven tests after it in `tests/ingestion/reconcile_cases.py` |
| Plaid and Shortcuts evidence reaches the queue over HTTP; drafts change no account; accept records once and replays | Hermetic API | `tests/ingestion/test_imports_api.py` |
| Live Plaid Sandbox data flows into review: 331 drafts, none in the ledger; one confirmation maps 68 more drafts to the account (the count varies with Sandbox data); one accepted record; re-sync adds nothing; disconnect revokes and removes 330 drafts, keeping the record redacted | **Plaid Sandbox** | [`plaid-sandbox-reconcile.json`](plaid-sandbox-reconcile.json) |

Gmail evidence in the central case is `unclassified` (no content extraction in
this lane); the person supplies its facts and confirms the suggested merge.
That reflects the shipped Gmail connector, not a gap in matching.

## Commands

```bash
python -m pytest tests/ingestion/test_reconcile.py tests/ingestion/test_imports_api.py -q --no-cov
ARGUS_DISPOSABLE_DATABASE_URL=... python -m pytest tests/test_ingestion_reconcile_postgres.py -q --no-cov
PLAID_ENV=sandbox PLAID_CREDENTIALS_INJECTED=true python scripts/ingestion/plaid_sandbox_reconcile.py
```

The local Postgres is PostgreSQL 16 with a minimal Supabase shim; four
unrelated search/vector index migrations do not apply there. CI runs the same
files against full local Supabase.

## Not covered

- No statement or document importer exists in the repository; the sink
  accepts `statement` candidates for that future path, and the central case
  submits them directly.
- Native review screens (Spanish first, English parity) are for the iPhone
  delivery owner; this lane provides the API and stable problem codes.
- Gmail content extraction, Shortcuts physical-device behavior and Plaid
  production remain as stated in their connector evidence.
