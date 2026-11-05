# What Argus can reuse from the payment ledger

This file is the assessment for [issue 716](https://github.com/lagarcess/argus/issues/716).

Read [payment-ledger-service](https://github.com/lagarcess/payment-ledger-service) at commit `2a6081f199be8526d6bc1378f7adb695112f4ea8`. That repository is an educational SQLite payment simulator. Argus can reuse the money rules and the retry, reversal, and concurrency proofs below. Argus cannot copy the service.

The rules live in `src/ledger.py` and `src/models.py`. The tests live in `tests/test_ledger.py` and `tests/test_api.py`. On 2026-09-27 those two files passed 43 tests against that commit, using SQLAlchemy 2 and pytest. The run called no paid provider. From a checkout of that commit, regenerate the count with `pytest tests/test_ledger.py tests/test_api.py -q`.

## Post integers and balance each currency alone

Posted money is a positive Python `int` in minor units. `Entry.amount` is a `BigInteger`. The check `ck_entry_positive_amount` requires `amount > 0`. The `direction` column carries the sign. `LedgerEngine._get_account_balance` sums debits and subtracts credits.

Cross-currency conversion does not post a float. `LedgerEngine._convert_minor_units` multiplies a `Decimal` rate, rounds with `ROUND_HALF_UP`, and stores an int. `test_cross_currency_payment_records_decimal_fx_snapshot` sends 1001 minor units at rate `0.925` and records 926 destination minor units. The snapshot stores `rounding_mode` `ROUND_HALF_UP`. `test_cross_currency_payment_rejects_non_integer_minor_units` rejects a float, a `Decimal` amount, and a numeric string. `test_precision_scale_limits` posts `900_000_000_000_000` minor units through `BigInteger`.

Each account has one currency. `CURRENCY_MINOR_UNITS` lists only `USD` and `EUR`, both with two decimal places. `LedgerEngine._verify_transaction_balanced_by_currency` and `verify_system_invariants` require debits to equal credits inside each currency. `test_seeded_ledger_balances_independently_by_currency` checks that bootstrap funding uses no `MULTI` account. `test_system_invariant_rejects_cross_currency_netting` posts a USD debit of 1234 against an EUR credit of 1234. Those two legs would net to zero if currency were ignored. `verify_system_invariants` raises `InvariantViolationError` instead. `test_cross_currency_success` checks that a real payment nets to zero in both `USD` and `EUR`.

A later Argus design can keep those rules. Store minor units as integers. Convert with `Decimal` and a named rounding mode. Balance each currency by itself.

Do not copy the simulator sign convention with those rules. In this ledger a debit increases a user balance and a credit decreases it. `models.py` documents that choice. Usual asset accounts use the opposite sign. Copying the functions without choosing a sign would invert balances.

Do not copy `_fmt_amount`. It divides a minor-unit int by 100 for display. That helper is not the posted arithmetic.

## Treat a retry as the same payment

`Transaction.idempotency_key` is unique. `LedgerEngine._payment_fingerprint` hashes the normalized request. The same key and the same fingerprint return the original transaction. The same key and a different payload raise `IdempotencyConflictError`. `_recover_idempotent_integrity_error` handles a unique-constraint collision. It returns the original row when the fingerprint matches. It raises `IdempotencyConflictError` when the fingerprint differs.

These tests cover that behavior.

- `test_idempotency_guard` and `test_same_idempotency_key_retry_returns_original_transaction` call the same payment twice and require one transaction id.
- `test_same_idempotency_key_with_different_payload_is_rejected` changes the amount and expects `IdempotencyConflictError`.
- `test_concurrent_same_key_requests_do_not_double_post` runs two threads with one key and requires one row.

## Undo by appending a linked reversal

`LedgerEngine.reverse_transaction` does not edit or delete the original rows. It inserts a new `Transaction` with `transaction_type` `REVERSAL`. The new idempotency key is `REV-` followed by the original key. `reversed_transaction_id` points at the original id. Each new entry keeps the same account and amount and flips `DEBIT` and `CREDIT`. A second reversal of the same payment raises `DuplicateTransactionError`.

`test_transaction_reversal` restores the sender balance. It also checks that the transaction count and the entry count both grow. `test_transaction_audit_marks_original_reversal_status` checks that the audit of the original payment reports `reversal_transaction_id`.

## Prove concurrency with three tests

Three tests in `tests/test_ledger.py` are real race tests. They run on a temporary SQLite file from `tests/conftest.py`. They do not prove Postgres.

`test_occ_conflict` uses `locking_strategy="OCC"`. During the balance read, another session renames the sender account. The rename bumps `Account.version_id`. The payment then raises `ConcurrencyConflictError`. The engine maps SQLAlchemy `StaleDataError` to that exception. On the OCC path, `flag_modified` marks the account name changed so the flush increments `version_id`.

`test_pessimistic_race_condition` starts two threads. Each thread tries to send the sender's full balance with `locking_strategy="PESSIMISTIC"`. Pessimistic mode runs `BEGIN IMMEDIATE`. One thread succeeds. The other raises `InsufficientFundsError`. The balance ends at 0. `verify_system_invariants` still passes.

`test_concurrent_same_key_requests_do_not_double_post` is the retry race named above.

Rewrite tests of this shape against the store Argus eventually uses. Do not copy the SQLite lock.

## Do not transplant the ledger

SQLite blocks a copy. `DATABASE_URL` in `src/models.py` is `sqlite:///ledger.db`. Pessimistic locking depends on `BEGIN IMMEDIATE` and the SQLite begin listener in that file. The tests enable SQLite WAL. Argus persistence is Supabase Postgres. Those locks are not the Postgres locks.

Account types block a copy. `AccountType` is only `USER` and `CORPORATE_FX_CLEARING`. A cross-currency payment moves value through a pre-funded clearing pool. Argus has no such accounts. This assessment does not add them.

Missing permissions block a copy. The ledger `src` tree, `tests` tree, and `AGENTS.md` contain no user id, no household, no authentication check, and no row security policy. `AccountType.USER` is a wallet label, not a signed-in person. Argus household permissions are not implemented. This assessment does not add them.

Rejecting a short balance is the wrong rule for an expense that already happened. `execute_cross_currency_payment` and `execute_same_currency_payment` raise `InsufficientFundsError` when the recorded balance is below the send amount. `test_overdraft_protection` shows that the failed payment leaves no transaction row. A reversal can raise the same error when flipping a user debit would drive that wallet below zero. The product rule for this assessment is different. Argus must record an expense that already happened when the balance on file is incomplete. Refusing that write would drop the expense. Keep the ledger refusal for a payment that tries to spend funds the ledger does not hold. Do not use that refusal to reject a historical expense.

The currency table is too small to copy. Cross-currency conversion accepts only `USD` and `EUR`. `_minor_unit_quantum` raises `ValueError` for any other code.

The README states that the project is not production payment infrastructure. Do not copy `src/api.py`, the dashboard, the bootstrap seeds, or the FX clearing liquidity check into Argus.

## This file changes no money schema

This assessment does not approve an Argus financial schema, a migration, a household permission, or a chat change. Decision 8 in `docs/specs/argus-grounded-finance-roadmap.md`, recorded 2026-09-08, remains the storage rule. A salary, an expense, or a debt the user types stays in the conversation and is not stored as a ledger balance.
