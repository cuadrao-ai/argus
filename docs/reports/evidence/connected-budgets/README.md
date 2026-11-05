# Connected spending budget demonstration

The [execution manifest](../../../specs/argus-execution-board.md#connected-personal-spending-budgets-lane)
owns scope, decisions and delivery status. This guide preserves only the isolated
local environment. The founder approved the original financial policy and resumed implementation.
Budgets are connected to the landed recording, Plan and Search features. The
real API/database and native connected journeys pass. The final financial-only
recording and exact-head PR gates complete the delivery record. This remains local simulator delivery;
physical-phone delivery over the internet belongs to its separate owner.

## Preserve the environment

Use `/Users/garces/.codex/worktrees/connected-budgets/private-alpha-next` on
`codex/connected-budgets`. The dedicated simulator is `Argus Connected Budgets`,
iPhone 17e with iOS 27, `CC81C737-2F0A-48EA-961C-D9ECFFACA219`.
The installed bundle identifier is `local.argus.foundation`. The ordinary installed
build talks directly to API 59000; response-loss testing temporarily uses 59012
and restores 59000 afterward.

The stack uses API 59000, Supabase 59001, Postgres 59002 and synthetic CAPTCHA
bridge 59005. The clickable mirror uses loopback port 59013. Optional response-loss
acceptance uses 59012. No service is publicly exposed. Existing demonstrations
and the physical-phone environment on ports 58700-58749 remain separate.

The ignored `ios/.build/accounts-local-59000/client.json` holds the two local
synthetic users. Do not publish that file, write journals or authentication logs.
Do not run `configure`, `seed`, a database reset or volume deletion on restart.

## Restart without losing records

Skip any service already running. Start each long-running service in its own
terminal and keep that terminal open.

```sh
cd /Users/garces/.codex/worktrees/connected-budgets/private-alpha-next
python3 ios/scripts/auth/local_stack.py start --accounts --port-base 59000
python3 ios/scripts/auth/local_stack.py api --accounts --port-base 59000 \
  --accounts-enabled on \
  --python /Users/garces/.codex/worktrees/5a42/private-alpha-next/.venv/bin/python
```

```sh
cd /Users/garces/.codex/worktrees/connected-budgets/private-alpha-next
python3 ios/scripts/auth/bridge.py --accounts --port-base 59000
```

Launch only this lane's simulator. Boot it only if it is shut down.

```sh
xcrun simctl boot CC81C737-2F0A-48EA-961C-D9ECFFACA219
xcrun simctl launch CC81C737-2F0A-48EA-961C-D9ECFFACA219 local.argus.foundation \
  -AppleLanguages '(en)' -AppleLocale en_US -appearancePreference dark
```

If the mirror is not running, start it in a separate terminal. Its cleanup targets
only the budget simulator.

```sh
cd /Users/garces/.codex/worktrees/connected-budgets/private-alpha-next
BUDGET_SIM=CC81C737-2F0A-48EA-961C-D9ECFFACA219
cleanup_budget_mirror() {
  npx --yes serve-sim@0.1.47 --kill "$BUDGET_SIM" >/dev/null 2>&1 || true
}
trap cleanup_budget_mirror EXIT INT TERM HUP
cleanup_budget_mirror
npx --yes serve-sim@0.1.47 --port 59013 --host 127.0.0.1 \
  --codec mjpeg --fit "$BUDGET_SIM"
```

[Open the local simulator mirror](http://localhost:59013). Its selected device must
be **Argus Connected Budgets**. The captain verified a live native frame; a loaded
HTML page alone does not prove streaming or financial behavior.

## Verification status

[The pre-implementation baseline](baseline.json) records 203 inherited financial
tests with zero skips against this lane's disposable Postgres. Registered native
sign-in, relaunch, sign-out and signed-out relaunch also passed against real local
Auth/API/Postgres. Raw logs and `.xcresult` diagnostics remain ignored.

[The fixture proof](fixture-api-proof.json) independently verifies five accounts
and eight canonical activities after repeated setup. It includes bank/card
purchases, a transfer, a card payment, another currency and an unknown balance.
Fifteen real API readbacks cover balances, entry identity and owner isolation.
The inherited Home reopening test also passes. Its [retained Home screenshot](pre-implementation-home.png)
shows DOP 963 in known balances, one unknown balance, DOP 140 spending and
USD 50 separately. These are preparation evidence, not budget progress.

`python3 ios/scripts/budgets-acceptance.py setup` resumes the exact saved fixture
writes without regenerating completed records. `readback` verifies only this
initial baseline, before later interactive demo changes. Neither command creates
a budget or defines which records a budget includes.

[The independent API/database journey](budget-api-proof.json) verifies a Groceries
budget with an initial limit of DOP 150: existing spending 120, new card purchase
80, correction to 60, then a received refund of 25 gives 155 spent. Editing the
limit to 160 leaves 5. Refunds deposited outside the selected accounts follow the
original purchase scope. Transfers/card payments and other currencies/categories
remain excluded; unknown balances remain unknown. The proof includes an accepted
budget response deliberately lost in transit, followed by the same command/key
replaying once. Definitions and actual activity were counted in Postgres.

`python3 ios/scripts/budgets-journey.py readback` verifies the retained main
budget's current 155/160 progress and four canonical contributors. The `run`
command resumes its saved writes, so it does not create duplicate financial
records. Keep its ignored private journal. Do not use the earlier baseline
`readback` after the recorded journey has changed balances.

236 focused financial/Plan/Search/budget tests passed on DB59002 with zero skips.
The Swift package passed 55 tests with four existing opt-in live-auth tests skipped;
all three new budget contract tests passed. All 23 generated OpenAPI compatibility
checks pass. The connected native journey and actual committed-response-loss
relaunch test pass. [Native proof](native-proof.json), [focused independent review](review-proof.json)
and the PR terminal audit record exact source heads and evidence retention.
The PR audit retains the accepted delivery evidence. [PR #753 is landed](../../../specs/argus-execution-board.md#pr-753-integration-landing)
in integration; its landing comment records exact-head CI and final parity. No
deployment or physical-device installation has occurred.

## Click through the retained journey

Open the mirror above. Use **Plan → Budgets → Groceries budget demo bf8087af**:
it shows **DOP 155 spent of 160**, four contributors and 5 remaining. Open a
contributor to inspect or correct it using the existing recording controls; return
to the same budget. Edit its limit or scope through **Edit budget**.

Search that same title to open live detail and return to the preserved query.
Home shows connected budget summaries; tapping one opens that same detail.
Fresh `Food …` budgets retain the recorded native journey: existing 120, card
purchase 80, correction to 60 and a linked refund of 25 received into an unknown
cash account. Their final limit is 160 and spending is 155. Other synthetic test
records remain deliberately preserved, so aggregate Home balances differ from
the initial preparation screenshot. Each budget's explicit scope keeps its own
progress stable.

[Short financial-only recording](budget-journey.mp4) accompanies the
[initial scope](budget-initial.png), [over-budget purchase](budget-over.png),
[correction](budget-correction.png), [cross-account refund](budget-refund.png),
[restored contributor position](budget-return.png), [archive/restore](budget-archived.png),
[reopened detail](budget-reopen.png), [Search return](budget-search.png),
[Spanish detail](budget-es.png), [Home summary/back](budget-home.png) and
[recovered exact command](budget-retry.png).

## Remaining limitations

This delivers personal monthly budgets without rollover, using the approved
received-month refund policy. Household budgets, goals, debt plans and all other
excluded MVEE slices retain their owners in the existing manifest. Signing,
physical-iPhone installation and internet deployment are not delivered here.
The inherited full-owner snapshot remains the scaling limit; there is no second
spending ledger or editable actual total. Budget navigation restores a surviving
contributor anchor; a deleted contributor cannot preserve its former row position.
Missing activity and unknown balances remain explicit. This local scene is
synthetic, owner-isolated and default-off for hosted financial access.
