# Personal money recording in the iPhone simulator

This checkpoint uses the real local Argus API and Supabase/Postgres with synthetic
registered users. It does not prove physical-iPhone access, the founder’s existing
identity, production data, or internet deployment. The
[execution manifest](../../../../specs/argus-execution-board.md) owns the full MVEE
and those outstanding delivery boundaries.

## Demonstration and observed results

The [transfer-label clarity addendum](transfer-label-review/README.md) verifies
the later visible From/To correction in English and Spanish. The accepted 2:55
recording below predates this label-only change and retains its financial proof.

[Personal money loop recording](personal-money-loop.mp4) is 2 minutes 55 seconds.
It combines three excerpts: income, spending and linked refund; an owned-account
transfer; and a credit-card payment. It shows real review, confirmation, account
balances and Home. It is **edited**, with cuts between independent accounts,
1.1× playback speed and 12fps compression. There is no credential entry, simulated
API response or invented financial UI in the selected clips. Exhaustive correction,
reconciliation and recovery checks are separate from this short demonstration.

The first excerpt captures three successful writes from a run whose later
correction automation failed to wait for the next field type. That failed test
is not counted as a pass. The complete income/correction/relaunch case subsequently
passed on the same product code after fixing the test selector. The transfer and
card excerpts come from their passing cases. [Verification](verification.json)
records the exact sources and terminal observations.

Passed native journeys:

- Income 1,000, purchase 250 and linked refund 50 change a new bank account from
  1,000 to 1,800. Corrections to 1,100/275/75 leave 1,900; reasons, Home totals and
  the same account survive reopening.
- Transfer 200 moves both account legs without becoming spending. Correcting it
  to 250 and moving a mistaken 100 bank purchase to a 125 cash purchase leaves
  bank 750/cash 225. Retired-leg history and both balances survive reopening.
- A card purchase 120 and payment 200 do not double-count spending. A linked 50
  refund received into the bank, payment corrected to 250, and an unlinked 200
  card refund leave bank 800/card credit 30. Home reflects purchase/refund changes;
  reopening preserves both sides. The DOP net change is negative for this case;
  the aggregate DOP month includes other synthetic test records.
- A late transfer is included in the bank’s checked balance but applied separately
  to cash: bank stays 940 with unexplained difference 0; cash becomes 560. USD
  income 100 and refund 25 leave its account unknown and display monthly net
  spending of -25. DOP totals remain unchanged, and Spanish/light input is verified.
  The original native identity assertions did not wait for B’s data and had no
  pending A command; those claims are superseded by the dedicated review proof below.
- The proxy drops exactly one response after income 25 has committed to a 100
  account. Reopening exposes pending recovery; retry preserves one record and
  balance 125. Another reopen finds the same record. Independent canonical
  [readback](native-record-readback.json) confirms all nine retained accounts.

The [identity-isolation review delta](isolation-review/README.md) now proves B’s
own persisted account has loaded while A has a real pending committed write,
then proves A can recover that command exactly once after switching back. It
passed with a clean full Xcode exit, as did direct-API restoration afterward.
The saved review accounts are `Pending A 6D519` (125) and `Isolated B 6D519` (321),
visible only to their respective synthetic users.

Seven original selected native cases passed. Six have terminal case results with the
finalizer limitation below. The final direct-API Home/reopening smoke check has a
clean `xcodebuild` exit 0. The launcher’s explicit fault opt-in tests passed 2/2.

## Retained demonstration

The dedicated simulator is **Argus Personal Money**, iPhone 17e on iOS 27,
`DD9EF306-EFED-41F1-9A8E-B42EBCEE07DA`. Its app bundle is
`local.argus.foundation`. The API is on 58500, Supabase 58501, Postgres 58502 and
CAPTCHA 58505, under the isolated project `ios-accounts-58500`.

For click-through review, open these retained accounts in Accounts:
`Daily money 4D01D` (1,900), `Transfer bank DBA3B` (750),
`Transfer cash DBA3B` (225), `Card funding FC26C` (800), and
`Everyday card FC26C` (30 credit), all DOP. Select an activity to inspect its
linked accounts, correction reason and revision history. Other uniquely named
synthetic accounts remain intact from acceptance runs. Additional retained cases
are `Checked bank 76CC7` (940), `Checked cash 76CC7` (560), `Unknown dollars 76CC7`
(unknown USD) and `Recovery 7CB3B` (125). The video’s first account is the earlier
`Daily money 67533`, whose successful create steps precede the later corrected
`4D01D` demonstration.

