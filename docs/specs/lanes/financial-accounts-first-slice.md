# Financial accounts first slice: create, reopen, edit, correct

**Status:** Bounded implementation spec for one lane. Ships default-off.
**Date:** September 28, 2026.
**Serves:** [MVEE](../argus-minimum-viable-ecosystem-experience.md) "Quick
account setup and optional assets", "Archiving accounts" and "Guest access and
registration" (published by PR #727, now on integration), and section 18 of
the proposed financial recording contract (PR #724, open at the time of
writing).
**Integration base:** `origin/codex/private-alpha-next` at
`4b84e054a0d8079b21f38784335ad3241809b4cd`; reconciled one way with
`c978927e167f57369f27391ac65995a3d6e5520a` before publication.

This document binds the four dependencies section 18 of the recording contract
names before code: the guest answer, the API_CONTRACT and DATA_MODEL
amendments, the correction behavior, and a Postgres acceptance gate. It does
not approve the rest of the recording contract, and it starts no activity,
balance-check, category, transfer, refund, import, plan, space, household or
chat work.

## Outcome

A registered person creates a financial account with a type, one currency, an
optional nickname, and a starting balance or an unknown balance. They reopen it
and read back the same accepted facts. They edit the nickname, the type while
the account has no activity, the ownership share, and the archived flag. They
correct the starting balance or its date through a revision that keeps the
previous values, the reason, the author and the time. Unknown stays unknown and
never reads as zero.

## Decisions bound here

| Dependency | Binding |
| --- | --- |
| Guest policy (G1) | Registered accounts only, enforced on the server. The API refuses a verified guest with `403 account_conversion_required` before any read or write, and row-level security refuses an anonymous JWT even on reads. Existing guest chat behavior and quotas are untouched. Registration is the gate, not payment. |
| Exposure | `ARGUS_FINANCIAL_ACCOUNTS_ENABLED`, default `false`. While off, every route under `/api/v1/financial-accounts` returns `404 financial_accounts_unavailable`, the same shape personalization memory uses for a hidden surface. The flag is a kill switch after founder acceptance, declared in `.env.example`, `render.yaml`, the `argus-env.sh` contract array and the release profile. |
| Opening-balance correction | Section 7 of the recording contract, narrowed to a slice with no activity: a correction appends a revision with a required reason, carries unchanged fields forward, bumps the account version, and reorders nothing because nothing can move. |
| Database acceptance gate | `tests/test_financial_accounts_postgres.py` in the `tests/test_*_postgres.py` family CI already runs against a disposable local Supabase stack with every migration applied. |

## Owners

| Concern | Owner |
| --- | --- |
| Currency validation and exponent | `src/argus/domain/recording/currency.py`, reading `home_country.currency_codes()` and babel `get_currency_precision`. No second currency table. |
| Account types, nature table, locks, the single liability sign flip, edit rules | `src/argus/domain/recording/accounts.py` |
| Opening anchor, revisions, balance derivation, correction rules | `src/argus/domain/recording/records.py` |
| Wire schemas | `src/argus/domain/recording/schemas.py` (pydantic). `src/argus/api/schemas.py` is at its modularity budget and is not touched. |
| Persistence | `src/argus/domain/recording/repository.py` (protocol plus an in-memory twin for `CUADRAO_PERSISTENCE_MODE=memory`) and `src/argus/domain/recording/postgres_repository.py` (psycopg over `DATABASE_URL`, the personalization-memory precedent). |
| Migration | `supabase/migrations/20260928200000_financial_accounts_first_slice.sql`: `financial_accounts`, `financial_records`, `financial_record_revisions`, `financial_account_idempotency`, two SQL functions, owner-only RLS. |
| HTTP | `src/argus/api/routers/financial_accounts.py` and `src/argus/api/financial_accounts.py` (flag, gate, repository selection). OpenAPI regenerated. |
| Contract docs | `docs/API_CONTRACT.md` (new endpoint section), `docs/DATA_MODEL.md` (new entity section and RLS rule). |
| Evidence | `docs/reports/evidence/financial-accounts-first-slice/`. |

## Product rules carried into code

1. Types: `cash`, `checking`, `savings`, `investment`, `credit_card`,
   `other_debt`, `property`, `vehicle`, `other_asset`. Nature derives from type
   by one table and is never stored. `credit_card` and `other_debt` are
   liabilities.
2. Currency: creates and currency edits accept one ISO 4217 code only when it
   is in `home_country.currency_codes()`. The minor-unit exponent comes from
   babel. Reads format a stored code without re-checking tender membership
   (same stored-currency contract as the profile). Every stored amount is an
   integer count of minor units. Input is a dot-decimal string; more fraction
   digits than the exponent allows is `amount_precision`; minor units beyond
   signed 64-bit storage are `amount_out_of_range`. The server never rounds
   input.
3. Sign: the person types a liability as a positive amount owed. The domain
   flips it once. A stored balance is the signed value to the owner.
4. Unknown: an account without an opening record has no known balance. Its
   balance reads `{"state": "unknown"}` and is never `0`.
