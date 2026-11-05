# Connected Plan and Home: local iPhone demonstration

This lane connects expected income, bills, recurrence and fulfillment to the
existing recording service. The [execution manifest](../../../specs/argus-execution-board.md#connected-plan-and-home-lane)
owns scope, status and the remaining MVEE work. Physical-iPhone installation and
internet deployment are not verified by this local demonstration.

## Recording and verified state

[Watch the 2m56s simulator recording](connected-plan-demo.mp4). It contains
chronological, normal-speed excerpts from the passing native test on September
29, 2026. Navigation and typing pauses are cut; no results or UI are simulated.
The source recording is retained locally as
`ios/.build/accounts-local-58600/plan-final-raw.mov` (323.288 seconds).
Source intervals are 8–34, 83–123, 128–159, 178–188, 198–223, 224–248 and
285–305 seconds. The video shows adding an expectation, Home's forecast,
payment, correction, linking existing income, editing the expectation, reopening,
and recurrence entry.

The main retained example is **Plan bank 5E1B**: DOP 100 starting cash,
Electricity 5E1B paid at 200 and corrected to 180, and Commission 5E1B linked to
one existing receipt of 450. Its actual balance is DOP 370. Editing expected
commission to 600 leaves that occurrence fulfilled. Weekly transport 5E1B is
expected at 10 from October 6; it does not change the recorded balance.
[Sanitized API readback](native-readback.json) independently confirms those
records after relaunch. Other uniquely named records are retained test data,
including deliberate unknown balances, unselected accounts and correction cases.

The reviewed product source is `20750992472ae3dfddb3f6f11718fa84f0ed3113`.
The main recording and screenshots were captured at `ab1e3e63`; later product deltas supply the saved owner-zone clock to occurrence lookup
and make the inherited account form dismiss every field's keyboard. Plan/Home
layout and money calculation source is unchanged. The clock delta has its own
[clean independent review](clock-review.md), and the captain reran the 209
financial/API/Postgres/OpenAPI checks on `36abc0bc` with zero skips. The
keyboard correction also has a [clean affected-delta review](focus-review.md)
at `20750992`.

A fresh-context independent reviewer, `plan_independent_review`, reviewed
`21309f08..196ccea2` once. Its three confirmed findings are recorded in
[review.md](review.md); the [affected-fix review](review-delta.md) is clean at
`ab1e3e63`. This substitutes for GitHub Codex under the founder's explicit grant.
It is not a claim that GitHub Codex reviewed this PR.

## Acceptance results

[Native acceptance record](native-acceptance.json): four assembled simulator
cases passed with clean Xcode exits, against real local Auth/API/Postgres:

- Complete create/forecast/pay/correct/link/edit/reopen journey (352 seconds).
- Unknown USD and Spanish/light presentation (122 seconds).
- Removing selected archived and retyped accounts, including unknown-balance
  creation with a nickname and working keyboard dismissal.
- Post-commit response loss, relaunch, owner A/B/A isolation and one recovered
  payment. The recovered account has DOP 80 and exactly one activity.

[HTTP proof](http-proof.json): 16 checks passed on September 29 at 19:17 UTC.
209 financial/API/Postgres/OpenAPI checks passed with zero skips, including
concurrency, atomic rollback, owner isolation, correction/refund semantics,
monthly/leap-day boundaries, saved time zones and proportional ownership.
The direct-API Home/reopen smoke also passed after removing the fault proxy
from the build. Final forecast screenshots at `20750992` show the dated
shortfall, later income and included accounts in the retained state.

50 Swift package checks and 12 native model checks passed; four separate live
package checks were not configured. The assembled tests above use the real
local service instead. Recovery-proxy/launcher checks, lint and modularity pass.

CI passed on backend-final `36abc0bc`. The final publication's exact-head CI
links and terminal verdict are recorded in the PR audit, avoiding a document
that tries to refer to its own commit. No paid or hosted acceptance was run.

## Retained environment

The dedicated simulator is **Argus Connected Plan**, iPhone 17e / iOS 27,
`4E22655F-72DC-468F-AEBB-97FBDC58B514`, bundle `local.argus.foundation`.
It uses real local Argus Auth/API/Postgres with synthetic registered identities:
API 58600, Supabase 58601, Postgres 58602 and CAPTCHA 58605. No paid providers are
configured. The older 584xx financial loop and 585xx personal-money demos remain
separate.

The ignored `ios/.build/accounts-local-58600/client.json` holds the synthetic
credentials. Never publish it or raw authentication logs. The installed app keeps
its session in the simulator Keychain.

## Click through

The retained starting view selects **Plan bank C6C5** (DOP 100) and
**Recovery plan AD6C** (DOP 80). It forecasts DOP -20 after Electricity C6C5
(200 on September 29), then DOP 480 after Commission C6C5 (500 on October 4).
Both expectations remain unpaid/unreceived, so you can exercise the recording
path yourself. Use **Show more** to find those named occurrences among the
retained test records. The separate **5E1B** example above preserves the completed
correction/link journey from the recording.


1. Open Plan. Choose included cash/bank accounts and the forecast's end date.
   Each currency has its own projection. An unknown selected balance keeps the
   total unknown. Expectations do not change Accounts or recorded net worth.
2. Add a bill or expected income, with its account, date and repeat schedule.
   Look for the shortfall before later income; a positive ending balance does
   not remove that warning.
3. Open an occurrence. Record a receipt/payment only after it happened, review
   the actual account/date/amount and any balance-check coverage, then confirm.
   Alternatively, select an existing matching activity and confirm the link.
4. Inspect the original activity, correct it, or edit the expectation. Recorded
   occurrences stay linked to the same activity. A changed actual account needs
   review; a refund does not automatically reopen the paid bill.
5. Reopen the app and inspect Plan, Home and the affected account.

Monthly schedules preserve the intended day, clamping to the last day in a short
month. Twice-monthly dates that clamp to the same day create one occurrence.
The saved time zone owns the planning day. Forecast steps show individual dated
movements, with bills before income on the same date; this is a conservative
ordering, not a claim about the time of day a payment arrives.

## Restart while preserving records

Use the retained checkout. Do not run `configure`, `seed`, `reset`, or remove
Docker volumes. Skip a service command if its port is already owned by this demo.
Start the API and CAPTCHA bridge in separate terminals and keep them running:

```sh
cd /Users/garces/.codex/worktrees/connected-plan-home/private-alpha-next
python3 ios/scripts/auth/local_stack.py start --accounts --port-base 58600
python3 ios/scripts/auth/local_stack.py api --accounts --port-base 58600 \
  --accounts-enabled on \
  --python /Users/garces/.codex/worktrees/5a42/private-alpha-next/.venv/bin/python
```

```sh
cd /Users/garces/.codex/worktrees/connected-plan-home/private-alpha-next
python3 ios/scripts/auth/bridge.py --accounts --port-base 58600
```

Launch the retained app:

```sh
xcrun simctl boot 4E22655F-72DC-468F-AEBB-97FBDC58B514 # only if shut down
xcrun simctl launch 4E22655F-72DC-468F-AEBB-97FBDC58B514 local.argus.foundation
open -a Simulator
```

If sign-in is needed, this existing read-only Home/reopen check uses the ignored
fixture without exposing credentials or appending financial records. Launch the
app again after the check finishes:

```sh
cd /Users/garces/.codex/worktrees/connected-plan-home/private-alpha-next
python3 ios/scripts/auth/run-ui.py 4E22655F-72DC-468F-AEBB-97FBDC58B514 \
  --accounts --port-base 58600 \
  --only ArgusFoundationUITests/FinancialLoopUITests/testRetainedHomeSurvivesReopening
xcrun simctl launch 4E22655F-72DC-468F-AEBB-97FBDC58B514 local.argus.foundation
```

## Repeat focused acceptance

Run cases serially; they deliberately create uniquely named synthetic records.
The complete native case is:

```sh
python3 ios/scripts/auth/run-ui.py 4E22655F-72DC-468F-AEBB-97FBDC58B514 \
  --accounts --port-base 58600 \
  --only ArgusFoundationUITests/FinancialLoopUITests/testConnectedPlanRecordsLinksCorrectsAndReopens
```

`testPlanKeepsUnknownCurrencyAndLocalizedPresentation` verifies unknown USD and
Spanish/light presentation. `testPlanResponseLossRecoversOnceAfterRelaunch`
requires explicit `--response-loss-proxy` opt-in and an app configured for the
local test proxy 58612. The proxy drops one response only after the API commits.
That case switches from owner A to B and back before retrying A's pending payment.
The normal retained demo uses direct API 58600, without injected failures.
`testPlanCanRemoveArchivedAndChangedSelectedAccounts` exercises removal of
previously selected accounts after archiving or changing to a non-cash type.

The independent real-HTTP journey is:

```sh
/Users/garces/.codex/worktrees/5a42/private-alpha-next/.venv/bin/python \
  scripts/verify_connected_plan.py ios/.build/accounts-local-58600/client.json \
  --output /tmp/connected-plan-http-proof.json
```

It checks the earlier shortfall, fulfillment, duplicate retries, corrections,
refunds, explicit linking, expectation edits, changed-account link review,
recurrence, unknown currency, identity isolation and fresh-session persistence.
It adds synthetic data; it does not replace or reset existing demo records.

## Delivery limits

This scope does not complete budgets, savings goals or debt-plan lifecycles.
They remain tracked in the MVEE manifest. The existing recording API does not yet
remove/restore activities; this lane makes no claim of that broader MVEE behavior.
Forecasts cover explicitly entered expectations and selected cash accounts;
missing bills and uncertain income are not an affordability guarantee. Currency
conversion and unresolved loan rules are not invented. No production changes,
signing, deployment or merge are included.
