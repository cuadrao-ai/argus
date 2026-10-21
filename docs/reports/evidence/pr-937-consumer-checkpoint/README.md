# Consumer keyboard checkpoint, October 9, 2026

PR #937 remains unmerged. This checkpoint adds tests and evidence only. It does not
change product code, Release flags, the founder's phone, or hosted services.

## Source and results

Integration base and refreshed integration are both `bbf4da23f01296af4ac639386fe9a0960218a49f`.
The inherited PR head is `8066c9b66952d538cf5c9a98f14d773ad65e5814`.
The added test commit is `d1433158c`. Integration is already an ancestor, so no
reconciliation merge was needed and there is no intervening integration overlap.

All four summaries here contain one executed test, one pass and zero skips.

| Test | What was exercised | Evidence |
| --- | --- | --- |
| `FinancialLoopUITests/testAccountEntryKeepsUnknownAndSignedBalances` | Real local API and fresh Postgres. Unknown balance, spending, signed balance, coverage review, save, app relaunch and retained DOP -25.50 | `account-summary.json`, `account-after-relaunch.png` |
| `CuadraoHomeChartUITests/testDistributionAccountRoundTrip` | Native sample preview. Distribution to account, rename, return with expansion and scroll position preserved | `distribution-summary.json`, `distribution-return.png` |
| `CuadraoPlanDesignUITests/testNativeEditMenuKeepsKeyboardAndAcceptsReplacement` | Native Select All, replacement, Paste, continued typing, exact final value and tap-away dismissal | `edit-menu-summary.json`, `edit-menu-continued-typing.png` |
| `CuadraoPlanDesignUITests/testDebtRateSavesWhileKeyboardIsFocusedAndSurvivesRelaunch` | Native sample preview. Type 12.75, save without dismissing keyboard, reopen editor, relaunch without resetting preview state and read 12.75 again | `rate-summary.json`, `rate-after-relaunch.png` |

The first three captures precede the test-only commit. Their application code is
identical to that commit. The final rate run uses its exact test source, including
scrolling the checked field into view for the screenshot. This evidence remains
valid for the following documentation-only commit; no executable source changes.

An independent read-only review found no issues in the two added tests and no
added comments or suppressions. The final delta only scrolls the rate into view
for capture. The existing account and distribution tests were not changed.

`python3 ios/FinancialModelTests/run.py` executed 121 tests with six assertion
failures, zero unexpected failures. This matches the six baseline failures
recorded in #898 and the Consumer handoff. It is not a green suite.
`python3 ios/DesignPreviewTests/run_no_keyboard_accessory.py` passed separately.
`python3 scripts/check_modularity_budget.py --top 3` and `git diff --check` passed.

## Reproduction

Use a dedicated simulator and an unused local port block. The successful connected
run used an iPhone 18 Pro simulator on iOS 27.0, with ports 59440 through 59451.
Check both listeners and retained Docker volume names before selecting the block.
No hosted `.env` is needed. The API launcher refuses a root `.env`.

```sh
python3 ios/scripts/auth/local_stack.py configure --accounts --port-base 59440
python3 ios/scripts/auth/local_stack.py start --accounts --port-base 59440
python3 ios/scripts/auth/local_stack.py seed --accounts --port-base 59440
python3 ios/scripts/auth/local_stack.py api --accounts --accounts-enabled on --port-base 59440 --python /absolute/path/to/dependency-complete/python
python3 ios/scripts/auth/bridge.py --accounts --port-base 59440
python3 ios/scripts/auth/run-ui.py SIMULATOR_ID --accounts --port-base 59440 --only ArgusFoundationUITests/FinancialLoopUITests/testAccountEntryKeepsUnknownAndSignedBalances
```

Run the API and CAPTCHA bridge in separate owned processes. Select each of the
other test identifiers from the table with one `--only` argument per invocation.
Read `xcrun xcresulttool get test-results summary --path RESULT.xcresult` after each
run. A zero exit code with zero tests is not acceptance.

The scripts generate synthetic `ARGUS_TEST_EMAIL`, `ARGUS_TEST_PASSWORD` and their
`_B` forms in ignored files. `ARGUS_TEST_ACCOUNTS_UI_ENABLED` is true. Credentials,
stack logs and generated configurations are not included in this evidence.

The first setup attempt used port 59500. Supabase restored an old retained volume
with missing auth deletion tables. Direct Auth login passed, but `/api/v1/me`
returned `503 auth_session_verification_unavailable`. That stack was stopped with
its data preserved. The fresh 59440 stack applied the current migrations and the
connected test passed. The old attempt is not evidence of a product regression.
The initial run also lacked the local CAPTCHA bridge, which is required above.

## Limits and remaining acceptance

- These runs did not reproduce either inherited journey failure. They do not prove
  the unknown cause of the previous runs or establish a long-run flake rate.
- The rate test checks native preview persistence. It does not claim hosted debt
  persistence or saved-receipt validation.
- An actual VoiceOver and Switch Control decimal-pad navigation walk remains open.
  XCTest element queries and ordinary taps do not prove those interaction modes.
- The six model-test baseline failures remain tracked in #898.
- CI must complete on the pushed head before a merge decision.
- Phone build 3454 and the intentionally stopped phone API/forwarder remain as the
  founder reported. No phone installation was performed.
