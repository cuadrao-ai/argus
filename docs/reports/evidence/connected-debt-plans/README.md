# Connected debt-payment plans local demonstration

The native app connects debt plans, original payments, Accounts, Plan, Home and
Search through real local Supabase Auth, Postgres and the Argus API. Three native
journeys passed, including accepted-response loss, correction, actual return,
archive/restore, existing card-payment linking, Spanish and reopening.
This is locally verified simulator delivery. Physical-phone internet delivery
and the complete MVEE remain unfinished.

Delivery checkout: `/Users/garces/.codex/worktrees/connected-debt-plans/private-alpha-next`.
Branch: `codex/connected-debt-plans`. [PR #757](https://github.com/lagarcess/argus/pull/757)
targets `codex/private-alpha-next`; merge is not authorized. Original and freshly
verified integration are `7c29b2a9b3f4680f6804a2abc8378df45b05540c`.
Behavior and visuals were captured at `70e34fe94641806ca3e80ac9ac6fff9ad73603f3`.
Subsequent preservation changes affect documentation/evidence only. The PR's
terminal audit records final publication SHA, applicable CI and parity.

## Click through

[Open the native simulator](http://localhost:59213). It is signed in to a retained
synthetic owner, uses the direct API and stays running in English/dark mode.
Select **Argus Foundation Compact** if the mirror shows another device.

1. Open **Search**, enter `c801d065`, and choose **Debts**. Open
   **Loan repayment c801d065**. Its recorded principal is DOP 500, while planned
   payments and the optional estimate are separate.
2. Expand **Funding account** to see DOP 1,560 recorded cash, DOP 1,500 reserved
   for the existing savings goal and DOP 60 unassigned. No second allocation
   system or invented safe-to-spend amount is used.
3. Inspect a recorded payment. **Correct entry** edits its original canonical
   activity. **Record returned payment** creates a separate dated return and
   preserves the original. Explicit loan principal, interest and fees must sum
   to the total, including explicit zero when appropriate.
4. **Record payment** fulfills the selected occurrence; **Extra payment** has
   no automatic future-date assignment. **Link recorded payment** uses an
   eligible existing activity without moving money again.
5. Edit, archive and restore the plan. Close it to return to the same Search
   context. Home and Plan use the same financial snapshot. Reopen the app to
   inspect the preserved state.

The native proof also retains **Updated loan 54949**, with DOP 550 principal
remaining after payment, correction, return and a second payment. Other native
fixtures remain intentionally preserved. Their records contribute to Home's
whole-owner totals; the accepted API readback verifies its named fixture only.

[90-second recording](debt-journey.mp4) shows payment confirmation, lost accepted
response, reopening, exact retry and correction. [Native proof](native-proof.json)
links sixteen unmodified financial screenshots and the passing test summaries.
[Independent review](review-proof.json) records the reviewed commits and fixes.

## Retained environment and restart

API 59200, Supabase 59201, Postgres 59202, synthetic CAPTCHA 59205 and mirror
59213 are lane-owned. Simulator **Argus Foundation Compact**,
`1A90F684-345F-465C-AA50-6A5298F34156`, runs separate bundle
`local.argus.debt-demo`. Its original foundation app, all earlier demos and phone
ports 58700–58749 remain untouched. The temporary fault proxy has been stopped.

Private synthetic credentials and exact-command journals stay in ignored
`ios/.build/accounts-local-59200/`. Never publish those files. Restart reuses the
existing users, database, app identity and records. Skip a running service; run
separate long-lived commands in separate terminals. Never configure, seed,
reset, erase or delete the retained environment.

```sh
cd /Users/garces/.codex/worktrees/connected-debt-plans/private-alpha-next
python3 ios/scripts/auth/local_stack.py start --accounts --port-base 59200
python3 ios/scripts/auth/local_stack.py api --accounts --port-base 59200 \
  --accounts-enabled on \
  --python /Users/garces/.codex/worktrees/5a42/private-alpha-next/.venv/bin/python
```

```sh
cd /Users/garces/.codex/worktrees/connected-debt-plans/private-alpha-next
python3 ios/scripts/auth/bridge.py --accounts --port-base 59200
```

Boot only this simulator if shut down, then launch its installed app.

```sh
xcrun simctl bootstatus 1A90F684-345F-465C-AA50-6A5298F34156 -b
xcrun simctl launch 1A90F684-345F-465C-AA50-6A5298F34156 local.argus.debt-demo \
  -AppleLanguages '(en)' -AppleLocale en_US -appearancePreference dark
```

To rebuild without changing identity, preserve the ignored `ios/Config/Local.xcconfig`,
which points this bundle at direct API59200. Build and install only this app.

```sh
cd /Users/garces/.codex/worktrees/connected-debt-plans/private-alpha-next
xcodebuild build -project ios/ArgusFoundation.xcodeproj -scheme ArgusFoundation \
  -destination 'platform=iOS Simulator,id=1A90F684-345F-465C-AA50-6A5298F34156' \
  -derivedDataPath ios/.build/DerivedData-59200 CODE_SIGNING_REQUIRED=NO
xcrun simctl install 1A90F684-345F-465C-AA50-6A5298F34156 \
  ios/.build/DerivedData-59200/Build/Products/Debug-iphonesimulator/ArgusFoundation.app
```

If absent, restart the mirror separately. Cleanup targets only this simulator.

```sh
cd /Users/garces/.codex/worktrees/connected-debt-plans/private-alpha-next
DEBT_SIM=1A90F684-345F-465C-AA50-6A5298F34156
cleanup_debt_mirror() {
  npx --yes serve-sim@0.1.47 --kill "$DEBT_SIM" >/dev/null 2>&1 || true
}
trap cleanup_debt_mirror EXIT INT TERM HUP
cleanup_debt_mirror
npx --yes serve-sim@0.1.47 --port 59213 --host 127.0.0.1 \
  --codec mjpeg --fit "$DEBT_SIM"
```

## API proof and recovery

[debt-api-proof.json](debt-api-proof.json) records independently expected balances,
costs, commitments and savings backing. Primary retained loan principal is DOP
500; monthly intention is DOP 500; actual interest/fees total DOP 85. Funding
cash is DOP 1,560, savings assignment DOP 1,500 and unassigned cash DOP 60.
USD and unknown debt stay separate. [debt-period-proof.json](debt-period-proof.json)
verifies the modeled payment boundary and unavailable elapsed boundary.

The optional model explicitly uses 12% nominal annual interest, zero recurring
fees, monthly periods and no new borrowing. Two projected payments and DOP 5.05
projected interest change no recorded balances or spending. A statement check
changes recorded principal and preserves unexplained differences; it does not
invent interest or fees.

```sh
cd /Users/garces/.codex/worktrees/connected-debt-plans/private-alpha-next
python3 ios/scripts/debts-journey.py readback
```

After deliberate human edits, use `readback --observe`. That writes a separately
labelled observation without overwriting accepted evidence. To recover an
interrupted fixture run, `run` resends pending exact bytes and key before further
writes. Never delete its private journal to replay the demo.

The API proof lost a successful plan-creation response and recovered one plan.
The native proof lost a successful payment response, relaunched and recovered
one payment. Replay is not a second payment. To rerun proxy acceptance, start
`python3 scripts/qa/financial_response_fault.py --listen-port 59212 --upstream-port 59200`
and follow the opt-in runner/configuration contract in `ios/scripts/auth/run-ui.py`.
Ordinary demonstration needs no proxy or new records.

## Verification and limits

- Three assembled native cases passed with zero failures/skips. Real registered
  auth/relaunch/sign-out passed separately, with unchanged auth runtime.
- 343 financial/API/OpenAPI and real-Postgres checks passed with zero skips,
  including budgets, savings, Search, owner isolation, stale writes, duplicate
  retries, corrections, component return limits, partial/extra/missed payments,
  payoff credit/reopening, interest-only payment/return and archive/restore.
- Three tests directly exercise the production native draft commands. The Swift
  package had 59 passes and four inherited opt-in live-auth skips; real native
  auth was exercised separately. Ruff, documentation links, whitespace and
  would-be merged-tree modularity passed. Final exact-head CI is recorded on PR #757.
- A fresh independent reviewer reviewed the finished diff once and only affected
  fixes afterward. Both confirmed findings were corrected at their shared cause.
  Latest reviewed source is `70e34fe94641806ca3e80ac9ac6fff9ad73603f3`.

Loan payments require a known actual breakdown; missing values are never guessed.
The optional estimate supports explicit monthly constant-rate assumptions. It
has no variable-rate, grace-period, lender-billing or automatic-accrual model.
Missing/unsupported terms or elapsed unpaid modeled boundaries show no invented
payoff. Unknown balances remain unknown and currencies never convert.

Existing full-owner snapshot loading remains a scale limit, with no new cache or
second ledger. Passing loan/card tests emit an invalid-frame runtime warning
also seen in retained savings acceptance. No visible failure was observed; shared
layout polish remains in the execution manifest. Signing, physical-phone internet
proof, deployment, real lender execution and the remaining MVEE are not delivered.
