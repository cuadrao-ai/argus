# PR #763 integration landing

## Landed change

- PR: [#763](https://github.com/lagarcess/argus/pull/763)
- Approved PR head: `7b80190d057c89b5f92b03845f374a810253dda1`
- Integration parent at squash: `9b5e8643f0493145bd672c2af6e7508371d4cfa0`
- Squash merge: `fbcc399bdb888d89af594422cfa319a4c26c60e5`
- Merge time: October 1, 2026, 05:29:24 UTC

## Outcome and remaining work

Default-off Household membership lifecycle behind `CUADRAO_HOUSEHOLDS_ENABLED`:
create household, synthetic invite, accept, explicit account grants (view/edit),
leave/remove/revoke/close/transfer-admin, security-definer membership RLS helper,
and deletion-safe historical attribution (`ON DELETE SET NULL` with active-admin
CHECK). Hermetic two-user lifecycle proof is in `tests/household/`, which
asserts `PERSISTENCE_MODE == "memory"` and mocks the Supabase gateway plus
auth-session checks. That is not real Auth/Postgres/RLS verification.

Native Home/Accounts/Search projections, physical-phone proof, shared plans,
private-source contributions, and external invitation delivery remain outside
this land. Real local Auth/API/Postgres and RLS verification of the migration,
locking and policies remains explicitly pending; no durable real-stack household
evidence is cited. #760 / design / sim / deploy were not touched. Exposure stays
default-off; no hosted migration or activation.

## Accepted evidence

- Pre-merge Exact head `7b80190d`: all 17 applicable CI checks SUCCESS; Codex
  review findings (recursive RLS, deletion-safe identity, lock order) fixed and
  resolved; **0** unresolved review threads; `mergeable_state: clean`.
- Original integration base `9b5e8643` unchanged through merge; no intervening
  semantic overlap or reconciliation merge.
- Hermetic in-memory household domain/lifecycle tests and OpenAPI compatibility
  passed on the review-fix head before promote. No real Auth/Postgres/RLS
  household proof is claimed or linked.

## Documentation and environment audit

Landing updates the execution manifest, integration ledger, documentation
authority remainder, and this report. `CUADRAO_HOUSEHOLDS_ENABLED` already landed
in `.env.example`, `render.yaml`, `.github/argus-env.sh`, and the private-alpha
release profile as `false`. No secrets inspected or rewritten. No linked issues
to close.

## Authority boundary

This checkpoint stops at `codex/private-alpha-next`. No main promotion,
deployment, hosted Blueprint sync, tester exposure, #760 edits, design-branch
work, or simulator ownership changes.
