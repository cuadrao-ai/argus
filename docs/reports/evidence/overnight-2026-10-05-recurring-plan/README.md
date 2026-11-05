# Recurring expectation to confirmed payment: real local API proof

Run date 2026-10-05 (America/Santo_Domingo), source head `f0288636517fd20955977bdd1f65ade0515048fb`
(clean tree). Issues #822 and #824, Track 2. This is local, synthetic, API-level evidence only. It is not
hosted, simulator or device acceptance, and it claims no enablement.

## Runtime

Real isolated Supabase Auth (59801), API (59800, `ARGUS_FINANCIAL_ACCOUNTS_ENABLED=true`) and Postgres
(59802) from `ios/scripts/auth/local_stack.py --accounts --port-base 59800`. Three synthetic registered
identities. Synthetic market data, no provider keys, no root `.env`. Base 60000 was not usable because
`local_stack.py api` refuses ports above 59900.

## Command

```
.venv/bin/python ios/scripts/recurring-plan-journey.py --port-base 59800 --write-evidence
```

Result: 11 checks, 77 assertions, all passed. `journey-proof.json` holds the check names, assertion counts and
the literal cadence date lists for this run. It contains no credentials or tokens. The script refuses any
allocation whose identities already have accounts or expectations.

| Check | Assertions |
| --- | --- |
| movement becomes a prefilled expectation without touching the original | 12 |
| Default window is unaffected by a longer request | 11 |
| currency separation | 6 |
| link an actual payment fulfils the occurrence once | 9 |
| record a new payment through fulfillment | 8 |
| correcting the linked payment follows the stored contract | 8 |
| authorization | 8 |
| a due date never posts money | 4 |
| unknown balance is not counted as known | 3 |
| empty plan invents no totals | 2 |
| cadence dates | 6 |

Key literals asserted (DOP checking opened at 50,000.00; actual expense 1,500.00 twelve days earlier):

- Default read: start today, end today + 30, one occurrence, starting 4850000, bills 150000, ending 4700000.
  A Plan read to today + 90 returns three occurrences and bills 450000; the next default read is the 30-day window again.
- Linking an actual 1,500.00 payment: bills 150000 to 0 and ending 4550000 to 4700000 once. The same key replays
  with no second effect, a different body on the same key returns 409 `idempotency_conflict`, and the same activity
  cannot fulfil a second occurrence (422 `activity_already_linked`).
- Recording a new payment through `/fulfillment`: bills 300000 to 150000, one occurrence fulfilled, resend recorded one payment.
- Correcting the linked amount keeps `fulfilled` (activity revision 2). Moving the payment to another account moves the
  occurrence to `needs_review` with `link_needs_review` and excludes it from the projection until explicitly relinked.
- User B receives 404 `financial_account_not_found` for user A's expectation (read and edit), occurrence candidates, link,
  fulfillment preview, fulfillment and the linked activity. No credentials returns 401.
- Month-end cadence on the 31st clamps to 30 and 28 and returns to 31; `twice_monthly` [15, 31] and `every_two_weeks` match an
  independent calendar oracle for the 366-day window (dates in `journey-proof.json`).

## Focused tests (also run for this change)

- `ios/scripts/test_recurring_plan_journey.py`: 18 passed (derivation, oracles, path and endpoint refusals).
- `tests/financial_accounts/test_plan.py`, `test_plan_api.py`, `test_plan_recurrence.py`, `test_plan_recurring_payment.py`
  and `tests/test_connected_plan_postgres.py`: 35 passed, 32 skipped without a database; 67 passed against the real
  local Postgres (`ARGUS_DISPOSABLE_DATABASE_URL` on port 59802, memory and Postgres variants of every scene).
  The Postgres variants are local evidence: CI sets that variable only for `tests/test_*_postgres.py`, so CI runs
  the memory variants of `test_plan_recurring_payment.py`.

## Known limitations

- Expectations carry no category (`ExpectationCreate` has no category field) and no source-activity link is stored.
- A prefilled expectation sent without `month_days` anchors every later date to the start day. If the first date was a
  clamped month end (for example 28 February from a 31 January movement), the series stays on the 28th. Sending
  `month_days: [<movement day>]` keeps the anchor. `test_monthly_without_month_days_follows_the_start_day_even_when_it_was_clamped`
  pins this.
- The candidate list for an occurrence matches by owner, direction, currency and account only, so the original movement
  that seeded the expectation is also offered for linking.
- Personal Plan only. No household, hosted or device acceptance. Dates are relative to the run day, so the literal date lists
  apply to 2026-10-05.

`journey-proof.json` records the run-time label "Home default window is independent of Plan horizon" for check 2. The label was renamed afterwards to say what the check proves (the API default window is unaffected by a longer request); the assertions did not change. What Home renders is proven by the native PR.