5. Nickname: optional, trimmed, up to 60 Unicode code points; blank clears it.
6. Ownership share: 1 to 10,000 basis points, default 10,000. It is a fact about
   the item, never a permission and never household access.
7. Balance date: an optional instant, never in the future (`date_in_future`),
   stored with its IANA zone (default `America/Santo_Domingo`). Today means the
   creation instant.
8. Locks: currency locks once the account has any record. Type locks once
   activity exists (none can in this slice); with only an opening, a change
   inside the same nature is allowed and a nature flip is refused
   (`nature_change_requires_empty_account`).
9. Archive: organizational. It changes no record and no balance. Restore is the
   same edit with `archived=false`.
10. Concurrency: account edits carry `expected_version`; opening writes carry
    both `expected_version` (the caller-visible account version) and
    `expected_revision`. A mismatch on either is `409 stale_version` and
    changes nothing. The account-version bind makes a concurrent currency or
    type edit between the client's read and the opening PUT unrepresentable
    as a successful write.
11. Idempotency: create requires `Idempotency-Key` with the contract grammar.
    The identity is the canonical hash of the validated request. Same key and
    identity replays the original account with no second write; same key with
    a different identity is `409 idempotency_conflict`. Keys are scoped to the
    user and to `financial_accounts.create`.
12. Correction: a revision carries a non-empty reason of up to 200 code points,
    the acting user and the server instant. Revision 1 is the original entry.
    Recording an opening on an account that has none uses the same route with
    `expected_revision: null` and the account's current `expected_version`.

## API surface

All routes require the flag, then a verified session, then the registered
account kind. See `docs/API_CONTRACT.md` "Financial accounts (first slice)" for
request and response shapes.

| Route | Purpose |
| --- | --- |
| `POST /api/v1/financial-accounts` | Create, `Idempotency-Key` required. `201` on first write, `200` on exact replay. |
| `GET /api/v1/financial-accounts` | List the caller's accounts, archived included and flagged. |
| `GET /api/v1/financial-accounts/{id}` | Reopen one account with its balance and opening history. |
| `PATCH /api/v1/financial-accounts/{id}` | Edit nickname, type, currency, archived, ownership share with `expected_version`. |
| `PUT /api/v1/financial-accounts/{id}/opening` | Record or correct the starting balance and its date with `expected_version` and `expected_revision`. |

## Acceptance

Deterministic (in-memory repository, no database), in
`tests/financial_accounts/`:

- create then reopen returns the same accepted data;
- known zero differs from unknown;
- currency precision and invalid inputs return the documented codes;
- duplicate create retries return one account; a changed body conflicts;
- unauthenticated and guest requests are refused; flag off hides the surface;
- edits enforce the locks and `expected_version`;
- corrections keep history and enforce `expected_version` plus `expected_revision`;
- an opening write that carries a stale caller-visible account version after a
  concurrent currency/type edit is `409 stale_version` and writes nothing.

The first-slice scenarios named in section 18 of the recording contract
(`clavito_large_opening`, `blank_opening_unknown`,
`first_slice_create_reopen_edit`, `multiple_precisions`, the create part of
`duplicate_submission`, and the account rows of `account_edit_rules`) are
re-expressed over a production driver with the same literal outcomes the
reference tests assert. The reference model itself is not imported: it is not
on integration, and its scenario functions read the in-memory `Store` directly,
so a driver swap is not possible without changing that seam.

Real database (`tests/test_financial_accounts_postgres.py`, skipped without
`ARGUS_DISPOSABLE_DATABASE_URL`):

- the migration applies on top of every checked-in migration;
- create-or-replay through the SQL function makes one account for concurrent
  duplicate requests and refuses a changed body;
- `expected_version` and `expected_revision` mismatches write nothing;
- owner-only RLS: another authenticated user reads nothing and updates nothing,
  an anonymous JWT reads nothing, and clients have no insert or update path
  because writes are function-owned;
- the same production repository the API uses runs the deterministic matrix
  against Postgres.

## No-touch

Chat runtime, the interpreter prompt and response-schema descriptions
(Never-Violate 12). Backtest admission and calculators. Profile columns. Guest
workspace, handoff and quota code. `tests/synthetic_ingestion/`. The frozen
mobile archive. PR #722's message and stream owner files. `src/argus/api/schemas.py`
and `src/argus/domain/supabase_gateway.py`, both at budget.

## Out of scope, deliberately

Activity, balance checks, categories, transfers, refunds, notes, statement
imports, plans, spaces other than the Personal default, household sharing,
linked debts, account removal, currency conversion, combined-currency totals,
and any chat action. None of these is a prerequisite for creating an account.

## Open items for the orchestrator

- PR #724's `Scene` seam reaches into `scene.store.book`; a driver-neutral seam
  would let the committed scenarios run unchanged against production. Not
  blocking; the literal outcomes are reproduced here.
- The reference model's `space_id` column is created with its Personal default
  so a later spaces slice needs no rewrite, but no route reads or writes it.