The earlier financial-loop demo on 58400 and simulator
`197C9C31-77FD-4D31-A9C6-EACA55732B15` is separate and preserved.

## Restart without replacing data

Use the retained checkout and ignored fixture. Do not run `configure`, `seed`,
`reset` or remove volumes. Skip a service command when its port is already owned
by the running demonstration. Start the API and CAPTCHA bridge in separate
terminals and keep them running:

```sh
cd /Users/garces/.codex/worktrees/money-recording-demo/private-alpha-next
python3 ios/scripts/auth/local_stack.py start --accounts --port-base 58500
python3 ios/scripts/auth/local_stack.py api --accounts --port-base 58500 \
  --accounts-enabled on \
  --python /Users/garces/.codex/worktrees/5a42/private-alpha-next/.venv/bin/python
```

```sh
cd /Users/garces/.codex/worktrees/money-recording-demo/private-alpha-next
python3 ios/scripts/auth/bridge.py --accounts --port-base 58500
```

Launch the retained app:

```sh
xcrun simctl boot DD9EF306-EFED-41F1-9A8E-B42EBCEE07DA # only if shut down
xcrun simctl launch DD9EF306-EFED-41F1-9A8E-B42EBCEE07DA local.argus.foundation
open -a Simulator
```

The ignored `ios/.build/accounts-local-58500/client.json` contains the synthetic
users; never paste it into source or evidence. The installed app retains its
session in the simulator Keychain. If sign-in is needed, use this read-only smoke
check with the retained fixture; it does not append financial records or expose
credentials in terminal output. Launch the app again after the check finishes:

```sh
python3 ios/scripts/auth/run-ui.py DD9EF306-EFED-41F1-9A8E-B42EBCEE07DA \
  --accounts --port-base 58500 \
  --only ArgusFoundationUITests/FinancialLoopUITests/testRetainedHomeSurvivesReopening
xcrun simctl launch DD9EF306-EFED-41F1-9A8E-B42EBCEE07DA local.argus.foundation
```

## Repeat scoped acceptance

Run each new journey serially, with no other verifier mutating the same identity:

```sh
python3 ios/scripts/auth/run-ui.py DD9EF306-EFED-41F1-9A8E-B42EBCEE07DA \
  --accounts --port-base 58500 \
  --only ArgusFoundationUITests/FinancialLoopUITests/testIncomeSpendingRefundAndCorrections
```

The other personal-money cases are `testTransferAndWrongAccountCorrection`,
`testCardPaymentRefundAndCreditBalance`,
`testMoneyReconciliationCurrenciesAndSpanish`, and
`testAccountAndActivityRowsOpenFromCenter`. They create uniquely named synthetic
accounts and compare Home against its starting values; no empty database is
assumed.

The response-loss case is separate and opt-in. It requires the local-only proxy
on 58512, an app built with that API address, and `--response-loss-proxy`. It drops
one already-committed response and verifies the same record after retry and
relaunch. Normal acceptance runs cannot arm this fault. Restore the 58500 app
configuration and build afterward. This proxy is not part of the user demo.

Raw logs and `.xcresult` bundles remain ignored because authentication diagnostics
may contain synthetic credentials. Selected visual artifacts and sanitized results
are the durable evidence. A screenshot alone does not prove a financial write.

## Limits of this checkpoint

Movements are same-currency only; no exchange rates or unresolved loan-payment
allocation rules are invented. The existing restriction on adding a balance check
before the latest observation remains. These are implementation limits, not new
MVEE product deferrals.

Six selected XCTest cases report their terminal pass in the retained logs, but
Xcode stalled while finalizing those result bundles. Their completed test finalizers
were stopped after terminal results. We do not claim a clean full `xcodebuild test`
exit or complete readable `.xcresult` bundles for those six cases. The final
read-only direct-API Home smoke test finished normally with exit 0. Sanitized
[terminal lines](terminal-cases.txt), independent screenshots and canonical API
readbacks preserve the actual observations.
